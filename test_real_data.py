"""
test_real_data.py — ground-truth regression tests.

These lock in the exact, externally-verified answers for the real
cell-count.csv (10,500 samples). They catch any regression that would silently
change a reported number.

If a *different* dataset is in place (e.g. the synthetic stand-in), the whole
module skips itself, so it never produces false failures — pair it with
test_pipeline.py, which holds the data-agnostic invariants.
"""
import os
import tempfile

import pandas as pd
import pytest

import db
import load_data
import analysis

# The real dataset has exactly 10,500 sample rows. Gate on that.
EXPECTED_ROWS = 10500


def _row_count(path):
    try:
        return len(pd.read_csv(path))
    except Exception:
        return -1


pytestmark = pytest.mark.skipif(
    _row_count(db.CSV_PATH) != EXPECTED_ROWS,
    reason="real cell-count.csv (10,500 rows) not present; skipping ground-truth tests",
)


@pytest.fixture(scope="module")
def conn():
    tmp = tempfile.mkdtemp()
    db_path = os.path.join(tmp, "real.db")
    load_data.load(csv_path=db.CSV_PATH, db_path=db_path)
    c = db.get_connection(db_path)
    yield c
    c.close()


def test_table_row_counts(conn):
    counts = {t: conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
              for t in ["projects", "subjects", "samples", "cell_counts"]}
    assert counts == {"projects": 3, "subjects": 3500,
                      "samples": 10500, "cell_counts": 52500}


def test_part2_row_count(conn):
    # 10,500 samples x 5 populations
    assert len(analysis.frequency_table(conn)) == 52500


def test_part3_cohort_sizes(conn):
    rf = analysis.responder_frequencies(conn)
    assert rf[rf.response == "yes"]["sample"].nunique() == 993
    assert rf[rf.response == "no"]["sample"].nunique() == 975


def test_part4_baseline_subset(conn):
    subset = analysis.baseline_subset(conn)
    assert len(subset) == 656

    per_project, by_response, by_sex = analysis.baseline_breakdowns(subset)
    assert dict(zip(per_project.project, per_project.n_samples)) == {"prj1": 384, "prj3": 272}
    assert dict(zip(by_response.response, by_response.n_subjects)) == {"no": 325, "yes": 331}
    assert dict(zip(by_sex.sex, by_sex.n_subjects)) == {"F": 312, "M": 344}


def test_part4_avg_bcells_headline(conn):
    # The Part 4 headline answer: melanoma males, responders, t=0.
    assert analysis.avg_bcells_male_responders_baseline(conn) == 10401.28
