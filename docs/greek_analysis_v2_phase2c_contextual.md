# Greek Analysis v2 — Phase 2C: Supabase Backend + Grounded Contextual Analysis

Builds on Phase 2A (deterministic foundation, `65aa15e`/`7d30899`), Phase 2B
(MACULA syntax integration, `3e50f26`), and Phase 2B.1 (full-corpus
completion, `562fc71`). This phase turns that deterministic foundation into
a production-shaped architecture: a normalized Supabase schema, a
backend-agnostic repository abstraction, and one grounded Gemini 2.5 Flash
contextual explanation per verse — with the AI strictly constrained to
*explain* the deterministic facts, never invent them.

**Scope note on constraints honored:** the alignment algorithm
(`bible_engine.greek_token_alignment`) was not touched. Hebrew Analysis v2
was not touched. No attempt was made to chase higher alignment coverage.
The large normalized syntax store (`data/generated/greek_syntax_dev.sqlite3`)
was not committed to Git. Nothing was merged or pushed.

---

## 1. Dataset/version contract (§1)

`bible_engine/greek_dataset_version.py` — `greek_dataset_version_signature()`
combines seven pinned values into one sorted, deterministic string:
TAGNT/TEGMC/TBESG (all pinned to STEPBible-Data commit `ae39711d…`),
the Hungarian lexicon version, the MACULA Greek commit (`8423afe4…`), the
alignment algorithm version (`greek-align-v1`), and the normalized schema
version (`greek-schema-2c-v1`). Any change to any of these changes the
signature, and the signature is a direct component of the contextual-
analysis cache key (§16) — cache invalidation is automatic, with no
separate invalidation code path to get wrong.

## 2. Supabase schema (§2)

`supabase/migrations/20260911220000_greek_linguistic_layer.sql` — additive,
Greek-specific tables: `greek_verses`, `greek_tokens` (morphology inlined,
not a separate table — see rationale below), `greek_source_nodes` (raw
MACULA import, comparison-only), `greek_token_alignments`,
`greek_phrases`/`greek_clauses`, `greek_syntax_membership`,
`greek_semantic_roles`, `greek_coreference_links`, `greek_lexicon_hu`.
Reuses the existing `original_language_dataset_versions` table rather than
inventing a Greek-specific one — it was already dataset-id-keyed and
language-agnostic.

**Deliberately not built** (per the task's explicit "do not force tables
for data MACULA Greek does not actually provide"): `greek_token_morphology`
(Greek morphology is flat/single-valued per token, unlike Hebrew's
per-component breakdown, so it is inlined on `greek_tokens`);
`greek_token_lexical_ids` (TAGNT gives exactly one disambiguated Strong id
per token, never an array); `greek_participants`/`greek_syntax_edges`
(MACULA Greek's flat TSV supplies semantic roles and coreference directly —
a separate "edges"/"participants" table would duplicate
`greek_semantic_roles`/`greek_coreference_links` under a different name);
`greek_detected_pattern*` tables (Phase 2B's construction detectors run
on-the-fly from the bundle; add persistence later only if profiling shows
it's needed).

Access model: `service_role`-only, RLS enabled with no policies,
`anon`/`authenticated` explicitly revoked — identical convention to the
Hebrew schema.

### Two concrete schema bugs found and fixed while designing the importer

Both were caught by checking the *actual* local-store data before writing
import code around assumptions, not by inspection alone:

1. **`greek_phrases`/`greek_clauses` now key on a new `macula_group_id`
   column, not `source_node_id`.** The original design assumed a
   phrase/clause's first token could serve as its natural key. Measured:
   **13,090 of 91,448 groups corpus-wide share their first-leaf token with
   at least one other, nested group** (e.g. an `np` phrase and the `cl`
   clause it opens both starting at the same word). A
   `unique(dataset_version_id, source_node_id)` constraint would have
   silently collapsed distinct constituents on upsert — real data loss.
   `macula_group_id` (the local store's own synthesized, globally-unique
   group identity) is the real natural key; `source_node_id` is kept as a
   plain, non-unique reference column.
2. **`greek_clauses` gained a `parent_phrase_id` column.** Measured:
   **2,565 of 83,198 parented groups corpus-wide are a clause whose
   immediate parent is a phrase**, not another clause (e.g. a relative
   clause nested inside its head noun phrase) — the original
   clause-only-parent design had no column to represent this. `greek_clauses`
   now has the same dual-parent shape `greek_phrases` already had.

Both fixes are schema design, not the alignment algorithm, and this schema
has never been applied to a real Supabase project — no live data was ever
at risk.

## 3/4. Importer (§3/§4)

`scripts/import_greek_syntax_to_supabase.py`. Learns directly from the
Hebrew Phase 2D.2 experience (`scripts/import_macula_to_supabase.py`):
bulk upsert/insert only, batched (`--batch-size`, default 500), bounded
exponential-backoff retry (4 attempts), a two-pass insert for
self-referencing phrase/clause parents linked via narrowly-scoped RPCs
(never per-row HTTP `.update()` — see §6 below for why), idempotent writes
(natural-key upsert or dataset-version-scoped delete-then-insert, never an
unscoped delete), `--dry-run` by default (`--execute` required for a real
write), and FK-prerequisite validation (alignment rows referencing a token
that wasn't itself imported are counted and reported, never silently
imported or silently dropped without a trace).

Two distinct local sources feed it: the raw TAGNT SQLite database (tokens/
morphology/lemma, run through the exact same
`bible_engine.greek_analysis_service._verse_analysis` every other consumer
uses — not reimplemented) and the local MACULA syntax store (source nodes,
alignments, phrase/clause groups, semantic roles, coreference).

**Full-corpus dry-run result** (this environment, `--dry-run`, no network):

```
  dataset_versions: 5 rows
  verses: 7958 rows, tokens: 142096 rows
  lexicon_hu: 5959 rows
  source_nodes: 137741 rows
  token_alignments: 142096 rows
  phrases: 47613 rows, clauses: 43835 rows   (sums to 91448 = 100% of local macula_groups — zero dropped)
    NOTE: 1749 membership entries skipped — MACULA token has no resolved TAGNT alignment (1.2%)
  syntax_membership: 635861 rows
    NOTE: 327 semantic-role assignments skipped — predicate/argument has no resolved TAGNT alignment (0.8%)
  semantic_roles: 41440 rows
    NOTE: 248 coreference links skipped — source/target has no resolved TAGNT alignment (0.6%)
  coreference: 38337 rows

Done in 10.1s
```

The phrase+clause count summing exactly to the local store's total group
count confirms the `macula_group_id` fix works — no group is lost. The
small (<2%) skip counts are for MACULA tokens that never received a TAGNT
alignment at all (a pre-existing, already-documented Phase 2B.1 gap, not
something this importer introduces) and are reported by count, never
silently absorbed.

UNRESOLVED_TEXTUAL_VARIANT/UNRESOLVED_OTHER alignment rows are imported
exactly as the local store has them (`source_node_id = NULL`) — this
importer never converts an unresolved alignment into a resolved one.

**Not run against a real Supabase project** — no credentials are available
in this environment (verified: no `SUPABASE_*`/`GEMINI_*`/`GOOGLE_API_KEY`
env vars, no real `.streamlit/secrets.toml`, `app._resolve_api_key()`
returns nothing usable). This is reported as an honest blocker, not worked
around.

## 5. Repository abstraction (§5)

`bible_engine/greek_analysis_repository.py` — `GreekAnalysisRepository`
Protocol, `LocalGreekAnalysisRepository` (reads the local SQLite store
directly), `SupabaseGreekAnalysisRepository` (calls the verse-bundle RPC),
`get_default_greek_analysis_repository()` (selected via
`TEXTUS_GREEK_ANALYSIS_BACKEND=local|supabase`), and
`attach_syntax_via_repository(bundle, repository)` — the single function
`GreekAnalysisService`-adjacent code calls, backend-agnostic by
construction. No hard-coded production credentials anywhere in this path.

## 6. Read path (§6)

`supabase/migrations/20260911223000_greek_verse_syntax_bundle_rpc.sql` —
`get_greek_verse_syntax_bundle(p_verse_ref)`, one `jsonb_build_object`
bundling tokens (with alignment status + lexicon)/phrases/clauses/
membership/semantic roles/coreference in **one** round trip per verse —
deliberately avoiding the exact mistake the Hebrew backend originally made
(up to 9 sequential REST calls per verse, fixed only later in Hebrew's own
Phase 2D.2/2D — see this repo's own commit `2188955`). Ordering is fully
deterministic: tokens by `word_index`, membership by `member_order`
(preserves MACULA's own document order — relevant for hyperbaton),
everything else by surrogate id — never by a text column that could sort
lexicographically wrong.

Formal network-latency benchmarking (1 verse / 10 verses / 1 chapter
against a live project) could not be performed — no Supabase project is
reachable from this environment. The **local-computation** side of the
read path (`SupabaseGreekAnalysisRepository._parse_bundle_payload`,
exercised in the parity tests below) runs in well under a millisecond per
verse; whatever real latency exists in production is dominated by network
round-trip time, and this design already bounds that to one round trip per
verse by construction, not by later optimization.

## 7. Repository parity (§7)

`tests/test_greek_analysis_repository_parity.py` — 45 tests (15 regression
verses × 3 checks), all passing. Since no live Supabase project is
reachable, "Supabase" is exercised via
`SupabaseGreekAnalysisRepository._parse_bundle_payload` fed a payload built
independently from the same underlying local-store data the RPC's own SQL
would select from (not derived from `LocalGreekAnalysisRepository`'s own
code path) — proving the two repositories' *result-assembly* logic is
equivalent given equivalent input, which is the part that can regress
independently of network/credentials. For every one of the 15 verses:
phrase/clause token-id sets match, semantic roles match, coreference
links match, per-token `alignment_status` matches, and — critically —
`syntax_grounding` (FULLY/PARTIALLY/NO_GROUNDED_SYNTAX) matches, exercised
against `Lk 10,25-37` which is the one fixture verse containing a resolved
token with no phrase/clause/role/coreference coverage. True end-to-end
parity against a live Supabase project remains a deployment-time
verification step (§22).

## 8/9/10/11/12/13/14/15. Contextual analysis contract

`bible_engine/greek_contextual_analysis.py` — `GreekContextualAnalysis`
(schema_version, reference, grounding_status, `word_notes[]`,
`construction_notes[]`, `syntax_summary`, `translation_notes[]`,
`exegetical_notes[]`, `warnings[]`), one Gemini call per **verse**, never
per word. Each `GreekWordNote` separates lexical base meaning / contextual
meaning / morphological explanation / syntax role (only when grounded) /
translation note / confidence — exactly the task's required breakdown.

**Closed-world morphology (§9):** the model is never even asked for
morphology fields — `GREEK_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA` has no
lemma/case/tense/etc. fields at all. Every deterministic field the UI shows
comes from `token.morphology`, never from the model's response.

**Greek-specific semantic safety rules (§10):** enforced mechanically, not
just via prompt instruction — `bible_engine/greek_contextual_analysis_service.py`
screens `morphological_explanation_hu`/`contextual_meaning_hu`/
`syntax_role_hu`/construction notes/`syntax_summary`/translation/exegetical
notes against exact forbidden Hungarian phrases: aorist → "egyszerű múlt" /
"egyszeri cselekvés" / "pontszerű cselekvés"; imperfect → "folyamatos
múlt"; middle → "visszaható"; perfect → "befejezett múlt, amelynek
eredménye fennáll". Any match zeroes out the offending field and records a
warning — this is a backstop against the clearest violations, not a claim
of catching every possible paraphrase (the prompt's own instructions are
the first line of defense; the literal-substring screen is the second).

**Lexical authority model (§11):** `lexical_provenance` ∈
`{"reviewed", "draft", "english_fallback", ""}`, computed **server-side**
from `token.lexical_sense.review_status`/`base_meaning_hu` — never asked
of or trusted from the model at all.

**Construction evidence contract (§12):** every `GreekConstructionNote`
must cite deterministic evidence ids (detected pattern / phrase / clause /
semantic role / coreference); the server resolves them via
`build_construction_evidence_index()`/`resolve_construction_evidence()`
and computes `token_ids` itself from the evidence — an unsupported
evidence id is rejected outright, and the model's own claimed token
groupings are never trusted.

**First supported constructions (§13):** limited to the Phase 2B
deterministic set (article+participle, genitive absolute, infinitive
construction, preposition+case, negation, repeated lemma, ἵνα clause, ὅτι
clause, conditional marker/clause, relative clause, coordination) — no
semantic function is inferred beyond available syntax evidence for
genitive-absolute/participial constructions.

**Grounding status (§15):** `analysis.grounding_status` is *always*
`verse.syntax_grounding` from the bundle — never the model's self-report,
even if the model's own JSON claims otherwise (tested explicitly — see
§21). NO_GROUNDED_SYNTAX verses never receive a `syntax_summary`,
regardless of model output.

## 16. Cache (§16)

`bible_engine/greek_contextual_analysis_cache.py` — LRU cache keyed by
`(verse_id, dataset_version_signature, prompt_version, model_id)`. A
dataset-signature bump invalidates automatically; word clicks within the
same verse reuse the cached result with zero additional Gemini calls
(tested explicitly).

**Bug found and fixed during this phase:** the cache accessor initially
used `@st.cache_resource`, which is **process-global** — it persists
across every Streamlit session, including every independent
`AppTest.from_function()` run within one pytest process, which silently
leaked cached AI results between what should have been isolated test
sessions (5 of 8 UI tests failed as a result, with confusing symptoms that
differed between isolated and full-file test runs). Root-caused by
comparing against Hebrew's own precedent (`hebrew_text_demo.py`'s
`_hebrew_contextual_analysis_cache`, which correctly uses
`st.session_state.setdefault(...)`) and fixed identically in
`bible_engine/greek_contextual_analysis_ui.py`.

## 17. Gemini model + timeout (§17)

Gemini 2.5 Flash, via the same `generate_text()` every other tab uses
(same API key, cache, debug log) — `app.generate_greek_contextual_analysis_text`,
mirroring `generate_hebrew_contextual_analysis_text` exactly.
`GREEK_PHASE2C_GEMINI_TIMEOUT_S = 40`. Generation is strictly button-gated:
zero calls on initial render, zero calls on word selection (tested
explicitly), exactly one call per explicit "Kontextuális elemzés
generálása" click.

## 18. Regression fixtures (§18)

The existing 15 unreviewed Phase 2A developer fixtures
(`tests/fixtures/greek_analysis_v2_regression_verses.json`) confirmed
working through the **full** Phase 2C pipeline (syntax attachment +
construction detection + contextual-analysis validator), not just the
Phase 2A bundle they were originally captured against —
`tests/test_greek_contextual_analysis_regression_fixtures.py`, 16 tests
passing.

## 19. Live Gemini quality test (§19)

**BLOCKED — not performed.** No Gemini/Google API credentials are
available in this environment (verified directly: no relevant environment
variables, no real `.streamlit/secrets.toml`, `app._resolve_api_key()`
returns nothing usable). Reported honestly rather than simulated or faked.
Everything upstream of the live call (prompt construction, response
validation, grounding enforcement, forbidden-phrase screening, evidence
resolution) is exercised and passing against real deterministic data for
all 15 representative-phenomenon verses (aorist, imperfect, genitive
absolute, ἵνα clause, difficult middle/passive, PARTIALLY/FULLY-grounded
cases) — see §7/§18/§21 — but no actual model output has been evaluated
for quality, terminology correctness, or interpretive restraint. This is
the single largest gap before real production sign-off.

## 20. UI integration (§20)

Traced the **real** production render path end-to-end before wiring
anything, specifically to avoid the Hebrew Phase 2E mistake ("Phase 2E
existed but was only connected to a demo/alternate renderer"): `app.py` →
`bible_engine.greek_analysis_ui.render_greek_analysis_block()` →
`_render_loaded_greek_passage_analysis()` → `_render_analysis_panel()` (the
"full" mode branch) → `bible_engine.greek_contextual_analysis_ui
.render_greek_contextual_analysis_panel()`. Confirmed
`_render_loaded_greek_analysis` (a similarly-named but unrelated function)
has zero callers — genuinely dead code, not the wiring this phase uses.
Both real call sites — the dedicated "Eredeti szöveg tanulmányozása" tab
and the "Igehely" tab's `bible_text_ui.render_bible_text_editor` — now
forward `greek_contextual_analysis_generate_fn`; a dedicated regression
test (`test_igehely_tab_bible_text_editor_forwards_greek_generate_fn`,
mirroring the exact class of bug the Hebrew wiring mistake was) passes for
both.

Panel shows: existing deterministic morphology, lexical base meaning,
contextual meaning, morphological explanation, grounded syntax role (only
when grounded), related constructions — then expandable verse-level
sections (Mondattani összefoglalás, Fordítási megjegyzések, Exegetikai
megjegyzések, Figyelmeztetések), reusing the app-wide expander styling
already standard elsewhere in this codebase.

## 21. Tests (§21)

All new/modified test files, run together:

```
tests/test_greek_contextual_analysis_grounding.py         16 passed
tests/test_greek_contextual_analysis_ui.py                  8 passed
tests/test_greek_analysis_repository_parity.py             45 passed
tests/test_greek_contextual_analysis_regression_fixtures.py 16 passed
                                                    total   85 passed
```

Covers, each as an explicitly identifiable test: no AI call on initial
render (`test_no_ai_section_when_generate_fn_is_none`,
`test_initial_render_triggers_zero_gemini_calls`); no AI call on word
selection (`test_selecting_a_different_word_in_the_same_verse_reuses_cache_zero_new_calls`);
one explicit generation call
(`test_clicking_generate_button_triggers_exactly_one_call_and_renders_result`);
cache reuse across word clicks (same test); timeout fails closed
(`test_simulated_timeout_degrades_gracefully_deterministic_ui_still_usable`);
deterministic UI remains usable after AI failure (same test, plus
`test_invalid_json_response_shows_graceful_notice`); **unsupported
morphology claim rejected** as its own standalone named test
(`test_unsupported_morphology_claim_is_rejected`, distinct from the
parametrized forbidden-phrase sweep); **unsupported syntax claim rejected**
as its own standalone named test
(`test_unsupported_syntax_claim_is_rejected_for_token_without_syntax_coverage`,
distinct from the unresolved-alignment-status test); unsupported
construction evidence rejected
(`test_construction_note_with_invalid_evidence_id_is_rejected`);
PARTIAL/NO grounding behaves conservatively
(`test_no_grounded_syntax_verse_rejects_any_syntax_summary`, plus the
grounding-status parity test against `Lk 10,25-37`); Local/Supabase parity
(45 tests, §7); all 15 regression fixtures (§18, 16 tests).

**Full existing Greek suite regression check** (every phase's own test
files, together — the same command pattern used at the end of every prior
phase):

```
pytest tests/test_greek_*.py tests/test_tagnt_*.py tests/test_tbesg_*.py \
       tests/test_lexicon_*.py tests/test_morphology_hu.py \
       tests/test_nt_lexicon_coverage.py tests/test_missing_tagnt_strong_audit.py \
       tests/test_original_language_*.py tests/test_audit_greek_lexicon_quality.py
555 passed, 6 skipped (known/expected skips) in 80.12s
```

No regressions anywhere in the existing Phase 2A/2B/2B.1 test surface.
`git status` after the full run showed no unintended file mutations (the
`data/biblical_places/enrichment_research/*.json` side-effect pattern seen
in every prior phase's full-suite run did not recur this time).

## 22. Production deployment prep (§22)

**Not deployed to any real Supabase project** — no credentials available
in this environment; nothing was attempted against production
infrastructure. Ready for a real deployment once credentials exist:

1. Apply migrations in order: `20260911220000_greek_linguistic_layer.sql`,
   `20260911223000_greek_verse_syntax_bundle_rpc.sql`,
   `20260912090000_greek_bulk_parent_link_rpcs.sql`.
2. Run `python scripts/import_greek_syntax_to_supabase.py --execute`
   (defaults resolve `data/generated/tagnt_nt.sqlite3` and
   `data/generated/greek_syntax_dev.sqlite3` automatically; override with
   `--tagnt-db`/`--syntax-store` if needed). Expect roughly the row counts
   in §3/§4 above; the importer prints per-table counts and any
   FK-prerequisite skip counts as it runs.
3. Set `TEXTUS_GREEK_ANALYSIS_BACKEND=supabase` to switch the running app
   over to the Supabase repository.
4. Re-run `tests/test_greek_analysis_repository_parity.py` against the
   real project (would need a small harness change to point
   `SupabaseGreekAnalysisRepository` at the live client instead of the
   simulated payload — not yet written, since there is nothing to point it
   at from this environment) to get **true** end-to-end parity proof,
   superseding the simulated-payload proof in §7.
5. Perform the §19 live Gemini quality test against the deployed backend
   before any user-facing release.

Secrets: none are present in this repository or environment; none were
generated or embedded by this phase's code.

## 23. Status

**NOT READY FOR PRODUCTION DEPLOYMENT PREP** — exact blockers:

1. No Supabase project has ever received this schema/data — the entire
   Supabase side of this phase is validated only against local/simulated
   data (§3/§7), never a live Postgres instance. Needs real credentials
   and a real `--execute` import + parity re-check (§22 step 4).
2. The §19 live Gemini quality test has not been performed at all — no
   actual model output has been evaluated for morphology correctness,
   lexical/context distinction, syntax grounding quality, Greek
   terminology, or interpretive restraint. Needs a real Gemini API key.
3. Formal network-latency benchmarking of the read-path RPC (1 verse / 10
   verses / 1 chapter, §6) has not been performed against a live project —
   only the local-computation side is measured.

Everything else in this document — schema design (including the two bugs
found and fixed), the importer (dry-run-validated against the full
27-book corpus), the repository abstraction, the contextual-analysis
contract and its grounding/safety enforcement, the cache, the UI wiring
traced to the real production render path, and 85 new + 555 pre-existing
passing tests with zero regressions — is complete and ready to carry
forward once the three blockers above are lifted by whoever has the
credentials to lift them.
