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

# Chaos and pressure thresholds, chosen in Task 3 (``python -m src.thresholds``).
# Pressure: best split of min rusher distance, PFF-pressured vs clean plays (Youden J 0.622).
PRESSURE_DISTANCE = 2.1     # yards, rusher to QB
# Drift: 95th percentile of max drift on clean pass plays (not fitted on dropBackType).
DRIFT_THRESHOLD = 2.74      # yards from the drop spot
# Hold: 95th percentile of time held on clean pass plays (same rule as drift).
HOLD_TIME_THRESHOLD = 4.0   # seconds from the snap

# Sensitivity check: (down, up) value per threshold, from the same plots.
SENSITIVITY = {
    "pressure_distance": (1.6, 2.6),  # +/-0.5 yd; Youden J 0.527 / 0.521
    "drift": (1.48, 12.26),           # clean pass p90 / p99
    "hold": (3.6, 5.5),               # clean pass p90 / p99
}

# League curve: success by seconds held after pressure.
CURVE_BIN_SECONDS = 0.5   # median post-pressure time is 0.7 s; 0.5 s splits the first 2 s into 4 bins
CURVE_MAX_SECONDS = 3.5   # 95th percentile of post-pressure time; later plays pooled in a "3.5+" bin

# Tie-break when two chaos rules fire on the same frame: the first listed wins.
# Box exit is the clearest visible event; hold time is only a clock.
OFF_SCRIPT_RULE_ORDER = ["box", "drift", "hold"]

# Format for intermediate tables in OUTPUTS_DIR.
OUTPUT_FORMAT = "csv"
PLAY_CONTEXT_PATH = OUTPUTS_DIR / f"play_context.{OUTPUT_FORMAT}"
TRACKING_FEATURES_PATH = OUTPUTS_DIR / f"tracking_features.{OUTPUT_FORMAT}"
QB_FRAMES_PATH = OUTPUTS_DIR / f"qb_frames.{OUTPUT_FORMAT}"
PLAY_LABELS_PATH = OUTPUTS_DIR / f"play_labels.{OUTPUT_FORMAT}"
LABEL_DISAGREEMENTS_PATH = OUTPUTS_DIR / f"label_disagreements.{OUTPUT_FORMAT}"
LEAGUE_SUMMARY_PATH = OUTPUTS_DIR / f"league_summary.{OUTPUT_FORMAT}"
LEAGUE_CURVE_PATH = OUTPUTS_DIR / f"league_curve.{OUTPUT_FORMAT}"
SENSITIVITY_PATH = OUTPUTS_DIR / f"sensitivity.{OUTPUT_FORMAT}"
PLOTS_DIR = OUTPUTS_DIR / "plots"

# dropBackType groups. Designed plays are left out of labels and analysis
# (movement is part of the call); scramble types are the expected chaos plays.
DESIGNED_DROPBACKS = ["DESIGNED_ROLLOUT_LEFT", "DESIGNED_ROLLOUT_RIGHT", "DESIGNED_RUN"]
CHAOS_DROPBACKS = ["SCRAMBLE", "SCRAMBLE_ROLLOUT_LEFT", "SCRAMBLE_ROLLOUT_RIGHT"]

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
