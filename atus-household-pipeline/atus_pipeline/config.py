"""Central place for every constant and analytic definition.

Keeping definitions here (rather than scattered through the code) means a
reviewer can see in one place what "child", "adult" and "household member"
mean, and changing a definition re-runs the whole pipeline consistently.
"""

# --- Source files (BLS multi-year ATUS microdata, 2003-2025) ---------------
# Verify names against https://www.bls.gov/tus/data/datafiles-0325.htm if BLS
# publishes a newer span; only YEAR_SPAN should need to change.
BLS_BASE_URL = "https://www.bls.gov/tus/datafiles"
YEAR_SPAN = "0325"
ROSTER_ZIP = f"atusrost-{YEAR_SPAN}.zip"
RESPONDENT_ZIP = f"atusresp-{YEAR_SPAN}.zip"

# BLS rejects requests that do not send a browser-like User-Agent.
USER_AGENT = "Mozilla/5.0 (compatible; atus-household-pipeline/1.0)"

# --- Columns we keep -------------------------------------------------------
ROSTER_COLS = ["TUCASEID", "TULINENO", "TEAGE", "TESEX", "TERRP"]
RESPONDENT_COLS = ["TUCASEID", "TUFINLWGT"]

# --- Analytic definitions --------------------------------------------------
# The Roster file lists household members AND the respondent's own
# non-household children under 18. TERRP (relationship to reference person)
# code 40 marks the latter; they must not count toward household composition.
# Confirm against the ATUS data dictionary for the file vintage you use.
NONHOUSEHOLD_CHILD_TERRP = 40

# Child: age <= CHILD_MAX_AGE. Adult: age > CHILD_MAX_AGE. Using one threshold
# for both guarantees every household member is exactly one of the two.
CHILD_MAX_AGE = 17

SEX_FEMALE = 2
VALID_SEX = (1, 2)

# Plausibility bounds for TEAGE (ATUS top-codes age, so the upper bound is loose).
AGE_MIN, AGE_MAX = 0, 120
# ATUS respondents are age 15+.
RESPONDENT_MIN_AGE = 15
