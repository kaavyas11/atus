"""Unit tests on a tiny synthetic ATUS fixture whose answers are computable by hand.

Run with:  python -m unittest discover -s tests   (or: python -m pytest)
"""
import sqlite3
import unittest

import numpy as np
import pandas as pd

from atus_pipeline import analyze, load, validate

# (TUCASEID, TULINENO, TEAGE, TESEX, TERRP)   sex: 1=M 2=F ; TERRP 40 = non-household child
ROSTER = [
    # A (2003): woman 30 + child 5                        -> single adult w/ child, female
    ("20030000000001", 1, 30, 2, 18), ("20030000000001", 2, 5, 1, 25),
    # B (2003): man 40 alone
    ("20030000000002", 1, 40, 1, 19),
    # C (2004): F35 + M37 + child 10, plus a NON-household child 8 (must be ignored)
    ("20040000000003", 1, 35, 2, 18), ("20040000000003", 2, 37, 1, 20),
    ("20040000000003", 3, 10, 2, 25), ("20040000000003", 4, 8, 1, 40),
    # D (2004): woman 70 alone
    ("20040000000004", 1, 70, 2, 19),
    # E (2004): M45 + child aged 17 (child) + person aged 18 (adult, boundary)
    ("20040000000005", 1, 45, 1, 18), ("20040000000005", 2, 17, 2, 25), ("20040000000005", 3, 18, 1, 25),
]
WEIGHTS = {"20030000000001": 1.0, "20030000000002": 2.0,
           "20040000000003": 3.0, "20040000000004": 4.0, "20040000000005": 5.0}


def make_db(roster=ROSTER, weights=WEIGHTS) -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    r = pd.DataFrame(roster, columns=["TUCASEID", "TULINENO", "TEAGE", "TESEX", "TERRP"])
    p = pd.DataFrame({"TUCASEID": list(weights), "TUFINLWGT": list(weights.values())})
    load.load_raw(conn, r, p)
    load.build_household(conn, child_max_age=17)
    return conn


class HouseholdBuildTests(unittest.TestCase):
    def setUp(self):
        self.h = pd.read_sql("SELECT * FROM household", make_db()).set_index("case_id")

    def test_one_row_per_household(self):
        self.assertEqual(len(self.h), 5)

    def test_nonhousehold_child_excluded(self):
        c = self.h.loc["20040000000003"]
        self.assertEqual((c.n_members, c.n_children, c.n_adults), (3, 1, 2))

    def test_age_boundary_17_child_18_adult(self):
        e = self.h.loc["20040000000005"]
        self.assertEqual((e.n_children, e.n_adults), (1, 2))

    def test_year_parsed_from_case_id(self):
        self.assertEqual(self.h.loc["20030000000001", "year"], 2003)


class ValidationTests(unittest.TestCase):
    def test_clean_data_passes(self):
        checks = validate.validate(make_db())
        self.assertTrue(all(c.passed for c in checks if c.severity == "error"))

    def test_duplicate_roster_key_fails(self):
        bad = ROSTER + [("20030000000002", 1, 41, 1, 19)]
        with self.assertRaises(validate.ValidationError):
            validate.validate(make_db(roster=bad))

    def test_bad_sex_code_fails(self):
        bad = [row if row[:2] != ("20030000000002", 1) else (*row[:3], 9, row[4]) for row in ROSTER]
        with self.assertRaises(validate.ValidationError):
            validate.validate(make_db(roster=bad))

    def test_nonpositive_weight_fails(self):
        bad_w = {**WEIGHTS, "20030000000002": 0.0}
        with self.assertRaises(validate.ValidationError):
            validate.validate(make_db(weights=bad_w))


class EstimateTests(unittest.TestCase):
    def setUp(self):
        self.h = analyze.read_households(make_db())
        self.est = analyze.estimate(self.h, n_boot=200, seed=1).set_index("estimate")

    def test_weights_normalised_within_year(self):
        self.assertTrue(np.allclose(self.h.groupby("year")["w"].sum(), 1.0))

    def test_weighted_estimates_match_hand_calculation(self):
        # Years weighted equally. 2003: A=1/3, B=2/3. 2004: C=3/12, D=4/12, E=5/12.
        e = self.est["weighted"]
        self.assertAlmostEqual(e["share_households_with_child"], 0.5)           # A,C,E
        self.assertAlmostEqual(e["share_one_adult_households"], 4 / 6)          # A,B,D
        self.assertAlmostEqual(e["share_living_alone_who_are_women"], 1 / 3)    # D / (B+D)
        self.assertAlmostEqual(e["share_single_adult_with_child_who_are_women"], 1.0)  # only A

    def test_unweighted_estimates(self):
        self.assertAlmostEqual(self.est.loc["share_households_with_child", "unweighted"], 3 / 5)

    def test_household_sizes_sum_to_one(self):
        sizes = self.est[self.est.index.str.startswith("household_size_")]["weighted"]
        self.assertAlmostEqual(sizes.sum(), 1.0)

    def test_ci_brackets_point_estimate_and_is_reproducible(self):
        e = self.est
        self.assertTrue(((e.ci_low <= e.weighted + 1e-9) | e.ci_low.isna()).all())
        again = analyze.estimate(self.h, n_boot=200, seed=1).set_index("estimate")
        pd.testing.assert_frame_equal(e, again)


if __name__ == "__main__":
    unittest.main()
