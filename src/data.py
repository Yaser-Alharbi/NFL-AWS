"""Loaders for the Big Data Bowl tables and per-game tracking files.

Every loader reads the ID columns in ``config.ID_COLS`` as nullable ``Int64`` so
joins line up across tables (ball rows in tracking keep ``<NA>`` for ``nflId``).
Tracking files mark "no event" with the literal string ``None``; it is read as NaN.
"""
from __future__ import annotations

from pathlib import Path
from typing import Iterable, Iterator, Optional

import pandas as pd

from . import config


def _read_csv(path: Path, **kwargs) -> pd.DataFrame:
    """Read a CSV, casting any ID columns present in its header to Int64."""
    header = pd.read_csv(path, nrows=0).columns
    dtype = {c: config.ID_DTYPE for c in config.ID_COLS if c in header}
    return pd.read_csv(path, dtype=dtype, **kwargs)


def load_games() -> pd.DataFrame:
    return _read_csv(config.DATASET_DIR / "games.csv")


def load_plays() -> pd.DataFrame:
    return _read_csv(config.DATASET_DIR / "plays.csv")


def load_players() -> pd.DataFrame:
    return _read_csv(config.DATASET_DIR / "players.csv")


def load_pff() -> pd.DataFrame:
    return _read_csv(config.DATASET_DIR / "pffScoutingData.csv")


def _tracking_path(game_id: int) -> Path:
    return config.TRACKING_DIR / f"tracking_{game_id}.csv"


def normalize_direction(df: pd.DataFrame) -> pd.DataFrame:
    """Rotate plays moving left by 180 degrees so the offense always moves right.

    Only rows with ``playDirection == "left"`` change. ``s``, ``a`` and ``dis``
    are direction-free and stay as they are. Returns a copy.
    """
    df = df.copy()
    left = df["playDirection"] == "left"
    df.loc[left, "x"] = config.FIELD_LENGTH - df.loc[left, "x"]
    df.loc[left, "y"] = config.FIELD_WIDTH - df.loc[left, "y"]
    df.loc[left, "o"] = (df.loc[left, "o"] + 180) % 360
    df.loc[left, "dir"] = (df.loc[left, "dir"] + 180) % 360
    return df


def load_tracking(game_id: int, normalize: bool = True) -> pd.DataFrame:
    """Load the tracking rows for one game. Raises if the file is missing."""
    path = _tracking_path(game_id)
    if not path.exists():
        raise FileNotFoundError(f"Tracking file not found: {path}")

    df = _read_csv(path, na_values=["None"])
    if normalize:
        df = normalize_direction(df)
    return df


def iter_tracking(
    game_ids: Optional[Iterable[int]] = None,
    normalize: bool = True,
    missing: Optional[list] = None,
) -> Iterator[tuple[int, pd.DataFrame]]:
    """Yield ``(game_id, df)`` one game at a time.

    Defaults to every gameId in games.csv. A missing file is printed, appended
    to ``missing`` (if given), and skipped, so the caller can report it after
    the loop.
    """
    if game_ids is None:
        game_ids = load_games()["gameId"].tolist()

    for game_id in game_ids:
        if not _tracking_path(game_id).exists():
            print(f"Missing tracking file for gameId={game_id}, skipped")
            if missing is not None:
                missing.append(game_id)
            continue
        yield game_id, load_tracking(game_id, normalize=normalize)
