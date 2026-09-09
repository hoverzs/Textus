-- Hebrew Analysis v2 — Phase 2D.2: syntax-grounding representation.
--
-- Phase 2D.1 introduced a three-state syntax-grounding model
-- (FULLY_GROUNDED_SYNTAX / PARTIALLY_GROUNDED_SYNTAX / NO_GROUNDED_SYNTAX,
-- see bible_engine.hebrew_analysis_repository) computed from
-- hebrew_token_alignments at READ time rather than stored as a column —
-- deliberately: it is fully derivable from data the base migration
-- (20260908190000_hebrew_linguistic_layer.sql) already stores, and a
-- stored column would only risk drifting out of sync with the alignment
-- table it summarizes. This migration adds the smallest thing actually
-- missing: a server-side VIEW that computes it in one query instead of
-- the three round trips (get verse id -> get its tokens -> get their
-- alignment types) bible_engine.hebrew_analysis_repository.SupabaseHebrewAnalysisRepository
-- previously had to make client-side for the same result.
--
-- No new table, no new stored fact, no change to the base schema's
-- authority rules — this is read-path plumbing only.
--
-- Same validation status as the base migration: parsed/reference-checked
-- locally, NOT applied to any real Supabase project from this
-- environment (no credentials available) — see
-- docs/hebrew_analysis_v2_phase2d2.md for exact manual-apply steps.

create or replace view hebrew_verse_syntax_grounding as
select
    v.verse_ref,
    v.id as verse_id,
    count(*) as token_count,
    -- A token with NO alignment row at all (should never happen — every
    -- token always gets exactly one align_token() attempt — but treated
    -- defensively as unresolved rather than silently counted as
    -- confirmed, since under-claiming grounding is the safe direction of
    -- error here) counts alongside genuine UNRESOLVED tokens.
    count(*) filter (where alignment_status.alignment_type = 'UNRESOLVED' or alignment_status.alignment_type is null) as unresolved_token_count,
    case
        when count(*) filter (where alignment_status.alignment_type = 'UNRESOLVED' or alignment_status.alignment_type is null) = 0 then 'FULLY_GROUNDED_SYNTAX'
        else 'PARTIALLY_GROUNDED_SYNTAX'
    end as grounding_status
from hebrew_verses v
join hebrew_tokens t on t.verse_id = v.id
join lateral (
    -- One row per token: a token is "confirmed" if ANY of its alignment
    -- rows (one per component for COMPOSITE tokens) is not UNRESOLVED;
    -- an UNRESOLVED token has exactly one row (component_index is null)
    -- per the base migration's own check constraint, so MIN() here just
    -- picks that single value for such tokens and any non-UNRESOLVED
    -- value otherwise (alignment_type is never NULL, so MIN is safe and
    -- deterministic — 'COMPOSITE' < 'EXACT' < 'UNRESOLVED' < 'VALIDATED_FALLBACK'
    -- alphabetically, but the filter above only cares about the
    -- UNRESOLVED/not-UNRESOLVED distinction, not which non-UNRESOLVED
    -- value was picked).
    select min(a.alignment_type) as alignment_type
    from hebrew_token_alignments a
    where a.token_id = t.token_id
) alignment_status on true
group by v.verse_ref, v.id;

-- Note: NO_GROUNDED_SYNTAX (no syntax data imported for the verse at all)
-- is NOT representable by this view alone — it is the absence of a row
-- here (or the absence of any hebrew_phrases/hebrew_clauses/
-- hebrew_syntax_edges row for the verse_ref), exactly mirroring
-- bible_engine.hebrew_analysis_repository._grounding_from_counts's own
-- "has_syntax" gate: a verse with zero syntax facts imported reports
-- NO_GROUNDED_SYNTAX regardless of what this view would compute, so a
-- caller must still check for at least one syntax fact before trusting
-- this view's grounding_status value — the Python repository layer
-- already does this (bible_engine/hebrew_analysis_repository.py,
-- _grounding_from_counts), unchanged by this migration.

grant select on hebrew_verse_syntax_grounding to service_role;
revoke all on hebrew_verse_syntax_grounding from anon, authenticated;
