Script vs Chaos: Plan
Question
When a QB's pass play breaks down under pressure, does leaving the script help or hurt?

Rules
Use only the provided dataset (hackathon rule). No nflverse, so no EPA.
QBs only. The data has no play calls or assignments, so other positions can't be judged on adherence.
Definitions
Pressure: any rusher credited with a hit, hurry, or sack on the play (PFF). The pressure moment is estimated from tracking as the first frame a rusher is within ~2 yds of the QB.
Chaos (tracking-based, not the PFF label): QB drifts more than X yds from his drop spot, leaves the pocket (outside the tackle box), or holds the ball past ~3.5s. dropBackType is used only as a sanity check.
Success: gain of at least 40% of yards to go (1st down), 60% (2nd), or 100% (3rd/4th), from prePenaltyPlayResult.
Disaster: sack or INT.
Chaos value: success rate on chaos plays minus scripted plays, pressured plays only, shrunk toward the league average (empirical Bayes) because of small samples.
Known biases to handle
Survivorship: failed escapes can get logged as scripted sacks. Defining chaos from tracking fixes this.
Self-selection: compare only plays from the moment pressure arrives.
Small samples: median ~9 pressured scrambles per QB. Use shrinkage and always show play counts.
Steps
Build play context: pressure flag, down/distance, result, success, disaster.
Tracking features per play: snap and end frames, drop spot, max drift, pocket exit, time held, pressure frame.
Label each play scripted or chaos, and validate the labels against dropBackType.
League-level analysis: success and disaster rates by scripted/chaos, and by seconds held after pressure.
Per-QB chaos value with shrinkage and sample counts.
Build the visualiser (single self-contained HTML).
Visualiser
QB quadrant (main): x = how often he breaks structure under pressure, y = chaos value. Quadrants: Magicians, Gamblers, Hidden weapon, Stay in structure.
Play replay: top-down animation of a selected QB's play. Shows the QB path, pocket, a pressure marker, and the trail changing color when he goes off script.
QB card: scripted vs chaos success, sack and INT rate, with play counts.
Optional: league success rate by seconds held after pressure, one line for scripted and one for chaos.