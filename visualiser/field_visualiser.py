"""Top-down NFL play visualiser.

Renders a single play from the Big Data Bowl tracking data as a top-down view of
the field. Players are drawn as direction arrows annotated with their jersey
number, and the ball is drawn as a brown marker. An interactive slider lets you
scrub through the play by frame (game timestamp), and the ``event`` tagged on the
current frame is shown as text below the field.

For now the visualiser restricts the play to the frames at and after the ball
snap (``ball_snap`` / ``autoevent_ballsnap``).

Usage (standalone, interactive window):

    python -m visualiser.field_visualiser --game 2021090900 --play 97

Usage (programmatic / Jupyter):

    from visualiser.field_visualiser import PlayVisualiser
    viz = PlayVisualiser.from_files(game_id=2021090900, play_id=97)
    viz.show()
"""
from __future__ import annotations

import argparse
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.widgets import Slider

# Field geometry (yards). The tracking x axis spans both end zones:
# [0, 10] = left end zone, [10, 110] = playing field, [110, 120] = right end zone.
FIELD_LENGTH = 120.0
FIELD_WIDTH = 53.3
END_ZONE = 10.0

# Events that mark the ball snap. Frames before the earliest of these are dropped.
SNAP_EVENTS = {"ball_snap", "autoevent_ballsnap"}

# Default location of the dataset relative to the repo root.
DEFAULT_DATASET = Path(__file__).resolve().parents[1] / "Dataset"


@dataclass
class TeamColors:
    offense: str = "#1f77b4"   # blue
    defense: str = "#d62728"   # red
    football: str = "#8B4513"  # brown


def _tracking_path(game_id: int, dataset_dir: Path) -> Path:
    return dataset_dir / "tracking" / f"tracking_{game_id}.csv"


def load_play(
    game_id: int,
    play_id: int,
    dataset_dir: Path = DEFAULT_DATASET,
    after_snap_only: bool = True,
) -> pd.DataFrame:
    """Load the tracking rows for a single play.

    Returns a dataframe sorted by ``frameId``. When ``after_snap_only`` is True
    (the default) only frames at or after the ball snap are kept.
    """
    path = _tracking_path(game_id, dataset_dir)
    if not path.exists():
        raise FileNotFoundError(f"Tracking file not found: {path}")

    # Only read the play we care about to keep memory small.
    cols = [
        "gameId", "playId", "nflId", "frameId", "time", "jerseyNumber",
        "team", "playDirection", "x", "y", "s", "a", "dir", "o", "event",
    ]
    df = pd.read_csv(path, usecols=cols)
    df = df[df["playId"] == play_id].copy()
    if df.empty:
        raise ValueError(f"No tracking rows for gameId={game_id}, playId={play_id}")

    df.sort_values(["frameId", "nflId"], inplace=True)

    if after_snap_only:
        snap_frames = df.loc[df["event"].isin(SNAP_EVENTS), "frameId"]
        if not snap_frames.empty:
            snap_frame = int(snap_frames.min())
            df = df[df["frameId"] >= snap_frame].copy()

    return df


def _load_meta(game_id: int, play_id: int, dataset_dir: Path) -> dict:
    """Load the possession/defensive team and play description for context."""
    meta: dict = {}
    plays_path = dataset_dir / "plays.csv"
    if plays_path.exists():
        plays = pd.read_csv(plays_path)
        row = plays[(plays["gameId"] == game_id) & (plays["playId"] == play_id)]
        if not row.empty:
            r = row.iloc[0]
            meta["possessionTeam"] = r.get("possessionTeam")
            meta["defensiveTeam"] = r.get("defensiveTeam")
            meta["playDescription"] = r.get("playDescription")
            meta["absoluteYardlineNumber"] = r.get("absoluteYardlineNumber")
    return meta


class PlayVisualiser:
    """Interactive top-down visualiser for a single play."""

    def __init__(
        self,
        tracking: pd.DataFrame,
        meta: Optional[dict] = None,
        colors: Optional[TeamColors] = None,
    ) -> None:
        if tracking.empty:
            raise ValueError("tracking dataframe is empty")
        self.df = tracking.reset_index(drop=True)
        self.meta = meta or {}
        self.colors = colors or TeamColors()

        self.frames = sorted(self.df["frameId"].unique())
        self.possession = self.meta.get("possessionTeam")

        # Precompute a frame -> rows lookup for fast scrubbing.
        self._by_frame = {f: g for f, g in self.df.groupby("frameId")}

        # Matplotlib handles, created on first draw.
        self.fig = None
        self.ax = None
        self.slider = None
        self._event_text = None
        self._artists: list = []

    # ------------------------------------------------------------------ #
    # Construction helpers
    # ------------------------------------------------------------------ #
    @classmethod
    def from_files(
        cls,
        game_id: int,
        play_id: int,
        dataset_dir: Path = DEFAULT_DATASET,
        after_snap_only: bool = True,
    ) -> "PlayVisualiser":
        tracking = load_play(game_id, play_id, dataset_dir, after_snap_only)
        meta = _load_meta(game_id, play_id, dataset_dir)
        return cls(tracking, meta)

    # ------------------------------------------------------------------ #
    # Field drawing
    # ------------------------------------------------------------------ #
    def _draw_field(self) -> None:
        ax = self.ax
        ax.set_facecolor("#2e7d32")  # grass green

        # End zones.
        ax.add_patch(plt.Rectangle((0, 0), END_ZONE, FIELD_WIDTH,
                                   color="#1b5e20", zorder=0))
        ax.add_patch(plt.Rectangle((FIELD_LENGTH - END_ZONE, 0), END_ZONE,
                                   FIELD_WIDTH, color="#1b5e20", zorder=0))

        # Yard lines every 5 yards within the field of play.
        for x in np.arange(END_ZONE, FIELD_LENGTH - END_ZONE + 1, 5):
            ax.axvline(x, color="white", lw=0.8, alpha=0.6, zorder=1)

        # Yard numbers every 10 yards (10..100 field yards).
        for x in np.arange(END_ZONE + 10, FIELD_LENGTH - END_ZONE, 10):
            yard = int(x - END_ZONE)
            label = str(yard if yard <= 50 else 100 - yard)
            ax.text(x, 3, label, color="white", ha="center", va="center",
                    fontsize=9, alpha=0.7, zorder=1)
            ax.text(x, FIELD_WIDTH - 3, label, color="white", ha="center",
                    va="center", fontsize=9, alpha=0.7, zorder=1, rotation=180)

        ax.set_xlim(0, FIELD_LENGTH)
        ax.set_ylim(0, FIELD_WIDTH)
        ax.set_aspect("equal")
        ax.set_xticks([])
        ax.set_yticks([])

    def _player_color(self, team: str) -> str:
        if team == "football":
            return self.colors.football
        if self.possession is not None and team == self.possession:
            return self.colors.offense
        return self.colors.defense

    # ------------------------------------------------------------------ #
    # Per-frame rendering
    # ------------------------------------------------------------------ #
    def _clear_artists(self) -> None:
        for art in self._artists:
            art.remove()
        self._artists = []

    def _draw_frame(self, frame_id: int) -> None:
        self._clear_artists()
        rows = self._by_frame.get(frame_id)
        if rows is None:
            return

        # Arrow length in yards for the direction indicator.
        arrow_len = 2.2

        for _, r in rows.iterrows():
            team = r["team"]
            color = self._player_color(team)

            if team == "football":
                dot, = self.ax.plot(r["x"], r["y"], marker="o", markersize=7,
                                    color=color, zorder=5)
                self._artists.append(dot)
                continue

            # dir is the angle of motion in degrees, 0 = pointing +y, going
            # clockwise. Convert to dx/dy on the field.
            ang = np.deg2rad(r["dir"]) if not pd.isna(r["dir"]) else 0.0
            dx = arrow_len * np.sin(ang)
            dy = arrow_len * np.cos(ang)

            arr = self.ax.annotate(
                "",
                xy=(r["x"] + dx, r["y"] + dy),
                xytext=(r["x"], r["y"]),
                arrowprops=dict(arrowstyle="-|>", color=color, lw=2),
                zorder=4,
            )
            self._artists.append(arr)

            jersey = r["jerseyNumber"]
            if not pd.isna(jersey):
                txt = self.ax.text(
                    r["x"], r["y"], str(int(jersey)),
                    color="white", fontsize=7, ha="center", va="center",
                    fontweight="bold", zorder=6,
                    bbox=dict(boxstyle="circle,pad=0.15", fc=color, ec="white", lw=0.5),
                )
                self._artists.append(txt)

        # Event text below the field.
        self._update_event_text(frame_id, rows)
        if self.fig is not None:
            self.fig.canvas.draw_idle()

    def _current_event(self, rows: pd.DataFrame) -> str:
        events = rows["event"].dropna()
        events = events[events != "None"]
        if events.empty:
            return "(no event)"
        return ", ".join(sorted(events.unique()))

    def _update_event_text(self, frame_id: int, rows: pd.DataFrame) -> None:
        time_val = rows["time"].iloc[0] if "time" in rows else ""
        event = self._current_event(rows)
        n = len(self.frames)
        idx = self.frames.index(frame_id) + 1
        label = (f"Frame {frame_id}  ({idx}/{n})   time: {time_val}\n"
                 f"Event: {event}")
        if self._event_text is None:
            self._event_text = self.fig.text(
                0.5, 0.06, label, ha="center", va="center", fontsize=11,
                color="black",
                bbox=dict(boxstyle="round,pad=0.5", fc="#f0f0f0", ec="gray"),
            )
        else:
            self._event_text.set_text(label)

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #
    def show(self) -> None:
        """Open an interactive window with a frame slider."""
        self.fig, self.ax = plt.subplots(figsize=(13, 6.5))
        self.fig.subplots_adjust(bottom=0.22, top=0.9)

        title_bits = []
        if self.meta.get("possessionTeam") and self.meta.get("defensiveTeam"):
            title_bits.append(
                f"{self.meta['possessionTeam']} (off) vs "
                f"{self.meta['defensiveTeam']} (def)"
            )
        desc = self.meta.get("playDescription")
        self.ax.set_title(
            " | ".join(title_bits) if title_bits else "Play visualiser",
            fontsize=11,
        )
        if desc:
            self.fig.suptitle(str(desc), fontsize=9, y=0.98)

        self._draw_field()

        # Slider axis.
        slider_ax = self.fig.add_axes([0.15, 0.12, 0.7, 0.03])
        self.slider = Slider(
            ax=slider_ax,
            label="Frame",
            valmin=self.frames[0],
            valmax=self.frames[-1],
            valinit=self.frames[0],
            valstep=1,
        )
        self.slider.on_changed(self._on_slide)

        self._draw_frame(self.frames[0])
        plt.show()

    def _on_slide(self, val: float) -> None:
        frame_id = int(round(val))
        # Snap to the nearest valid frame id.
        if frame_id not in self._by_frame:
            frame_id = min(self.frames, key=lambda f: abs(f - frame_id))
        self._draw_frame(frame_id)

    def save_frame(self, frame_id: int, out_path: str) -> None:
        """Render a single frame to an image file (no interactivity)."""
        self.fig, self.ax = plt.subplots(figsize=(13, 6.5))
        self.fig.subplots_adjust(bottom=0.22, top=0.9)
        self._draw_field()
        if frame_id not in self._by_frame:
            frame_id = min(self.frames, key=lambda f: abs(f - frame_id))
        self._draw_frame(frame_id)
        self.fig.savefig(out_path, dpi=120, bbox_inches="tight")
        plt.close(self.fig)


def _parse_args(argv: Optional[list] = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Top-down NFL play visualiser")
    p.add_argument("--game", type=int, required=True, help="gameId")
    p.add_argument("--play", type=int, required=True, help="playId")
    p.add_argument("--dataset", type=Path, default=DEFAULT_DATASET,
                   help="path to the Dataset directory")
    p.add_argument("--all-frames", action="store_true",
                   help="include frames before the ball snap")
    p.add_argument("--save", type=str, default=None,
                   help="save a frame to this image path instead of showing")
    p.add_argument("--frame", type=int, default=None,
                   help="frame id to save when using --save")
    return p.parse_args(argv)


def main(argv: Optional[list] = None) -> None:
    args = _parse_args(argv)
    viz = PlayVisualiser.from_files(
        game_id=args.game,
        play_id=args.play,
        dataset_dir=args.dataset,
        after_snap_only=not args.all_frames,
    )
    if args.save:
        frame = args.frame if args.frame is not None else viz.frames[0]
        viz.save_frame(frame, args.save)
        print(f"Saved frame {frame} to {args.save}")
    else:
        viz.show()


if __name__ == "__main__":
    main()
