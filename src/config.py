"""Single home for every path and threshold used by the pipeline."""
from __future__ import annotations

from pathlib import Path

# Paths (relative to the repo root).
ROOT = Path(__file__).resolve().parents[1]
DATASET_DIR = ROOT / "Dataset"
TRACKING_DIR = DATASET_DIR / "tracking"
OUTPUTS_DIR = ROOT / "outputs"  # intermediate tables (gitignored)
EXPORT_DIR = ROOT / "export"    # JSON for the visualiser (tracked)

# Field geometry (yards), from Dataset_desc.md.
FIELD_LENGTH = 120.0
FIELD_WIDTH = 53.3

# Success: gain >= ratio * yardsToGo, by down (from tasks.md).
SUCCESS_RATIO = {1: 0.4, 2: 0.6, 3: 1.0, 4: 1.0}

# Chaos and pressure thresholds. Set in Task 3 from the data.
PRESSURE_DISTANCE = None    # yards, rusher to QB; set in Task 3
DRIFT_THRESHOLD = None      # yards from the drop spot; set in Task 3
HOLD_TIME_THRESHOLD = None  # seconds from the snap; set in Task 3

# Format for intermediate tables in OUTPUTS_DIR.
OUTPUT_FORMAT = "csv"
PLAY_CONTEXT_PATH = OUTPUTS_DIR / f"play_context.{OUTPUT_FORMAT}"
TRACKING_FEATURES_PATH = OUTPUTS_DIR / f"tracking_features.{OUTPUT_FORMAT}"
QB_FRAMES_PATH = OUTPUTS_DIR / f"qb_frames.{OUTPUT_FORMAT}"

# Tracking event names, from a scan of all 122 tracking files.
# Each list is in order of preference: the first name found on a play wins.
SNAP_EVENTS = ["ball_snap", "autoevent_ballsnap"]
PASS_EVENTS = ["pass_forward", "autoevent_passforward"]
SACK_EVENTS = ["qb_sack", "qb_strip_sack"]
# QB takes off. Tracking stops 5 frames after it (median, 472 plays).
RUN_EVENTS = ["run"]

# Tracking frame rate. `time` only has 1-second resolution; full seconds hold
# 10 frames (measured on games 2021090900 and 2021110100).
FRAMES_PER_SECOND = 10

# PFF roles and alignments used by the pipeline.
PASSER_ROLE = "Pass"
RUSHER_ROLE = "Pass Rush"
TACKLE_POSITIONS = ["LT", "RT"]
PRESSURE_COLS = ["pff_hit", "pff_hurry", "pff_sack"]

# ID columns, read as nullable Int64 in every file so joins match.
ID_COLS = [
    "gameId", "playId", "nflId", "pff_nflIdBlockedPlayer",
    "foulNFLId1", "foulNFLId2", "foulNFLId3",
]
ID_DTYPE = "Int64"
