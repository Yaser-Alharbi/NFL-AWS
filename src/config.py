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

# ID columns, read as nullable Int64 in every file so joins match.
ID_COLS = [
    "gameId", "playId", "nflId", "pff_nflIdBlockedPlayer",
    "foulNFLId1", "foulNFLId2", "foulNFLId3",
]
ID_DTYPE = "Int64"
