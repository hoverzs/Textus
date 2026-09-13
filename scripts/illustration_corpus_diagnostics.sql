-- Read-only diagnostics for the illustration corpus (illustrations.sqlite3).
--
-- WHY THIS FILE EXISTS: this Claude session audited illustration_engine's
-- retrieval pipeline but has NO access to the actual built database --
-- `illustrations.sqlite3` is gitignored (see `.gitignore`'s blanket
-- `*.sqlite3` rule; unlike the Greek/Hebrew lexicon runtime DBs, it has no
-- `!data/generated/illustrations.sqlite3` exception) and the raw source
-- text files under `data/raw/illustrations/` that `scripts/build_
-- illustration_database.py` needs to rebuild it are not present in this
-- checkout either. Every number in the retrieval module's own comments
-- (e.g. "the real 157-unit QA-passed corpus") is a snapshot from a PAST
-- audit's local machine, not something this session could re-verify.
--
-- Run this against your actual copy, e.g.:
--   sqlite3 data/generated/illustrations.sqlite3 < scripts/illustration_corpus_diagnostics.sql
-- or paste sections into any SQLite browser (DB Browser for SQLite, etc).
-- Every query below is SELECT-only -- nothing here writes to the database.
--
-- NOTE: this corpus is plain SQLite, not Supabase/Postgres -- there is no
-- Supabase project backing illustration_engine (Supabase in this repo's
-- recent commit history is for the unrelated Greek Analysis v2 subsystem).

-- 1. Overall size and workflow-status breakdown -----------------------------
SELECT status, COUNT(*) AS unit_count
FROM illustration_units
GROUP BY status
ORDER BY unit_count DESC;

-- 2. Machine-QA verdict breakdown (independent axis from `status` above) ---
SELECT COALESCE(qa_status, 'NULL (never QA-checked)') AS qa_status, COUNT(*) AS unit_count
FROM illustration_units
GROUP BY qa_status
ORDER BY unit_count DESC;

-- 3. THE production-mode-visible corpus size --------------------------------
-- This is what mode="production" retrieval actually searches over -- the
-- number that matters for real end-user empty-result reports. Compare
-- against query 1's total row count: a big gap between "total units" and
-- this number means most of the QA-passed/enriched corpus is sitting
-- un-reviewed and invisible to production users (P4-class coverage gap,
-- not a retrieval bug).
SELECT COUNT(*) AS production_visible_unit_count FROM published_illustration_units;

-- 4. Content-completeness NULL rates (pre-publish units only; published
--    units cannot have NULLs here, the DB CHECK constraint forbids it) ----
SELECT
    COUNT(*) AS non_published_units,
    SUM(CASE WHEN title_hu IS NULL THEN 1 ELSE 0 END) AS missing_title_hu,
    SUM(CASE WHEN modern_hu_text IS NULL THEN 1 ELSE 0 END) AS missing_modern_hu_text,
    SUM(CASE WHEN summary_hu IS NULL THEN 1 ELSE 0 END) AS missing_summary_hu,
    SUM(CASE WHEN moral_hu IS NULL THEN 1 ELSE 0 END) AS missing_moral_hu,
    SUM(CASE WHEN human_reviewed_at IS NULL THEN 1 ELSE 0 END) AS never_human_reviewed
FROM illustration_units
WHERE status != 'published';

-- 5. Units with ZERO taxonomy tags attached (invisible to any topic/function
--    scoring -- can only ever be found via free-text keyword overlap) -----
SELECT COUNT(*) AS units_with_no_tags
FROM illustration_units u
WHERE NOT EXISTS (SELECT 1 FROM illustration_unit_tags ut WHERE ut.unit_id = u.id);

-- 6. Topic-tag distribution -- look for topics with 0 or near-0 coverage.
--    Recall the controlled vocabulary (PILOT_TOPICS in illustration_sqlite.py)
--    has only 10 slugs, all virtue/vice-shaped (alazat/buszkeseg/
--    becsuletesseg/bolcsesseg/eszesseg/igazsagossag/irgalom/kapzsisag/
--    turelem/tekintely_es_hatalom) -- if a topic shows 0 here, no candidate
--    can ever score a topic-match point for it, regardless of how the
--    planner tags a passage.
SELECT t.slug AS topic_slug, COUNT(*) AS units_tagged
FROM tags t
LEFT JOIN illustration_unit_tags ut ON ut.tag_id = t.id
WHERE t.category = 'topic'
GROUP BY t.slug
ORDER BY units_tagged DESC;

-- 7. Homiletic-function-tag distribution (same reasoning as #6) ------------
SELECT t.slug AS function_slug, COUNT(*) AS units_tagged
FROM tags t
LEFT JOIN illustration_unit_tags ut ON ut.tag_id = t.id
WHERE t.category = 'function'
GROUP BY t.slug
ORDER BY units_tagged DESC;

-- 8. Per-source coverage -- is the corpus dominated by one or two sources? -
SELECT s.code AS source_code, s.title, s.license_status, COUNT(u.id) AS unit_count
FROM sources s
LEFT JOIN stories st ON st.source_id = s.id
LEFT JOIN illustration_units u ON u.story_id = st.id
GROUP BY s.id
ORDER BY unit_count DESC;

-- 9. Per-source PUBLISHED coverage specifically (what production actually
--    draws from, per source) -------------------------------------------
SELECT s.code AS source_code, COUNT(p.id) AS published_unit_count
FROM sources s
LEFT JOIN stories st ON st.source_id = s.id
LEFT JOIN published_illustration_units p ON p.story_id = st.id
GROUP BY s.id
ORDER BY published_unit_count DESC;

-- 10. Exact-duplicate detection: same title_hu text reused across units ----
SELECT title_hu, COUNT(*) AS occurrences
FROM illustration_units
WHERE title_hu IS NOT NULL
GROUP BY title_hu
HAVING COUNT(*) > 1
ORDER BY occurrences DESC;

-- 11. Exact-duplicate detection: same original_text checksum across
--     DIFFERENT stories (a raw source imported twice, or two sources
--     containing the same underlying tale) -------------------------------
SELECT original_text_checksum, COUNT(*) AS story_count, GROUP_CONCAT(id) AS story_ids
FROM stories
WHERE original_text_checksum IS NOT NULL
GROUP BY original_text_checksum
HAVING COUNT(*) > 1;

-- 12. Provenance integrity: units with a NULL raw-story checksum ALWAYS fail
--     `retrieval._verify_checksum` and are silently excluded from every
--     search result, in every mode, with no visible error anywhere. SQLite
--     has no built-in SHA-256, so a mismatched-but-present checksum can't be
--     detected in pure SQL -- for that, run `illustration_engine.retrieval.
--     _verify_checksum(connection, unit_id)` per id in Python instead.
SELECT u.id AS unit_id, u.status, u.story_id, st.title_original
FROM illustration_units u
JOIN stories st ON st.id = u.story_id
WHERE st.original_text_checksum IS NULL;

-- 13. narrative_status distribution (historical-accuracy framing tag) ------
SELECT COALESCE(narrative_status, 'NULL (not yet classified)') AS narrative_status, COUNT(*) AS unit_count
FROM illustration_units
GROUP BY narrative_status
ORDER BY unit_count DESC;

-- 14. Multiple units per story -- how much does `extracted_scene`/
--     `condensed_story` derivation actually fan out one story into several
--     retrievable units? ---------------------------------------------------
SELECT unit_count, COUNT(*) AS story_count
FROM (
    SELECT story_id, COUNT(*) AS unit_count
    FROM illustration_units
    GROUP BY story_id
) per_story
GROUP BY unit_count
ORDER BY unit_count;

-- 15. license_status breakdown across sources -- how much of the corpus is
--     structurally BARRED from ever reaching production regardless of QA?
SELECT license_status, COUNT(*) AS source_count
FROM sources
GROUP BY license_status;
