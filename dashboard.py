#!/usr/bin/env python3
"""
dashboard.py — interactive dashboard (Streamlit).

Run with:  streamlit run dashboard.py     (or `make dashboard`)

If teiko.db is missing, it is built automatically from cell-count.csv so the
dashboard works on a fresh checkout.
"""
from __future__ import annotations

import os

import pandas as pd
import plotly.express as px
import streamlit as st

import db
import analysis
import load_data

st.set_page_config(page_title="Teiko · Immune Profiling Dashboard", layout="wide")


@st.cache_resource
def get_conn():
    if not os.path.exists(db.DB_PATH):
        load_data.load()
    return db.get_connection()


@st.cache_data
def cached_frequency():
    return analysis.frequency_table(get_conn())


@st.cache_data
def cached_responder():
    f = analysis.responder_frequencies(get_conn())
    return f, analysis.responder_stats(f)


@st.cache_data
def cached_baseline():
    conn = get_conn()
    subset = analysis.baseline_subset(conn)
    return (subset, *analysis.baseline_breakdowns(subset),
            analysis.avg_bcells_male_responders_baseline(conn))


st.title("Immune Profiling Dashboard")
st.caption("Loblaw Bio · miraclib clinical trial — cell population analysis")

tab1, tab2, tab3, tab4 = st.tabs(
    ["Overview", "Part 2 · Frequencies", "Part 3 · Response analysis", "Part 4 · Baseline subset"]
)

# --------------------------------------------------------------------------
# Overview
# --------------------------------------------------------------------------
with tab1:
    conn = get_conn()
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Projects", conn.execute("SELECT COUNT(*) FROM projects").fetchone()[0])
    c2.metric("Subjects", conn.execute("SELECT COUNT(*) FROM subjects").fetchone()[0])
    c3.metric("Samples", conn.execute("SELECT COUNT(*) FROM samples").fetchone()[0])
    c4.metric("Populations", conn.execute(
        "SELECT COUNT(DISTINCT population) FROM cell_counts").fetchone()[0])
    st.markdown(
        "This dashboard answers Bob's four questions: per-sample population "
        "**frequencies** (Part 2), a **responder vs non-responder** comparison for "
        "melanoma patients on miraclib (Part 3), and a **baseline subset** breakdown "
        "(Part 4). Use the tabs above."
    )
    samples_df = pd.read_sql_query(
        """SELECT p.project_name AS project, sub.condition, sub.treatment,
                  s.sample_type, s.time_from_treatment_start AS t, sub.response
           FROM samples s JOIN subjects sub ON sub.subject_id = s.subject_id
           JOIN projects p ON p.project_id = sub.project_id""", conn)
    st.subheader("Sample composition")
    cc1, cc2 = st.columns(2)
    cc1.plotly_chart(px.histogram(samples_df, x="condition", color="treatment",
                                  barmode="group", title="Samples by condition & treatment"),
                     use_container_width=True)
    cc2.plotly_chart(px.histogram(samples_df, x="sample_type", color="response",
                                  barmode="group", title="Samples by type & response"),
                     use_container_width=True)

# --------------------------------------------------------------------------
# Part 2 — frequencies
# --------------------------------------------------------------------------
with tab2:
    st.subheader("Relative frequency of each population per sample")
    freq = cached_frequency()
    samples = sorted(freq["sample"].unique())
    pick = st.multiselect("Filter samples (empty = all)", samples, default=[])
    view = freq[freq["sample"].isin(pick)] if pick else freq
    st.dataframe(view, use_container_width=True, height=420)
    st.download_button("Download table (CSV)", view.to_csv(index=False),
                       "part2_frequency_table.csv", "text/csv")
    if pick:
        st.plotly_chart(
            px.bar(view, x="sample", y="percentage", color="population",
                   title="Population composition (%) by sample", barmode="stack"),
            use_container_width=True)

# --------------------------------------------------------------------------
# Part 3 — response analysis
# --------------------------------------------------------------------------
with tab3:
    st.subheader("Responders vs non-responders — melanoma · miraclib · PBMC")
    rfreq, rstats = cached_responder()
    if rfreq.empty:
        st.info("No melanoma/miraclib/PBMC samples with response data in the current dataset.")
    else:
        nr = rfreq[rfreq.response == "yes"]["sample"].nunique()
        nn = rfreq[rfreq.response == "no"]["sample"].nunique()
        st.caption(f"{nr} responder samples · {nn} non-responder samples")
        fig = px.box(
            rfreq.replace({"response": {"yes": "Responder", "no": "Non-responder"}}),
            x="population", y="percentage", color="response", points="all",
            title="Relative frequency by population and response",
            color_discrete_map={"Responder": "#2a9d8f", "Non-responder": "#e76f51"},
        )
        fig.update_layout(yaxis_title="Relative frequency (%)", xaxis_title="")
        st.plotly_chart(fig, use_container_width=True)

        st.markdown("**Statistical test** — Mann–Whitney U (two-sided), "
                    "Benjamini–Hochberg FDR across populations.")
        st.dataframe(rstats, use_container_width=True)
        if not rstats.empty:
            sig = rstats.loc[rstats["significant_q<0.05"], "population"].tolist()
            raw = rstats.loc[rstats["p_value"] < 0.05, "population"].tolist()
            if sig:
                st.success(f"Significant after FDR correction (q<0.05): {', '.join(sig)}")
            elif raw:
                st.warning(f"Nominally significant (raw p<0.05) but not after FDR: "
                           f"{', '.join(raw)}. Larger n needed to confirm.")
            else:
                st.info("No population reaches significance in the current dataset.")

# --------------------------------------------------------------------------
# Part 4 — baseline subset
# --------------------------------------------------------------------------
with tab4:
    st.subheader("Baseline subset — melanoma · miraclib · PBMC · time = 0")
    subset, per_project, by_response, by_sex, avg_b = cached_baseline()
    st.metric("Avg B-cell count (melanoma males, responders, t=0)",
              "N/A" if avg_b is None else f"{avg_b:.2f}")
    if subset.empty:
        st.info("No samples match the baseline criteria in the current dataset.")
    else:
        d1, d2, d3 = st.columns(3)
        with d1:
            st.markdown("**Samples per project**")
            st.dataframe(per_project, use_container_width=True, hide_index=True)
        with d2:
            st.markdown("**Subjects by response**")
            st.dataframe(by_response, use_container_width=True, hide_index=True)
        with d3:
            st.markdown("**Subjects by sex**")
            st.dataframe(by_sex, use_container_width=True, hide_index=True)
        st.markdown("**Matching samples**")
        st.dataframe(subset, use_container_width=True)
