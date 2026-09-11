# Greek Analysis v2 — Phase 2B: Deterministic Syntax Integration

**Scope:** verify/pin a MACULA Greek syntax source; design and measure a
TAGNT↔MACULA token-identity alignment; build a normalized local syntax
store; extend `GreekAnalysisBundle` with phrase/clause/semantic-role/
coreference structures; implement a first deterministic construction-
detection set; lock in Greek-specific safety rules against label
overreach. **No MACULA import overrides TAGNT morphology. No Gemini/AI
contextual layer. Hebrew Analysis v2 and production Supabase data
untouched.**
**Branch:** `greek-analysis-v2-audit` · **Base:** `7d30899` (Phase 2A)
**Prior phases:** [`greek_analysis_v2_inventory.md`](greek_analysis_v2_inventory.md) (audit) ·
[`greek_analysis_v2_phase2a_foundation.md`](greek_analysis_v2_phase2a_foundation.md) (deterministic foundation)

---

## 1. Syntax source: verified, pinned, deliberately not vendored

Investigated directly (per instruction: not assumed from the Hebrew
MACULA-Hebrew implementation) — **Clear Bible's `Clear-Bible/macula-greek`**
(Biblica, Inc, CC BY 4.0), distinct from Hebrew's own MACULA repository.

| | Value |
|---|---|
| Repository | `Clear-Bible/macula-greek` |
| Commit pinned | `main` @ time of fetch — flat TSV and lowfat XML both retrieved 2026-09-11 (no numbered release tag exists upstream; the repo's own `pushed_at` at fetch time was `2026-07-07`) |
| License | CC BY 4.0 (Biblica, Inc, 2022-2024) — confirmed via the repo's own `LICENSE.md`, not GitHub's auto-detected "Other" |
| Textual base chosen | **SBLGNT** (Society of Biblical Literature Greek New Testament), not Nestle1904 — see §1.1 for why |
| Representations available | `tei` (readable text), `nodes` (nested XML, recursive-tree-friendly), `lowfat` (nested XML, query/display-friendly), `tsv` (flat word-level table, no tree) — this phase used **both** `tsv` and `lowfat` (see §1.2) |
| Token nodes | ✅ (137,741 for the whole NT) |
| Phrases | ✅ (`<wg class="np\|pp\|vp\|adjp\|advp">` in `lowfat`) |
| Clauses | ✅ (`<wg class="cl">` in `lowfat`) |
| Dependency-ish relations | Partial — a short `role` code (`s`/`v`/`o`/...) per token in the flat TSV; full dependency-tree edges are not separately modeled beyond the phrase/clause nesting itself |
| Semantic roles | ✅ — the flat TSV's own `frame` column (e.g. `"A0:n40001002001 A1:n40001002004"`), no XML needed |
| Participant/coreference | ✅ — the flat TSV's `referent` (pronoun→antecedent) and `subjref` (participle/infinitive→implicit subject) columns, genuinely populated (14,542 and 16,625 non-empty rows of 137,741 — NOT empty, contrary to an initial assumption corrected during this phase; see §1.3) |
| Discourse features | Not found in either representation used this phase |

### 1.1 SBLGNT chosen over Nestle1904 — evidence, not assumption

STEPBible TAGNT's own documentation states its Greek "follows NA27" (Nestle-
Aland), and its `edition_flags` distinguish **N** ("Ancient"/Nestlé-Aland,
"translated by most Bibles") from **K** ("Traditional"/Textus Receptus) and
**O** ("Others"). SBLGNT (2010) is a modern eclectic edition much closer to
the NA tradition than Nestle1904 (1904, over a century of textual scholarship
earlier). Confirmed empirically, not just by reasoning: in Jn 3:16, TAGNT's
word 11 "αὐτοῦ" ("his") carries `edition_flags="ko"` (present in K/
Traditional and O/Other, **absent** from N/Ancient) — and SBLGNT indeed
**omits** this exact word, matching the prediction precisely. This became
the backbone of the alignment's textual-variant classification (§2/§3).

### 1.2 Representation choice: flat TSV (full corpus) + bounded lowfat XML (9 books)

The flat TSV (20.8 MB, 137,741 rows, whole NT) supplied full-corpus token
identity, morphology (MACULA's own independent decoding — never used to
override TAGNT's, see §2), lemma, Strong number, semantic roles, and
coreference — **no XML needed for any of that**. Only phrase/clause
constituent *structure* requires the nested `lowfat` XML, which is
published **per book** (14.8 MB for Matthew alone; ~150+ MB for all 27
books combined). Given the explicit instruction not to commit large raw
source trees, and given time/scope constraints, this phase fetched lowfat
XML for the **9 books containing the 15 Phase 2A regression verses**
(Matthew, Mark, Luke, John, Romans, 1 Corinthians, Philippians, 1 Timothy,
2 Peter — ~67.6 MB), not all 27. **This is an explicit, documented scope
boundary, not a claim of full-corpus phrase/clause coverage** — see §13.

### 1.3 A correction made during this phase's own investigation

An early draft of the local store's module docstring asserted "MACULA's
`referent`/`subjref` columns were measured to be empty for every token."
This was **checked before being asserted** (per this project's established
practice of verifying claims against real data) and found **wrong**:
direct measurement against the full flat TSV shows 14,542 non-empty
`referent` values and 16,625 non-empty `subjref` values. The store schema
and code were corrected to include a `coreference_links` table before any
of it was used downstream — see §5/§6.

### 1.4 Not vendored, by design

Neither the flat TSV (20.8 MB) nor the 9 lowfat XML files (67.6 MB) are
committed to this repository — matching this phase's explicit instruction
and the Phase 2A precedent (TAGNT's own raw source was fetched, used to
verify reproducibility, and discarded rather than vendored). Re-fetch
commands are the exact URLs in §1 above; `scripts/build_greek_syntax_store.py`
is the deterministic, checksummable-in-principle rebuild path (see §13 for
why full checksum-pinning was not completed this phase).

---

## 2. Alignment design

`bible_engine/greek_token_alignment.py`. TAGNT remains authoritative for
morphology and identity (Phase 2A) — this module only ever determines
*which* MACULA node (if any) a given TAGNT token corresponds to, so
MACULA's syntax/role/coreference facts can be attached to the *correct*
TAGNT token. No AI is used anywhere in this module.

Five-status taxonomy (all Greek-specific, none copied from Hebrew's own
alignment status set, which this phase did not consult for the shape):

| Status | Evidence | Meaning |
|---|---|---|
| `EXACT` | Accent/breathing/case-insensitive surface match | Strongest possible evidence |
| `COMPOSITE` | Surfaces differ (elision/movable-nu/spelling), but lemma **and** Strong number **and** morphology (case/number) all agree | Same lexeme, orthographic edition variant |
| `VALIDATED_FALLBACK` | Neither surface nor lemma match, but position (after known-variant skips) plus morphology compatibility corroborate a match | Weakest positive tier — rare (0.46% of the corpus) |
| `UNRESOLVED_TEXTUAL_VARIANT` | No counterpart found, and the token's own `edition_flags` do **not** include the Ancient/Nestlé ("n"/"N") marker SBLGNT follows | **Expected, well-understood absence** — a genuine textual variant, not a failure |
| `UNRESOLVED_OTHER` | No counterpart found despite Ancient/Nestlé-tradition flagging | Genuine, uninvestigated discrepancy |

### 2.1 Why a naive positional walk fails, with a real example

A pure two-pointer/position-based walk breaks the instant TAGNT and MACULA
disagree on ANY token count difference within a verse — every token after
the divergence point shifts by one and false-mismatches cascade. Measured
directly: before fixing this, a single K/O-only variant early in 1 Cor 1:2
caused **four subsequent, otherwise-perfectly-matching tokens** to be
misclassified as unresolved. The final design uses a **consumable pool**
of MACULA tokens per verse (not a hard pointer): each TAGNT token searches
a local window first (cheap, handles the common case), then — only if that
fails — the verse's entire remaining unconsumed pool, so a genuine
**word-order transposition between editions** also resolves correctly. 1
Cor 1:2 is a second, independently well-documented textual-critical case
this phase's own investigation surfaced: TAGNT places "τῇ οὔσῃ ἐν Κορίνθῳ"
before "ἡγιασμένοις ἐν Χριστῷ Ἰησοῦ"; SBLGNT has the two four-word chunks
swapped. Both are fully intact — the pool-based whole-verse search
resolves all 8 tokens correctly instead of cascading.

### 2.2 A real bug this phase's own testing caught and fixed

The whole-verse fallback search's lemma+Strong tier initially had no
morphology check. Measured directly on Jn 3:16 (the same verse used to
validate §1.1): TAGNT's genitive "αὐτοῦ" (the known K/O-only variant) was
being **falsely matched** to a completely different, distant MACULA token
"αὐτὸν" (accusative, word 20) purely because both are forms of the common
pronoun αὐτός/G0846 — the exact class of false-positive risk a global
search introduces for frequently-repeated lemmas (pronouns, articles,
conjunctions). Fixed by requiring case/number morphology agreement for
**every** lemma+Strong candidate, not only the weaker `VALIDATED_FALLBACK`
tier. Regression-tested (`tests/test_greek_token_alignment.py::
test_repeated_common_lemma_does_not_cross_match_wrong_occurrence`).

---

## 3. Alignment baseline (full corpus, 142,096 TAGNT tokens)

```
EXACT                        135,397   (95.29%)
COMPOSITE                      1,344   ( 0.95%)
VALIDATED_FALLBACK               651   ( 0.46%)
UNRESOLVED_TEXTUAL_VARIANT     3,055   ( 2.15%)
UNRESOLVED_OTHER               1,649   ( 1.16%)
---------------------------------------------
Resolved (EXACT+COMPOSITE+FALLBACK): 137,392 / 142,096 = 96.69%
```

**Verse-level**: 6,690 of 7,958 verses (84.1%) have **zero**
`UNRESOLVED_OTHER` tokens at all.

**Book-level** (resolved % = EXACT+COMPOSITE+VALIDATED_FALLBACK / total),
every one of the 27 books is above 94.8%:

```
Lowest 5:  MRK 94.85%  PHM 95.42%  REV 96.29%  COL 96.33%  LUK 96.39%
Highest 3: 2CO 98.15%  2PE 98.56%  3JN 99.10%
```

### 3.1 `UNRESOLVED_OTHER` (1.16%, 1,649 tokens) — categorized, not chased further

Per instruction ("do not chase the final tiny fraction indefinitely"),
this residual was investigated to the point of a clear, honest category —
not resolved token-by-token. Root cause, confirmed by direct inspection:
**greedy first-match consumption of a repeated common lemma near another
occurrence of the same lemma**, combined with residual cases genuinely
outside the alignment algorithm's evidence tiers (no surface, lemma, or
positional-morphology match found anywhere in the verse's MACULA pool).
No further sub-categorization was attempted — the two known-and-fixed bug
classes (§2.1, §2.2) already account for the large improvement from an
initial ~92.96%/1.94%-unresolved-other baseline to the current
96.69%/1.16%.

---

## 4. Corpus-wide invariants — all passing

`tests/test_greek_syntax_invariants.py`, run against the actual built
store (12 tests, all pass):

- Every TAGNT token has exactly one alignment row (142,096 = 142,096).
- An `UNRESOLVED_*` row never carries a `macula_xml_id`; a resolved row
  always does.
- Every non-null `macula_xml_id` references a real row in
  `macula_source_nodes` — **no relation via coincidental id equality**.
- No two TAGNT tokens claim the same MACULA node.
- Every phrase/clause member token exists.
- **Phrase/clause members legitimately span verse boundaries** — this was
  investigated as a suspected bug and found to be genuine source
  structure: MACULA's `<sentence>` groups are sentence-scoped, not
  verse-scoped (e.g. Matthew's genealogy, Mat 1:2–1:17, is one long nested
  sentence). Measured: 44,810 cross-verse group-membership pairs, all
  confirmed to stay within the same book and an adjacent chapter (the
  invariant that WOULD catch a real bug — a cross-book or distant-chapter
  reference — holds with zero violations).
- Semantic-role and coreference-link rows reference real nodes only, after
  filtering MACULA's own `"n00000000000"` implicit-argument sentinel
  (1,891 of 43,662 frame arguments, 4.3% — a documented MACULA convention,
  not missing data) and 4 genuinely out-of-range upstream ids (Luke 1:54's
  frame data references token positions beyond what that verse's own TSV
  export tokenizes — a tiny, measured upstream inconsistency, filtered at
  insert time with the exact count and example recorded in code).
- Every book's resolved rate is at least 90% (floor test; actual minimum
  is 94.85%, see §3).

---

## 5. Normalized local syntax store

`bible_engine/greek_syntax_sqlite.py` + `scripts/build_greek_syntax_store.py`
→ `data/generated/greek_syntax_dev.sqlite3` (60,788,736 bytes / ~58 MB).

| Table | Rows | Scope |
|---|---|---|
| `macula_source_nodes` | 137,741 | Full 27-book corpus |
| `token_alignments` | 142,096 | Full 27-book corpus (every TAGNT token) |
| `macula_groups` (phrases+clauses) | 54,279 | 9 books (§1.2) |
| `semantic_role_assignments` | 43,662 → filtered to real, non-sentinel rows | Full corpus |
| `coreference_links` | 38,585 | Full corpus |

**Not committed to git** (`.gitignore`'s blanket `*.sqlite3` rule applies;
not added to the explicit whitelist the way `tagnt_nt.sqlite3`/
`tbesg_lexicon.sqlite3` were) — at ~58 MB, comparable in size to
already-committed production databases, but per the instruction's explicit
caution ("large generated stores must remain scratch/local unless there is
a strong reason") this phase treats that as a decision for the repository
owner, not an automatic default. It is fully reproducible from the pinned
source (§1) via `scripts/build_greek_syntax_store.py`; every test that
needs it is marked `skipif(not store.exists())` so a fresh checkout without
it still has a fully working, tested Phase 2A-only fallback
(`get_greek_analysis_with_syntax()` degrades to `NO_GROUNDED_SYNTAX`
automatically — verified by
`test_missing_syntax_store_degrades_to_phase_2a_bundle_unchanged`).

---

## 6. `GreekAnalysisBundle` upgrade

`bible_engine/greek_analysis_bundle.py` gains `GreekCoreferenceLink` (new —
the phase brief's suggested structure, needed once §1.3's correction was
made) and a `coreference` field on `GreekVerseAnalysis`; `GreekPhraseAnalysis`/
`GreekClauseAnalysis`/`GreekSemanticRole`/`GreekParticipantMention`/
`GreekDetectedPattern` already existed as always-empty Phase 2A
placeholders (§9 of that phase) and are now genuinely populated.
`bible_engine/greek_syntax_service.py::attach_syntax()` populates them from
the store **without ever modifying** a Phase 2A token/morphology/lexical
field — verified by
`test_attach_syntax_never_changes_phase_2a_token_morphology_fields`.

`syntax_grounding` (adapted, not copied, from Hebrew's three-value
convention):

- `FULLY_GROUNDED_SYNTAX` — every token in the verse resolved **and**
  phrase/clause group data exists for it (e.g. Mt 9:18, Mk 1:9–11, Php 1:21).
- `PARTIALLY_GROUNDED_SYNTAX` — some tokens resolved and at least one of
  {phrase/clause data, semantic roles, coreference} present, but not full
  coverage (e.g. Jn 3:16 — 25/26 tokens resolved, the known textual
  variant correctly excluded; or any verse in the 18 non-lowfat-scoped
  books, which still get full-corpus semantic-role/coreference data).
- `NO_GROUNDED_SYNTAX` — no syntax store available, or nothing resolved
  for this verse (Phase 2A behavior, unchanged).

`get_greek_analysis_with_syntax(reference)` is the new convenience
entrypoint (`bible_engine/greek_analysis_service.py`); `get_greek_analysis()`
(Phase 2A) is untouched.

---

## 7/9. No overinterpretation — locked in as tests, not just prose

`tests/test_greek_syntax_safety_rules.py` (9 tests). Concretely:

- `GreekPhraseAnalysis`/`GreekSemanticRole` dataclasses carry only the
  source's own verbatim role/rule codes — no field shaped to hold a
  stronger claim ("modifies", "emphasizes").
- No detector emits a `pattern_type` naming a participle's function
  (temporal/causal/concessive) or a genitive's semantic subtype
  (possessive/source/subjective/objective) — checked against real detector
  output on regression verses, not just by inspection.
- The genitive-absolute detector's `confidence` is `"probable"`, never
  `"certain"` — structural grounding (genitive noun + genitive participle
  in their own non-root clause) does not make every reading airtight.
- No detector's Hungarian explanation string uses interpretive/theological
  vocabulary ("hangsúly", "jelentőség", "teológiai", "elkerülhetetlen") —
  checked programmatically against real output, not just written correctly
  once.
- Article+participle detection requires morphological (case+number)
  agreement, not bare adjacency — verified with a real code/gender
  mismatch case.

These six general Greek-safety principles from the phase brief (aorist ≠
"simple past" interpretation, imperfect ≠ universal continuous past,
middle ≠ universal reflexive, passive morphology ≠ guaranteed semantic
passive, participle form ≠ adverbial function, genitive case ≠ semantic
subtype, article presence ≠ theological/discourse-emphasis claim) were
already locked in at the **morphology-label** level in Phase 2A
(`tests/test_greek_terminology_rules.py`, unchanged, still passing); this
phase extends the same discipline to the **syntax/construction** level.

---

## 8. Deterministic construction detection — first set

`bible_engine/greek_construction_detection.py`, `detect_patterns(verse)`.

| Construction | Evidence tier | Works on |
|---|---|---|
| Repeated lemma | Token morphology only | Every verse |
| Multiple negation | Token morphology only | Every verse |
| Article + participle | Token morphology (adjacency + case/number agreement) | Every verse |
| Preposition + case | Token morphology (adjacency, article-mediated) | Every verse |
| Infinitive construction | Token morphology only | Every verse |
| ἵνα / ὅτι clause | Lemma presence; clause EXTENT reported when syntax-grounded (most-specific enclosing clause, not the outermost sentence — a real bug this phase caught and fixed, see code comments), token-only presence otherwise | Every verse; stronger with syntax |
| Conditional clause marker (εἰ/ἐάν) | Token morphology only | Every verse |
| Relative clause marker | Token morphology (pronoun_type) only | Every verse |
| **Genitive absolute** | **Requires clause-boundary evidence** — a genitive noun + genitive participle inside their OWN non-root clause (audit §8: pure morphology cannot distinguish this from an ordinary phrase) | Syntax-grounded verses only (9-book scope) |
| Coordinated structures | Syntax-grounded: same-type phrase siblings under one parent; token-only fallback (lower value) otherwise | All verses, stronger with syntax |

**Verified on real data, not just unit fixtures**: Mt 9:18's genitive
absolute ("Ταῦτα αὐτοῦ λαλοῦντος αὐτοῖς") is correctly detected as its own
clause (MACULA's own tree independently identifies it as a sibling clause
of the main narrative clause — this phase's detector correctly recognizes
that structural fact, it does not invent it). Jn 3:16's ἵνα clause resolves
to exactly its 12-token extent ("ἵνα πᾶς ὁ πιστεύων … ζωὴν αἰώνιον"), not
the whole 26-token verse.

Per instruction, participle *function* (attributive/adverbial/
circumstantial) is explicitly NOT inferred — only the infinitive/
participle *form* is reported (§7/§9).

---

## 10. Regression verses — syntax coverage

All 15 Phase 2A fixtures (`tests/fixtures/greek_analysis_v2_regression_verses.json`,
still `"reviewed": false`) build successfully through
`get_greek_analysis_with_syntax()` and `detect_patterns()` with no errors —
parametrized test, `tests/test_greek_syntax_service.py::
test_all_15_regression_verses_build_without_error`. Four verses have a
dedicated construction-presence assertion (genitive absolute in Mt 9:18,
ἵνα in Jn 3:16, ὅτι in Mt 9:18, a conditional marker somewhere in 1 Cor
15:13–14) — deterministic **expected structures only**, no semantic
goldens, per instruction.

---

## 11. Performance

Measured directly (warm process, local SQLite, no network):

```
1 verse (Jn 3:16, with syntax attachment):        ~59 ms
10 regression verses (sequential, separate calls): ~606 ms  (~61 ms/verse)
1 chapter (Jn 3, 36 verses, ONE call):             ~118 ms  (~3.3 ms/verse)
```

**A real N+1-shaped finding, not premature optimization**: per-verse
sequential calls cost ~61 ms/verse, but batching 36 verses into one
`load_greek_passage_tokens()` call (Phase 2A's existing batch-capable
repository function) costs ~3.3 ms/verse — an **18× difference** driven
almost entirely by per-call SQLite connection/query overhead, not by the
syntax-attachment work itself. This is directly relevant to the future
Supabase backend design (§14 blockers): a per-verse REST-call pattern
would reproduce this same 18× penalty at network latency instead of local
SQLite latency, i.e. far worse — the Hebrew Phase 2A/2B import-performance
lesson ("batched RPC, not per-row REST") applies here too, before any
Supabase work begins.

---

## 12. Tests

New files this phase, all passing:

| File | Tests |
|---|---|
| `tests/test_greek_token_alignment.py` | 8 |
| `tests/test_greek_syntax_invariants.py` | 12 |
| `tests/test_greek_syntax_safety_rules.py` | 9 |
| `tests/test_greek_syntax_service.py` | 25 (includes all 15 regression verses parametrized, performance checks) |

```
$ pytest tests/test_greek_*.py tests/test_tagnt_*.py tests/test_tbesg_*.py \
         tests/test_lexicon_*.py tests/test_morphology_hu.py \
         tests/test_nt_lexicon_coverage.py tests/test_missing_tagnt_strong_audit.py \
         tests/test_original_language_*.py tests/test_audit_greek_lexicon_quality.py
472 passed, 6 skipped in 71.87s
```

The 6 skips are the same pre-existing, environmental ones noted in the
Phase 2A report (commentary database not built locally; RÚF 2014 licensed
text not committed) — unrelated to this phase. Phase 2A's own test suite
(morphology/lexicon/bundle/terminology-rule tests) re-run unchanged and
still green, confirming this phase did not regress it.

---

## 13. Remaining blockers before Phase 2C

None block STARTING Phase 2C (Supabase + contextual analysis) outright,
but each needs an explicit decision or follow-up, not silent assumption:

1. **Phrase/clause syntax data covers 9 of 27 books.** The other 18 books
   (including, notably, none of the Johannine epistles, Hebrews beyond
   token-level, Acts, Revelation) have full-corpus token alignment and
   semantic-role/coreference data, but no phrase/clause structure. A future
   phase extending to all 27 books is mechanical (same code, more
   downloads/parse time) but not yet done.
2. **The MACULA source is not checksum-pinned** the way TAGNT/TBESG/TEGMC
   were in Phase 2A — `main` was fetched at a point in time with no
   upstream release tag to pin against. A future phase should record exact
   SHA-256 checksums of the fetched files (this phase recorded WHEN and
   WHAT was fetched, but not per-file hashes) for full reproducibility
   parity with Phase 2A's TAGNT/TBESG/TEGMC provenance rigor.
3. **`greek_syntax_dev.sqlite3` (~58 MB) is not committed** — a deliberate,
   conservative default per instruction, but it means a fresh checkout
   needs ~90 seconds of local rebuild (with the source files re-fetched)
   before syntax-grounded features are available; the repository owner
   should decide whether to commit it (Phase 2A precedent: TAGNT/TBESG are
   committed at comparable sizes) or keep the current documented-and-
   reproducible-but-uncommitted state.
4. **1.16% of tokens (`UNRESOLVED_OTHER`) remain genuinely uninvestigated**
   beyond the root-cause category identified in §3.1 — acceptable per
   instruction ("don't chase the final tiny fraction"), but worth revisiting
   if a future phase needs syntax data for a SPECIFIC verse that happens to
   fall in this residual.
5. **Coordinated-structure and preposition+case detectors are token-
   adjacency-based outside the 9-book syntax scope** — lower-confidence
   than they could be with full phrase/clause data; not incorrect, just
   less evidence-rich for 18 of 27 books.

---

## 14. Conclusion

**READY FOR PHASE 2C — SUPABASE + CONTEXTUAL ANALYSIS**,
with the understanding that:

- Phase 2C's Supabase design should account for the measured ~18×
  per-verse-vs-batched performance gap (§11) from the start (batched
  RPCs, not per-verse REST calls — the Hebrew import lesson applies here
  before any Greek Supabase work begins), and
- Phase 2C should make an explicit decision on blocker #3 (commit the
  syntax store or keep it as a documented local-rebuild artifact) as part
  of its own Supabase-migration planning, since that decision directly
  shapes how the Supabase schema gets seeded.

Every other blocker (§13) is a scope-extension or provenance-rigor item
that can proceed in parallel with, not before, Phase 2C's own work — none
of them represent unverified or unsafe data.
