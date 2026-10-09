"""Task 4: league-level scripted vs chaos on pressured plays, plus the Task 3 sensitivity check.

Pressured plays: PFF pressure flag AND a tracking pressure frame (see ``labels``).
PFF-pressured plays with no rusher within ``PRESSURE_DISTANCE`` before the end
frame have no pressure moment, so they are dropped and counted.

Self-selection fix: time is measured from the pressure frame. Seconds held
after pressure = ``(end_frame - pressure_frame) / FRAMES_PER_SECOND``.

Chaos before pressure (off-script frame earlier than the pressure frame) counts
as chaos in every table. The number of such plays is reported.

Rates: success rate leaves out plays with NA success (down 0) and reports how
many plays it used; sack and INT rates use all plays.

Curve views. The hold rule makes every long hold chaos, so scripted plays can't
reach the long bins. Two views show the curve without that effect:
- ``split``: scripted, plus one chaos line per ``off_script_rule``.
- ``no_hold``: labels from the drift and box rules only; hold-only plays count
  as scripted.

Survivorship check: sacks labelled chaos by tracking vs by ``dropBackType``. A
sack that is chaos only through the hold rule is not a failed escape, so failed
escapes = chaos sacks where the drift or box rule fired.

Run: ``python -m src.league``
"""
from __future__ import annotations

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from . import config, labels
from .thresholds import SERIES, SURFACE, TEXT, TEXT_MUTED, _style

KEYS = ["gameId", "playId"]
# Fourth categorical slot of the reference palette, for the 4-line split view.
SERIES_4 = SERIES + ["#eda100"]


def rates(df: pd.DataFrame, by) -> pd.DataFrame:
    df = df.assign(success=df["success"].astype("boolean"))
    g = df.groupby(by)
    return pd.DataFrame({
        "plays": g.size(),
        "success_plays": g["success"].count(),
        "success_rate": g["success"].mean().astype(float),
        "sacks": g["sack"].sum(),
        "sack_rate": g["sack"].mean(),
        "ints": g["interception"].sum(),
        "int_rate": g["interception"].mean(),
    })


def pressured_plays(labeled: pd.DataFrame) -> pd.DataFrame:
    pff = labeled["pressure"]
    has_frame = labeled["pressure_frame"].notna()
    print(f"PFF-pressured plays (labelled set): {pff.sum()}")
    print(f"  dropped, no rusher within {config.PRESSURE_DISTANCE} yd before the end frame: {(pff & ~has_frame).sum()}")
    print(f"  excluded, tracking pressure frame but no PFF pressure: {(~pff & has_frame).sum()}")
    p = labeled[labeled["pressured"]].copy()
    print(f"pressured plays: {len(p)}")
    pre = (p["label"] == "chaos") & p["chaos_before_pressure"]
    print(f"  chaos plays that went off script before the pressure frame (counted as chaos): "
          f"{pre.sum()} of {(p['label'] == 'chaos').sum()}")
    return p


def main_table(p: pd.DataFrame) -> pd.DataFrame:
    by_label = rates(p, "label").reset_index().rename(columns={"label": "value"}).assign(group="label")
    by_rule = (rates(p[p["label"] == "chaos"], "off_script_rule").reset_index()
               .rename(columns={"off_script_rule": "value"}).assign(group="chaos by off_script_rule"))
    table = pd.concat([by_label, by_rule], ignore_index=True)
    return table[["group", "value"] + [c for c in table if c not in ("group", "value")]]


def curve(p: pd.DataFrame, line: pd.Series, view: str) -> pd.DataFrame:
    """Success rate by seconds held after pressure, one row per (line, bin)."""
    step = round(config.CURVE_BIN_SECONDS * config.FRAMES_PER_SECOND)
    last = round(config.CURVE_MAX_SECONDS / config.CURVE_BIN_SECONDS)
    after = (p["end_frame"] - p["pressure_frame"]).astype(int)
    bin_idx = (after // step).clip(upper=last)
    out = rates(p.assign(line=line, bin=bin_idx), ["line", "bin"]).reset_index()
    out["bin_start"] = out["bin"] * config.CURVE_BIN_SECONDS
    out["bin_label"] = [f"{s:g}+" if b == last else f"{s:g}-{s + config.CURVE_BIN_SECONDS:g}"
                        for b, s in zip(out["bin"], out["bin_start"])]
    out.insert(0, "view", view)
    return out.drop(columns="bin")


def plot_curve(c: pd.DataFrame, title: str, path) -> None:
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(8, 6.5), sharex=True, facecolor=SURFACE,
                                      gridspec_kw={"height_ratios": [2, 1]})
    names = sorted(c["line"].unique(), key=lambda n: (n != "scripted", n))  # fixed color per line
    for color, name in zip(SERIES_4, names):
        sub = c[c["line"] == name]
        label = f"{name} (n={sub['plays'].sum()})"
        top.plot(sub["bin_start"], sub["success_rate"], color=color, linewidth=2,
                 marker="o", markersize=5, label=label)
        bottom.plot(sub["bin_start"], sub["plays"], color=color, linewidth=2, marker="o", markersize=5)
    _style(top, title, "")
    top.set_ylabel("success rate", color=TEXT_MUTED)
    top.set_ylim(0, 1)
    top.legend(frameon=False, labelcolor=TEXT, fontsize=9, loc="best")
    _style(bottom, "Plays per bin", "seconds held after pressure")
    bottom.set_ylabel("plays", color=TEXT_MUTED)
    ticks = c.drop_duplicates("bin_start").sort_values("bin_start")
    bottom.set_xticks(ticks["bin_start"], ticks["bin_label"])
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"saved {path}")


def survivorship(labeled: pd.DataFrame) -> None:
    sacks = labeled[labeled["sack"]]
    tracking = sacks["label"] == "chaos"
    dropback = sacks["dropBackType"].isin(config.CHAOS_DROPBACKS)
    moved = sacks["drift_frame"].notna() | sacks["box_frame"].notna()
    print(f"\nsacks (designed plays dropped): {len(sacks)}")
    print(f"  chaos by tracking rules: {tracking.sum()}")
    print(f"  chaos by dropBackType (scramble types): {dropback.sum()}")
    print(pd.crosstab(tracking.map({True: "tracking chaos", False: "tracking scripted"}),
                      dropback.map({True: "scramble type", False: "other dropBackType"})).to_string())
    print("  chaos sacks by off_script_rule:", sacks.loc[tracking, "off_script_rule"].value_counts().to_dict())
    print("  chaos sacks by rules_fired:", sacks.loc[tracking, "rules_fired"].value_counts().to_dict())
    print(f"  chaos sacks from the hold rule only (not failed escapes): {(tracking & sacks['hold_only']).sum()}")
    print(f"  failed escapes (chaos sacks with drift or box fired): {(tracking & moved).sum()}")
    print(f"    of which scramble type in dropBackType: {(tracking & moved & dropback).sum()}")


def sensitivity(df: pd.DataFrame, frames: pd.DataFrame) -> pd.DataFrame:
    variants = [("base", {})]
    for name, (down, up) in config.SENSITIVITY.items():
        variants += [(f"{name} down ({down})", {name: down}), (f"{name} up ({up})", {name: up})]
    variants.append(("no hold rule", {"rules": ["drift", "box"]}))

    tables = []
    for name, kwargs in variants:
        p = labels.label_plays(df, frames, **kwargs)
        p = p[p["pressured"]]
        tables.append(rates(p, "label").reset_index().assign(variant=name))
    out = pd.concat(tables, ignore_index=True)
    out = out[["variant"] + [c for c in out if c != "variant"]]
    print("\nsensitivity (pressured plays):")
    print(out.pivot(index="variant", columns="label", values=["plays", "success_rate"])
          .loc[[v for v, _ in variants]].round(3).to_string())
    return out


def build_league():
    df, frames = labels.load_inputs()
    labeled = labels.label_plays(df, frames)
    p = pressured_plays(labeled)

    summary = main_table(p)
    print("\nmain table (pressured plays):")
    print(summary.round(3).to_string(index=False))

    split = curve(p, p["label"].where(p["label"] == "scripted", "chaos: " + p["off_script_rule"].fillna("")),
                  "split")
    no_hold = labels.label_plays(df, frames, rules=["drift", "box"])
    p_no_hold = no_hold[no_hold["pressured"]]
    nh = curve(p_no_hold, p_no_hold["label"], "no_hold")
    curves = pd.concat([split, nh], ignore_index=True)
    print("\ncurve:")
    print(curves[["view", "line", "bin_label", "plays", "success_plays", "success_rate"]]
          .round(3).to_string(index=False))

    survivorship(labeled)
    sens = sensitivity(df, frames)
    return summary, curves, sens


def main() -> None:
    summary, curves, sens = build_league()
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_curve(curves[curves["view"] == "split"],
               "Success by seconds held after pressure, chaos split by first rule broken",
               config.PLOTS_DIR / "league_curve_split.png")
    plot_curve(curves[curves["view"] == "no_hold"],
               "Success by seconds held after pressure, labels without the hold rule",
               config.PLOTS_DIR / "league_curve_no_hold.png")
    summary.to_csv(config.LEAGUE_SUMMARY_PATH, index=False)
    curves.to_csv(config.LEAGUE_CURVE_PATH, index=False)
    sens.to_csv(config.SENSITIVITY_PATH, index=False)
    print(f"saved {config.LEAGUE_SUMMARY_PATH}, {config.LEAGUE_CURVE_PATH}, {config.SENSITIVITY_PATH}")


if __name__ == "__main__":
    main()
