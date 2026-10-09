"""Task 3b-c: label each play scripted or chaos, and check the labels against dropBackType.

Designed plays (``config.DESIGNED_DROPBACKS``) are left out: their movement is
part of the call.

Chaos rules, each giving the first frame it fires (NA if it never does):
- ``drift``: first frame with drift from the drop spot > ``DRIFT_THRESHOLD``.
- ``box``: first frame the QB is outside the tackle box (``box_exit_frame``).
  NA on plays with no tackles at the snap; the other rules still apply.
- ``hold``: first frame with time since the snap > ``HOLD_TIME_THRESHOLD``,
  only if the end frame reaches it (same as ``time_held > HOLD_TIME_THRESHOLD``).

A play is ``chaos`` if any rule fires, else ``scripted``. ``off_script_frame`` is
the earliest rule frame and ``off_script_rule`` the rule at that frame; on a tie
the first rule in ``config.OFF_SCRIPT_RULE_ORDER`` wins. ``rules_fired`` lists
every rule that fired, and ``hold_only`` marks plays where only the hold rule did.

Pressure frame: first frame with the nearest pass rusher within
``PRESSURE_DISTANCE`` of the QB (from ``qb_frames.rusher_dist``, the same rule as
``tracking_features``). ``pressured`` = PFF pressure flag AND a pressure frame.

Every threshold is an argument (default from config), so the sensitivity check
and the no-hold view in ``league.py`` reuse ``label_plays``.

Run: ``python -m src.labels``
"""
from __future__ import annotations

import pandas as pd

from . import config, data

KEYS = ["gameId", "playId"]
RULES = ["drift", "box", "hold"]


def load_inputs() -> tuple[pd.DataFrame, pd.DataFrame]:
    """Play context joined to tracking features (designed plays dropped), and qb_frames."""
    context = pd.read_csv(config.PLAY_CONTEXT_PATH, dtype={"qbId": config.ID_DTYPE})
    features = pd.read_csv(config.TRACKING_FEATURES_PATH)
    frames = pd.read_csv(config.QB_FRAMES_PATH, dtype={"in_box": "boolean"})
    df = context.merge(features, on=KEYS)
    print(f"play_context rows: {len(context)}, with tracking features: {len(df)}")
    print(f"  PFF-pressured plays with no tracking features (dropped): "
          f"{context['pressure'].sum() - df['pressure'].sum()}")
    designed = df["dropBackType"].isin(config.DESIGNED_DROPBACKS)
    print(f"dropped (designed dropBackType): {designed.sum()}")
    df = df[~designed].reset_index(drop=True)
    print(f"plays to label: {len(df)}")
    return df, frames


def _first_frame(frames: pd.DataFrame, mask: pd.Series) -> pd.Series:
    """First frameId per play where ``mask`` holds."""
    return frames.loc[mask].groupby(KEYS)["frameId"].min()


def label_plays(
    df: pd.DataFrame,
    frames: pd.DataFrame,
    pressure_distance: float = config.PRESSURE_DISTANCE,
    drift: float = config.DRIFT_THRESHOLD,
    hold: float = config.HOLD_TIME_THRESHOLD,
    rules: list[str] = RULES,
) -> pd.DataFrame:
    """Add pressure, rule frames and the label to ``df`` (one row per play)."""
    df = df.set_index(KEYS).drop(columns=["pressure_frame"], errors="ignore")
    df["pressure_frame"] = _first_frame(frames, frames["rusher_dist"] <= pressure_distance).astype("Int64")
    df["pressured"] = df["pressure"] & df["pressure_frame"].notna()

    rule_frames = pd.DataFrame(index=df.index)
    rule_frames["drift"] = _first_frame(frames, frames["drift"] > drift)
    rule_frames["box"] = df["box_exit_frame"]
    hold_frame = df["snap_frame"] + round(hold * config.FRAMES_PER_SECOND) + 1
    rule_frames["hold"] = hold_frame.where(df["end_frame"] >= hold_frame)
    rule_frames = rule_frames[rules].astype("Int64")

    fired = rule_frames.notna()
    for r in rules:
        df[f"{r}_frame"] = rule_frames[r]
    df["rules_fired"] = fired.apply(lambda row: "+".join(r for r in rules if row[r]), axis=1)
    df["hold_only"] = df["rules_fired"] == "hold"
    df["off_script_frame"] = rule_frames.min(axis=1).astype("Int64")

    # Tie-break: among rules at the earliest frame, the first in OFF_SCRIPT_RULE_ORDER.
    order = [r for r in config.OFF_SCRIPT_RULE_ORDER if r in rules]
    at_first = rule_frames.eq(df["off_script_frame"], axis=0).fillna(False).astype(bool)[order]
    df["off_script_rule"] = at_first.idxmax(axis=1).where(at_first.any(axis=1))
    df["n_rules_at_first"] = at_first.sum(axis=1)
    df["label"] = df["off_script_frame"].notna().map({True: "chaos", False: "scripted"})
    df["chaos_before_pressure"] = (df["off_script_frame"] < df["pressure_frame"]).fillna(False).astype(bool)
    return df.reset_index()


def report_labels(df: pd.DataFrame) -> None:
    print("\nlabel counts:", df["label"].value_counts().to_dict())
    print("off_script_rule counts:", df["off_script_rule"].value_counts().to_dict())
    print("rules_fired counts:", df.loc[df["label"] == "chaos", "rules_fired"].value_counts().to_dict())
    ties = df[df["n_rules_at_first"] > 1]
    rule_cols = [c for c in ["drift_frame", "box_frame", "hold_frame"] if c in df]
    tie_pairs = ties[rule_cols].eq(ties["off_script_frame"], axis=0).fillna(False).astype(bool).apply(
        lambda row: "+".join(c.removesuffix("_frame") for c in rule_cols if row[c]), axis=1
    )
    print(f"ties (2+ rules on the off-script frame): {len(ties)}", tie_pairs.value_counts().to_dict())
    print(f"pressured plays (PFF flag and a pressure frame): {df['pressured'].sum()}")


def cross_tab(df: pd.DataFrame) -> pd.DataFrame:
    """Labels vs dropBackType, agreement, and the disagreement table."""
    for name, sub in [("all plays", df), ("pressured plays", df[df["pressured"]])]:
        print(f"\nlabel x dropBackType, {name}:")
        print(pd.crosstab(sub["dropBackType"].fillna("NaN"), sub["label"], margins=True).to_string())

        trad = sub[sub["dropBackType"] == "TRADITIONAL"]
        scr = sub[sub["dropBackType"].isin(config.CHAOS_DROPBACKS)]
        trad_ok = (trad["label"] == "scripted").sum()
        scr_ok = (scr["label"] == "chaos").sum()
        print(f"  agreement: TRADITIONAL scripted {trad_ok}/{len(trad)} ({trad_ok / len(trad):.3f}), "
              f"scramble types chaos {scr_ok}/{len(scr)} ({scr_ok / len(scr):.3f}), "
              f"overall {(trad_ok + scr_ok) / (len(trad) + len(scr)):.3f} "
              "(NaN and UNKNOWN not scored)")

    trad_chaos = (df["dropBackType"] == "TRADITIONAL") & (df["label"] == "chaos")
    scr_scripted = df["dropBackType"].isin(config.CHAOS_DROPBACKS) & (df["label"] == "scripted")
    print("\nTRADITIONAL labelled chaos, by rules_fired:",
          df.loc[trad_chaos, "rules_fired"].value_counts().to_dict())
    print("scramble types labelled scripted, by passResult:",
          df.loc[scr_scripted, "passResult"].value_counts().to_dict())
    print("scramble types labelled scripted, max_drift quantiles:",
          df.loc[scr_scripted, "max_drift"].quantile([0.25, 0.5, 0.75]).round(2).to_dict())

    plays = data.load_plays()[KEYS + ["playDescription"]]
    out = df[trad_chaos | scr_scripted].assign(
        disagreement=lambda d: d["label"].map({"chaos": "TRADITIONAL labelled chaos",
                                               "scripted": "scramble type labelled scripted"})
    )
    cols = KEYS + ["disagreement", "dropBackType", "passResult", "rules_fired", "off_script_rule",
                   "max_drift", "box_exit_frame", "time_held", "end_reason", "pressured"]
    return out[cols].merge(plays, on=KEYS, how="left")


def build_labels():
    df, frames = load_inputs()
    labeled = label_plays(df, frames)

    # Check: pressure frame from qb_frames matches the tracking_features column.
    saved = df.set_index(KEYS)["pressure_frame"].astype("Int64")
    mine = labeled.set_index(KEYS)["pressure_frame"].astype("Int64")
    mismatch = (saved.fillna(-1) != mine.reindex(saved.index).fillna(-1)).sum()
    print(f"pressure frame mismatches vs tracking_features: {mismatch}")
    assert mismatch == 0, "rerun python -m src.tracking_features with the current PRESSURE_DISTANCE"
    assert len(labeled) == len(df)
    assert labeled.loc[labeled["label"] == "chaos", "off_script_rule"].notna().all()

    report_labels(labeled)
    return labeled, cross_tab(labeled)


def main() -> None:
    labeled, disagreements = build_labels()
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    labeled.to_csv(config.PLAY_LABELS_PATH, index=False)
    disagreements.to_csv(config.LABEL_DISAGREEMENTS_PATH, index=False)
    print(f"\nsaved {config.PLAY_LABELS_PATH} ({len(labeled)} rows)")
    print(f"saved {config.LABEL_DISAGREEMENTS_PATH} ({len(disagreements)} rows)")


if __name__ == "__main__":
    main()
