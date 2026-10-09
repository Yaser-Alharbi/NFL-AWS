# Script vs Chaos: Plan

## Question

When a QB's pass play breaks down under pressure, does leaving the script help or hurt?

## Rules

- Use only the provided dataset (hackathon rule). No nflverse, so no EPA.
- QBs only. The data has no play calls or assignments, so other positions can't be judged on adherence.

## Definitions

- **Pressure:** any rusher credited with a hit, hurry, or sack on the play (PFF). The pressure moment is estimated from tracking as the first frame a rusher gets within a set distance of the QB (distance not chosen yet).
- **Chaos (tracking-based, not the PFF label):** QB drifts too far from his drop spot, leaves the tackle box (the space between the two tackles at the snap), or holds the ball too long. The thresholds are not chosen yet; set them from the data. `dropBackType` is used only as a sanity check.
- **Success:** gain of at least 40% of yards to go (1st down), 60% (2nd), or 100% (3rd/4th), from `prePenaltyPlayResult`.
- **Sack and INT rate:** reported next to success rate.
- **Chaos value:** success rate on chaos plays minus scripted plays, pressured plays only, shrunk toward the league average (empirical Bayes) because of small samples.

## Known biases to handle

- **Survivorship:** failed escapes can get logged as scripted sacks. Defining chaos from tracking fixes this.
- **Self-selection:** compare only plays from the moment pressure arrives.
- **Small samples:** median of 9 pressured scrambles per QB (measured). Use shrinkage and always show play counts.

## Steps

1. Build play context: pressure flag, down/distance, result, success, sack, INT.
2. Tracking features per play: snap and end frames, drop spot, max drift, pocket exit, time held, pressure frame.
3. Label each play scripted or chaos, and validate the labels against `dropBackType`.
4. League-level analysis: success, sack and INT rates by scripted/chaos, and by seconds held after pressure.
5. Per-QB chaos value with shrinkage and sample counts.
6. Build the visualiser (single self-contained HTML).

## Status

- First-pass preview built: https://claude.ai/artifact/Twf3dsqZojotN9y1Lx95Rq
- The preview labels plays off-script with PFF's `dropBackType` (SCRAMBLE*), counts a play as pressured if pressure happened at any point, and shows raw QB rates. It does not yet follow the definitions above (tracking-based chaos, pressure moment, shrinkage), so it still carries the survivorship bias.
- In the replay, the QB trail changes color when he leaves the tackle box.
- Not built yet: optional view 4.

## Visualiser

1. **QB quadrant (main):** x = how often he breaks structure under pressure, y = chaos value. Corners described in plain words (e.g. "off-script often, and it gains"), no invented names.
2. **Play replay:** top-down animation of a selected QB's play. Shows the QB path, pocket, a pressure marker, and the trail changing color when he goes off script.
3. **QB card:** scripted vs chaos success, sack and INT rate, with play counts.
4. **Optional:** league success rate by seconds held after pressure, one line for scripted and one for chaos.

## Parked

- Bad Game Breakdown (per-game attribution vs a player's own baseline). Shelved because the metrics and approach aren't original.