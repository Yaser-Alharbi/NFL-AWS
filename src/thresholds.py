"""Task 3a: distribution plots and candidate values for the three thresholds.

Designed plays (``config.DESIGNED_DROPBACKS``) are left out, as in the labels.
Candidates are printed and drawn on the plots; the chosen values go into config.

Candidate rules (searched on a 0.1 grid, the frame/position resolution):
- Pressure distance: the distance that best separates PFF-pressured plays from
  clean plays on ``min_rusher_dist`` (max of true-positive rate minus
  false-positive rate, i.e. Youden's J).
- Drift and hold time: two rules each, so they can be compared.
  * percentiles of clean pass plays (not PFF-pressured, ``end_reason == pass``).
  * Youden's J for scramble types vs ``TRADITIONAL``. This one is fitted on
    ``dropBackType``, so the later cross-tab against it is not independent.

Run: ``python -m src.thresholds``
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config

KEYS = ["gameId", "playId"]
GRID_STEP = 0.1
PERCENTILES = [0.75, 0.9, 0.95, 0.99]

# Reference palette (dataviz skill), light mode, first three categorical slots.
SURFACE = "#fcfcfb"
TEXT = "#0b0b0b"
TEXT_MUTED = "#52514e"
SERIES = ["#2a78d6", "#eb6834", "#1baf7a"]


def load_plays() -> pd.DataFrame:
    context = pd.read_csv(config.PLAY_CONTEXT_PATH)
    features = pd.read_csv(config.TRACKING_FEATURES_PATH)
    df = context.merge(features, on=KEYS)
    print(f"plays with context and features: {len(df)}")
    designed = df["dropBackType"].isin(config.DESIGNED_DROPBACKS)
    print(f"dropped (designed dropBackType): {designed.sum()}")
    return df[~designed].reset_index(drop=True)


def youden(values: pd.Series, positive: pd.Series, grid: np.ndarray, above: bool):
    """Best cut on ``grid``. ``above`` = positives sit above the cut."""
    v, pos = values.to_numpy(), positive.to_numpy(dtype=bool)
    hit = (v[:, None] > grid) if above else (v[:, None] <= grid)
    j = hit[pos].mean(axis=0) - hit[~pos].mean(axis=0)
    i = int(j.argmax())
    return round(float(grid[i]), 2), round(float(j[i]), 3)


def _grid(values: pd.Series) -> np.ndarray:
    return np.round(np.arange(GRID_STEP, values.max() + GRID_STEP, GRID_STEP), 2)


def _style(ax, title: str, xlabel: str) -> None:
    ax.set_facecolor(SURFACE)
    ax.set_title(title, color=TEXT, loc="left", fontsize=11)
    ax.set_xlabel(xlabel, color=TEXT_MUTED)
    ax.set_ylabel("share of group's plays per bin", color=TEXT_MUTED)
    ax.tick_params(colors=TEXT_MUTED)
    ax.grid(axis="y", color="#e4e3df", linewidth=0.8)
    ax.set_axisbelow(True)
    for side in ["top", "right"]:
        ax.spines[side].set_visible(False)
    for side in ["left", "bottom"]:
        ax.spines[side].set_color("#c3c2b7")


def _plot(groups: dict, bins, title: str, xlabel: str, cuts: dict, path, logx=False) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    for color, (name, values) in zip(SERIES, groups.items()):
        ax.hist(values, bins=bins, weights=np.full(len(values), 1 / len(values)), histtype="step",
                linewidth=2, color=color, label=f"{name} (n={len(values)})")
    for i, (name, x) in enumerate(cuts.items()):
        ax.axvline(x, color=TEXT_MUTED, linestyle="--", linewidth=1)
        ax.annotate(f"{name}: {x}", (x, 1), xycoords=("data", "axes fraction"),
                    xytext=(4, -12 - 12 * i), textcoords="offset points", color=TEXT_MUTED, fontsize=8)
    if logx:
        ax.set_xscale("log")
    _style(ax, title, xlabel)
    ax.legend(frameon=False, labelcolor=TEXT, fontsize=9, loc="best")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"saved {path}")


def build_thresholds(df: pd.DataFrame) -> dict:
    scramble = df["dropBackType"].isin(config.CHAOS_DROPBACKS)
    traditional = df["dropBackType"] == "TRADITIONAL"
    clean_pass = df[~df["pressure"] & (df["end_reason"] == "pass")]
    print(f"scramble-type plays: {scramble.sum()}, TRADITIONAL: {traditional.sum()}")
    print(f"clean pass plays (not pressured, end_reason pass): {len(clean_pass)}")
    out = {}

    # Pressure distance.
    rush = df.dropna(subset=["min_rusher_dist"])
    print(f"\n[pressure distance] plays with no rusher distance (left out): {len(df) - len(rush)}")
    cut, j = youden(rush["min_rusher_dist"], rush["pressure"], _grid(rush["min_rusher_dist"]), above=False)
    print(f"  Youden vs PFF pressure: {cut} yd (J = {j})")
    for t in np.round(cut + np.arange(-1.0, 1.01, 0.5), 2):
        hit = rush["min_rusher_dist"] <= t
        tpr, fpr = hit[rush["pressure"]].mean(), hit[~rush["pressure"]].mean()
        print(f"    {t} yd: J = {tpr - fpr:.3f} (pressured within: {tpr:.3f}, clean within: {fpr:.3f})")
    out["pressure_distance"] = {"youden_pff": cut}
    _plot(
        {"PFF pressured": rush.loc[rush["pressure"], "min_rusher_dist"],
         "not pressured": rush.loc[~rush["pressure"], "min_rusher_dist"]},
        np.arange(0, rush["min_rusher_dist"].max() + 0.25, 0.25),
        "Closest pass rusher to the QB, snap to end frame", "min rusher-QB distance (yd)",
        {"Youden": cut}, config.PLOTS_DIR / "pressure_distance.png",
    )

    # Max drift.
    zero = (df["max_drift"] <= 0).sum()
    print(f"\n[drift] plays with max drift 0: {zero}")
    drift_cut, j = youden(df.loc[scramble | traditional, "max_drift"], scramble[scramble | traditional],
                          _grid(df["max_drift"]), above=True)
    pct = clean_pass["max_drift"].quantile(PERCENTILES).round(2)
    print(f"  Youden scramble types vs TRADITIONAL: {drift_cut} yd (J = {j})")
    print("  clean pass plays percentiles:", pct.to_dict())
    out["drift"] = {"youden_dropback": drift_cut, **{f"clean_p{int(p * 100)}": v for p, v in pct.items()}}
    pos = df[df["max_drift"] > 0]
    _plot(
        {"scramble types": pos.loc[scramble, "max_drift"],
         "TRADITIONAL": pos.loc[traditional, "max_drift"],
         "clean pass plays": clean_pass.loc[clean_pass["max_drift"] > 0, "max_drift"]},
        np.logspace(np.log10(pos["max_drift"].min()), np.log10(pos["max_drift"].max()), 50),
        f"Max drift from the drop spot ({zero} plays with drift 0 not shown)", "max drift (yd, log scale)",
        {"Youden": drift_cut, "clean p95": pct[0.95]}, config.PLOTS_DIR / "max_drift.png", logx=True,
    )

    # Time held.
    hold_cut, j = youden(df.loc[scramble | traditional, "time_held"], scramble[scramble | traditional],
                         _grid(df["time_held"]), above=True)
    pct = clean_pass["time_held"].quantile(PERCENTILES).round(2)
    print(f"\n[hold time] Youden scramble types vs TRADITIONAL: {hold_cut} s (J = {j})")
    print("  clean pass plays percentiles:", pct.to_dict())
    print("  end_reason counts:", df["end_reason"].value_counts().to_dict())
    out["hold"] = {"youden_dropback": hold_cut, **{f"clean_p{int(p * 100)}": v for p, v in pct.items()}}
    running = df["end_reason"].isin(["run", "qb_crossed_los"])
    _plot(
        {"pass": df.loc[df["end_reason"] == "pass", "time_held"],
         "sack": df.loc[df["end_reason"] == "sack", "time_held"],
         "run or crossed LOS": df.loc[running, "time_held"]},
        # Edges sit between the 0.1 s steps so no value lands on an edge.
        np.arange(-0.05, df["time_held"].max() + 0.2, 0.2),
        "Time held, snap to end frame, by end reason", "time held (s)",
        {"Youden": hold_cut, "clean p90": pct[0.9]}, config.PLOTS_DIR / "time_held.png",
    )
    return out


def main() -> None:
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    build_thresholds(load_plays())


if __name__ == "__main__":
    main()
