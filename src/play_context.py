"""Task 1: one row per play with QB, situation, outcome and pressure flags.

Run: ``python -m src.play_context``
"""
from __future__ import annotations

import pandas as pd

from . import config, data

KEYS = ["gameId", "playId"]


def build_play_context() -> pd.DataFrame:
    plays = data.load_plays()
    pff = data.load_pff()
    print(f"plays.csv rows: {len(plays)}")

    # Passer from PFF. Flag plays with zero or multiple passers.
    passers = pff[pff["pff_role"] == config.PASSER_ROLE]
    n_passers = passers.groupby(KEYS).size().rename("n_passers")
    df = plays.merge(n_passers, on=KEYS, how="left")
    df["n_passers"] = df["n_passers"].fillna(0).astype(int)
    print(f"plays with 0 passers: {(df['n_passers'] == 0).sum()}")
    print(f"plays with >1 passers: {(df['n_passers'] > 1).sum()}")
    before = len(df)
    df = df[df["n_passers"] == 1]
    print(f"dropped (passer count != 1): {before - len(df)}")
    df = df.merge(passers[KEYS + ["nflId"]].rename(columns={"nflId": "qbId"}), on=KEYS)

    # Pressure: any rusher credited with a hit, hurry or sack.
    credited = pff[config.PRESSURE_COLS].eq(1).any(axis=1)
    rushers = pff["pff_role"] == config.RUSHER_ROLE
    print(f"pressure credits on non-rushers (rows): {(credited & ~rushers).sum()}")
    pressure = credited[rushers].groupby([pff.loc[rushers, k] for k in KEYS]).any()
    df = df.merge(pressure.rename("pressure"), left_on=KEYS, right_index=True, how="left")
    df["pressure"] = df["pressure"].fillna(False).astype(bool)

    # Success by down. Downs with no ratio (down 0) get NA.
    ratio = df["down"].map(config.SUCCESS_RATIO)
    print(f"plays with no success ratio for their down (success = NA): {ratio.isna().sum()}")
    df["success"] = (df["prePenaltyPlayResult"] >= ratio * df["yardsToGo"]).astype("boolean")
    df.loc[ratio.isna(), "success"] = pd.NA

    df["sack"] = df["passResult"] == "S"
    df["interception"] = df["passResult"] == "IN"
    print(f"plays with NaN dropBackType (kept): {df['dropBackType'].isna().sum()}")

    cols = KEYS + [
        "qbId", "possessionTeam", "defensiveTeam", "down", "yardsToGo",
        "prePenaltyPlayResult", "passResult", "dropBackType",
        "pressure", "success", "sack", "interception",
    ]
    df = df[cols].reset_index(drop=True)
    print(f"final rows: {len(df)}")
    print(f"pressured: {df['pressure'].sum()}, sacks: {df['sack'].sum()}, INTs: {df['interception'].sum()}")
    return df


def main() -> None:
    df = build_play_context()
    config.OUTPUTS_DIR.mkdir(exist_ok=True)
    df.to_csv(config.PLAY_CONTEXT_PATH, index=False)
    print(f"saved {config.PLAY_CONTEXT_PATH}")


if __name__ == "__main__":
    main()
