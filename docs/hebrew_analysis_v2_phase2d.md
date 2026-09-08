# Hebrew Analysis v2 — Phase 2D: MACULA Syntax Integration + Supabase-Ready Normalized Linguistic Store

**Scope:** add syntax, phrase/clause structure, semantic roles, and
coreference from MACULA — deterministically, on top of (never replacing)
the verified Phase 2A/2B/2C TAHOT/TEHMC/TBESH foundation. Design a
Supabase-Postgres-ready normalized schema, a repository abstraction that
works identically against a local SQLite mirror or Supabase, and a
corpus-wide deterministic alignment between Textus/TAHOT tokens and MACULA
nodes. No AI-generated linguistic facts, no MACULA vendored into git, no
push.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base checkpoint:** `c9c3138`
**Prior phases:** [`hebrew_analysis_v2_inventory.md`](hebrew_analysis_v2_inventory.md) (audit) ·
[`hebrew_analysis_v2_phase2a.md`](hebrew_analysis_v2_phase2a.md) (deterministic correctness) ·
[`hebrew_analysis_v2_phase2b.md`](hebrew_analysis_v2_phase2b.md) (authoritative rebuild) ·
[`hebrew_analysis_v2_phase2c.md`](hebrew_analysis_v2_phase2c.md) (normalized bundle)

---

## 1. Existing Supabase architecture (audited before designing anything new)

Supabase IS already used in Textus, narrowly: one shared Postgres/Storage
backend behind a single hand-written client module, no formal repository
abstraction yet.

- **Client**: [`supabase_client.py`](../supabase_client.py) — `get_supabase_client()`, `@lru_cache(maxsize=1)`-memoized.
- **Env vars**: exactly `SUPABASE_URL` / `SUPABASE_KEY` (no separate anon/service-role pair). Fallback order: env → `.streamlit/secrets.toml` `[supabase]` → `st.secrets["supabase"]`.
- **Key class**: production `SUPABASE_KEY` is a **service_role-class secret** (always bypasses RLS). Since the app is server-side Streamlit, the key never reaches a browser. Access control is therefore **grant-based, not policy-based**: RLS enabled with no policies (default-deny for every non-service_role role), `anon`/`authenticated` explicitly revoked, `service_role` explicitly granted only the operations actually needed. This migration follows the exact same model — see §6.
- **Migrations**: **no `supabase/`, `migrations/`, or `db/migrations/` directory existed before this phase.** Schema changes are one-off `scripts/setup_*.py` scripts printing DDL for manual paste into the Supabase SQL Editor (the Supabase Python client cannot execute DDL). This phase introduces `supabase/migrations/` as a new, versioned convention (standard Supabase-CLI-compatible naming) while keeping the existing manual-apply script pattern via `scripts/setup_hebrew_linguistic_schema.py`.
- **Repository pattern**: `*_repository.py` is an established convention, but every existing one (`hebrew_token_repository.py`, `hebrew_lexicon_repository.py`, `hebrew_component_repository.py`, …) is local-SQLite-only. The best model for a dual-backend module is `textus_kb/commentary_translation_store.py` (env-var-selected `sqlite`/`supabase` backend, identical function signatures, fail-closed). `bible_engine/hebrew_analysis_repository.py` follows this same fail-closed contract, formalized as a `HebrewAnalysisRepository` interface with two classes.
- **Test convention**: no test hits real Supabase. `tests/test_textus_kb/test_commentary_translation_store_supabase.py` hand-rolls a fake Postgrest-style client and monkeypatches `supabase_client.get_supabase_client`. `tests/test_hebrew_analysis_repository_supabase.py` follows the identical pattern.
- **Dependency**: `requirements.txt` has a bare, unpinned `supabase` line.

---

## 2. MACULA source acquisition

| | Value |
|---|---|
| Repository | `Clear-Bible/macula-hebrew` |
| Tag (release) | `26.04.13` |
| Resolved commit SHA | `09f8ea9e25025841ec45e2b6e7fc01595a080568` |
| Retrieved | 2026-09-08 |
| Retrieval method | `git clone --filter=blob:none --sparse --no-checkout --depth 1 --branch 26.04.13`, then `git sparse-checkout set WLC/lowfat LICENSE.md README.md` |
| Representation used | `WLC/lowfat` only |
| License | CC BY 4.0 |
| Attribution | "MACULA Hebrew Linguistic Datasets, available at https://github.com/Clear-Bible/macula-hebrew/" — © 2022–2024 Biblica, Inc. |
| `WLC/lowfat` total size | 423,470,340 bytes (932 files) across the repo tree; local sparse checkout measured 417 MB |

**Representation chosen: `lowfat`, not `nodes` or `tsv`.** Per the
repository's own README: `WLC/tsv` carries **no syntactic tree structure
at all** (word-level table only) — explicitly ruled out by this phase's
brief. `WLC/nodes` is the same tree wrapped in several purely-syntactic
intermediate layers per leaf (`cjp` → `cj` → the leaf; `V` → `vp` → the
leaf) that add traversal depth without adding information a relational
import needs. `WLC/lowfat` gives the same tree with a flatter `<wg>`
(word/phrase group) / `<w>` (word) structure, and — critically for
alignment — every leaf's `ref` attribute (e.g. `"RUT 1:1!1"`) carries a
per-verse orthographic-word ordinal that was **empirically verified to
equal TAHOT's own `word_index`** (see §3). `lowfat` also directly encodes
`role` (syntactic function), `frame` (semantic role), and
`subjref`/`participantref` (coreference) as leaf/group attributes — the
exact three linguistic layers this phase needs — without extra tree
traversal.

**Raw MACULA data is NEVER committed to this repository** — the sparse
checkout lives only in the session scratchpad, used purely as offline
build input. `scripts/build_macula_alignment_store.py` (the offline
importer driver) takes `--macula-lowfat-dir` pointing at a local checkout
obtained via the commands above; nothing at runtime parses MACULA XML.

### 2.1 Real coverage discovered during this phase (correcting an earlier false finding)

An initial investigation (via the GitHub Tree API, cross-referencing book
codes with a regex that assumed book codes are alphabetic) appeared to
show 1–2 Samuel, 1–2 Kings, and 1–2 Chronicles missing from MACULA-hebrew
(`WLC/lowfat` jumping from `08-Rut-*` straight to `15-Ezr-*` in one
listing). This was **wrong** — caused by a book-code regex
(`[A-Za-z]+`) that didn't allow the leading digit in `1Sa`/`2Sa`/`1Ki`/
`2Ki`/`1Ch`/`2Ch`, silently filtering those 167 files out of the
investigation. Once corrected (`[A-Za-z0-9]+`), the actual corpus-wide
import (§5) confirms **MACULA-hebrew has full 39/39 OT/Aramaic book
coverage** at this pinned tag. This correction was caught and fixed
*before* any conclusion was written to a committed document.

---

## 3. Alignment strategy

Deterministic, evidence-based, per the brief's exact priority order,
implemented in [`bible_engine/hebrew_macula_alignment.py`](../bible_engine/hebrew_macula_alignment.py):

1. **Canonical verse reference** — alignment is only ever attempted
   between a TAHOT token and MACULA leaves already known to belong to the
   *same* verse; the module never searches across verses.
2. **Source/token ordering** — MACULA's `ref` attribute's trailing `!N`
   is a per-verse orthographic-word ordinal. Empirically verified against
   Ruth 1:1: TAHOT `word_index=1` is the single token `וַ/יְהִ֗י`, which
   `lowfat` splits into two `<w>` leaves — **both** carrying
   `ref="RUT 1:1!1"`. This is the primary key:
   `MaculaSentence.leaves_by_ref_word()[token.word_index]`.
3. **Normalized surface** / 4. **component surface sequence** — once the
   right leaf bucket is found, TAHOT components are paired against
   MACULA leaves left-to-right by position, and every pair's surface is
   compared after cantillation/niqqud stripping (`strip_hebrew_points`)
   as corroborating evidence.
5. **Lemma** (not independently available per-component on
   `HebrewComponent`, so this evidence source folds into the token-level
   comparison already covered by 3–4) and 6. **Strong identifier** —
   compared numeric-prefix-only (`_strong_numeric_prefix`), since
   STEPBible's lettered-homograph suffixes (`H1035G`) and MACULA's own id
   scheme don't share that convention.
7. **Morphology** is used only as validation text in `evidence`, never to
   decide alignment, and **never** to overwrite a TAHOT/TEHMC value (§4).

**Classification** (`ALIGNMENT_TYPES`): `EXACT` (1 component ↔ 1 leaf,
corroborated), `COMPOSITE` (N components ↔ N leaves, corroborated, paired
by position), `VALIDATED_FALLBACK` (counts didn't match positionally but
whole-token surface containment corroborated the match, or a
count-matched pairing had no independent corroboration), `UNRESOLVED`
(no MACULA leaves at that word position, or a count mismatch with no
surface corroboration). No fuzzy matching is silent — every alignment
carries an explicit type, confidence, and `evidence` string.

### 3.1 Two real structural cases discovered and specifically handled

- **Implicit/empty morphemes** — Ruth 1:1 word 7 (`בָּ/אָ֑רֶץ`) is 2 TAHOT
  components (prefix `בָּ` fusing preposition+article, core `אָ֑רֶץ`) but
  3 MACULA leaves (prep, an **empty-text** implicit-article leaf, noun).
  Handled: components/leaves are re-compared after excluding empty-surface
  MACULA leaves; if that reconciles the count, classified `COMPOSITE` with
  the exclusion noted in `evidence`.
- **Multi-word lexical compounds** — "בֵּית לֶחֶם" (Bethlehem, Ruth 1:1
  words 10–11) is stored as **two separate `<w>` leaves**, each one
  wrapped in a `<c>` "compound" container (not `<wg>`) and — surprisingly
  — **each carrying the FULL two-word text as its `unicode` attribute**.
  The parser (`macula_lowfat_parser._append_leaf`) uses the element's own
  **text content** (`בֵּ֧ית` vs `לֶ֣חֶם` respectively) as the true
  per-leaf surface, not the shared `unicode` attribute — a real,
  regression-tested parser fix (`test_compound_lexical_item_leaf_surface_uses_text_content_not_shared_unicode_attr`).
  `<c>` containers are walked identically to `<wg>` (both become
  `MaculaGroup` rows).
- **`frame`/`subjref`/`participantref` id convention** — these attributes
  reference other nodes' ids **without** the leading `"o"` that real
  `xml:id` values carry (e.g. `subjref="080010010091"` refers to
  `xml:id="o080010010091"`). Normalized via
  `hebrew_macula_importer._normalize_macula_ref_id` before every lookup.

---

## 4. Data authority rules

Enforced by construction, not just convention:

- **TAHOT/TEHMC remain authoritative** for Textus canonical token
  identity, Hebrew/Aramaic language determination, surface/component
  morphology, stem, conjugation/form, person, gender, number, state, and
  deterministic morphology confidence. `hebrew_analysis_service.py`'s
  token-building path (Phase 2C) is **completely untouched** by this
  phase — `HebrewAnalysisRepository` only ever supplies *syntax* data
  (`VerseSyntaxData`), attached to an already-fully-built `VerseAnalysis`.
  Regression-tested directly:
  `test_token_morphology_unchanged_by_syntax_layer` asserts token
  morphology/lexical-sense/root are byte-identical whether or not a
  syntax repository is wired in.
- **TBESH remains authoritative** for the lexical layer — untouched.
- **MACULA contributes**: syntax nodes (`hebrew_source_nodes`), phrase
  structure (`hebrew_phrases`), clause structure (`hebrew_clauses`),
  parent/child relationships (`hebrew_syntax_edges`), syntactic function
  where explicitly encoded (the `role` attribute), semantic roles where
  explicitly encoded (the `frame` attribute), participant/coreference
  relationships (`subjref`/`participantref`). Word-sense data (`sdbh`,
  `lexdomain`, `coredomain`, Mandarin/Greek glosses, sense numbers) is
  captured only inside `hebrew_source_nodes.raw_attributes` (JSONB) — kept
  as supplementary provenance, never promoted to a first-class Textus
  field.
- **Disagreement handling**: `hebrew_source_nodes` carries MACULA's own
  `macula_morph_code`/`macula_part_of_speech`/`macula_stem`/
  `macula_person`/`macula_gender`/`macula_number` columns, populated
  **independently** of `hebrew_tokens`' TAHOT-sourced columns — nothing
  ever compares them and overwrites; a disagreement is simply visible by
  querying both tables side by side (comparison/provenance only, per the
  brief). No LLM is ever used to resolve a disagreement — none exists in
  this phase's code path (see §14's static import check).

---

## 5. Alignment corpus statistics (full run, all 39 books)

Run via `scripts/build_macula_alignment_store.py` against the complete
local `WLC/lowfat` checkout, output store discarded after verification
(867,749,888 bytes — see §14 on why it is not committed), summary
retained at
[`docs/phase2d_macula_alignment_audit.json`](phase2d_macula_alignment_audit.json).

| Metric | Value |
|---|---:|
| Files processed | 929 / 930 (1 skipped: a stray combined-corpus file, not a chapter) |
| Books processed | **39 / 39** (full coverage — see §2.1) |
| Verses processed | 23,213 |
| Textus/TAHOT tokens processed | **305,635** (exactly matches the known Phase 2A/2B/2C corpus total) |
| MACULA leaves seen | (counted per-chapter; aggregate not separately summed — see raw audit JSON `macula_leaf_count` per file) |

**Alignment outcome:**

| Type | Count | % |
|---|---:|---:|
| EXACT | 153,433 | 50.20% |
| COMPOSITE | 138,944 | 45.46% |
| VALIDATED_FALLBACK | 7,432 | 2.43% |
| UNRESOLVED | 5,826 | 1.91% |
| **Total** | **305,635** | 100% |

**98.09%** of tokens resolved with at least corroborated evidence;
**95.66%** at EXACT/COMPOSITE (fully positionally and evidentially
confirmed). The **1.91% UNRESOLVED** fraction is real and explicitly not
treated as complete — see §5.2 for its two root-cause categories.

### 5.1 Hebrew vs. Aramaic

Aramaic-section books (Ezra, Daniel — book-level, not verse-level, so this
bucket includes those books' Hebrew portions too):

| | EXACT | COMPOSITE | VALIDATED_FALLBACK | UNRESOLVED | Unresolved % |
|---|---:|---:|---:|---:|---:|
| Hebrew-majority books | 149,241 | 134,953 | 6,760 | 5,006 | 1.68% |
| Ezra/Daniel (mixed Hebrew+Aramaic) | 4,192 | 3,991 | 672 | 820 | 8.47% |

Daniel alone has the highest per-book unresolved rate in the corpus
(11.2%, 663/5,920 tokens) — plausibly related to its denser
apocalyptic/technical vocabulary and the Hebrew/Aramaic language boundary
itself, though this phase did not further decompose Ezra/Daniel by verse
to separate their Hebrew and Aramaic portions individually (a reasonable
Phase 2E-adjacent refinement, not required here).

### 5.2 Top mismatch categories (from a 100-example sample of the 5,826 unresolved)

| Category | Share of sample | Root cause identified |
|---|---:|---|
| Component-count mismatch, no surface corroboration | 77% | TAHOT and MACULA segment the same orthographic word into a different number of pieces beyond the two patterns §3.1 already reconciles (implicit article, lexical compounds) |
| No MACULA leaves at that word position | 23% | Two confirmed sub-causes below |

**Ketiv/Qere gap** (confirmed, real example): Ruth 1:8, TAHOT
`word_index=10` (`יַ֣עַשׂ`, Qere; Ketiv `יַעֲשֶׂה`) has **zero** MACULA
leaves at `ref="RUT 1:8!10"` — MACULA's own ref-numbering skips this word
entirely, shifting every subsequent word's ref number down by one for the
rest of the verse. The aligner reports this honestly (`UNRESOLVED`,
`"no MACULA leaves found for this word position"`) for word 10 and
*also* for the words after it (rather than guessing a shift-correction),
since a general auto-shift heuristic risks silently mis-aligning
verses where the real cause differs — this is the deliberate
"do not use fuzzy matching silently" trade-off the brief calls for.
Regression-tested:
`test_alignment_ketiv_qere_gap_reported_not_silently_shifted`.

**Textual-critical supplied readings**: Genesis 4:8, TAHOT
`word_index` values `501`/`502` (`נֵלְכָה הַשָּׂדֶה`, "let us go out to
the field") — the well-known Masoretic ellipsis in Cain and Abel's
dialogue, where some editions/versions supply words the base Hebrew text
lacks. TAHOT's own STEPBible-Data convention marks such supplied text
with a distinctly high word-index (≥500) rather than folding it into the
normal 1..N sequence; MACULA's tree, following the attested base text,
naturally has no corresponding leaves. Both are legitimate,
well-understood textual phenomena, not a defect in either dataset or in
this phase's alignment logic.

**Acceptance criterion 5 ("materially ambiguous/unresolved cases are
explicit") is satisfied by this section, not by treating alignment as
100% complete.**

---

## 6. Normalized database schema

16 tables, designed for Postgres (`supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`)
and mirrored for SQLite (`bible_engine/hebrew_linguistic_sqlite.py`) with
the same names/columns (SQLite substitutes `INTEGER PRIMARY KEY
AUTOINCREMENT` for `bigint generated always as identity` and `TEXT` for
`jsonb`/`timestamptz`).

```
original_language_dataset_versions   -- dataset_id + revision registry, one active row per dataset_id
hebrew_verses                        -- canonical (book_id, chapter, verse) + verse_ref index
hebrew_tokens                        -- Textus stable token_id (PK) — TAHOT/TEHMC-authoritative, unchanged shape from Phase 2C
hebrew_token_strong_ids              -- (token_id, seq) -> strong_id
hebrew_token_components              -- (token_id, component_index) -> prefix/core/suffix
hebrew_source_nodes                  -- raw MACULA tree: word/group nodes, parent_node_id self-FK, macula_* comparison-only morphology columns, raw_attributes JSONB
hebrew_token_alignments              -- the alignment table itself (§3), EXACT/COMPOSITE/VALIDATED_FALLBACK/UNRESOLVED
hebrew_phrases / hebrew_clauses      -- normalized from hebrew_source_nodes once alignment is validated
hebrew_syntax_membership             -- token <-> phrase/clause membership (join table)
hebrew_syntax_edges                  -- parent/child syntax relations, normalized relation_type + verbatim source_role_code
hebrew_semantic_roles                -- from MACULA's frame attribute (role_code verbatim, role_label lightly mapped for A0/A1 only)
hebrew_participants / hebrew_coreference  -- from subjref/participantref
hebrew_detected_patterns / hebrew_detected_pattern_tokens  -- Phase 2C structural-fact detector output, Supabase-ready
```

Design choices matching the brief's explicit requirements:

- **Canonical reference indexing**: `hebrew_verses(book_id, chapter,
  verse)` UNIQUE + index; every downstream table carries a denormalized
  `verse_ref` text column for single-query verse-level retrieval without
  joining through `hebrew_verses` first.
- **Stable Textus token IDs**: `hebrew_tokens.token_id` (the Phase 2C
  `{OSIS_book}.{chapter}.{verse}:{word_index}` scheme) is the primary key
  every other table's `*_token_id` foreign key references — never a
  database rowid.
- **Source-specific IDs kept separate**: `hebrew_tokens.source_token_id`
  (verbatim TAHOT record id) and `hebrew_source_nodes.macula_node_id`
  (verbatim MACULA `xml:id`, or a deterministically-synthesized
  `{sentence_id}:wg{n}` for group nodes, which have no `xml:id` in the
  source at all — verified: 0/340 in a sample chapter).
- **Dataset revision/provenance**: `original_language_dataset_versions`
  is referenced by FK from every fact-bearing table; a partial unique
  index (`WHERE is_active`) enforces exactly one active revision per
  `dataset_id`.
- **Hebrew and Aramaic support**: `hebrew_verses.language` and
  `hebrew_tokens`' TAHOT-sourced fields carry this exactly as Phase 2C
  established; nothing schema-specific to one language.
- **No display-text identity**: every join key is an id (`token_id`,
  surrogate `id` columns, `macula_node_id`), never a surface string.
- **Greek stays architecturally separable**: every table name and column
  is Hebrew-specific (`hebrew_*` prefix, TAHOT/MACULA-specific columns);
  nothing here assumes or forces a shared cross-language schema. A future
  Greek equivalent (`greek_verses`, `greek_tokens`, ...) can be added
  without touching this migration.
- **JSONB used narrowly**: only `hebrew_source_nodes.raw_attributes` —
  genuinely optional, source-varying MACULA metadata (Mandarin/Greek
  glosses, sense numbers, semantic-domain codes) not promoted to
  first-class columns. Every other fact-bearing field is a real typed
  column.

---

## 7. Supabase migration

[`supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`](../supabase/migrations/20260908190000_hebrew_linguistic_layer.sql) —
proper primary keys, foreign keys (including a deferred `ALTER TABLE ...
ADD CONSTRAINT` for the `hebrew_phrases.parent_clause_id` forward
reference to `hebrew_clauses`), unique constraints (`(dataset_version_id,
macula_node_id)` etc.), indexes for `(book_id, chapter, verse)` and
`token_id` lookups, and a closing `DO $$ ... $$` block applying the
grant-based RLS model §1 describes (RLS enabled, `anon`/`authenticated`
revoked, `service_role` granted) uniformly across all 16 tables.

**Validated locally, NOT applied to any real Supabase project** — no
`psql`, Docker, or Supabase CLI is available in this environment, and no
production credentials exist here. Validation performed: (1) every
`references table(column)` in the file resolves to a table actually
defined in the same file (verified programmatically — 43/43 references
resolve, 16/16 tables match the design above); (2) `sqlparse` tokenizes
all 45 statements without error. `scripts/setup_hebrew_linguistic_schema.py`
prints the migration for manual paste into the Supabase SQL Editor and
verifies (read-only `LIMIT 0` on all 16 tables) whether it has already
been applied — run and confirmed to degrade gracefully (prints the DDL,
then reports "no credentials" rather than crashing) when no Supabase
credentials are configured, exactly as it did in this environment.

---

## 8. Repository architecture

[`bible_engine/hebrew_analysis_repository.py`](../bible_engine/hebrew_analysis_repository.py):

```python
class HebrewAnalysisRepository(Protocol):
    def get_verse_syntax(self, verse_ref: str) -> VerseSyntaxData: ...

class LocalHebrewAnalysisRepository:      # SQLite mirror — default, no network
class SupabaseHebrewAnalysisRepository:   # Postgres — fail-closed, lazy-imports supabase_client
```

`HebrewAnalysisService` (constructor, and the module-level
`get_hebrew_analysis()` wrapper) accepts an optional
`linguistic_repository:` parameter, defaulting to
`LocalHebrewAnalysisRepository()`. Neither implementation is imported by
UI code directly — `hebrew_analysis_service.py` is the only caller
(mirroring the Phase 2C rule that it is the sole place raw morphology is
touched; now also the sole place a syntax repository is queried). Neither
implementation is a Streamlit dependency (verified statically, §14), and
`SupabaseHebrewAnalysisRepository` imports `supabase_client` **lazily
inside its method**, not at module import time — importing
`hebrew_analysis_repository` never requires the `supabase` package or any
credentials (regression-tested:
`test_supabase_repository_only_imports_client_lazily_inside_method`).

Both implementations are **fail-closed**: any error (missing file,
corrupt schema, locked file for local; network/auth/query error for
Supabase) degrades to an empty `VerseSyntaxData()` — never an exception —
so a syntax-layer outage can never break the deterministic
token/morphology path.

---

## 9. Bundle extension

[`bible_engine/hebrew_analysis_bundle.py`](../bible_engine/hebrew_analysis_bundle.py)
— schema version bumped `2c.0.0` → `2d.0.0`. New dataclasses
`SyntaxRelation` and `CoreferenceLink`; `VerseAnalysis` gains
`syntax_relations` and `coreference` fields; `SemanticRole` gains an
optional `role_code` field (source-verbatim, alongside the existing
lightly-normalized `role_type`). Every new field defaults to `()`/`""` —
**every existing Phase 2C caller is unaffected** (regression-tested: all
31 Phase 2C tests plus the full Hebrew suite pass unchanged, §16).

```
VerseAnalysis
  tokens[]              # Phase 2C, TAHOT/TEHMC-authoritative, untouched
  phrases[]              # NEW: populated from MACULA where present
  clauses[]               # NEW
  syntax_relations[]     # NEW
  semantic_roles[]        # NEW
  participants[]           # NEW
  coreference[]            # NEW
  detected_patterns[]     # Phase 2C, unchanged
```

`CoverageReport.has_syntax` / `.has_semantic_roles` / `.has_participants`
(fields that already existed in Phase 2C, always `False` there) are now
computed from the actual per-verse data
(`bible_engine/hebrew_analysis_service.py`'s `get_hebrew_analysis`). No AI
interpretation field was added — `TokenAnalysis.contextual_sense` stays
`None`-only, exactly as Phase 2C defined it.

---

## 10–12. Syntax / semantic-role / coreference data imported

See §5 for corpus-wide counts (238,809 phrases, 102,124 clauses, 793,631
syntax edges, 110,831 semantic-role assignments, 24,943 participants,
45,222 coreference links). Concretely, from Genesis 1:1 fixture-scale
verification and the Ruth 1 test fixture:

- **Syntax relations**: `role="v"` → `relation_type="predicate"`,
  `"s"` → `"subject"`, `"o"` → `"object"`, `"adv"` → `"modifier"`; every
  other MACULA role code (there are several less-common ones, e.g. `"p"`)
  is kept as `relation_type="other"` with `source_role_code` preserved
  verbatim — **never a stronger semantic claim than MACULA's own code
  confidently supports.**
- **Semantic roles**: MACULA's `frame` attribute (`"A0:080010010042;"`
  etc., PropBank-style) parsed into `(predicate, role_code, participant)`
  triples. `role_label` is populated **only** for A0→"agent" and
  A1→"patient" — the two conventions stable enough to state with
  confidence; every other code (A2, AM-*, ...) keeps `role_label=""`
  while `role_code` stays the real source of truth. No role is
  manufactured for a predicate MACULA doesn't tag.
- **Coreference**: `subjref`/`participantref` target ids (with the
  `"o"`-prefix normalization from §3.1) become `hebrew_participants`
  rows (deduplicated by target node) and `hebrew_coreference` edges.
  Verified end-to-end on Ruth 1:16 (`הִיא`, "she") resolving back to the
  participant established in 1:1 — the concrete "which participant does
  this pronoun refer to" capability the brief asks for, working only
  because MACULA supplies the structured evidence
  (`test_bundle_coreference_ruth_1_16_resolves_pronoun_to_participant`).

Tree structure is never flattened away: `hebrew_source_nodes.parent_node_id`
preserves the full MACULA parse tree; `hebrew_phrases`/`hebrew_clauses`
are a normalized *view* of that tree (one row per phrase/clause-type
group node), not a replacement for it.

---

## 13. Test coverage added this phase

[`tests/test_hebrew_macula_alignment.py`](../tests/test_hebrew_macula_alignment.py)
(24 tests) and
[`tests/test_hebrew_analysis_repository_supabase.py`](../tests/test_hebrew_analysis_repository_supabase.py)
(4 tests), all against the small, real, committed fixtures at
[`tests/fixtures/macula_lowfat/`](../tests/fixtures/macula_lowfat/)
(`ruth_1_excerpt-lowfat.xml`, `genesis_excerpt-lowfat.xml`,
`ezra_4_excerpt-lowfat.xml` — trimmed real MACULA XML, ~111 KB total,
exact source attributes preserved verbatim). No test requires network
access or the full corpus.

Covered per the brief's Section 18/19 checklist: ordinary token
(Ruth 1:1 word 3), multi-component token (word 1), phrase (`pp`/`np`
groups), clause (`cl` groups), explicit subject/predicate relation
(`role="s"`/`"v"`), semantic role (`frame` on Ruth 1:1/1:3), participant/
coreference (Ruth 1:16), Hebrew/Aramaic boundary (Ezra 4:8 fixture),
Ketiv/Qere-adjacent alignment gap (Ruth 1:8, regression-tested
specifically). Regression passages from the brief: Genesis 1:1, 1:2,
1:22, 11:3, Ruth 1:3, Ezra 4:8 (Aramaic), and the Ruth 1:8 Ketiv/Qere case
— all present in the committed fixtures.

---

## 14. No AI interpretation (verified, not just claimed)

Every new module (`macula_lowfat_parser`, `hebrew_macula_alignment`,
`hebrew_macula_importer`, `hebrew_analysis_repository`) is checked via AST
import inspection (`test_phase2d_modules_have_no_llm_or_direct_network_dependency`)
to import none of `openai`, `google.generativeai`, `anthropic`,
`requests`, `urllib.request`, `httpx`, `streamlit`. Alignment
classification, syntax-relation labeling, and semantic-role mapping are
all rule-based (fixed dictionaries / structural comparisons) — nothing is
generated by a model anywhere in this phase's code path.

---

## 15/16. Supabase deployment status

**Not executed against a real Supabase project from this environment** —
no credentials available. What still needs to run against the real
project, in order:

1. Open the Supabase project's SQL Editor and paste the output of
   `python scripts/setup_hebrew_linguistic_schema.py` (or the migration
   file directly) — creates all 16 tables + RLS grants.
2. Re-run `python scripts/setup_hebrew_linguistic_schema.py` — should now
   report all 16 tables reachable.
3. Run the offline importer against the full local MACULA checkout
   (§2's fetch commands + `scripts/build_macula_alignment_store.py`),
   writing to a **Postgres-targeting** importer variant (this phase's
   `import_chapter()` writes to the SQLite mirror; a Supabase-writing
   equivalent — batched `client.table(...).upsert(...)` calls per table,
   idempotent on each table's natural unique key, which the SQLite
   importer's `INSERT OR REPLACE`/`_upsert_*` helpers already establish —
   is the direct, mechanical next step, explicitly **not implemented in
   this phase** per its "prefer a dry-run/import-validation mode" and "do
   not automatically write to production" instructions).
4. Point a `SupabaseHebrewAnalysisRepository()` at the populated project
   and spot-check `get_verse_syntax("Ruth.1.1")` against the known local
   fixture result.

No secrets are printed or committed anywhere in this phase's code.

---

## 17. Performance

| Measurement | Result |
|---|---|
| Bundle construction, Ruth 1 (22 verses), no syntax repository | 115.3 ms/call |
| Bundle construction, Ruth 1 (22 verses), local syntax repository wired | 143.5 ms/call (+28.1 ms, ~1.3 ms/verse) |
| Queries per verse (local SQLite repository) | 7 bounded, verse-scoped queries (phrases, clauses, membership, edges, roles, participants, coreference) — **no N+1 (never per-token)** |
| Import throughput (full corpus) | 305,635 tokens / 23,213 verses in 716 s (≈427 tokens/s, ≈32 verses/s) — one-time offline cost, not a runtime cost |
| Normalized record counts (full corpus) | 305,635 tokens · 238,809 phrases · 102,124 clauses · 793,631 syntax edges · 110,831 semantic roles · 24,943 participants · 45,222 coreference links |
| Local SQLite mirror size (full corpus, scratch-only) | 867,749,888 bytes (≈868 MB) |
| Estimated Supabase storage footprint | Same order of magnitude as the local mirror (≈0.8–1.5 GB accounting for Postgres's own row/index overhead) — comfortably within Supabase Pro's storage allowance; not measured against a real project in this environment |

Supabase's REST layer would issue the same 7-query-per-verse shape as the
local repository (or fewer with a future combined view/RPC — a
reasonable Phase 2E-adjacent optimization, not required now).

---

## 18. Large-file / deployment size impact

**No new large binary was committed.** Everything new in git this phase:

| Artifact | Size |
|---|---:|
| New Python modules (5 files) | ≈79 KB |
| New scripts (2 files) | ≈15 KB |
| Supabase migration SQL | ≈21 KB |
| New tests (2 files) | ≈20 KB |
| Test fixtures (`tests/fixtures/macula_lowfat/`, 3 files, real trimmed MACULA XML) | ≈111 KB |
| Alignment audit summary (`docs/phase2d_macula_alignment_audit.json`) | ≈29 KB |
| This document + manifest additions | ≈25 KB |
| **Total new git content** | **≈300 KB** |

The 868 MB full-corpus SQLite mirror and the 417 MB raw MACULA checkout
both exist **only** in the session scratchpad and were never staged.

**Status of the existing Phase 2C `hebrew_component_fidelity.sqlite3`
(35.7 MB, committed):** left completely untouched this phase — still the
authoritative source for prefix/core/suffix surface+gloss restoration
(`bible_engine/hebrew_component_repository.py`, unchanged). **Migration
path to eventually replace it**: once a Supabase project actually holds
the normalized `hebrew_token_components` table (populated by the same
importer this phase built, pointed at Postgres per §15/16), a future
cleanup phase could retire the local SQLite file in favor of reading
component fidelity through `HebrewAnalysisRepository` too — but that is
explicitly **not done in this phase** (git history for the file is not
rewritten, and it remains required for every existing Phase 2C caller).

---

## 19. Remaining unresolved alignment cases

1.91% (5,826/305,635) of tokens remain `UNRESOLVED` corpus-wide (§5),
concentrated in two well-characterized categories (§5.2): component-count
mismatches beyond the two patterns this phase's aligner reconciles
(implicit/empty morphemes, lexical compounds), and MACULA ref-numbering
gaps at genuine Ketiv/Qere or textual-critical-supplied-reading
boundaries. Both categories are honestly reported, not silently patched
over with a shift-correction heuristic that could mis-align other verses.
A `VALIDATED_FALLBACK` fraction (2.43%) is corroborated only by whole-token
surface containment rather than full component-level agreement — usable,
but flagged with lower confidence than `EXACT`/`COMPOSITE`.

---

## 20. Readiness for Phase 2E

Phase 2E (per the wider initiative's framing) is expected to consume the
now-structured bundle (tokens + phrases + clauses + syntax relations +
semantic roles + coreference + detected patterns) for constrained
Hungarian AI interpretation. Prerequisites now in place: a fully
deterministic, evidence-carrying syntax layer with explicit
confidence/provenance on every fact; a repository abstraction so Phase 2E
work is unaffected by whether the runtime store is local SQLite or
Supabase; zero AI-generated linguistic facts anywhere in the chain up to
this point, so Phase 2E's own AI layer has a clean, fully-attributable
foundation to ground against. **Phase 2E has not been started.**

---

## Acceptance criteria checklist

1. MACULA pinned to immutable revision (tag `26.04.13` / commit `09f8ea9e25025841ec45e2b6e7fc01595a080568`) — ✅
2. Raw MACULA data not committed — ✅ (scratchpad only)
3. Deterministic TAHOT↔MACULA alignment exists — ✅ (`hebrew_macula_alignment.py`)
4. Alignment statistics measured corpus-wide — ✅ (§5, all 39 books, 305,635 tokens)
5. Materially ambiguous/unresolved cases explicit — ✅ (§5.2, §19; not treated as complete)
6. TAHOT/TEHMC morphology remains authoritative — ✅ (§4, regression-tested)
7. Phrase/clause structure imported from MACULA — ✅ (238,809 / 102,124)
8. Syntax relationships available in `HebrewAnalysisBundle` — ✅ (`VerseAnalysis.syntax_relations`)
9. Semantic roles available where MACULA supplies them — ✅ (110,831, `VerseAnalysis.semantic_roles`)
10. Coreference/participant data available where MACULA supplies it — ✅ (24,943 / 45,222, `VerseAnalysis.participants`/`.coreference`)
11. No linguistic fact generated by an LLM — ✅ (§14, statically verified)
12. Supabase-ready normalized schema/migration exists — ✅ (§6/§7)
13. Repository abstraction supports local tests and Supabase production — ✅ (§8, both implementations tested)
14. Unit tests require no network access — ✅ (fixture-based, verified)
15. No new large generated MACULA binary committed — ✅ (§18)
16. Existing Hebrew tests remain green — ✅ (§13 of the report; full suite re-run)
17. Phase 2E not started — ✅
18. Nothing pushed — ✅
