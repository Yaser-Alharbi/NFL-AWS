# Script vs Chaos: Tasks

Implementation tasks (steps 1 to 5 of `plan.md`) plus the data handoff to the visualiser (step 6).
Rules: only `Dataset/`, QBs only, no invented numbers. Every threshold is set from the data and recorded in one config.

## 0. Setup
- [x] Project layout: `src/` (pipeline code), `outputs/` (intermediate tables), `export/` (JSON for the visualiser).
- [x] One config file holding every threshold and path (pressure distance, drift, hold time, success ratios).
- [x] Loader for games, plays, players, PFF scouting.
- [x] Tracking loader that reads one game file at a time (122 files, too big to load together).
- [x] Normalize coordinates so the offense always moves the same way (use `playDirection`).

## 1. Play context
- [x] One row per play (`gameId`, `playId`).
- [x] QB `nflId` from PFF (`pff_role == Pass`). Flag and report plays with zero or multiple passers.
- [x] Down, yards to go, `prePenaltyPlayResult`, `passResult`, `dropBackType`.
- [x] Pressure flag: any rusher with `pff_hit`, `pff_hurry` or `pff_sack` on the play.
- [x] Success flag: gain >= 40% of yards to go (1st), 60% (2nd), 100% (3rd/4th).
- [x] Sack flag (`passResult == S`) and INT flag (`passResult == IN`).
- [x] Report row counts and how many plays each filter drops.
- [x] Save `outputs/play_context`.

## 2. Tracking features per play
- [x] Snap frame (`event == ball_snap`). List event values first; do not assume names.
- [x] End frame: first of pass forward, sack, QB run past the line, or play end. Record which one.
- [x] Drop spot: QB position at the end of the drop (define and document the rule).
- [x] Max drift from the drop spot, up to the end frame.
- [x] Tackle box: lateral span between the two tackles at the snap (from `pff_positionLinedUp`). First frame the QB leaves it.
- [x] Time held: snap to end frame, in seconds.
- [ ] Pressure frame: first frame any pass rusher is within the pressure distance of the QB.
- [x] Per-frame QB drift and box status kept for the replay export.
- [x] Save `outputs/tracking_features`. Report plays with missing frames or events.

## 3. Thresholds and labels
- [ ] Plot distributions of rusher-QB distance, max drift and time held.
- [ ] Choose the pressure distance, drift threshold and hold-time threshold from those plots. Record them in the config with a one-line reason each.
- [ ] Label each play `scripted` or `chaos` (drift OR box exit OR hold-time breach).
- [ ] Record the off-script frame: first frame any chaos rule is broken.
- [ ] Cross-tab labels against `dropBackType`. Report agreement and inspect the disagreements.
- [ ] Sensitivity check: rerun the main result with each threshold moved up and down.

## 4. League-level analysis
- [ ] Filter to pressured plays, measured from the pressure frame (the self-selection fix).
- [ ] Decide how to handle plays where chaos started before pressure. Document the choice.
- [ ] Success, sack and INT rate for scripted vs chaos, with play counts.
- [ ] Success rate by seconds held after pressure, one curve for scripted and one for chaos. Show the counts per bin.
- [ ] Survivorship check: how many sacks get labelled chaos under the tracking rules vs under `dropBackType`.

## 5. Per-QB chaos value
- [ ] Per QB: pressured plays, chaos plays, scripted plays, chaos rate under pressure.
- [ ] Raw chaos value = chaos success rate minus scripted success rate.
- [ ] Empirical Bayes shrinkage toward the league average (beta-binomial on each rate, or shrink the difference). Document the method and the fitted prior.
- [ ] Set a minimum play count to appear in the visualiser. Show counts everywhere.
- [ ] Quadrant assignment, split at the league chaos rate and zero chaos value (or the league average). Describe each corner in plain words.
- [ ] Save `outputs/qb_summary`.

## 6. Export for the visualiser (handoff)
- [ ] Agree on the JSON schema with the visualiser side before building it.
- [ ] `qb_summary.json`: QB id, name, team, counts, chaos rate, raw and shrunk chaos value, scripted/chaos success, sack and INT rates, quadrant.
- [ ] `league_curve.json`: seconds-held bins, scripted and chaos success rate, counts.
- [ ] `replays.json`: per selected play, frames for the QB, rushers and ball, tackle-box edges, pressure frame, off-script frame, outcome.
- [ ] `meta.json`: thresholds used, data scope, build date.
- [ ] Keep the files small enough to embed in a single HTML file (subset of replays per QB).

## 7. Checks before handoff
- [ ] Spot-check 5 to 10 replays by eye against `playDescription`.
- [ ] Every number in the export comes from code, not typed in by hand.
- [ ] Update `plan.md` Status once the definitions are implemented.