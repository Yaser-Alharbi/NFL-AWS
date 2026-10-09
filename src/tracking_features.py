"""Task 2: per-play QB tracking features, plus a per-frame QB table for replays.

Frames run from the snap frame to the end frame. Coordinates are normalized so
the offense moves toward increasing x (see ``data.normalize_direction``).

End frame: first of a pass event, a sack event, a run event (QB takes off), the
QB's x passing the line of scrimmage (ball x at the snap), or the last frame. ``end_reason`` records which.

Drop spot rule: backward speed is the QB's velocity away from the line,
``-s * sin(dir)`` (dir 90 = toward the line after normalization). After the frame
of peak backward speed, the drop ends at the first frame where backward speed
reaches 0 or stops falling (next frame higher). If the QB never moves back, the
drop spot is the snap position; if the speed never stops falling, the end frame.
Raw x differences were too noisy (0.01 yd steps) and rollouts kept x decreasing.

Time held is ``(end_frame - snap_frame) / config.FRAMES_PER_SECOND``, because the
``time`` column only has 1-second resolution.

Pressure frame needs ``config.PRESSURE_DISTANCE`` (set in Task 3). Until then it
is NA, and the per-frame nearest-rusher distance is saved for Task 3.

Run: ``python -m src.tracking_features``
"""
from __future__ import annotations

from collections import Counter

import numpy as np
import pandas as pd

from . import config, data

KEYS = ["gameId", "playId"]


def _first_event_frame(events: pd.Series, names: list[str], start: int):
    """First frameId >= start for the first name in ``names`` found on the play."""
    for name in names:
        frames = events.index[(events == name) & (events.index >= start)]
        if len(frames):
            return int(frames.min())
    return None


def _drop_frame(qb: pd.DataFrame) -> int:
    """Drop spot frame (see module docstring). ``qb`` is indexed by frameId."""
    back = (-qb["s"] * np.sin(np.radians(qb["dir"]))).to_numpy()
    peak = int(back.argmax())
    if back[peak] <= 0:
        return int(qb.index[0])
    for i in range(peak, len(back) - 1):
        if back[i] <= 0 or back[i + 1] > back[i]:
            return int(qb.index[i])
    return int(qb.index[-1])


def _play_features(play: pd.DataFrame, qb_id, rusher_ids, tackle_ids, issues: Counter):
    events = play.drop_duplicates("frameId").set_index("frameId")["event"].sort_index()
    snap = _first_event_frame(events, config.SNAP_EVENTS, 0)
    if snap is None:
        issues["no snap event"] += 1
        return None, None

    qb = play[play["nflId"] == qb_id].set_index("frameId").sort_index()
    if qb.empty:
        issues["no QB rows"] += 1
        return None, None
    ball = play[play["team"] == "football"].set_index("frameId")
    if snap not in ball.index or snap not in qb.index:
        issues["no ball or QB at snap"] += 1
        return None, None
    los_x = ball.at[snap, "x"]

    qb = qb.loc[snap:]
    candidates = {
        "pass": _first_event_frame(events, config.PASS_EVENTS, snap),
        "sack": _first_event_frame(events, config.SACK_EVENTS, snap),
        "run": _first_event_frame(events, config.RUN_EVENTS, snap),
        "qb_crossed_los": int(qb.index[qb["x"] > los_x].min()) if (qb["x"] > los_x).any() else None,
        "play_end": int(qb.index.max()),
    }
    end_reason, end = min(((k, v) for k, v in candidates.items() if v is not None), key=lambda kv: kv[1])
    qb = qb.loc[:end]

    drop = _drop_frame(qb)
    drop_xy = qb.loc[drop, ["x", "y"]].to_numpy(dtype=float)
    drift = np.hypot(qb["x"] - drop_xy[0], qb["y"] - drop_xy[1])
    drift[qb.index < drop] = np.nan

    # Tackle box: lateral span between the two tackles at the snap.
    tackles = play[(play["frameId"] == snap) & play["nflId"].isin(tackle_ids)]
    if len(tackles) == 2:
        box_lo, box_hi = tackles["y"].min(), tackles["y"].max()
        in_box = qb["y"].between(box_lo, box_hi)
        exits = qb.index[~in_box]
        box_exit = int(exits.min()) if len(exits) else None
    else:
        issues["tackles not found at snap"] += 1
        box_lo = box_hi = np.nan
        in_box = pd.Series(pd.NA, index=qb.index, dtype="boolean")
        box_exit = None

    # Nearest pass rusher per frame.
    rush = play[play["nflId"].isin(rusher_ids) & play["frameId"].between(snap, end)]
    rush = rush.join(qb[["x", "y"]], on="frameId", rsuffix="_qb")
    rush_dist = np.hypot(rush["x"] - rush["x_qb"], rush["y"] - rush["y_qb"]).groupby(rush["frameId"]).min()
    rush_dist = rush_dist.reindex(qb.index)
    if config.PRESSURE_DISTANCE is not None:
        hits = rush_dist.index[rush_dist <= config.PRESSURE_DISTANCE]
        pressure_frame = int(hits.min()) if len(hits) else None
    else:
        pressure_frame = None

    t_since_snap = (qb.index - snap) / config.FRAMES_PER_SECOND

    row = {
        "snap_frame": snap,
        "end_frame": end,
        "end_reason": end_reason,
        "los_x": los_x,
        "drop_frame": drop,
        "drop_x": drop_xy[0],
        "drop_y": drop_xy[1],
        "max_drift": np.nanmax(drift.to_numpy()),
        "box_lo": box_lo,
        "box_hi": box_hi,
        "box_exit_frame": box_exit,
        "time_held": (end - snap) / config.FRAMES_PER_SECOND,
        "min_rusher_dist": rush_dist.min(),
        "pressure_frame": pressure_frame,
    }
    frames = pd.DataFrame({
        "frameId": qb.index,
        "t_since_snap": np.asarray(t_since_snap),
        "x": qb["x"].to_numpy(),
        "y": qb["y"].to_numpy(),
        "drift": drift.to_numpy(),
        "in_box": in_box.to_numpy(),
        "rusher_dist": rush_dist.to_numpy(),
    })
    return row, frames


def build_tracking_features():
    context = pd.read_csv(config.PLAY_CONTEXT_PATH, dtype={"qbId": config.ID_DTYPE})
    pff = data.load_pff()
    rushers = pff[pff["pff_role"] == config.RUSHER_ROLE].groupby(KEYS)["nflId"].apply(set)
    tackles = pff[pff["pff_positionLinedUp"].isin(config.TACKLE_POSITIONS)].groupby(KEYS)["nflId"].apply(set)
    qbs = context.set_index(KEYS)["qbId"]

    rows, frame_tables = [], []
    issues: Counter = Counter()
    missing_games: list = []
    seen = 0
    for game_id, track in data.iter_tracking(missing=missing_games):
        for play_id, play in track.groupby("playId"):
            key = (game_id, play_id)
            if key not in qbs.index:
                issues["play not in play_context"] += 1
                continue
            seen += 1
            row, frames = _play_features(
                play, qbs[key], rushers.get(key, set()), tackles.get(key, set()), issues
            )
            if row is None:
                continue
            rows.append({"gameId": game_id, "playId": play_id, **row})
            frames.insert(0, "playId", play_id)
            frames.insert(0, "gameId", game_id)
            frame_tables.append(frames)
        print(f"game {game_id}: {len(rows)} plays so far")

    features = pd.DataFrame(rows)
    qb_frames = pd.concat(frame_tables, ignore_index=True)
    for col in ["box_exit_frame", "pressure_frame"]:
        features[col] = features[col].astype("Int64")

    no_tracking = len(context) - seen
    print(f"play_context rows: {len(context)}")
    print(f"missing tracking files: {len(missing_games)}")
    print(f"plays with features: {len(features)}")
    for name, n in issues.items():
        print(f"  {name}: {n}")
    print(f"  play_context plays never seen in tracking: {no_tracking}")
    print("end_reason counts:", features["end_reason"].value_counts().to_dict())
    return features, qb_frames


def main() -> None:
    features, qb_frames = build_tracking_features()
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    features.to_csv(config.TRACKING_FEATURES_PATH, index=False)
    qb_frames.to_csv(config.QB_FRAMES_PATH, index=False)
    print(f"saved {config.TRACKING_FEATURES_PATH} ({len(features)} rows)")
    print(f"saved {config.QB_FRAMES_PATH} ({len(qb_frames)} rows)")


if __name__ == "__main__":
    main()
