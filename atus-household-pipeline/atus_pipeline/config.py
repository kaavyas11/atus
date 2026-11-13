"""All definitions are here because it is easier to keep track of this way.
"""

# --- Source files (BLS multi-year ATUS microdata, 2003-2025) ---------------

YEAR_SPAN = "0325"
ROSTER_ZIP = f"atusrost-{YEAR_SPAN}.zip"
RESPONDENT_ZIP = f"atusresp-{YEAR_SPAN}.zip"

USER_AGENT = "Mozilla/5.0 (compatible; atus-household-pipeline/1.0)"

# --- Columns we keep -------------------------------------------------------
ROSTER_COLS = ["TUCASEID", "TULINENO", "TEAGE", "TESEX", "TERRP"]
RESPONDENT_COLS = ["TUCASEID", "TUFINLWGT"]

# --- Analytic definitions --------------------------------------------------

# code 40 marks the latter; they must not count toward household composition.

NONHOUSEHOLD_CHILD_TERRP = 40

CHILD_MAX_AGE = 17

SEX_FEMALE = 2
VALID_SEX = (1, 2)

# Plausibility bounds for TEAGE (ATUS top-codes age, so the upper bound is loose).
AGE_MIN, AGE_MAX = 0, 120
# ATUS respondents are age 15+.
RESPONDENT_MIN_AGE = 15
