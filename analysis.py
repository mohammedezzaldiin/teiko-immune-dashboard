#!/usr/bin/env python3
"""
analysis.py — Parts 2, 3, 4.

Importable functions (used by the dashboard) + a main() that writes every
required output table/plot to ./outputs and prints a readable report.

Run with:  python analysis.py
"""
from __future__ import annotations

import os

import matplotlib
matplotlib.use("Agg")  # headless / no display needed
import matplotlib.pyplot as plt
import pandas as pd
from scipy import stats

import db

OUTDIR = os.path.join(os.path.dirname(__file__), "outputs")


# ---------------------------------------------------------------------------
# Part 2 — relative frequency table
# ---------------------------------------------------------------------------
def frequency_table(conn) -> pd.DataFrame:
    """
    One row per (sample, population) with total_count, count, percentage.

    Percentage = count / (sum of all populations for that sample) * 100.
    Computed in SQL with a window function so it scales to large tables.
    """
    query = """
        SELECT
            c.sample_id                                              AS sample,
            SUM(c.count) OVER (PARTITION BY c.sample_id)             AS total_count,
            c.population                                             AS population,
            c.count                                                  AS count,
            ROUND(100.0 * c.count
                  / SUM(c.count) OVER (PARTITION BY c.sample_id), 4) AS percentage
        FROM cell_counts c
        ORDER BY c.sample_id, c.population;
    """
    return pd.read_sql_query(query, conn)


# ---------------------------------------------------------------------------
# Part 3 — responders vs non-responders (melanoma + miraclib + PBMC)
# ---------------------------------------------------------------------------
def responder_frequencies(conn) -> pd.DataFrame:
    """
    Per-sample population percentages for melanoma patients on miraclib,
    PBMC samples only, annotated with response (yes/no).
    """
    query = """
        WITH totals AS (
            SELECT sample_id, SUM(count) AS total
            FROM cell_counts GROUP BY sample_id
        )
        SELECT
            s.sample_id                              AS sample,
            sub.response                             AS response,
            c.population                             AS population,
            100.0 * c.count / t.total                AS percentage
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        JOIN cell_counts c ON c.sample_id = s.sample_id
        JOIN totals t      ON t.sample_id = s.sample_id
        WHERE LOWER(sub.condition) = 'melanoma'
          AND LOWER(sub.treatment) = 'miraclib'
          AND UPPER(s.sample_type) = 'PBMC'
          AND sub.response IN ('yes', 'no');
    """
    return pd.read_sql_query(query, conn)


def responder_stats(freq: pd.DataFrame) -> pd.DataFrame:
    """
    Mann-Whitney U (two-sided) per population comparing responders vs
    non-responders, with Benjamini-Hochberg FDR correction across populations.
    """
    rows = []
    for pop, grp in freq.groupby("population"):
        r = grp.loc[grp.response == "yes", "percentage"].values
        nr = grp.loc[grp.response == "no", "percentage"].values
        if len(r) < 1 or len(nr) < 1:
            continue
        try:
            u, p = stats.mannwhitneyu(r, nr, alternative="two-sided")
        except ValueError:
            u, p = float("nan"), float("nan")
        rows.append({
            "population": pop,
            "n_responder": len(r),
            "n_non_responder": len(nr),
            "median_responder_pct": round(float(pd.Series(r).median()), 3),
            "median_non_responder_pct": round(float(pd.Series(nr).median()), 3),
            "u_statistic": float(u),
            "p_value": float(p),
        })
    out = pd.DataFrame(rows)
    if out.empty:
        return out

    # Benjamini-Hochberg FDR correction across the populations tested.
    out = out.sort_values("p_value").reset_index(drop=True)
    m = len(out)
    out["rank"] = out.index + 1
    out["q_value"] = (out["p_value"] * m / out["rank"]).clip(upper=1.0)
    # enforce monotonicity of BH q-values
    out["q_value"] = out["q_value"][::-1].cummin()[::-1].round(4)
    out["p_value"] = out["p_value"].round(4)
    out["significant_q<0.05"] = out["q_value"] < 0.05
    return out.drop(columns="rank").sort_values("p_value").reset_index(drop=True)


def boxplot(freq: pd.DataFrame, path: str) -> None:
    """Boxplot of responder vs non-responder percentages, one panel per population."""
    pops = sorted(freq["population"].unique())
    n = len(pops)
    fig, axes = plt.subplots(1, n, figsize=(3.2 * max(n, 1), 4.2), sharey=False)
    if n == 1:
        axes = [axes]
    colors = {"yes": "#2a9d8f", "no": "#e76f51"}
    for ax, pop in zip(axes, pops):
        sub = freq[freq.population == pop]
        data, labels, box_colors = [], [], []
        for resp, label in [("yes", "Responder"), ("no", "Non-resp.")]:
            vals = sub.loc[sub.response == resp, "percentage"].values
            if len(vals):
                data.append(vals)
                labels.append(f"{label}\n(n={len(vals)})")
                box_colors.append(colors[resp])
        if not data:
            continue
        bp = ax.boxplot(data, patch_artist=True, widths=0.55)
        ax.set_xticks(range(1, len(labels) + 1))
        ax.set_xticklabels(labels)
        for patch, c in zip(bp["boxes"], box_colors):
            patch.set_facecolor(c)
            patch.set_alpha(0.6)
        # overlay jittered individual points for transparency on small n
        rng = __import__("numpy").random.default_rng(0)
        for i, vals in enumerate(data, start=1):
            xs = i + rng.uniform(-0.08, 0.08, size=len(vals))
            ax.scatter(xs, vals, s=16, color="#264653", zorder=3, alpha=0.75)
        ax.set_title(pop, fontsize=11)
        ax.set_ylabel("Relative frequency (%)")
        ax.grid(axis="y", alpha=0.25)
    fig.suptitle("Melanoma · miraclib · PBMC — responders vs non-responders", fontsize=12)
    fig.tight_layout(rect=[0, 0, 1, 0.95])
    fig.savefig(path, dpi=150)
    plt.close(fig)


# ---------------------------------------------------------------------------
# Part 4 — baseline subset (melanoma PBMC, miraclib, time = 0)
# ---------------------------------------------------------------------------
def baseline_subset(conn) -> pd.DataFrame:
    """Melanoma PBMC samples at baseline (t=0) from miraclib-treated patients."""
    query = """
        SELECT
            s.sample_id, s.sample_type, s.time_from_treatment_start,
            sub.subject_id, p.project_name AS project,
            sub.condition, sub.sex, sub.response, sub.treatment
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        JOIN projects p   ON p.project_id   = sub.project_id
        WHERE LOWER(sub.condition) = 'melanoma'
          AND LOWER(sub.treatment) = 'miraclib'
          AND UPPER(s.sample_type) = 'PBMC'
          AND s.time_from_treatment_start = 0;
    """
    return pd.read_sql_query(query, conn)


def baseline_breakdowns(subset: pd.DataFrame):
    """Return (samples_per_project, subjects_by_response, subjects_by_sex)."""
    per_project = (
        subset.groupby("project").size().reset_index(name="n_samples")
        if not subset.empty else pd.DataFrame(columns=["project", "n_samples"])
    )
    subj = subset.drop_duplicates("subject_id")
    by_response = (
        subj.groupby("response").size().reset_index(name="n_subjects")
        if not subj.empty else pd.DataFrame(columns=["response", "n_subjects"])
    )
    by_sex = (
        subj.groupby("sex").size().reset_index(name="n_subjects")
        if not subj.empty else pd.DataFrame(columns=["sex", "n_subjects"])
    )
    return per_project, by_response, by_sex


def avg_bcells_male_responders_baseline(conn) -> float | None:
    """Average B-cell COUNT for melanoma males, responders, at time=0 (PBMC, miraclib)."""
    query = """
        SELECT AVG(c.count) AS avg_b
        FROM samples s
        JOIN subjects sub ON sub.subject_id = s.subject_id
        JOIN cell_counts c ON c.sample_id = s.sample_id
        WHERE LOWER(sub.condition) = 'melanoma'
          AND LOWER(sub.treatment) = 'miraclib'
          AND UPPER(s.sample_type) = 'PBMC'
          AND s.time_from_treatment_start = 0
          AND UPPER(sub.sex) = 'M'
          AND LOWER(sub.response) = 'yes'
          AND c.population = 'b_cell';
    """
    val = conn.execute(query).fetchone()[0]
    return None if val is None else round(float(val), 2)


# ---------------------------------------------------------------------------
# main — write all outputs
# ---------------------------------------------------------------------------
def main() -> None:
    os.makedirs(OUTDIR, exist_ok=True)
    conn = db.get_connection()

    # Part 2
    freq = frequency_table(conn)
    freq.to_csv(os.path.join(OUTDIR, "part2_frequency_table.csv"), index=False)
    print(f"[Part 2] frequency table: {len(freq)} rows "
          f"({freq['sample'].nunique()} samples) -> outputs/part2_frequency_table.csv")

    # Part 3
    rfreq = responder_frequencies(conn)
    rstats = responder_stats(rfreq)
    rfreq.to_csv(os.path.join(OUTDIR, "part3_responder_frequencies.csv"), index=False)
    rstats.to_csv(os.path.join(OUTDIR, "part3_stats.csv"), index=False)
    boxplot(rfreq, os.path.join(OUTDIR, "part3_boxplots.png"))
    print(f"\n[Part 3] melanoma/miraclib/PBMC samples: {rfreq['sample'].nunique()} "
          f"(responders {rfreq[rfreq.response=='yes']['sample'].nunique()}, "
          f"non {rfreq[rfreq.response=='no']['sample'].nunique()})")
    if not rstats.empty:
        print(rstats.to_string(index=False))
        sig = rstats.loc[rstats["significant_q<0.05"], "population"].tolist()
        print("  Significant after FDR (q<0.05):", sig if sig else "none")
    print("  -> outputs/part3_stats.csv, outputs/part3_boxplots.png")

    # Part 4
    subset = baseline_subset(conn)
    per_project, by_response, by_sex = baseline_breakdowns(subset)
    subset.to_csv(os.path.join(OUTDIR, "part4_baseline_samples.csv"), index=False)
    per_project.to_csv(os.path.join(OUTDIR, "part4_samples_per_project.csv"), index=False)
    by_response.to_csv(os.path.join(OUTDIR, "part4_subjects_by_response.csv"), index=False)
    by_sex.to_csv(os.path.join(OUTDIR, "part4_subjects_by_sex.csv"), index=False)
    avg_b = avg_bcells_male_responders_baseline(conn)

    print(f"\n[Part 4] baseline melanoma/miraclib/PBMC samples: {len(subset)}")
    print("  samples per project:\n   ", per_project.to_dict("records"))
    print("  subjects by response:", by_response.to_dict("records"))
    print("  subjects by sex:     ", by_sex.to_dict("records"))
    print(f"  avg B-cell count (melanoma males, responders, t=0): "
          f"{'N/A' if avg_b is None else f'{avg_b:.2f}'}")
    print("  -> outputs/part4_*.csv")

    conn.close()


if __name__ == "__main__":
    main()
