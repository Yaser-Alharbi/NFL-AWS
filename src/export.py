"""Task 6: export JSON for the visualiser.

Inputs are the saved pipeline outputs (Tasks 1 to 5); nothing is recomputed here
except the replay frames, which are read from tracking.

Files written to ``config.EXPORT_DIR``:
- ``qb_summary.json``: one row per QB from ``qb_summary`` (all columns), plus
  the league split values and the quadrant descriptions.
- ``league.json``: the main table (``league_summary``) and the curve
  (``league_curve``, both views).
- ``replays/<qbId>.json``: every pressured play of that QB (QBs with
  ``meets_min`` only), loaded by the page when the QB is selected. Frames
  from ``REPLAY_PRE_SNAP`` frames before the snap to ``REPLAY_POST_END`` frames
  after the end frame, for every player and the ball. Coordinates are normalized
  (offense moves toward increasing x), the same frame as ``tracking_features``.
  Per entity and frame: ``[x*10, y*10, o]`` as ints (o = -1 when missing).
- ``meta.json``: thresholds, data scope, build date.

``--embed`` also writes ``visualiser/standalone.html`` with the JSON inlined.
All replays together are too big for one file, so it keeps the first
``config.QB_MIN_PLAYS`` chaos and scripted plays per QB (in game order); every
QB shown has at least that many of each.

Run: ``python -m src.export [--embed]``
"""
from __future__ import annotations

import argparse
import json
from datetime import date

import pandas as pd

from . import config, data

KEYS = ["gameId", "playId"]
REPLAY_PRE_SNAP = 10   # frames kept before the snap
REPLAY_POST_END = 10   # frames kept after the end frame
VIS_DIR = config.ROOT / "visualiser"
FILES = ["meta", "qb_summary", "league"]


def _records(df: pd.DataFrame) -> list[dict]:
    """DataFrame rows as dicts with NaN -> None and numpy scalars -> Python."""
    return json.loads(df.to_json(orient="records"))


def export_qb_summary() -> tuple[dict, pd.DataFrame]:
    qb = pd.read_csv(config.QB_SUMMARY_PATH, dtype={"qbId": config.ID_DTYPE})
    prior = json.loads(config.QB_PRIOR_PATH.read_text())
    from .qb_summary import QUADRANTS
    corners = [{"often": o, "better": b, "text": t} for (o, b), t in QUADRANTS.items()]
    out = {
        "league": prior["league"],
        "splits": prior["quadrant_splits"],
        "min_plays": prior["min_plays"],
        "priors": prior["priors"],
        "quadrants": corners,
        "qbs": _records(qb),
    }
    return out, qb


def export_league() -> dict:
    summary = pd.read_csv(config.LEAGUE_SUMMARY_PATH)
    curve = pd.read_csv(config.LEAGUE_CURVE_PATH)
    return {"summary": _records(summary), "curve": _records(curve)}


def _clip(play: pd.DataFrame, row) -> dict:
    f0 = max(int(play["frameId"].min()), int(row.snap_frame) - REPLAY_PRE_SNAP)
    f1 = min(int(play["frameId"].max()), int(row.end_frame) + REPLAY_POST_END)
    clip = play[play["frameId"].between(f0, f1)]

    ents = clip.drop_duplicates("nflId")[["nflId", "jerseyNumber", "team"]]
    ents = ents.sort_values(["team", "jerseyNumber"], na_position="last")
    keys = [-1 if pd.isna(n) else int(n) for n in ents["nflId"]]
    index = {k: i for i, k in enumerate(keys)}
    entities = [
        {"id": None if k == -1 else k,
         "jersey": None if pd.isna(j) else int(j),
         "team": t}
        for k, j, t in zip(keys, ents["jerseyNumber"], ents["team"])
    ]

    frames = []
    for _, g in clip.groupby("frameId"):
        f = [None] * len(entities)
        for n, x, y, o in g[["nflId", "x", "y", "o"]].itertuples(index=False):
            f[index[-1 if pd.isna(n) else int(n)]] = [
                round(x * 10), round(y * 10), -1 if pd.isna(o) else round(o)]
        frames.append(f)

    ev = clip.dropna(subset=["event"]).drop_duplicates("frameId")
    events = [[int(fr), e] for fr, e in zip(ev["frameId"], ev["event"])]
    return {"firstFrame": f0, "entities": entities, "frames": frames, "events": events}


def export_replays(qb: pd.DataFrame) -> dict:
    labeled = pd.read_csv(config.PLAY_LABELS_PATH, dtype={"qbId": config.ID_DTYPE})
    keep_qbs = set(qb.loc[qb["meets_min"].astype(bool), "qbId"])
    p = labeled[labeled["pressured"] & labeled["qbId"].isin(keep_qbs)]
    plays = data.load_plays()[KEYS + ["quarter", "gameClock", "playDescription"]]
    games = data.load_games()[["gameId", "week"]]
    p = p.merge(plays, on=KEYS, how="left").merge(games, on="gameId", how="left")
    print(f"replays: {len(p)} pressured plays from {len(keep_qbs)} QBs")

    out, missing = [], 0
    for game_id, gp in p.groupby("gameId"):
        track = data.load_tracking(int(game_id))
        by_play = dict(tuple(track.groupby("playId")))
        for row in gp.itertuples(index=False):
            if row.playId not in by_play:
                missing += 1
                continue
            clip = _clip(by_play[row.playId], row)
            out.append({
                "gameId": int(row.gameId), "playId": int(row.playId), "qbId": int(row.qbId),
                "week": int(row.week), "quarter": int(row.quarter), "clock": row.gameClock,
                "offense": row.possessionTeam, "defense": row.defensiveTeam,
                "down": int(row.down), "yardsToGo": int(row.yardsToGo),
                "description": row.playDescription,
                "label": row.label, "offScriptRule": None if pd.isna(row.off_script_rule) else row.off_script_rule,
                "rulesFired": None if pd.isna(row.rules_fired) or row.rules_fired == "" else row.rules_fired,
                "chaosBeforePressure": bool(row.chaos_before_pressure),
                "success": None if pd.isna(row.success) else bool(row.success),
                "sack": bool(row.sack), "interception": bool(row.interception),
                "passResult": None if pd.isna(row.passResult) else row.passResult,
                "yards": None if pd.isna(row.prePenaltyPlayResult) else int(row.prePenaltyPlayResult),
                "dropBackType": None if pd.isna(row.dropBackType) else row.dropBackType,
                "snapFrame": int(row.snap_frame), "endFrame": int(row.end_frame), "endReason": row.end_reason,
                "pressureFrame": int(row.pressure_frame),
                "offScriptFrame": None if pd.isna(row.off_script_frame) else int(row.off_script_frame),
                "dropFrame": int(row.drop_frame), "drop": [round(row.drop_x, 2), round(row.drop_y, 2)],
                "losX": round(row.los_x, 2),
                "box": None if pd.isna(row.box_lo) else [round(row.box_lo, 2), round(row.box_hi, 2)],
                **clip,
            })
        print(f"game {game_id}: {len(out)} replays so far")
    print(f"replays exported: {len(out)}, missing tracking: {missing}")
    by_qb: dict[int, list] = {}
    for r in sorted(out, key=lambda r: (r["gameId"], r["playId"])):
        by_qb.setdefault(r["qbId"], []).append(r)
    return by_qb


def export_meta(n_replays: int, embedded: bool = False) -> dict:
    return {
        "built": date.today().isoformat(),
        "scope": "Dataset/ only (2021 weeks 1-8). Pressured QB pass plays; designed rollouts and runs left out.",
        "thresholds": {
            "pressure_distance_yd": config.PRESSURE_DISTANCE,
            "drift_yd": config.DRIFT_THRESHOLD,
            "hold_s": config.HOLD_TIME_THRESHOLD,
            "rule_order": config.OFF_SCRIPT_RULE_ORDER,
        },
        "success_ratio": config.SUCCESS_RATIO,
        "min_plays": config.QB_MIN_PLAYS,
        "frames_per_second": config.FRAMES_PER_SECOND,
        "replay_window": {"pre_snap": REPLAY_PRE_SNAP, "post_end": REPLAY_POST_END},
        "replays": n_replays,
        "embedded_subset": config.QB_MIN_PLAYS if embedded else None,
    }


def embed_subset(by_qb: dict) -> dict:
    keep = {}
    for qb_id, plays in by_qb.items():
        keep[qb_id] = [p for label in ("chaos", "scripted")
                       for p in [p for p in plays if p["label"] == label][:config.QB_MIN_PLAYS]]
    return keep


def write_standalone(payload: dict) -> None:
    html = (VIS_DIR / "index.html").read_text()
    blob = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
    tag = '<script id="embedded-data" type="application/json"></script>'
    assert tag in html, "embedded-data tag not found in index.html"
    out = VIS_DIR / "standalone.html"
    out.write_text(html.replace(tag, f'<script id="embedded-data" type="application/json">{blob}</script>'))
    print(f"saved {out} ({out.stat().st_size / 1e6:.2f} MB)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true", help="also write visualiser/standalone.html")
    args = ap.parse_args()

    qb_json, qb = export_qb_summary()
    payload = {"qb_summary": qb_json, "league": export_league()}
    by_qb = export_replays(qb)
    n = sum(len(v) for v in by_qb.values())
    payload["meta"] = export_meta(n)

    config.EXPORT_DIR.mkdir(exist_ok=True)
    for name in FILES:
        path = config.EXPORT_DIR / f"{name}.json"
        path.write_text(json.dumps(payload[name], separators=(",", ":")))
        print(f"saved {path} ({path.stat().st_size / 1e6:.2f} MB)")
    rep_dir = config.EXPORT_DIR / "replays"
    rep_dir.mkdir(exist_ok=True)
    total = 0
    for qb_id, plays in by_qb.items():
        path = rep_dir / f"{qb_id}.json"
        path.write_text(json.dumps(plays, separators=(",", ":")))
        total += path.stat().st_size
    print(f"saved {len(by_qb)} files in {rep_dir} ({total / 1e6:.2f} MB total)")
    if args.embed:
        sub = embed_subset(by_qb)
        payload["meta"] = export_meta(n, embedded=True)
        payload["replays"] = {str(k): v for k, v in sub.items()}
        write_standalone(payload)


if __name__ == "__main__":
    main()
