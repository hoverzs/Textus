# Greek Analysis v2 — Production Validation

Continues from Phase 2C (`docs/greek_analysis_v2_phase2c_contextual.md`,
checkpoint `002d8a0`). That phase built and locally validated the Supabase
schema, importer, repository abstraction, and contextual-analysis contract
but could not test any of it against a real project or a real Gemini call —
no credentials were available in that environment. This document reports
what changed once real credentials and a real production Supabase project
became available: the schema was deployed, the full 27-book corpus was
imported, and — critically — **real** Local↔Supabase parity testing against
live data found and fixed five genuine bugs that simulated testing had
masked. Hebrew Analysis v2 was not touched at any point. Nothing was merged
or pushed.

---

## 1. Credentials (found, not created)

Per the explicit instruction not to ask for new credentials before checking
existing ones: the main Textus checkout's own `.streamlit/secrets.toml` had
its `[supabase]` block commented out, but three other local worktrees
(`hebrew-analysis-v2-audit-efc152`, `repo-preflight-audit-0a9ce5`,
`textus-illustration-db-plan-6e94d2`) already had an active one. Copied that
file into this worktree's `.streamlit/` directory (a local, non-git file
copy — `secrets.toml` is gitignored) so the normal Textus loading path
(`supabase_client._load_supabase_secrets()`: env → project `secrets.toml` →
`st.secrets`, first source wins; `app._load_builtin_api_key()`: identical
order) picks it up. Both credentials verified present via the app's own
loader functions, boolean result only:

- **Supabase: FOUND** — project `secrets.toml`, `[supabase]` block.
- **Gemini: FOUND** — project `secrets.toml`, top-level `GEMINI_API_KEY`.

**Incident:** one verification command printed both secret values in
plaintext into the session transcript (a too-broad `grep` pattern, not a
system limitation). Flagged to the user immediately; recommended rotating
both keys. No further command in this session printed a credential value.

## 2. Remote schema verification

Read-only checks against the real project confirmed it is genuinely
production (not a sandbox): `hebrew_verses` (23,213 rows) and
`hebrew_tokens` (305,635 rows) exist and were read only for reference, never
written. Before any migration: all 10 `greek_*` tables did not exist
(`PGRST205`). After the user applied all three migrations in the Supabase
SQL Editor:

- All 10 `greek_*` tables: **EXISTS, 0 rows** (clean slate).
- `get_greek_verse_syntax_bundle` RPC: **exists, callable** (verified with a
  nonexistent verse ref, got the expected empty-shaped bundle).
- `bulk_link_greek_clause_parents` / `bulk_link_greek_phrase_parents` RPCs:
  initially **missing** (migration 3 had not actually been applied — the
  PostgREST error hint pointed at Hebrew's own `bulk_link_clause_parents`,
  confirming no Greek-named function existed at all, not a schema-cache
  lag). Re-verified after the user applied migration 3: **exist, callable**,
  and the cardinality guard correctly raises on a deliberately mismatched
  test call.
- Key columns from both Phase 2C schema fixes spot-checked directly:
  `greek_phrases`/`greek_clauses.macula_group_id`, `.parent_phrase_id`,
  `greek_token_alignments.alignment_status`/`.unresolved_category`,
  `greek_syntax_membership.member_order` — all present.
- PK/FK/index/grant introspection: no direct SQL or Management API access
  is available from this environment (no `psycopg2`/`asyncpg`, no DB
  connection string) — not independently re-verified beyond the applied
  migration text (already reviewed against commit `002d8a0`) and the
  service-role read/write behavior these checks themselves exercised.

## 3. Bounded real import benchmark

Ran the importer's new `--books` flag (added this session) against 10 small
books (Php, Col, 1Th, 2Th, Tit, Phm, Jud, 1Jn, 2Jn, 3Jn — ~94,000 rows total
across all 9 tables) with `--execute` against the real project:

```
Done in 32.6s — verses:564 tokens:9818 lexicon_hu:5959 source_nodes:9552
token_alignments:9818 phrases:3772 clauses:2647 syntax_membership:46725
semantic_roles:2708 coreference:3205
```

~2,890 rows/sec aggregate, zero retries, bulk parent-link RPCs completed in
under 0.3s each. Remote counts matched the importer's own report exactly.
Not pathological — proceeded to the full import.

**Bug found and fixed before the full import:** `greek_syntax_membership`
had no scoped-delete step at all (unlike Hebrew's precedent), so re-running
the importer (bounded subset, then full corpus) would have silently
duplicated membership rows for every group re-imported via natural-key
upsert. Added `delete_where_in` (mirroring Hebrew's own) scoped to the
specific phrase/clause remote ids being reimported, in both `RemoteWriter`
and `DryRunWriter`, before the full run.

## 4. Full production import

`python scripts/import_greek_syntax_to_supabase.py --execute` (default,
27-book corpus) completed in **409.5s (~6.8 min)**, zero retries:

```
verses:7958 tokens:142096 lexicon_hu:5959 source_nodes:137741
token_alignments:142096 phrases:47613 clauses:43835
syntax_membership:635861 semantic_roles:41440 coreference:38337
```

Identical to the local dry-run's own counts to the row. Hebrew data
untouched throughout (never read via a write path, only the two read-only
reference checks in §2).

## 5. Remote counts / invariants — exact match, local store as authority

| Table | Remote | Local (authority) |
|---|---:|---:|
| greek_verses | 7,958 | 7,958 |
| greek_tokens | 142,096 | 142,096 |
| greek_source_nodes | 137,741 | 137,741 |
| greek_token_alignments | 142,096 | 142,096 |
| greek_phrases | 47,613 | 47,613 |
| greek_clauses | 43,835 | 43,835 |
| greek_syntax_membership | 635,861 | 635,861 |
| greek_semantic_roles | 41,440 | 41,440 |
| greek_coreference_links | 38,337 | 38,337 |
| greek_lexicon_hu | 5,959 | 5,959 |

**Alignment-status distribution** (remote): EXACT 135,397 + COMPOSITE 1,344
+ VALIDATED_FALLBACK 651 + UNRESOLVED_TEXTUAL_VARIANT 3,055 +
UNRESOLVED_OTHER 1,649 = 142,096 — sums exactly, no unresolved row was
silently dropped or converted to resolved.

**Syntax-grounding distribution** (local store, authoritative — computed by
`scripts/report_greek_syntax_grounding.py`): **FULLY_GROUNDED_SYNTAX 69.43%
(5,525) / PARTIALLY_GROUNDED_SYNTAX 30.28% (2,410) / NO_GROUNDED_SYNTAX
0.29% (23)** — matches the Phase 2B.1 expected figures exactly. (No
`greek_participants`/`greek_syntax_edges` tables exist by design — see
Phase 2C doc §2 for why; nothing to compare there.)

`original_language_dataset_versions` gained exactly 5 new active rows
(tagnt, tegmc, tbesg, greek_hu_lexicon, macula_greek_sblgnt) alongside
Hebrew's pre-existing 2 (tahot, macula_hebrew_lowfat) — all 7 active,
Hebrew's untouched.

**No unexplained difference anywhere in this section.**

## 6. Real Local ↔ Supabase parity — five real bugs found and fixed

`tests/test_greek_analysis_repository_real_supabase_parity.py` (new) hits
the **live, deployed** RPC via `SupabaseGreekAnalysisRepository`'s default
client for all 15 regression verses, comparing every field the task listed
(token order/ids, lemma, morphology, lexical identity/provenance,
alignment, phrases, clauses, syntax membership, semantic roles,
coreference, detected constructions, grounding status) against
`LocalGreekAnalysisRepository`. **First run: 19 of 30 checks failed.** Real
end-to-end testing against live data found what the Phase 2C simulated-
payload test (built from a per-verse-scoped simulation) had structurally
masked:

1. **Cross-verse semantic-role arguments silently dropped locally.**
   `bible_engine/greek_analysis_repository.py` and
   `bible_engine/greek_syntax_service.py` both built their MACULA↔TAGNT
   alignment map scoped to only the queried verse's own tokens — but a
   role's argument (e.g. a participle's understood subject, named several
   verses earlier) routinely lies in a different verse. The Supabase
   import (built with a genuinely global map) resolved these correctly;
   local silently dropped them. Fixed: both files now do one narrowly-
   targeted extra lookup for any "other side" xml_id not in the per-verse
   map — example found: Mt 9:18's participle "having come" (word 19/20)
   correctly links back to "Jesus" named in Mt 9:15.
2. **Cross-verse coreference targets silently mistyped.**
   `greek_syntax_service.py` fell back to the *raw MACULA xml_id* when a
   coreference target wasn't in the per-verse map (`macula_to_tagnt.get(x,
   x)`) — a differently-typed, inconsistent value the Supabase side never
   produces. Fixed to resolve via the same extra lookup, matching the
   importer's skip-if-truly-unresolvable behavior instead of a wrong-typed
   fallback.
3. **Cross-verse clause/phrase membership dropped.** A clause or phrase can
   span a verse boundary (e.g. Mt 28:19-20's one long sentence) — its
   member tokens on the far side were silently excluded locally for the
   same per-verse-scoping reason. Fixed with the same extra-lookup
   mechanism, applied to group membership too.
4. **A predicate/source lookup could be "hijacked" by an unrelated
   cross-verse resolution.** The first attempt at fix #1–3 merged the
   extra-resolved ids directly into the *same* map used for predicate/
   source lookups — which let an xml_id resolved for one row's argument
   leak into and silently override a *different* row's predicate/source
   lookup (observed: several 2Pt 1:1 / Mk 1:9-11 roles appearing with a
   predicate from a wholly unrelated verse). Fixed by keeping a strict
   per-verse map for predicate/source and a separate combined map for
   argument/target/membership resolution — never merged.
5. **Missing dual-parent-type representation.** `GreekPhraseAnalysis` had
   no field for "my parent is a clause" and `GreekClauseAnalysis` none for
   "my parent is a phrase" — even though real MACULA data has both (a
   phrase's parent can be a clause and vice versa; see the Phase 2C
   schema's own `greek_clauses.parent_phrase_id` fix). Local code blindly
   stuffed the raw group id into `parent_phrase_id` regardless of the
   parent's real type; the Supabase-side parsing simply discarded whichever
   column didn't match the dataclass's one field. This produced a false-
   positive `coordinated_structure` detection in Lk 10:25-37 (two
   unrelated clause-parented phrases both showing `parent_phrase_id=None`
   and being grouped as "siblings" by the detector). Fixed by adding both
   fields to the shared dataclasses (`greek_analysis_bundle.py`), fixing
   both local attach functions to determine and set the correct one, fixing
   `_parse_bundle_payload` to read both columns (the RPC already returned
   them), and fixing `_detect_coordinated_structures` to group by the full
   `(parent_phrase_id, parent_clause_id)` identity and never treat "no
   parent" as a shared sibling group.
   
   A related, independent design inconsistency was found alongside #1:
   `greek_syntax_service.py`'s role query matched when *either* the
   predicate or the argument was in-verse (`OR argument_xml_id IN (...)`),
   diverging from `greek_analysis_repository.py`'s and the Supabase
   import's own predicate-owns-the-verse convention. Aligned to the
   stricter, consistent convention.

None of this touched `bible_engine.greek_token_alignment` (the alignment
algorithm) — every fix is in the syntax-attachment/repository layer that
consumes already-computed alignments, or in the shared data model.

**After all five fixes: 30/30 real parity checks pass** for all 15
regression verses, across every deterministic field and detected
constructions.

**Also fixed:** the Phase 2C *simulated*-payload parity test
(`tests/test_greek_analysis_repository_parity.py`) was updated to build its
own maps globally rather than per-verse (matching the real importer), so it
no longer silently agrees with a locally-buggy implementation — now a
genuine (if secondary) regression guard rather than a false-positive risk.
All 45 of its checks still pass.

## 7. Real network read-path performance

Measured against the live project via `SupabaseGreekAnalysisRepository`:

| Scope | Total time | Per-verse avg | RPC calls |
|---|---:|---:|---:|
| 1 verse | 1,524 ms (cold) | — | 1 |
| 10 representative verses | 2,166 ms | 217 ms | 10 |
| 1 chapter (Jn 3, 36 verses) | 7,731 ms | 215 ms | 36 |

Confirmed by code inspection: `get_verse_syntax()` issues exactly one
`client.rpc("get_greek_verse_syntax_bundle", ...)` call — no N+1 pattern,
never the up-to-9-sequential-calls-per-verse mistake the architecture was
explicitly designed to avoid (Hebrew's original approach, fixed in this
repo's own commit `2188955`). ~215 ms/verse (after connection warm-up) is a
normal single-RPC round trip and is not pathological for a per-word-click
UI that fetches one verse at a time.

## 8. Live Gemini 2.5 Flash quality test

`scripts/live_gemini_quality_test.py` (new) ran the **real**
Supabase-backed bundle through the **real** contextual-analysis prompt and
validator, calling Gemini 2.5 Flash directly via the same REST endpoint/
schema/system-prompt `app.py` uses, with the real `GEMINI_API_KEY`. 7/7
calls succeeded (14.0–34.7 s each, all well within the 40 s timeout),
covering aorist, imperfect, perfect, middle voice, chained participles,
genitive absolute, and — deliberately — a genuine NO_GROUNDED_SYNTAX verse
(**Mk 9:44**, absent from SBLGNT/the critical text, hence zero MACULA
alignment).

**What worked well:**
- Morphology correctness: no factual errors across all 7 (deponents,
  moods, voices, tenses all correctly identified).
- Lexical vs. contextual meaning: cleanly separated in every word note.
- **NO_GROUNDED_SYNTAX (Mk 9:44) behaved exactly as designed**: all 5 word
  notes show `syntax_role=''` (5 validator warnings confirm each was
  actively zeroed), `syntax_summary=''`, and the model *itself* correctly
  flagged the verse's textual-critical status ("this verse does not appear
  in NA28/UBS5...") as a warning — the strongest possible proof point for
  the architecture's core guarantee.
- **Evidence-grounding contract proven both directions on live output**:
  Mt 28:19-20 produced 3 invalid-evidence-id rejections (the model cited
  raw token ids as if they were construction evidence) — correctly
  discarded; the same response's truncation (400→320, 341→320 chars) fired
  cleanly with the expected "…" marker.
- Genuine interpretive restraint on the named risk cases: 1Tim 3:1's middle
  voice (ὀρέγεται) was explained as subject-affectedness/for-one's-benefit,
  never "reflexive"; deponent πορευθέντες was correctly noted as
  active-in-meaning despite its passive/middle form; Jn 1:1's anarthrous
  θεός was given the standard qualitative (not indefinite/definite) reading
  without collapsing Father/Son distinction; participle function was
  consistently offered as "X or Y" rather than asserted flatly.

**One actionable, non-blocking finding:** two explanations closely
paraphrased mechanically-forbidden formulas without matching the literal
string — Jn 19:30 described the aorist as marking a "pontszerű eseményt"
(point-like *event*) where the forbidden string is "pontszerű *cselekvés*"
(point-like *action*), and separately described the perfect almost
word-for-word as "a past action whose result continues into the present" —
the same idea as the banned formula in different phrasing. The mechanical
screen is documented as a backstop against the clearest violations, not
every paraphrase (the prompt's own instructions are the first line of
defense) — this is a real, concrete gap in that backstop, not a functional
failure of the architecture, and is not a blocker. Recommend broadening the
forbidden-phrase list with a few paraphrase variants as a low-cost
follow-up.

## 9. Production UI path

Re-confirmed (per Phase 2C's own trace): `app.py` →
`bible_engine.greek_analysis_ui.render_greek_analysis_block()` →
`_render_loaded_greek_passage_analysis()` → `_render_analysis_panel()` →
`bible_engine.greek_contextual_analysis_ui.render_greek_contextual_analysis_panel()`,
which calls `get_greek_analysis()` + `attach_syntax_via_repository(bundle,
get_default_greek_analysis_repository())` — the repository-abstraction path
now proven correct in §6, not the separate (also-fixed, but not
production-used) `get_greek_analysis_with_syntax()` path.

Ran the 8 UI integration tests with `TEXTUS_GREEK_ANALYSIS_BACKEND=supabase`
explicitly set: **8/8 pass**, and the Supabase client library's own
deprecation warnings appear in the test output — proof the real client was
actually instantiated and hit the live project during these AppTest runs,
not a mock. Confirmed again: no Gemini call on initial render, none on word
selection, exactly one on explicit "Kontextuális elemzés generálása" click,
cache reuse across word clicks, deterministic UI survives a
timeout/failure.

## 10. Cache behavior

Unchanged from Phase 2C: `st.session_state`-based (per-session, not
`st.cache_resource`), keyed by `(verse_id, dataset_version_signature,
prompt_version, model_id)`. No further issues found this session.

## 11. Production config

Verified directly from `bible_engine/greek_analysis_repository.py`
(`_configured_greek_analysis_backend()`):

```
TEXTUS_GREEK_ANALYSIS_BACKEND = "supabase"
```

(env var; defaults to `"local"` if unset or any other value). **Not set in
Streamlit Cloud** — this session only verified it locally and did not touch
any Cloud secrets, per instruction. Setting this one variable in the
deployed app's secrets is the actual activation step; until then, the
deployed app continues reading the local SQLite store exactly as before.

## 12. Tests

```
tests/test_greek_contextual_analysis_grounding.py            16
tests/test_greek_contextual_analysis_ui.py                    8  (+ 8 again with SUPABASE backend forced)
tests/test_greek_analysis_repository_parity.py                45
tests/test_greek_analysis_repository_real_supabase_parity.py  30  (NEW — live project)
tests/test_greek_contextual_analysis_regression_fixtures.py   16
tests/test_greek_syntax_safety_rules.py                        9
                                                        total 124 (132 counting the backend-forced UI rerun)
```

Full existing Greek suite (every phase's own tests, run together):

```
pytest tests/test_greek_*.py tests/test_tagnt_*.py tests/test_tbesg_*.py \
       tests/test_lexicon_*.py tests/test_morphology_hu.py \
       tests/test_nt_lexicon_coverage.py tests/test_missing_tagnt_strong_audit.py \
       tests/test_original_language_*.py tests/test_audit_greek_lexicon_quality.py
602 passed, 5 skipped (known/expected) in 112.23s
```

Zero regressions. `git status` shows no unintended file mutations after any
run this session.

## 13. Remaining items (not blockers)

1. **Deployment activation step**: set `TEXTUS_GREEK_ANALYSIS_BACKEND=supabase`
   in the deployed app's Streamlit Cloud secrets when ready to cut over —
   deliberately not done from this session per instruction.
2. **Forbidden-phrase paraphrase gap** (§8): broaden the mechanical
   safety-net phrase list with a few close paraphrases of the aorist/
   perfect formulas found live. Low cost, not urgent — the prompt-level
   instruction remains the primary defense and was itself largely
   respected.
3. **Credential rotation**: rotate the Gemini and Supabase keys exposed in
   this session's transcript (§1) at the user's convenience.
4. PK/FK/index/grant introspection (§2) was not independently re-verified
   beyond the reviewed migration text and observed read/write behavior —
   no tooling for direct SQL access exists in this environment.

None of these block a merge/deploy decision on the code itself.

## 14. Status

**READY TO MERGE AND DEPLOY**

The Greek Analysis v2 Supabase backend is live, fully imported (exact
row-count and grounding-distribution match against the local-store
authority), passes 30/30 real end-to-end parity checks against production
after five genuine bugs were found and fixed via that same real testing,
performs a single RPC round trip per verse at normal network latency, and
produced correct, safety-respecting output from 7/7 real Gemini 2.5 Flash
calls — including the architecturally critical NO_GROUNDED_SYNTAX case
behaving exactly as designed. The production UI path was re-traced and
proven (not merely inspected) to use the Supabase backend correctly when
selected. 602 pre-existing tests plus 124 new/updated tests all pass with
zero regressions. The only remaining action is the deployment-time
`TEXTUS_GREEK_ANALYSIS_BACKEND=supabase` config flip, which was
intentionally left for the user to apply.
