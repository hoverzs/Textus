-- Automated corpus approval provenance (Option B, user-approved 2026-09-13).
--
-- CONTEXT: the production illustration corpus has 549 qa_status='passed'
-- units, all independently verified (read-only production audit, same
-- date) to meet every publish condition EXCEPT human_reviewed_at --
-- content-complete, publishable-license source, valid story/source FK,
-- at least one taxonomy tag, no legacy/strategy mismatch. Requiring 549
-- individual human clicks to satisfy a field whose only job is to record
-- "a human looked at this" doesn't make the corpus safer, it just forces
-- the field to say something true by brute force. This migration adds a
-- SEPARATE, explicitly-versioned, fully-auditable provenance path for
-- that specific, narrow case -- it does NOT touch what human_reviewed_at
-- means or how the existing human-review workflow works.
--
-- HARD RULE THIS MIGRATION ENFORCES, NOT JUST DOCUMENTS: `human_reviewed_at`
-- is written ONLY by a human approving a unit (illustration_review_ui.py /
-- SupabaseIllustrationReviewRepository.approve_unit()) -- the automated
-- path below NEVER writes it, and the new publish CHECK below makes a
-- published-via-automation row structurally REQUIRE human_reviewed_at to
-- stay NULL alongside approval_method='automated_corpus_approval' (see
-- the CHECK's exact shape -- it is an OR of two mutually exclusive
-- provenance shapes, not a relaxation of either one).

-- ===========================================================================
-- 1. New provenance columns
-- ===========================================================================

alter table illustration_units
    add column if not exists approval_method text
        check (approval_method is null or approval_method in ('human_review', 'automated_corpus_approval')),
    add column if not exists auto_approved_at timestamptz,
    add column if not exists auto_approval_rule_version text;

comment on column illustration_units.approval_method is
    'Provenance of how this unit reached approved/published status -- ''human_review'' (a person clicked Approve; human_reviewed_at is set) or ''automated_corpus_approval'' (a versioned, auditable policy rule approved it; human_reviewed_at stays NULL, always). Never inferred or backfilled from human_reviewed_at alone -- always written explicitly by the code path that actually performed the approval.';
comment on column illustration_units.auto_approved_at is
    'Timestamp of automated corpus approval. NULL unless approval_method=automated_corpus_approval. Structurally distinct from human_reviewed_at -- the two are never the same column and never satisfy the same CHECK branch.';
comment on column illustration_units.auto_approval_rule_version is
    'Which versioned automated-approval policy (e.g. corpus_qa_passed_v1, see apply_automated_corpus_approval_v1()) approved this unit. Always set together with auto_approved_at in the same write, never independently -- makes every published record''s actual provenance queryable forever: SELECT approval_method, count(*) FROM illustration_units WHERE status=''published'' GROUP BY 1.';

-- ===========================================================================
-- 2. Replace the publish CHECK -- found by definition text, not a
--    hardcoded constraint name (Postgres auto-names unnamed CHECK
--    constraints positionally, and this migration ALTERs the existing
--    table rather than recreating it, so guessing a name would be
--    fragile). The OLD constraint required human_reviewed_at
--    unconditionally; the NEW one requires EITHER a complete human_review
--    provenance OR a complete automated_corpus_approval provenance --
--    never a partial/blended state, never optional on either branch.
-- ===========================================================================

do $$
declare
    v_conname text;
begin
    -- Postgres pretty-prints pg_get_constraintdef() in UPPERCASE (HUMAN_
    -- REVIEWED_AT IS NOT NULL, not human_reviewed_at is not null) -- ilike
    -- (case-insensitive), not like, is required here. Also excludes any
    -- definition already mentioning approval_method, so this stays safe
    -- to re-run (idempotent) even after the new constraint below exists.
    select conname into v_conname
    from pg_constraint
    where conrelid = 'illustration_units'::regclass
      and contype = 'c'
      and pg_get_constraintdef(oid) ilike '%human_reviewed_at is not null%'
      and pg_get_constraintdef(oid) not ilike '%approval_method%';
    if v_conname is not null then
        execute format('alter table illustration_units drop constraint %I', v_conname);
    end if;
end;
$$;

-- SQL three-valued-logic trap, caught by local real-Postgres validation
-- (not assumed): if approval_method is NULL, `approval_method = 'human_
-- review'` evaluates to NULL, not FALSE -- so both OR branches below
-- would evaluate to NULL, the whole AND-chain to NULL, and a CHECK
-- constraint treats a NULL result as PASSING (only an explicit FALSE
-- fails it). Without the `approval_method is not null` guard below, a
-- published row with human_reviewed_at set but approval_method left NULL
-- would have silently slipped past this constraint. The explicit guard
-- forces a definite FALSE in that case instead of an ambiguous NULL.
alter table illustration_units add constraint illustration_units_publish_provenance_check check (
    status != 'published'
    or (
        title_hu is not null and modern_hu_text is not null and summary_hu is not null
        and approval_method is not null
        and (
            (approval_method = 'human_review' and human_reviewed_at is not null)
            or (
                approval_method = 'automated_corpus_approval'
                and auto_approved_at is not null
                and auto_approval_rule_version is not null
                and human_reviewed_at is null  -- structurally impossible to fake human review via this branch
            )
        )
    )
);

-- ===========================================================================
-- 3. Extend the reviewed-content-protection trigger to ALSO cover
--    automated-approval provenance -- the ORIGINAL trigger only fired
--    when OLD.human_reviewed_at IS NOT NULL, which means an automated-
--    approved published unit (human_reviewed_at always NULL, by design)
--    would have had ZERO protection against silent content rewriting.
--    Extending the WHEN condition and the protected-field list, and the
--    "legitimate reset" escape hatch, so BOTH provenance kinds get the
--    identical guarantee: content can only change together with EVERY
--    provenance field cleared and status reset to needs_review.
-- ===========================================================================

create or replace function trg_illustration_units_protect_reviewed_content() returns trigger as $$
begin
    if (old.human_reviewed_at is not null or old.approval_method is not null)
       and (
            new.title_hu is distinct from old.title_hu
            or new.modern_hu_text is distinct from old.modern_hu_text
            or new.summary_hu is distinct from old.summary_hu
            or new.moral_hu is distinct from old.moral_hu
            or new.narrative_status is distinct from old.narrative_status
            or new.enrichment_model is distinct from old.enrichment_model
            or new.enrichment_prompt_version is distinct from old.enrichment_prompt_version
            or new.enrichment_generated_at is distinct from old.enrichment_generated_at
            or new.enrichment_warnings is distinct from old.enrichment_warnings
       )
       and not (
            new.human_reviewed_at is null and new.approval_method is null
            and new.auto_approved_at is null and new.auto_approval_rule_version is null
            and new.status = 'needs_review'
       )
    then
        raise exception 'review_gate: reviewed content can only change together with ALL provenance fields cleared (human_reviewed_at, approval_method, auto_approved_at, auto_approval_rule_version) AND status reset to needs_review (unit id=%)', new.id;
    end if;
    new.updated_at := now();
    return new;
end;
$$ language plpgsql;
-- CREATE OR REPLACE FUNCTION alone is sufficient -- the existing trigger
-- (illustration_units_protect_reviewed_content, created in
-- 20260913120000) already references this function by name and picks up
-- the new body automatically; no DROP/CREATE TRIGGER needed.

-- ===========================================================================
-- 4. corpus_qa_passed_v1 -- explicit, versioned, narrow automated-approval
--    policy + the ONE batch operation that applies it. Deliberately NOT a
--    general "publish everything" helper -- every single row is
--    independently re-verified against every eligibility condition
--    server-side, in this function, regardless of what the caller
--    believes is eligible. Fail-closed PER ROW: an ineligible unit_id in
--    the input array is skipped with a specific reason, never silently
--    published and never aborting the whole batch.
-- ===========================================================================

create or replace function apply_automated_corpus_approval_v1(p_unit_ids bigint[])
returns table(unit_id bigint, outcome text, detail text)
language plpgsql
security definer
set search_path = public
as $$
declare
    v_id bigint;
    v_unit record;
    v_tag_count integer;
    v_original_length integer;
    v_expected_mode text;
    v_expected_derivation text;
    v_mismatch boolean;
begin
    foreach v_id in array p_unit_ids
    loop
        select u.id, u.status, u.qa_status, u.title_hu, u.modern_hu_text, u.summary_hu,
               u.derivation_type, u.human_reviewed_at, s.license_status,
               length(st.original_text) as original_length
          into v_unit
        from illustration_units u
        join illustration_stories st on st.id = u.story_id
        join illustration_sources s on s.id = st.source_id
        where u.id = v_id;

        if not found then
            unit_id := v_id; outcome := 'skipped'; detail := 'unit not found or story/source relation invalid';
            return next; continue;
        end if;

        if v_unit.qa_status is distinct from 'passed' then
            unit_id := v_id; outcome := 'skipped'; detail := format('qa_status=%L, not passed', v_unit.qa_status);
            return next; continue;
        end if;

        if v_unit.title_hu is null or v_unit.modern_hu_text is null or v_unit.summary_hu is null then
            unit_id := v_id; outcome := 'skipped'; detail := 'missing required content field';
            return next; continue;
        end if;

        if v_unit.license_status not in ('public_domain_confirmed', 'public_domain_assumed_by_age', 'permission_granted') then
            unit_id := v_id; outcome := 'skipped'; detail := format('source license_status=%L not publishable', v_unit.license_status);
            return next; continue;
        end if;

        if v_unit.human_reviewed_at is not null then
            unit_id := v_id; outcome := 'skipped'; detail := 'already has human review -- automated approval must never touch it';
            return next; continue;
        end if;

        if v_unit.status is distinct from 'needs_review' then
            unit_id := v_id; outcome := 'skipped'; detail := format('status=%L, expected needs_review', v_unit.status);
            return next; continue;
        end if;

        select count(*) into v_tag_count from illustration_unit_tags where illustration_unit_tags.unit_id = v_id;
        if v_tag_count = 0 then
            unit_id := v_id; outcome := 'skipped'; detail := 'no taxonomy tags';
            return next; continue;
        end if;

        -- Strategy-mismatch check -- mirrors illustration_engine.
        -- enrichment_pipeline.derive_enrichment_strategy/
        -- is_legacy_strategy_mismatch EXACTLY (thresholds verified against
        -- that module's actual constants, not assumed, during the
        -- read-only audit this policy is based on).
        v_original_length := coalesce(v_unit.original_length, 0);
        if v_original_length <= 1500 then
            v_expected_mode := 'direct_unit'; v_expected_derivation := 'full_story_translation';
        elsif v_original_length <= 3000 then
            v_expected_mode := 'direct_unit'; v_expected_derivation := 'condensed_story';
        else
            v_expected_mode := 'unit_proposal'; v_expected_derivation := null;
        end if;

        if v_expected_mode = 'unit_proposal' then
            v_mismatch := v_unit.derivation_type is distinct from 'extracted_scene';
        else
            v_mismatch := v_unit.derivation_type is distinct from v_expected_derivation;
        end if;

        if v_mismatch then
            unit_id := v_id; outcome := 'skipped'; detail := 'legacy/strategy mismatch';
            return next; continue;
        end if;

        update illustration_units
        set status = 'published',
            approval_method = 'automated_corpus_approval',
            auto_approved_at = now(),
            auto_approval_rule_version = 'corpus_qa_passed_v1'
        where id = v_id;

        unit_id := v_id; outcome := 'published'; detail := 'corpus_qa_passed_v1';
        return next;
    end loop;
end;
$$;

revoke all on function apply_automated_corpus_approval_v1(bigint[]) from public, anon, authenticated;
grant execute on function apply_automated_corpus_approval_v1(bigint[]) to service_role;

comment on function apply_automated_corpus_approval_v1(bigint[]) is
    'The corpus_qa_passed_v1 policy, applied as one explicit, auditable batch operation. service_role-only (never anon/authenticated). Re-verifies EVERY eligibility condition server-side per unit_id, independent of whatever the caller believes is eligible: qa_status=passed, complete content, publishable source license, no existing human review, status=needs_review, at least one taxonomy tag, no legacy/strategy mismatch. NEVER writes human_reviewed_at. Skips (never errors on) ineligible units with a specific reason, so a batch call is always fully auditable row-by-row.';
