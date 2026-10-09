# Quarter-Back Improvisation Insight

**Winner, NFL x UCL CDI x AWS Big Data Bowl Hackathon (London)**

**Team:** [Ansh Shah](https://github.com/shahansh004) · [Yaser Alharbi](https://github.com/Yaser-Alharbi)

Live Demo:

https://yaser-alharbi.github.io/NFL-AWS-Hackathon-Winner/

> When a QB's pass play breaks down under pressure, does leaving the script help or hurt?

- **What we built:** Using only the provided NFL tracking and PFF data, we label each pressured QB play as scripted or chaos from the QB's movement and give each QB a chaos value, shown in a single-page visualiser.
- **What it reveals:** Which quarterbacks gain when they improvise, and which do better staying in structure.
- **Who would use it:** Coaches, scouts, and analysts, for QB evaluation and game planning.

## How to run

Run every command from the repo root.

### 1. Create the environment (once)

```
conda env create -f environment.yml
conda activate nfl-dbb
```

If the environment already exists and `environment.yml` changed, update it with `conda env update -f environment.yml --prune`.

### 2. Run the pipeline

`outputs/` is not in git, so a fresh clone needs the full pipeline. One command runs every step in order:

```
python -m src.run_all
```

To resume at a step and reuse what earlier steps wrote, pass `--from`, for example `python -m src.run_all --from qb_summary`.

The same steps one at a time:

```
python -m src.play_context
python -m src.tracking_features
python -m src.thresholds
python -m src.labels
python -m src.league
python -m src.qb_summary
python -m src.visualiser
```

`src.visualiser` writes the JSON files and `script_vs_chaos.html` to `export/`. If `outputs/` is already filled, `python -m src.visualiser` on its own rebuilds the page.

### 3. Open the visualiser

The page is one self-contained HTML file. Open it in a browser:

```
open export/script_vs_chaos.html          # macOS
start export\script_vs_chaos.html         # Windows (PowerShell)
```
