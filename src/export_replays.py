"""Export chaos-event replay clips for the field visualiser.

Interim chaos rule (Option A, until the tracking thresholds in tasks.md step 3 exist):
  - play is chaos if dropBackType starts with "SCRAMBLE"
  - chaos frame = first frame after the snap where the QB's y leaves the tackle box
    (lateral span between LT and RT at the snap, from pff_positionLinedUp)
Plays with no QB, no tackles, no snap, or no box exit are skipped and counted.

Usage:
  python src/export_replays.py            # writes visualiser/data/replays.json
  python src/export_replays.py --embed    # also writes visualiser/standalone.html
"""
import argparse
import glob
import json
import os
from datetime import date

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA = os.path.join(ROOT, "Dataset")
OUT_DIR = os.path.join(ROOT, "visualiser", "data")
HTML = os.path.join(ROOT, "visualiser", "index.html")

PRE_FRAMES = 20   # frames kept before the chaos frame
POST_FRAMES = 40  # frames kept after the chaos frame
SNAP_EVENTS = ("ball_snap", "autoevent_ballsnap")


def load_candidates():
    plays = pd.read_csv(os.path.join(DATA, "plays.csv"))
    games = pd.read_csv(os.path.join(DATA, "games.csv"))
    players = pd.read_csv(os.path.join(DATA, "players.csv"), usecols=["nflId", "displayName"])
    pff = pd.read_csv(os.path.join(DATA, "pffScoutingData.csv"),
                      usecols=["gameId", "playId", "nflId", "pff_role", "pff_positionLinedUp"])

    chaos = plays[plays["dropBackType"].fillna("").str.startswith("SCRAMBLE")]
    chaos = chaos.merge(games[["gameId", "week", "homeTeamAbbr", "visitorTeamAbbr"]], on="gameId")

    qb = pff[pff["pff_role"] == "Pass"].groupby(["gameId", "playId"])["nflId"].agg(list).rename("qb")
    lt = pff[pff["pff_positionLinedUp"] == "LT"].groupby(["gameId", "playId"])["nflId"].first().rename("lt")
    rt = pff[pff["pff_positionLinedUp"] == "RT"].groupby(["gameId", "playId"])["nflId"].first().rename("rt")
    chaos = chaos.join(qb, on=["gameId", "playId"]).join(lt, on=["gameId", "playId"]).join(rt, on=["gameId", "playId"])
    names = dict(zip(players["nflId"], players["displayName"]))
    return chaos, names


def clip_play(trk, row, names, skipped):
    qbs = row["qb"] if isinstance(row["qb"], list) else []
    if len(qbs) != 1 or pd.isna(row["lt"]) or pd.isna(row["rt"]):
        skipped["no_qb_or_tackles"] += 1
        return None
    qb_id = qbs[0]

    frame_events = trk.dropna(subset=["event"]).query("event != 'None'").groupby("frameId")["event"].first()
    snaps = frame_events[frame_events.isin(SNAP_EVENTS)]
    if snaps.empty:
        skipped["no_snap"] += 1
        return None
    snap = int(snaps.index.min())

    at_snap = trk[trk["frameId"] == snap].set_index("nflId")
    if row["lt"] not in at_snap.index or row["rt"] not in at_snap.index:
        skipped["no_qb_or_tackles"] += 1
        return None
    lo, hi = sorted((at_snap.at[row["lt"], "y"], at_snap.at[row["rt"], "y"]))

    qb_path = trk[(trk["nflId"] == qb_id) & (trk["frameId"] > snap)].sort_values("frameId")
    out = qb_path[(qb_path["y"] < lo) | (qb_path["y"] > hi)]
    if out.empty:
        skipped["no_box_exit"] += 1
        return None
    chaos_frame = int(out["frameId"].iloc[0])

    last = int(trk["frameId"].max())
    f0, f1 = max(1, chaos_frame - PRE_FRAMES), min(last, chaos_frame + POST_FRAMES)
    clip = trk[(trk["frameId"] >= f0) & (trk["frameId"] <= f1)]

    # entity table: players then ball (nflId NaN)
    ents = clip.drop_duplicates("nflId")[["nflId", "jerseyNumber", "team"]]
    ents = ents.sort_values(["team", "jerseyNumber"], na_position="last")
    ent_ids = list(ents["nflId"])
    idx = {(-1 if pd.isna(n) else n): i for i, n in enumerate(ent_ids)}
    entities = []
    for n, j, t in ents.itertuples(index=False):
        if pd.isna(n):
            entities.append({"id": None, "jersey": None, "team": "football"})
        else:
            entities.append({"id": int(n), "jersey": None if pd.isna(j) else int(j), "team": t})

    # frames: per entity [x*10, y*10, o] as ints (o = -1 when missing); null if entity absent
    frames = []
    for fid, g in clip.groupby("frameId"):
        rowf = [None] * len(entities)
        for n, x, y, o in g[["nflId", "x", "y", "o"]].itertuples(index=False):
            k = idx[-1 if pd.isna(n) else n]
            rowf[k] = [round(x * 10), round(y * 10), -1 if pd.isna(o) else round(o)]
        frames.append(rowf)

    return {
        "gameId": int(row["gameId"]), "playId": int(row["playId"]),
        "week": int(row["week"]), "home": row["homeTeamAbbr"], "away": row["visitorTeamAbbr"],
        "quarter": int(row["quarter"]), "clock": row["gameClock"],
        "down": int(row["down"]), "yardsToGo": int(row["yardsToGo"]),
        "offense": row["possessionTeam"], "defense": row["defensiveTeam"],
        "dropBackType": row["dropBackType"], "passResult": None if pd.isna(row["passResult"]) else row["passResult"],
        "description": row["playDescription"],
        "qbId": int(qb_id), "qbName": names.get(qb_id, str(qb_id)),
        "playDirection": trk["playDirection"].iloc[0],
        "snapFrame": snap, "chaosFrame": chaos_frame, "firstFrame": f0,
        "box": [round(lo, 2), round(hi, 2)],
        "events": [[int(f), e] for f, e in frame_events.items()],
        "entities": entities, "frames": frames,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--embed", action="store_true", help="also write visualiser/standalone.html with data inlined")
    args = ap.parse_args()

    cand, names = load_candidates()
    print(f"candidate SCRAMBLE* plays: {len(cand)}")
    skipped = {"no_qb_or_tackles": 0, "no_snap": 0, "no_box_exit": 0, "no_tracking": 0}
    clips = []
    cols = ["gameId", "playId", "nflId", "frameId", "jerseyNumber", "team", "playDirection", "x", "y", "o", "event"]
    for path in sorted(glob.glob(os.path.join(DATA, "tracking", "tracking_*.csv"))):
        gid = int(os.path.basename(path)[9:-4])
        gplays = cand[cand["gameId"] == gid]
        if gplays.empty:
            continue
        trk = pd.read_csv(path, usecols=cols)
        trk = trk[trk["playId"].isin(gplays["playId"])]
        by_play = dict(tuple(trk.groupby("playId")))
        for _, row in gplays.iterrows():
            if row["playId"] not in by_play:
                skipped["no_tracking"] += 1
                continue
            c = clip_play(by_play[row["playId"]], row, names, skipped)
            if c:
                clips.append(c)

    print(f"exported clips: {len(clips)}  skipped: {skipped}")
    payload = {
        "meta": {
            "rule": "interim, dropBackType SCRAMBLE*; chaos frame = first QB exit from LT-RT box after snap",
            "preFrames": PRE_FRAMES, "postFrames": POST_FRAMES,
            "candidates": int(len(cand)), "exported": len(clips), "skipped": skipped,
            "built": date.today().isoformat(),
        },
        "plays": clips,
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    out = os.path.join(OUT_DIR, "replays.json")
    with open(out, "w") as f:
        json.dump(payload, f, separators=(",", ":"))
    print(f"wrote {out} ({os.path.getsize(out) / 1e6:.2f} MB)")

    if args.embed:
        with open(HTML) as f:
            html = f.read()
        data = json.dumps(payload, separators=(",", ":")).replace("</", "<\\/")
        html = html.replace("<script id=\"embedded-data\" type=\"application/json\"></script>",
                            f"<script id=\"embedded-data\" type=\"application/json\">{data}</script>")
        sa = os.path.join(ROOT, "visualiser", "standalone.html")
        with open(sa, "w") as f:
            f.write(html)
        print(f"wrote {sa} ({os.path.getsize(sa) / 1e6:.2f} MB)")


if __name__ == "__main__":
    main()
