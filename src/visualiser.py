"""Tasks 6-7: export JSON for the visualiser, run the checks, build the HTML.

Reads ``outputs/`` (Tasks 1-5), ``Dataset/`` and ``config``. Writes to ``export/``:
- ``qb_summary.json``: every row of ``qb_summary.csv``. The page draws only
  ``meets_min`` QBs.
- ``league_summary.json``: rows of ``league_summary.csv`` (pressured plays).
- ``league_curve.json``: rows of ``league_curve.csv`` (views ``no_hold`` and ``split``).
- ``replays.json``: every pressured play of the ``meets_min`` QBs. Frames run
  from the snap frame to the end frame, as in the labels, with coordinates
  normalized so the offense moves toward increasing x. Per-frame xy for the QB,
  the ball and each pass rusher as flat ``[x, y, x, y, ...]`` arrays (null where
  a frame is missing), at source precision (2 decimals).
- ``meta.json``: thresholds, priors and quadrant splits, data scope, build date.
- ``script_vs_chaos.html``: ``src/visualiser_template.html`` with all of the
  above embedded as one JSON block.

Run: ``python -m src.visualiser``
"""
from __future__ import annotations

import json
import math
from datetime import date

import numpy as np
import pandas as pd

from . import config, data

KEYS = ["gameId", "playId"]
PLACEHOLDER = "/*__DATA__*/"
SPOT_CHECK_PLAYS = 8   # tasks.md 7: spot-check 5 to 10 replays
SPOT_CHECK_SEED = 0

PLAY_COLS = [
    "gameId", "playId", "qbId", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
    "prePenaltyPlayResult", "passResult", "success", "sack", "interception", "dropBackType",
    "label", "off_script_rule", "rules_fired", "snap_frame", "end_frame", "end_reason",
    "drop_frame", "pressure_frame", "off_script_frame", "drop_x", "drop_y", "box_lo", "box_hi", "los_x",
]
COORD_COLS = ["drop_x", "drop_y", "box_lo", "box_hi", "los_x"]


def _records(df: pd.DataFrame) -> list[dict]:
    """Rows as dicts, NaN and NA as None."""
    return json.loads(df.to_json(orient="records"))


def _flat_xy(rows: pd.DataFrame, frames: np.ndarray) -> list:
    """``[x, y, x, y, ...]`` for each frame in ``frames``; None where a frame is missing."""
    xy = rows.drop_duplicates("frameId").set_index("frameId").reindex(frames)[["x", "y"]]
    return [None if math.isnan(v) else v for v in xy.to_numpy(float).round(2).ravel().tolist()]


def _dump(obj, path, indent=None) -> None:
    sep = (",", ":") if indent is None else (",", ": ")
    path.write_text(json.dumps(obj, indent=indent, separators=sep, allow_nan=False))
    print(f"saved {path} ({path.stat().st_size / 1e6:.2f} MB)")


def load_inputs():
    qb = pd.read_csv(config.QB_SUMMARY_PATH, dtype={"qbId": config.ID_DTYPE})
    labeled = pd.read_csv(config.PLAY_LABELS_PATH, dtype={"qbId": config.ID_DTYPE})
    prior = json.loads(config.QB_PRIOR_PATH.read_text())
    league = pd.read_csv(config.LEAGUE_SUMMARY_PATH)
    curve = pd.read_csv(config.LEAGUE_CURVE_PATH)
    assert qb["meets_min"].notna().all(), "set config.QB_MIN_PLAYS and rerun python -m src.qb_summary"
    print(f"QBs: {len(qb)}, meeting the minimum ({config.QB_MIN_PLAYS} chaos and scripted plays): "
          f"{qb['meets_min'].sum()}")
    return qb, labeled, prior, league, curve


def replay_plays(qb: pd.DataFrame, labeled: pd.DataFrame) -> pd.DataFrame:
    """Pressured plays of the shown QBs, with game and play context."""
    shown = qb.loc[qb["meets_min"], "qbId"]
    p = labeled[labeled["pressured"] & labeled["qbId"].isin(shown)][PLAY_COLS].copy()
    p[COORD_COLS] = p[COORD_COLS].round(2)
    plays = data.load_plays()[KEYS + ["playDescription", "quarter", "gameClock"]]
    games = data.load_games()[["gameId", "week", "homeTeamAbbr", "visitorTeamAbbr"]]
    p = p.merge(plays, on=KEYS, how="left").merge(games, on="gameId", how="left")
    print(f"replay plays (pressured plays of shown QBs): {len(p)}")
    return p.sort_values(KEYS).reset_index(drop=True)


def rusher_table() -> pd.DataFrame:
    """Pass rushers per play with name and PFF pressure credit."""
    pff = data.load_pff()
    rush = pff[pff["pff_role"] == config.RUSHER_ROLE].copy()
    rush["credited"] = rush[config.PRESSURE_COLS].eq(1).any(axis=1)
    players = data.load_players()[["nflId", "displayName"]]
    return rush[KEYS + ["nflId", "credited"]].merge(players, on="nflId", how="left")


def build_replays(p: pd.DataFrame) -> list[dict]:
    rushers = {k: g for k, g in rusher_table().groupby(KEYS)}
    meta = {(r["gameId"], r["playId"]): r for r in _records(p)}
    out, missing = {}, []
    for game_id, track in data.iter_tracking(game_ids=sorted(p["gameId"].unique()), missing=missing):
        plays = p[p["gameId"] == game_id]
        track = track[track["playId"].isin(plays["playId"])]
        by_play = dict(tuple(track.groupby("playId")))
        for row in plays.itertuples(index=False):
            key = (row.gameId, row.playId)
            frames = np.arange(row.snap_frame, row.end_frame + 1)
            t = by_play[row.playId]
            people = t[t["team"] != "football"]
            rec = dict(meta[key])
            rec["qb"] = _flat_xy(people[people["nflId"] == row.qbId], frames)
            rec["ball"] = _flat_xy(t[t["team"] == "football"], frames)
            rec["rushers"] = [
                {"nflId": int(r.nflId), "name": r.displayName, "credited": bool(r.credited),
                 "xy": _flat_xy(people[people["nflId"] == r.nflId], frames)}
                for r in rushers.get(key, pd.DataFrame(columns=["nflId"])).itertuples(index=False)
            ]
            out[key] = rec
        print(f"game {game_id}: {len(out)} replays so far")
    assert not missing, f"missing tracking files: {missing}"
    return [out[(g, pl)] for g, pl in zip(p["gameId"], p["playId"])]


def build_meta(qb: pd.DataFrame, labeled: pd.DataFrame, prior: dict, n_replays: int) -> dict:
    games = data.load_games()
    return {
        "build_date": date.today().isoformat(),
        "scope": {
            "seasons": sorted(int(s) for s in games["season"].unique()),
            "weeks": [int(games["week"].min()), int(games["week"].max())],
            "games": len(games),
        },
        "counts": {
            "labelled_plays": len(labeled),
            "pressured_plays": int(qb["pressured_plays"].sum()),
            "qbs": len(qb),
            "qbs_shown": int(qb["meets_min"].sum()),
            "replays": n_replays,
        },
        "thresholds": {
            "pressure_distance": config.PRESSURE_DISTANCE,
            "drift": config.DRIFT_THRESHOLD,
            "hold": config.HOLD_TIME_THRESHOLD,
            "success_ratio": config.SUCCESS_RATIO,
            "curve_bin_seconds": config.CURVE_BIN_SECONDS,
            "curve_max_seconds": config.CURVE_MAX_SECONDS,
            "off_script_rule_order": config.OFF_SCRIPT_RULE_ORDER,
            "qb_min_plays": config.QB_MIN_PLAYS,
            "frames_per_second": config.FRAMES_PER_SECOND,
        },
        "designed_dropbacks": config.DESIGNED_DROPBACKS,
        "priors": prior["priors"],
        "league": prior["league"],
        "quadrant_splits": prior["quadrant_splits"],
    }


def check(qb: pd.DataFrame, labeled: pd.DataFrame, replays: list[dict], league: pd.DataFrame,
          template: str) -> None:
    """Tasks.md 7 checks that code can do."""
    rp = pd.DataFrame([{k: r[k] for k in ["gameId", "playId", "qbId", "label"]} for r in replays])
    per_qb = rp.groupby("qbId").size()
    shown = qb[qb["meets_min"]].set_index("qbId")["pressured_plays"]
    assert per_qb.reindex(shown.index).fillna(0).astype(int).equals(shown.astype(int)), \
        "replays per QB != pressured_plays in qb_summary"
    assert not rp.duplicated(KEYS).any()
    lab = labeled.set_index(KEYS)["label"]
    assert (rp.set_index(KEYS)["label"] == lab.reindex(rp.set_index(KEYS).index)).all(), \
        "replay label != play_labels"
    print(f"check: replays per QB match qb_summary ({len(shown)} QBs), labels match play_labels")

    bad_qb = sum(None in r["qb"] for r in replays)
    bad_ball = sum(None in r["ball"] for r in replays)
    bad_rush = sum(None in x["xy"] for r in replays for x in r["rushers"])
    print(f"check: replays with a missing QB frame: {bad_qb}, missing ball frame: {bad_ball}, "
          f"rusher tracks with a missing frame: {bad_rush}")
    assert bad_qb == 0 and bad_ball == 0, "QB or ball frame missing between snap and end frame"

    # No stat value typed into the template: counts and percents from the data must not appear.
    stats = {str(int(v)) for v in league["plays"]} | {str(int(qb["pressured_plays"].sum()))}
    stats |= {f"{100 * v:.1f}" for v in league["success_rate"]}
    found = sorted(s for s in stats if s in template)
    assert not found, f"template contains stat values: {found}"
    print("check: template holds no league counts or success rates")


def spot_check_sample(replays: list[dict], qb: pd.DataFrame) -> None:
    names = qb.set_index("qbId")["name"]
    rp = pd.DataFrame(replays).sample(SPOT_CHECK_PLAYS, random_state=SPOT_CHECK_SEED)
    print(f"\nspot-check sample ({SPOT_CHECK_PLAYS} replays, seed {SPOT_CHECK_SEED}):")
    for r in rp.itertuples(index=False):
        print(f"  {r.gameId} {r.playId} {names[r.qbId]}: {r.label} "
              f"({r.off_script_rule if isinstance(r.off_script_rule, str) else '-'}), "
              f"passResult {r.passResult}, end {r.end_reason}\n    {r.playDescription}")


def build_visualiser():
    qb, labeled, prior, league, curve = load_inputs()
    p = replay_plays(qb, labeled)
    replays = build_replays(p)
    meta = build_meta(qb, labeled, prior, len(replays))
    template = config.VISUALISER_TEMPLATE.read_text()
    assert template.count(PLACEHOLDER) == 1, f"template needs exactly one {PLACEHOLDER}"
    check(qb, labeled, replays, league, template)
    spot_check_sample(replays, qb)
    return {
        "meta": meta,
        "qbs": _records(qb),
        "league": _records(league),
        "curve": _records(curve),
        "replays": replays,
    }, template


def main() -> None:
    payload, template = build_visualiser()
    config.EXPORT_DIR.mkdir(exist_ok=True)
    print()
    _dump(payload["qbs"], config.EXPORT_QB_SUMMARY_PATH, indent=1)
    _dump(payload["league"], config.EXPORT_LEAGUE_SUMMARY_PATH, indent=1)
    _dump(payload["curve"], config.EXPORT_LEAGUE_CURVE_PATH, indent=1)
    _dump(payload["replays"], config.EXPORT_REPLAYS_PATH)
    _dump(payload["meta"], config.EXPORT_META_PATH, indent=1)

    blob = json.dumps(payload, separators=(",", ":"), allow_nan=False).replace("</", "<\\/")
    config.VISUALISER_PATH.write_text(template.replace(PLACEHOLDER, blob))
    print(f"saved {config.VISUALISER_PATH} ({config.VISUALISER_PATH.stat().st_size / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
