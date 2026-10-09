"""Task 5: per-QB chaos value on pressured plays, with empirical Bayes shrinkage.

Input: ``play_labels`` (Task 3), pressured plays only, the same set as ``league``
(Task 4): PFF pressure flag AND a tracking pressure frame. Plays that went off
script before the pressure frame count as chaos. Passers whose
``officialPosition`` is not ``config.QB_POSITION`` are dropped.

Per QB: pressured, chaos and scripted plays; chaos rate = chaos / pressured.
Success, sack and INT rates per label come from ``league.rates`` (success leaves
out NA success; sack and INT use all plays).

Raw chaos value = chaos success rate - scripted success rate. NA if either label
has no plays with a success value.

Shrinkage (empirical Bayes, beta-binomial on each rate). For chaos success and
scripted success separately, a Beta(alpha, beta) prior is fitted across QBs by
maximum marginal likelihood: maximize the sum over QBs of
``betaln(k + alpha, n - k + beta) - betaln(alpha, beta)`` (k successes in n plays).
Each QB's shrunk rate is the posterior mean ``(k + alpha) / (n + alpha + beta)``:
QBs with few plays move toward the prior mean, QBs with many plays stay near
their own rate. Shrunk chaos value = shrunk chaos success - shrunk scripted
success. The fitted priors go to ``config.QB_PRIOR_PATH``. Sack and INT rates
are not shrunk.

Minimum plays: ``meets_min`` = at least ``config.QB_MIN_PLAYS`` chaos plays AND as
many scripted plays. Candidates are printed: play-count quantiles, and each
prior's strength (alpha + beta), the play count at which a QB's own plays carry
half the weight of the shrunk rate.

Quadrant (every QB; the visualiser filters on ``meets_min``):
- x = chaos rate, split at the league chaos rate (all chaos plays / all
  pressured plays). At or above the split = often.
- y = shrunk chaos value, split at the league chaos value (pooled chaos success
  - pooled scripted success). Above = better off script than the league average.
  Not split at 0: every QB's shrunk value is below 0, which left two corners empty.

Run: ``python -m src.qb_summary``
"""
from __future__ import annotations

import json

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from scipy.optimize import minimize
from scipy.special import betaln

from . import config, data
from .league import pressured_plays, rates
from .thresholds import SERIES, SURFACE, TEXT, TEXT_MUTED, _style

LABELS = ["chaos", "scripted"]
QUANTILES = [0.1, 0.25, 0.5, 0.75, 0.9]

# Plain-words corners, keyed by (chaos rate >= league, shrunk chaos value > league).
QUADRANTS = {
    (True, True): "Leaves the script often under pressure, and does better off script than the league average",
    (True, False): "Leaves the script often under pressure, and does worse off script than the league average",
    (False, True): "Rarely leaves the script, but does better off script than the league average",
    (False, False): "Rarely leaves the script, and does worse off script than the league average",
}

COLS = [
    "qbId", "name", "team", "pressured_plays", "chaos_plays", "scripted_plays", "chaos_rate",
    "chaos_success_plays", "chaos_successes", "chaos_success_rate",
    "scripted_success_plays", "scripted_successes", "scripted_success_rate",
    "chaos_sacks", "chaos_sack_rate", "chaos_ints", "chaos_int_rate",
    "scripted_sacks", "scripted_sack_rate", "scripted_ints", "scripted_int_rate",
    "raw_chaos_value", "shrunk_chaos_success", "shrunk_scripted_success", "shrunk_chaos_value",
    "meets_min", "quadrant",
]


def load_pressured() -> pd.DataFrame:
    labeled = pd.read_csv(config.PLAY_LABELS_PATH, dtype={"qbId": config.ID_DTYPE})
    players = data.load_players()[["nflId", "officialPosition", "displayName"]]
    labeled = labeled.merge(players.rename(columns={"nflId": "qbId"}), on="qbId", how="left")
    not_qb = labeled["officialPosition"] != config.QB_POSITION
    print(f"labelled plays: {len(labeled)}")
    print(f"dropped (passer not {config.QB_POSITION}): {not_qb.sum()} plays, "
          f"{labeled.loc[not_qb, 'qbId'].nunique()} passers,",
          labeled.loc[not_qb, "officialPosition"].value_counts(dropna=False).to_dict())
    return pressured_plays(labeled[~not_qb])


def per_qb(p: pd.DataFrame) -> pd.DataFrame:
    """One row per QB: counts and raw rates per label, chaos rate, raw chaos value."""
    p = p.assign(success=p["success"].astype("boolean"))
    by_label = rates(p, ["qbId", "label"])
    by_label["successes"] = p.groupby(["qbId", "label"])["success"].sum()
    wide = by_label.unstack("label")
    wide.columns = [f"{label}_{col}" for col, label in wide.columns]
    counts = [c for c in wide if not c.endswith("_rate")]
    wide[counts] = wide[counts].fillna(0).astype(int)  # QB with no plays of a label

    qb = p.groupby("qbId").agg(
        name=("displayName", "first"),
        team=("possessionTeam", lambda s: s.mode().iloc[0]),
        n_teams=("possessionTeam", "nunique"),
        pressured_plays=("label", "size"),
    )
    print(f"\nQBs with pressured plays: {len(qb)}")
    print(f"  QBs with more than one team (most common team kept): {(qb['n_teams'] > 1).sum()}")
    for label in LABELS:
        print(f"  QBs with 0 {label} plays: {(wide[f'{label}_plays'] == 0).sum()}")
    qb = qb.drop(columns="n_teams").join(wide)
    qb["chaos_rate"] = qb["chaos_plays"] / qb["pressured_plays"]
    qb["raw_chaos_value"] = qb["chaos_success_rate"] - qb["scripted_success_rate"]
    print(f"  QBs with raw chaos value NA: {qb['raw_chaos_value'].isna().sum()}")
    return qb.reset_index()


def fit_prior(k: pd.Series, n: pd.Series) -> dict:
    """Beta(alpha, beta) prior by maximum marginal likelihood of the beta-binomial."""
    use = n > 0
    k, n = k[use].to_numpy(float), n[use].to_numpy(float)

    def neg_loglik(log_ab):
        a, b = np.exp(log_ab)
        return -(betaln(k + a, n - k + b) - betaln(a, b)).sum()

    pooled = k.sum() / n.sum()
    fit = minimize(neg_loglik, np.log([pooled, 1 - pooled]), method="Nelder-Mead")
    assert fit.success, f"prior fit did not converge: {fit.message}"
    a, b = np.exp(fit.x)
    return {"alpha": float(a), "beta": float(b), "prior_mean": float(a / (a + b)),
            "prior_strength": float(a + b), "qbs": int(use.sum()), "pooled_rate": float(pooled)}


def shrink(qb: pd.DataFrame) -> dict:
    """Fit one prior per label and add the shrunk rates and shrunk chaos value."""
    priors = {}
    print("\n[shrinkage] beta-binomial prior per rate:")
    for label in LABELS:
        k, n = qb[f"{label}_successes"], qb[f"{label}_success_plays"]
        pr = fit_prior(k, n)
        priors[f"{label}_success"] = pr
        qb[f"shrunk_{label}_success"] = (k + pr["alpha"]) / (n + pr["prior_strength"])
        print(f"  {label} success: alpha {pr['alpha']:.3f}, beta {pr['beta']:.3f}, "
              f"prior mean {pr['prior_mean']:.3f}, strength {pr['prior_strength']:.2f} "
              f"(QBs fitted: {pr['qbs']}, pooled rate {pr['pooled_rate']:.3f})")
    qb["shrunk_chaos_value"] = qb["shrunk_chaos_success"] - qb["shrunk_scripted_success"]
    return priors


def min_play_candidates(qb: pd.DataFrame, priors: dict) -> None:
    print("\n[minimum plays] plays per QB, quantiles:")
    for label in LABELS:
        print(f"  {label}:", qb[f"{label}_plays"].quantile(QUANTILES).to_dict())
        print(f"  {label} prior strength (own plays = half the weight): "
              f"{priors[f'{label}_success']['prior_strength']:.2f}")
    if config.QB_MIN_PLAYS is None:
        print("  QB_MIN_PLAYS not set: meets_min left NA")
        qb["meets_min"] = pd.NA
        return
    qb["meets_min"] = (qb["chaos_plays"] >= config.QB_MIN_PLAYS) & (qb["scripted_plays"] >= config.QB_MIN_PLAYS)
    print(f"  QB_MIN_PLAYS = {config.QB_MIN_PLAYS}: {qb['meets_min'].sum()} of {len(qb)} QBs qualify")


def plot_counts(qb: pd.DataFrame, priors: dict, path) -> None:
    fig, ax = plt.subplots(figsize=(8, 4.5), facecolor=SURFACE)
    top = max(qb["chaos_plays"].max(), qb["scripted_plays"].max())
    bins = np.arange(0, top + 5, 5)
    for color, label in zip(SERIES, LABELS):
        ax.hist(qb[f"{label}_plays"], bins=bins, histtype="step", linewidth=2,
                color=color, label=f"{label} plays (QBs={len(qb)})")
        s = round(priors[f"{label}_success"]["prior_strength"], 2)
        ax.axvline(s, color=color, linestyle="--", linewidth=1)
        ax.annotate(f"{label} prior strength: {s}", (s, 1), xycoords=("data", "axes fraction"),
                    xytext=(4, -12 if label == "chaos" else -24), textcoords="offset points",
                    color=TEXT_MUTED, fontsize=8)
    _style(ax, "Pressured chaos and scripted plays per QB", "plays per QB")
    ax.set_ylabel("QBs", color=TEXT_MUTED)
    ax.legend(frameon=False, labelcolor=TEXT, fontsize=9, loc="center right")
    fig.tight_layout()
    fig.savefig(path, dpi=150, facecolor=SURFACE)
    plt.close(fig)
    print(f"saved {path}")


def league_values(qb: pd.DataFrame) -> dict:
    rate = {label: qb[f"{label}_successes"].sum() / qb[f"{label}_success_plays"].sum() for label in LABELS}
    out = {
        "chaos_rate": float(qb["chaos_plays"].sum() / qb["pressured_plays"].sum()),
        "chaos_success_rate": float(rate["chaos"]),
        "scripted_success_rate": float(rate["scripted"]),
        "chaos_value": float(rate["chaos"] - rate["scripted"]),
    }
    print(f"\nleague (pooled, QB pressured plays): chaos rate {out['chaos_rate']:.3f}, "
          f"chaos success {out['chaos_success_rate']:.3f}, scripted success "
          f"{out['scripted_success_rate']:.3f}, chaos value {out['chaos_value']:.3f}")
    return out


def assign_quadrants(qb: pd.DataFrame, league: dict) -> None:
    often = qb["chaos_rate"] >= league["chaos_rate"]
    better = qb["shrunk_chaos_value"] > league["chaos_value"]
    qb["quadrant"] = [QUADRANTS[(o, b)] for o, b in zip(often, better)]
    print(f"\nquadrants (x split: league chaos rate {league['chaos_rate']:.3f}, "
          f"y split: league chaos value {league['chaos_value']:.3f}):")
    print("  all QBs:", qb["quadrant"].value_counts().to_dict())
    if config.QB_MIN_PLAYS is not None:
        print("  QBs meeting the minimum:", qb.loc[qb["meets_min"], "quadrant"].value_counts().to_dict())


def build_qb_summary():
    p = load_pressured()
    qb = per_qb(p)
    priors = shrink(qb)
    min_play_candidates(qb, priors)
    league = league_values(qb)
    assign_quadrants(qb, league)

    assert (qb["chaos_plays"] + qb["scripted_plays"] == qb["pressured_plays"]).all()
    assert qb["pressured_plays"].sum() == len(p)

    qb = qb[COLS].sort_values("shrunk_chaos_value", ascending=False).reset_index(drop=True)
    print("\nper QB (sorted by shrunk chaos value):")
    show = ["name", "team", "pressured_plays", "chaos_plays", "scripted_plays", "chaos_rate",
            "raw_chaos_value", "shrunk_chaos_value", "meets_min"]
    print(qb[show].round(3).to_string(index=False))

    meta = {
        "priors": priors,
        "league": league,
        "quadrant_splits": {"chaos_rate": league["chaos_rate"], "chaos_value": league["chaos_value"]},
        "min_plays": config.QB_MIN_PLAYS,
    }
    return qb, meta, priors


def main() -> None:
    qb, meta, priors = build_qb_summary()
    config.PLOTS_DIR.mkdir(parents=True, exist_ok=True)
    plot_counts(qb, priors, config.PLOTS_DIR / "qb_counts.png")
    qb.to_csv(config.QB_SUMMARY_PATH, index=False)
    config.QB_PRIOR_PATH.write_text(json.dumps(meta, indent=2))
    print(f"saved {config.QB_SUMMARY_PATH} ({len(qb)} rows), {config.QB_PRIOR_PATH}")


if __name__ == "__main__":
    main()
