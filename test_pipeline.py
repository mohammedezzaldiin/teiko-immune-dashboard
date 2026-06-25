"""
test_pipeline.py — sanity/integration tests.

Run with:  pytest -q   (or `make test`)

Builds a throwaway DB from the current cell-count.csv in a temp location and
checks the core invariants of each part. These are guards against regressions,
not a full validation of the (synthetic) numbers.
"""
import os
import tempfile

import pandas as pd
import pytest

import db
import load_data
import analysis


@pytest.fixture(scope="module")
def conn():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "test.db")
    load_data.load(csv_path=db.CSV_PATH, db_path=db_path)
    c = db.get_connection(db_path)
    yield c
    c.close()


def test_tables_populated(conn):
    for table in ["projects", "subjects", "samples", "cell_counts"]:
        assert conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0] > 0


def test_part2_percentages_sum_to_100(conn):
    freq = analysis.frequency_table(conn)
    per_sample = freq.groupby("sample")["percentage"].sum()
    # every sample's population percentages must add up to ~100% (within rounding)
    assert ((per_sample - 100).abs() < 1e-2).all()


def test_part2_columns(conn):
    freq = analysis.frequency_table(conn)
    assert list(freq.columns) == ["sample", "total_count", "population", "count", "percentage"]


def test_part3_only_target_cohort(conn):
    rfreq = analysis.responder_frequencies(conn)
    # responder column must only contain yes/no (PBMC melanoma miraclib)
    assert set(rfreq["response"].unique()) <= {"yes", "no"}


def test_part3_stats_have_pvalues(conn):
    rfreq = analysis.responder_frequencies(conn)
    rstats = analysis.responder_stats(rfreq)
    if not rstats.empty:
        assert rstats["p_value"].between(0, 1).all()
        assert rstats["q_value"].between(0, 1).all()


def test_part4_baseline_filter(conn):
    subset = analysis.baseline_subset(conn)
    if not subset.empty:
        assert (subset["time_from_treatment_start"] == 0).all()
        assert subset["sample_type"].str.upper().eq("PBMC").all()
        assert subset["condition"].str.lower().eq("melanoma").all()
        assert subset["treatment"].str.lower().eq("miraclib").all()


def test_part4_avg_bcells_is_number_or_none(conn):
    val = analysis.avg_bcells_male_responders_baseline(conn)
    assert val is None or isinstance(val, float)
