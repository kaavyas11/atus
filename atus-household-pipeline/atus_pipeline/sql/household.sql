-- One row per ATUS household, with composition counts and the survey weight.
--
-- Definitions (see config.py):
--   * Non-household children (TERRP = {nonhh_code}) are excluded from members.
--   * child = TEAGE <= {child_max_age};  adult = TEAGE > {child_max_age}.
--   * weight = the respondent's final weight (TUFINLWGT). ATUS samples one
--     person per household, so this weights *people* (and hence the
--     households they live in as seen by a randomly chosen person 15+).
DROP TABLE IF EXISTS household;

CREATE TABLE household AS
SELECT
    m.TUCASEID                                                       AS case_id,
    CAST(substr(m.TUCASEID, 1, 4) AS INTEGER)                        AS year,
    COUNT(*)                                                         AS n_members,
    SUM(CASE WHEN m.TEAGE <= {child_max_age} THEN 1 ELSE 0 END)      AS n_children,
    SUM(CASE WHEN m.TEAGE >  {child_max_age} THEN 1 ELSE 0 END)      AS n_adults,
    SUM(CASE WHEN m.TESEX = {female} THEN 1 ELSE 0 END)              AS n_women,
    SUM(CASE WHEN m.TEAGE > {child_max_age}
              AND m.TESEX = {female} THEN 1 ELSE 0 END)              AS n_adult_women,
    MAX(r.TUFINLWGT)                                                 AS weight
FROM raw_roster      AS m
JOIN raw_respondent  AS r ON r.TUCASEID = m.TUCASEID
WHERE m.TERRP <> {nonhh_code}
GROUP BY m.TUCASEID;

CREATE UNIQUE INDEX idx_household_case ON household (case_id);
