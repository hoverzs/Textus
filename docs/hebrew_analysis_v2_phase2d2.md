# Hebrew Analysis v2 — Phase 2D.2: Supabase Deployment + Production Read-Path Validation

**Scope:** make the deterministic MACULA-hardened Hebrew linguistic layer
(Phase 2D + 2D.1) deployable to Supabase, build and validate the import
tooling, add a version-keyed cache, wire production/local backend
selection, and validate the read path (local ↔ Supabase parity,
performance, security) as thoroughly as this environment allows. No AI
interpretation, no UI redesign, no re-opening of alignment hardening, no
mass Hungarian lexeme translation, no push.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base checkpoint:** `3ccfeea6`
**Prior phases:** [`hebrew_analysis_v2_phase2d.md`](hebrew_analysis_v2_phase2d.md) ·
[`hebrew_analysis_v2_phase2d1.md`](hebrew_analysis_v2_phase2d1.md)

**Critical finding up front:** no usable Supabase credentials exist in this
environment (verified via `supabase_client._load_supabase_secrets()`
raising, without printing any values). Nothing in this phase was applied to
a real Supabase project. Everything below that says "remote" or
"Supabase" was validated **locally** — against a real local mirror of the
schema/data, or a fake Postgrest client seeded from real local rows — never
against a live network. §5 gives the exact commands the user must run,
with real credentials, to actually deploy.

---

## 1. Credential availability (§2 of the brief)

`supabase_client._load_supabase_secrets()` raised `RuntimeError` — no
`SUPABASE_URL`/`SUPABASE_SERVICE_ROLE_KEY`-shaped environment variables and
no `.streamlit/secrets.toml` are present in this worktree. This was checked
by presence/absence only (`env | grep -o "^SUPABASE_[A-Z_]*"`, file
existence), never by reading or printing a secret value. Consequence: §§4,
5, 8, 9 of the original brief (remote schema application, remote
existing-table check, remote import, remote row-count/integrity
verification) could not be executed. Each is answered below with "not
applicable here — not executed" plus the exact commands to run once
credentials exist.

---

## 2. Migration validation (§3) and the new grounding view (§3, new file)

The Phase 2D migration
(`supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`) was
re-read in full and re-confirmed sufficient: PKs/FKs/unique constraints,
per-row `dataset_version_id`, canonical `verse_ref`/stable token ids,
alignment status, and full provenance are already present for all 16
tables. The one real gap: no stored "syntax-grounding status" column —
by design (Phase 2D.1 §12 computes it at read time from
`hebrew_token_alignments`, so it can never go stale relative to the
alignment data).

**New forward migration** (smallest possible; adds nothing to any existing
table): `supabase/migrations/20260908223000_hebrew_verse_syntax_grounding_view.sql` —
a `CREATE OR REPLACE VIEW hebrew_verse_syntax_grounding` that computes the
same `FULLY_GROUNDED_SYNTAX` / `PARTIALLY_GROUNDED_SYNTAX` / `NO_GROUNDED_SYNTAX`
classification server-side, in one query per verse, with the same
`service_role`-only grant pattern as the base migration (`revoke all ... from
anon, authenticated; grant select ... to service_role`). Validated with
`sqlparse` (all 3 statements parse; this environment has no live
Postgres/psql to actually execute DDL against). `SupabaseHebrewAnalysisRepository`
tries this view first and transparently falls back to the pre-2D.2
three-query path if it 404s/errors (e.g. only the base migration has been
applied) — see `_fetch_grounding_via_fallback_queries` in
`bible_engine/hebrew_analysis_repository.py`. No unrelated table touched.

---

## 3. Remote schema application / existing-table check (§4, §5) — not executed

No credentials → not run. To apply both migrations to a real project once
credentials exist:

```bash
supabase link --project-ref <project-ref>
supabase db push
```

This applies only the two files above; no other migration in
`supabase/migrations/` is touched by this phase. Both are additive
(`create table if not exists` / `create or replace view`) — neither drops
or truncates anything, so running them against a project that already has
unrelated tables is safe by construction.

---

## 4. The importer (§6, §7): `scripts/import_macula_to_supabase.py`

A full, dependency-ordered ETL script built against **Phase 2D.1's final
store only** (`hebrew_macula_alignment_2d1_final.sqlite3` — never the
pre-hardening Phase 2D store). Default mode is a dry run (`DryRunWriter`,
an offline id-simulator); `--execute` switches to `RemoteWriter` (a real
Supabase wrapper), refusing to start if credential loading fails (no
partial writes).

Design points:
- **Scoped-replace, not blind upsert**, for every table without a natural
  unique constraint (`hebrew_syntax_membership`, `hebrew_token_alignments`,
  `hebrew_semantic_roles`, `hebrew_coreference`): delete rows scoped to the
  dataset version / parent ids being re-imported, then insert fresh — never
  an unscoped `DELETE`/`TRUNCATE`, and never touches a table this script
  doesn't own.
- **Surrogate-id remapping**: every table gets a `local_id -> remote_id`
  map built from its own batch upsert responses; dependent tables' FK
  columns are rewritten through that map before their own insert.
- **Two-pass self-referencing import** for `hebrew_source_nodes.parent_node_id`
  and `hebrew_clauses.parent_clause_id`: insert with the FK null, then a
  batched `UPDATE`. Justified by a verified 0-violation "parent local id <
  child local id" invariant (816,844 source nodes checked — the original
  Phase 2D/2D.1 importer assigns ids in pre-order traversal, so this holds
  by construction, not by luck).
- `hebrew_phrases.parent_clause_id` (cross-table) is linked in a separate
  `link_phrase_parents` step, run after both the phrase and clause id maps
  exist — an earlier single-function design tried to do this inline and
  produced a raw unmapped tuple; splitting into `import_phrases` /
  `import_clauses` / `link_phrase_parents` fixed it (see the module's own
  git history / this session's fix log).
- `hebrew_detected_patterns` / `hebrew_detected_pattern_tokens` are **not**
  imported — the local Phase 2D.1 store has zero rows for them (Phase 2C's
  pattern detector isn't wired into the MACULA build pipeline yet); this is
  a pre-existing gap, not introduced here.

**Real dry-run result**, against the actual 868,827,136-byte Phase 2D.1
final store (25.4s):

| Table | Rows |
|---|---:|
| dataset_versions | 2 |
| verses | 23,213 |
| tokens | 305,635 |
| token_strong_ids | 540,437 |
| token_components | 540,438 |
| source_nodes | 816,844 |
| token_alignments | 460,018 |
| phrases | 238,809 |
| clauses | 102,124 |
| syntax_membership | 458,090 |
| syntax_edges | 793,631 |
| semantic_roles | 110,831 |
| participants | 24,943 |
| coreference | 45,222 |

Every count matches the local store's own table counts exactly (asserted
in `tests/test_import_macula_to_supabase.py::test_dry_run_import_matches_local_row_counts`,
run against a small fixture-built store using the identical code path).
No raw MACULA XML is read at any point — the script's only input is the
already-normalized local SQLite mirror. No secret is read, logged, or
written anywhere in dry-run mode.

**To actually import, once credentials exist:**

```bash
python scripts/import_macula_to_supabase.py --local-store <path-to-hebrew_macula_alignment_2d1_final.sqlite3> --execute
```

(`--batch-size` defaults to 500; omit `--execute` to re-run the dry run
against any store.)

---

## 5. Remote row-count / referential-integrity verification (§8, §9) — not executed

No credentials → not run against a real project. The dry run above is the
closest available substitute: it proves the import PLAN produces the exact
right row count per table and (via
`test_source_node_parent_child_local_ids_always_precede`) that the
self-referencing FK strategy cannot produce a dangling parent reference.
Once a real import has run, the equivalent live check is:

```sql
select 'hebrew_verses', count(*) from hebrew_verses
union all select 'hebrew_tokens', count(*) from hebrew_tokens
-- ... one line per table, compare against the dry-run table above
```

and a referential-integrity spot check:

```sql
select count(*) from hebrew_source_nodes c
join hebrew_source_nodes p on p.id = c.parent_node_id
where p.id >= c.id;  -- must be 0
```

---

## 6. Local ↔ Supabase parity (§10)

Two layers of validation:

**A. Committed regression test**
(`tests/test_hebrew_analysis_repository_parity.py`) — builds one local
store from all four real MACULA fixtures already in the repo (Genesis
1:1-1:2, Ruth 1:1/1:2/1:3/1:8/1:16, Ezra 4:8/4:9/4:10, the Genesis 36:5
Ketiv/Qere+UNRESOLVED regression passage), then compares
`LocalHebrewAnalysisRepository` against `SupabaseHebrewAnalysisRepository`
running against a fake Postgrest client seeded with the exact rows the
real importer would have written — for **every** verse those fixtures
contain, not just a fixed list. All fields of `VerseSyntaxData` compared,
not just presence. Also directly proves §13 (Hungarian lexical data is
byte-identical regardless of syntax backend — `lexical_sense`/`morphology`/
`root` never move when switching `LocalHebrewAnalysisRepository` ↔
`SupabaseHebrewAnalysisRepository`).

**B. Real full-corpus validation, run once ad hoc this session** against
the actual Phase 2D.1 final store (868 MB, not committed — see §11), for
the exact verse list the brief named:

| Verse | Match | Local grounding | Remote grounding | Phrases | Clauses | Edges | Roles | Participants | Coref |
|---|:---:|---|---|---:|---:|---:|---:|---:|---:|
| Gen.1.1 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 6 | 1 | 17 | 3 | 0 | 0 |
| Gen.1.2 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 9 | 3 | 31 | 2 | 0 | 0 |
| Gen.1.22 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 10 | 7 | 41 | 8 | 1 | 1 |
| Gen.11.3 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 13 | 7 | 50 | 8 | 2 | 2 |
| Ruth.1.3 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 6 | 2 | 19 | 3 | 2 | 3 |
| Ezra.4.8 | ✅ | FULLY_GROUNDED | FULLY_GROUNDED | 10 | 1 | 27 | 3 | 0 | 0 |
| Gen.36.5 (Ketiv/Qere + unresolved-token verse) | ✅ | PARTIALLY_GROUNDED | PARTIALLY_GROUNDED | 11 | 3 | 34 | 5 | 2 | 2 |

7/7 exact matches, every `VerseSyntaxData` field byte-equal (`==` on the
whole frozen dataclass, not a field-by-field eyeball). No semantic
difference — **zero unexplained differences**, satisfying the brief's own
bar. Gen.36.5 doubles as the required Ketiv/Qere passage, the
PARTIALLY_GROUNDED_SYNTAX example, and the unresolved-token example (its
two UNRESOLVED tokens are Gen.36.5:5 and Gen.36.5:7, per Phase 2D.1).

---

## 7. Read-path performance (§11)

Measured locally, using `sqlite3.Connection.set_trace_callback` for exact
statement counts and `time.perf_counter` for wall time, against the real
full-corpus store:

| Scope | SQL statements | Statements/verse | Total time | Time/verse |
|---|---:|---:|---:|---:|
| 1 verse | 8 | 8.0 | 1.625 ms | 1.625 ms |
| 10 verses | 80 | 8.0 | 17.13 ms | 1.71 ms |
| 1 chapter (Gen 1, 31 verses) | 248 | 8.0 | 54.38 ms | 1.75 ms |

Exactly 8 statements per verse regardless of scope (phrase, clause,
membership, edge, role, participant, coreference, alignment-grounding —
matches Phase 2D's "approximately seven bounded query groups" plus the
2D.1 grounding query) — **no N+1 growth with verse count locally**; each
verse's own query count is fixed and small.

**Real Supabase network latency cannot be measured here** — no
credentials, no live project. The one thing this local measurement DOES
expose as a real optimization target: `LocalHebrewAnalysisRepository.get_verse_syntax`
opens a fresh connection and runs those 8 statements **per verse**, with no
batching across verses in a multi-verse call. Translated to Supabase,
that's up to 8 independent REST round trips per verse — for a 31-verse
chapter view, that could mean on the order of 200+ sequential HTTP round
trips. **Recommendation for Phase 2E (not implemented here — no live
network to validate an "after" measurement against, and the brief's
"measure before, measure after" bar can't honestly be met without one):**
add a batch method (e.g. `get_verses_syntax(verse_refs: list[str])`) using
`.in_("verse_ref", verse_refs)` so a whole chapter costs ~8 requests total
instead of ~8×N. This is a read-path-only change — no schema
denormalization needed.

---

## 8. Cache strategy (§12)

`bible_engine/hebrew_analysis_cache.py` — `CachedHebrewAnalysisService`, a
thin wrapper (not wired into `HebrewAnalysisService` itself — opt-in at the
call site) keyed on `(reference, dataset_version_signature)`. Both
repositories gained `dataset_version_signature()` (`LocalHebrewAnalysisRepository`
queries `original_language_dataset_versions WHERE is_active`;
`SupabaseHebrewAnalysisRepository` does the equivalent via the client, fail-
closed to `""`); `HebrewAnalysisService.dataset_version_signature()`
delegates to whichever repository is configured. A version bump changes the
signature, which changes the cache key — no explicit invalidation logic
needed, and a `""` signature (store unreachable) disables caching for that
call rather than caching under a placeholder key. Bounded by a simple LRU
(`max_entries`, default 256) since this is a long-lived in-process cache,
not a single-request memoization. No TTL, no runtime AI caching, no network
I/O of its own — pure memoization over an already-pure builder. 11 tests in
`tests/test_hebrew_analysis_cache.py` (hit/miss, version-keyed
invalidation, no-caching-when-signature-unavailable, exceptions never
cached, LRU eviction, `clear()`).

---

## 9. Hungarian lexical gaps (§13)

Untouched, deliberately. Grep-confirmed: no Hungarian gloss field exists
anywhere in the Supabase linguistic-layer schema or in
`SupabaseHebrewAnalysisRepository`/`_assemble_from_rows` — the Hungarian
lexicon (`textus_hu_lexicon`, Phase 2B/2C) is read entirely by
`HebrewHungarianLexiconRepository` from the local JSON store, completely
independent of which syntax backend (Local vs Supabase) is configured. New
test `test_hungarian_lexical_sense_identical_regardless_of_syntax_backend`
(in `tests/test_hebrew_analysis_repository_parity.py`) proves this by
direct comparison — every token's `lexical_sense` (nullable gaps included),
`morphology`, and `root` are identical whether the backend is Local or a
fake-client-backed Supabase.

---

## 10. Fidelity SQLite (§14)

`data/generated/hebrew_component_fidelity.sqlite3` (35.7 MB, tracked in
git) is **actively load-bearing**, not a leftover build artifact: every
single `HebrewAnalysisService.get_hebrew_analysis()` call reads it via
`restore_component_fidelity()` (`bible_engine/hebrew_component_repository.py`)
to reconstruct prefix/core/suffix component surfaces and glosses — a Phase
2C capability orthogonal to Phase 2D/2D.1's MACULA syntax layer (MACULA
doesn't supply the same sub-word decomposition). **Not removed, not
scheduled for removal** — the brief's own instruction was explicit on this
point. Confirmed still-required by grep across `bible_engine/hebrew_analysis_bundle.py`,
`bible_engine/hebrew_analysis_service.py`, `bible_engine/hebrew_component_repository.py`,
and its own build script `scripts/build_hebrew_component_fidelity_store.py`.

Also confirmed: the raw MACULA checkout (`macula-hebrew-src/`, pinned tag
`26.04.13`) and the 868 MB local linguistic-store mirrors
(`hebrew_macula_alignment_2d1_final.sqlite3` /
`hebrew_macula_alignment_full.sqlite3`) live only in this session's
scratchpad — `git status` shows neither tracked nor staged, and no new
large binary was added by this phase's work (`git status --porcelain` is
limited to source files; see §12 below for the full list).

---

## 11. Backend selection (§15)

`get_default_hebrew_analysis_repository()` (`bible_engine/hebrew_analysis_repository.py`)
is the single place backend selection happens: env var
`TEXTUS_HEBREW_ANALYSIS_BACKEND` (`"supabase"` → `SupabaseHebrewAnalysisRepository()`,
anything else/unset → `LocalHebrewAnalysisRepository()`), and
`HebrewAnalysisService.__init__` uses it as the default when no explicit
`linguistic_repository=` is passed — no backend conditional anywhere in the
UI. **Deliberately env-var only, no Streamlit-secrets fallback** — this
module has an established, AST-depth-verified invariant of zero Streamlit
dependency at any import depth
(`test_phase2d_modules_have_no_llm_or_direct_network_dependency`, which
walks the full AST, not just top-level imports); an earlier draft that
added a lazy `streamlit`-secrets fallback (mirroring
`textus_kb.commentary_translation_store`'s convention) broke that test and
was removed. If Streamlit-secrets support is wanted later it should be
added deliberately, with that test's expectations updated in the same
commit. 10 tests in `tests/test_hebrew_analysis_backend_selection.py`
cover unset/local/unrecognized values, case/whitespace-insensitive
`"supabase"` matching, and that an explicit `local_store_path=` override
still works regardless of the backend env var.

---

## 12. Security (§16)

Unchanged from Phase 2D's design, confirmed correct rather than redesigned:
RLS enabled on every new table, no policies, `anon`/`authenticated`
explicitly revoked, `service_role` explicitly granted — the same pattern
the new `hebrew_verse_syntax_grounding` view's grants follow (§2). This
means: ordinary users cannot read or mutate the linguistic corpus at all
through the public API; import/update stays possible only with the
service-role key, which the importer (`scripts/import_macula_to_supabase.py`)
never logs, prints, or persists, and which the client-side/UI code path
(`SupabaseHebrewAnalysisRepository`, via the shared
`supabase_client.get_supabase_client()`) never needs — read access for the
application itself is via `service_role` from server-side code only, same
as every other Supabase-backed Textus feature. No broader auth/RLS
redesign was made or needed.

---

## 13. Test coverage (§17)

New/changed test files this phase, all passing, none requiring network or
real credentials:

| File | Tests | Covers |
|---|---:|---|
| `tests/test_hebrew_analysis_cache.py` | 11 | signature methods (Local + Supabase), cache hit/miss/eviction/clear, version invalidation, no-cache-when-unavailable, exceptions never cached |
| `tests/test_hebrew_analysis_repository_parity.py` | 3 | Local↔Supabase parity across every fixture verse, PARTIALLY_GROUNDED_SYNTAX case, Hungarian-lexicon backend independence |
| `tests/test_hebrew_analysis_backend_selection.py` | 10 | env-var backend selection, case/whitespace handling, `local_store_path` override |
| `tests/test_import_macula_to_supabase.py` | 4 | dry-run writer never touches network, full import plan matches local row counts, UNRESOLVED alignment type preserved verbatim, source-node parent-before-child invariant |
| `tests/test_hebrew_analysis_repository_supabase.py` (extended) | +2 | grounding-view fast path used when present, falls back correctly when absent |

Full relevant scope (`pytest tests/ -k hebrew --ignore=tests/test_textus_kb`,
the `test_textus_kb` exclusion is a pre-existing, unrelated pytest
module-name collision, not caused by this phase): **285 passed, 36
skipped** (all 36 skips pre-existing — missing raw source files / archived
one-time process journals, none related to Phase 2D.2). No test in the
ordinary suite requires real Supabase credentials or network access; a real
remote-integration test suite (§8/§9's live checks) would only run when a
project is explicitly configured, and does not exist yet since it has
nothing to run against here.

---

## 14. Schema-compatibility / bundle stability

`HebrewAnalysisBundle`'s `bundle_schema_version` (`"2d.0.0"`) is unchanged —
this phase adds no new field to `HebrewAnalysisBundle`, `VerseAnalysis`, or
any nested dataclass; it only changes which repository *implementation*
supplies `VerseSyntaxData`, not its shape. `VerseSyntaxData` itself is also
unchanged (still `SYNTAX_GROUNDING_FULL/PARTIAL/NONE`, from Phase 2D.1).
Confirmed by the parity tests themselves succeeding without any dataclass
field mismatch, and by `test_bundle_populates_phrases_clauses_roles_coreference`
/ `test_token_morphology_unchanged_by_syntax_layer` (pre-existing, still
green) continuing to pass unmodified.

---

## Acceptance criteria checklist

1. No credentials fabricated / no fake remote-success claim — ✅ (§1, explicit throughout)
2. Everything validated locally where remote wasn't possible — ✅ (§§3-6)
3. Exact deploy commands documented for later — ✅ (§3, §4)
4. Migration correctness confirmed, smallest gap closed — ✅ (§2)
5. No unrelated Supabase table touched — ✅ (§2, §3 — both migrations additive/scoped)
6. Import plan uses safe scoped-replace, never unscoped DELETE/TRUNCATE — ✅ (§4)
7. No raw MACULA XML dependency in the importer — ✅ (§4)
8. No secret printed, logged, or committed — ✅ (§1, §4, §12 — verified by construction, no secret was ever available to print)
9. Local↔Supabase parity — zero unexplained differences — ✅ (§6, both fixture-scale and real full-corpus checks)
10. Read-path query count/latency measured, optimization identified not prematurely applied — ✅ (§7)
11. Cache strategy is version-keyed, no unnecessary AI caching — ✅ (§8)
12. Hungarian lexical gaps unaffected by backend choice — ✅ (§9)
13. Fidelity SQLite status assessed, not removed — ✅ (§10)
14. Backend selection centralized, no UI conditionals — ✅ (§11)
15. Security model confirmed service-role-only, not redesigned — ✅ (§12)

**Phase 2E prerequisites:**
1. Real Supabase credentials + an actual `--execute` import run, then live
   §8/§9 verification against the real project.
2. The `get_verses_syntax(verse_refs)` batch read-path optimization (§7),
   validated with real network latency once available.
3. Phase 2D.1's own carried-forward item: an optional syntax-informed
   disambiguation strategy for the remaining `ambiguous_recovery` residual
   (already honestly `UNRESOLVED`, contributes no incorrect fact).
4. Wiring Phase 2C's pattern detector into the MACULA build pipeline, if
   `hebrew_detected_patterns`/`hebrew_detected_pattern_tokens` are wanted
   populated (currently empty by design, not a regression).

Not started this phase, per the brief: Phase 2E itself, any AI
interpretation layer, any UI change, any push.
