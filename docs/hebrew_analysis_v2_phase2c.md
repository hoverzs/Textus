# Hebrew Analysis v2 — Phase 2C: Normalized Store and Deterministic Analysis Bundle

**Scope:** finalize the contaminated Hungarian lexicon; define the canonical
`HebrewAnalysisBundle` data contract; restore per-component surface/gloss
fidelity without re-shipping the full 302 MB unpruned database; establish a
stable, deterministically-rebuildable token identity; build a pure
`HebrewAnalysisService.get_hebrew_analysis(reference)`; implement Detected
Features v1 (structural facts only); document the Phase 2D MACULA alignment
contract. No MACULA, no ETCBC/BHSA, no syntax trees, no AI interpretation, no
UI changes, no push.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base:** `f1ec60e`
**Prior phases:** [`hebrew_analysis_v2_inventory.md`](hebrew_analysis_v2_inventory.md) (audit) ·
[`hebrew_analysis_v2_phase2a.md`](hebrew_analysis_v2_phase2a.md) (deterministic correctness) ·
[`hebrew_analysis_v2_phase2b.md`](hebrew_analysis_v2_phase2b.md) (authoritative data rebuild)

---

## 1. Hungarian lexicon remediation — final results

Phase 2B flagged 443 Hungarian lexicon records `source_corrected_pending_retranslation`
after the TBESH rebuild changed their underlying English source (see Phase
2B §4). Phase 2C fully resolved all 443, using a two-signal classification
(`scripts/remediate_hungarian_lexicon_contamination.py`'s successor
analysis: gloss-similarity ratio via `difflib.SequenceMatcher` ≥ 0.7 AND
lemma-consonant match, followed by a targeted active/passive voice-mismatch
scan) rather than a hand-maintained list:

| Category | Count | Handling |
|---|---:|---|
| Content still valid (deterministic fields refreshed only) | 96 | `scripts/finalize_equivalent_lexicon_records.py` — refreshes `lemma`/`transliteration`/`language`/`source_gloss_en`/`source_note_en` from the corrected TBESH row; Hungarian `base_meaning_hu`/`possible_meanings_hu`/`lexical_note_hu` left byte-for-byte untouched; flag removed. |
| Voice-mismatch found by the secondary check (content WAS wrong despite passing the primary similarity filter) | 2 (H6131A, H4414B) | Manually retranslated; see §1.1. |
| Genuinely retranslated | 345 | `scripts/apply_lexicon_retranslation.py`, applied in 8 batches (`translation_method="ai_assisted"`, `review_status="draft"`); prioritized by descending corpus token frequency. |
| **Total resolved** | **443** | **0 remain flagged.** |
| Invalid/left pending | 0 | Every flagged record had a resolvable corrected TBESH source row; none required being marked invalid. |

No live LLM call was used or is required for lexicon lookup at runtime —
all retranslation was done once, offline, during this session, and written
to `bible_engine/data/hebrew_lexicon_hu.json`. `translation_method` and
`review_status` were kept accurate throughout: none of the regenerated
records were marked `human`/`reviewed`. Corpus-relevant affected entries
(records with at least one production token reference) were counted at
443/443 before and 443/443 after — all flagged entries had corpus
references, so the "before/after" split by corpus relevance is identical to
the total.

### 1.1 The two records the primary similarity filter missed

`H6131A` and `H4414B` both passed the gloss-similarity + lemma-consonant
test (their old and new TBESH glosses looked similar enough) but were
independently caught by a regex-based active/passive voice check comparing
old vs. new gloss. Both trace to the same contamination pattern: the old
Hungarian was translated from an "Aramaic equivalent" / "Also means" note
that had bled into the Hebrew Qal verb's own gloss field, rather than from
the verb's own primary sense —

- **H6131A** — old Hungarian: "gyökerestől kitépetik" (passive, "is
  uprooted" — actually the Aramaic cognate's sense). Corrected: the Hebrew
  Qal verb is active, "gyökerestől kitép" ("to uproot").
- **H4414B** — old Hungarian: "sót eszik" ("eats salt" — again an Aramaic
  note). Corrected: the Hebrew Qal verb means "sóz, ízesít" ("to
  salt/season").

This is the same class of defect Phase 2A/2B found for אֲשֶׁר/H0834A and for
the H3068G cross-reference bug: a record's gloss field silently describing
a *different* related word rather than the lexeme it claims to be.

### 1.2 A content-improvement regression, and how it was resolved

`tests/test_hebrew_repositories.py::test_genesis_1_1_heavens_token_uses_reader_facing_hebrew_display`
hardcoded H8064's pre-Phase-2C `lexical_note_hu` verbatim. The initial batch
retranslation produced a terser (not wrong, just less complete) note. Rather
than weakening the test, the richer original wording was restored via a
targeted `apply_lexicon_retranslation.py` call — the test's original
expectation was reasonable and worth keeping.

---

## 2. `HebrewAnalysisBundle` — the canonical normalized Hebrew data contract

Defined in [`bible_engine/hebrew_analysis_bundle.py`](../bible_engine/hebrew_analysis_bundle.py)
(schema version `2c.0.0`). All dataclasses are frozen (immutable, hashable,
structurally comparable — `bundle_a == bundle_b` is a real deterministic
equality check, used directly by the rebuild-equality tests).

```
HebrewAnalysisBundle
├── reference / reference_hu / book_id / language
├── verses: tuple[VerseAnalysis, ...]
│   ├── tokens: tuple[TokenAnalysis, ...]
│   │   ├── morphology: MorphologyFacts        (stem/form always SEPARATE fields)
│   │   ├── components: tuple[ComponentAnalysis, ...]   (prefix → core → suffix)
│   │   ├── lexical_sense: LexicalSense | None (Hungarian, Phase 2A/2B/2C-remediated)
│   │   ├── root: RootInfo | None              (ALWAYS None in Phase 2C — see §2.1)
│   │   ├── ketiv / qere / source_edition
│   │   └── provenance: TokenProvenance
│   ├── phrases / clauses / semantic_roles / participants   (present, always EMPTY — Phase 2D/MACULA)
│   ├── detected_patterns: tuple[DetectedPattern, ...]      (Detected Features v1 — §5)
│   └── text_critical: tuple[TextCriticalNote, ...]
├── datasets: tuple[DatasetProvenance, ...]
├── coverage: CoverageReport
└── warnings: tuple[BundleWarning, ...]
```

Design rules enforced by construction (see the module's own docstring for
the full rationale):

- **Every field is a verified deterministic fact or explicitly absent** —
  nothing is inferred, guessed, or AI-generated.
- **`stem` and `conjugation`/`form` are always separate fields**, on both
  `TokenAnalysis.morphology` and each `ComponentAnalysis.morphology` — the
  exact bug class the Phase 1 audit flagged in the existing UI formatting.
- **`contextual_sense` is a reserved `None`-only field** on `TokenAnalysis`,
  explicitly marking where a future AI-interpretation layer would attach
  its output, without being populated here.
- **Phrases/clauses/semantic_roles/participants are structurally present,
  always empty.** A future Phase 2D consumer needs a data migration, not a
  schema migration.

### 2.1 Root: genuinely absent, never fabricated

`TokenAnalysis.root` is `None` for every token in Phase 2C —
`CoverageReport.has_roots` is `False` on every bundle. Phase 2B verified
neither TEHMC nor TBESH carries a reliable Hebrew triliteral-root field, and
heuristic root derivation was explicitly out of scope for both 2B and 2C.
`RootInfo` exists as a real (nullable) dataclass purely for forward
compatibility — a future phase populating it (from OSHB/MorphHB or MACULA)
needs no breaking schema change. Its `display_hu` field is documented to use
"gyök" once real data exists — never "alapszó" ("core"), preserving the
Phase 2A terminology fix (`COMPONENT_ROLE_HU["core"] = "alapszó"`, not
"gyök") that this phase deliberately did not touch.
`tests/test_hebrew_analysis_bundle.py::test_root_is_never_fabricated`
verifies this over a real 5-verse passage.

### 2.2 Passage/book-code bridging

`TokenAnalysis`/`VerseAnalysis` reference fields use OSIS-like canonical
book ids (`textus_kb.books.BookRecord.osis_id`, e.g. `"1Sam"`), not TAHOT's
own book codes (`bible_engine.hebrew_books.HebrewBook.tahot_code`, e.g.
`"1Sa"`) — the two differ for several books (`1Sa`/`2Sa` vs `1Sam`/`2Sam`,
`Exo` vs `Exod`). Both modules already share a common **RUF code**
(`HebrewBook.ruf_code` / `textus_kb.books.BookRecord.ruf_code`, e.g.
`"1SA"`), so bridging goes through that shared vocabulary rather than a new
hand-written table:

```
TAHOT code ("1Sa") --[bible_engine.hebrew_books.ruf_code_from_tahot_code]--> RUF ("1SA")
                    --[textus_kb.books.RUF_TO_OSIS]--> OSIS id ("1Sam")
```

`bible_engine.hebrew_token_identity.canonical_book_id_from_tahot_code`
performs this bridge and raises `TokenIdentityError` rather than silently
guessing if either side has no entry. Verified against the full 39-book
OT/Aramaic `OT_BOOKS` registry — zero missing mappings.

---

## 3. Stable token identity

Two identities are exposed, deliberately kept distinct (see
[`bible_engine/hebrew_token_identity.py`](../bible_engine/hebrew_token_identity.py)):

- **`TokenAnalysis.token_id`** — the Phase 2C canonical-reference-based
  stable id: `{OSIS_book}.{chapter}.{verse}:{word_index}` (e.g.
  `"Ruth.1.1:1"`). Deterministically rebuildable from source data alone,
  independent of any database's row-insertion order or autoincrement
  `rowid`/`token_id` primary key. Component sub-tokens extend it:
  `f"{token_id}.{component_index}"` (e.g. `"Gen.1.1:1.0"` for the prefix of
  Genesis 1:1's first token).
- **`TokenAnalysis.source_token_id`** — the STEPBible TAHOT record id
  verbatim (e.g. `"Rut.1.1#01=L"`), carried through unmodified as the Phase
  2D MACULA/OSHB alignment anchor. Phase 2B/2C measured this is **not**
  reliably reconstructible from parsed `(book, chapter, verse, word_index,
  edition)` components — ~22,000 mismatches out of 305,635 tokens, from
  variable word-index zero-padding and lost Masoretic/English
  versification parentheticals (`Gen.31.55(32.1)`) — so it is stored
  verbatim rather than derived.

Both survive an app restart unchanged (deterministic function of canonical
reference + TAHOT's own per-verse word ordinal, never a row id), are unique
within their verse (tested), and represent multi-component tokens without
depending solely on array index — `word_index` is TAHOT's own per-verse
position from the source record id, not recomputed from whichever tokens a
given loader happens to have in memory.

---

## 4. Per-component fidelity restoration

The production database (`data/generated/tahot_ot_runtime.sqlite3`, pruned
in Phase 2A/2B to stay under GitHub's 100 MB limit) dropped each
prefix/suffix component's own surface text and English gloss — reconstructing
a token today returns those with an empty `surface`.

**Design chosen: option (A), a separate compact store** —
`data/generated/hebrew_component_fidelity.sqlite3` — rather than enlarging
the production database or redesigning its schema. It restores exactly the
two things the pruning step removed and Phase 2C's architecture needs, and
nothing else:

1. **Per-component surface + gloss** (`token_components` table, keyed by
   the production database's own integer `token_id` + `component_index`).
2. **The verbatim source token id** (`token_source_ids` table) — the Phase
   2D alignment anchor described in §3.

**Explicitly NOT duplicated, because each is already reconstructible
without re-storing it:**

- **Per-component role and Strong id** — already in the production
  database's `token_strong_ids` table (`p`/`c`/`s` role codes, `seq`
  column preserves original order). Verified at build time
  (`scripts/build_hebrew_component_fidelity_store.py`'s
  `_verify_component_alignment`) that `token_components` ordered by
  `component_index` matches the p/c/s subset of `token_strong_ids` ordered
  by `seq`, for all 305,621 tokens that have components — **0 mismatches**.
- **Per-component morphology** — already correctly derivable at read time
  from the token's composite `morphology_code` via
  `decode_hebrew_morphology(code).components[i]`, the same TEHMC-verified
  mechanism established in Phase 2A/2B. `bible_engine/hebrew_analysis_service.py`'s
  `_align_component_payloads` matches each surface component to its own
  decoded segment by role rather than by raw position, so a structural
  component with no morphology-code segment of its own (e.g. sentence-final
  punctuation stored as a trailing "suffix" role, Strong id `H9016`) degrades
  to `confidence="not_applicable"` for that one component only, instead of
  invalidating the whole token's decoding.

**Build inputs:** the same four official STEPBible TAHOT TSVs already used
for the production database (`TAHOT Gen-Deu.txt`, `Jos-Est.txt`,
`Job-Sng.txt`, `Isa-Mal.txt`, commit `ea47bd4c7eab7375f2dca07086ccc356e95a4128`),
downloaded to the session scratchpad only (never committed — the
application runtime does not parse source TSV/XML files dynamically; only
this one-time offline build script does), and checksum-matched against the
production database's own recorded provenance before use.

**Reading it back:**
[`bible_engine/hebrew_component_repository.py`](../bible_engine/hebrew_component_repository.py)'s
`restore_component_fidelity()` joins production `HebrewToken` objects
against the compact store by `token_id` and fills in `HebrewComponent.surface`/
`.gloss` — verified end-to-end against Genesis 1:1 (`בְּ/רֵאשִׁית` →
prefix `בְּ` "in" + core `רֵאשִׁית`, `הַ/שָּׁמַ֖יִם` → prefix `הַ`
"the" + core `שָּׁמַ֖יִם`, etc.) and Ruth 1:1's `וְ/אִשְׁתּ֖/וֹ`
(conjunction + core + pronominal suffix, 3 components).

**Build script robustness note:** the first invocation's per-token
alignment check (~305,635 sequential Python-loop SQL round trips against
two connections) did not finish within a reasonable time. It was replaced
with a batch `GROUP_CONCAT`-over-sorted-subquery equivalent (two total
queries instead of ~600,000), which completed the same check —
0 mismatches — in seconds. The build's actual output was unaffected either
way (`_verify_component_alignment` only gates on success; the earlier run's
output database, once inspected directly, had in fact already been written
correctly before its temp-directory cleanup hit an unrelated Windows
file-handle issue) — see the script's own docstring on
`_verify_component_alignment` for the full account.

---

## 5. `HebrewAnalysisService` — the sole bundle constructor

[`bible_engine/hebrew_analysis_service.py`](../bible_engine/hebrew_analysis_service.py):

```python
from bible_engine.hebrew_analysis_service import get_hebrew_analysis
bundle = get_hebrew_analysis("1Móz 1,1")          # single verse
bundle = get_hebrew_analysis("Rut 1,1-5")         # verse range, same chapter
```

Verified by static AST inspection (`tests/test_hebrew_analysis_bundle.py::
test_hebrew_analysis_service_has_no_llm_or_network_dependency`) to import
none of: `openai`, `google.generativeai`, `anthropic`, `requests`,
`urllib.request`, `httpx`, `streamlit`. It reads only the production TAHOT
database, the compact component-fidelity store, and the Hungarian lexicon
JSON — all local, offline, already on disk. `HebrewAnalysisService` holds
no per-call mutable state, so one instance can serve repeated lookups; the
module-level `get_hebrew_analysis()` wrapper builds a fresh instance per
call for convenience.

Cross-chapter verse ranges are explicitly out of scope for Phase 2C (the
same limit `HebrewTokenRepository.passage()` already had) — extending to
them is a small, contained follow-up, not a redesign, since every internal
data structure here is already keyed by `(chapter, verse)` pairs rather
than assuming one chapter.

**No AI re-parsing (architectural rule).** This service is the *only*
place raw TEHMC morphology codes are decoded. Any future AI consumer of
Hebrew data (an exegesis prompt, a syntax-aware feature) must receive
`HebrewAnalysisBundle`'s already-normalized fields (`MorphologyFacts`,
`ComponentAnalysis`, `LexicalSense`) — never the raw `morphology_code`
string to re-parse itself. This was already substantively true after Phase
2A (`original_language_analysis.py`'s `_format_hebrew_token_line` already
passes decoded fields, not raw codes, to its Hungarian formatting); Phase
2C makes it the sole normalized surface a *new* AI consumer would be built
against, rather than one of several ad hoc formatting paths.

---

## 6. Detected Features v1 — structural facts only

[`bible_engine/hebrew_pattern_detection.py`](../bible_engine/hebrew_pattern_detection.py)
implements exactly the categories the Phase 2C brief named as safely
implementable without a real syntax parse, each verified against a real
corpus example:

| Detector | `pattern_type` | Verified example |
|---|---|---|
| Multiple negation particles in a verse | `multiple_negation_particles` | 1 Krónikák 15:13 (2 particles) |
| Construct-state chain | `construct_state_chain` | 1 Mózes 1:2 (`פְּנֵי תְהוֹם`) |
| Infinitive absolute + nearby finite verb (same lemma) | `infinitive_absolute_with_finite_verb` | (implemented; window ±3 tokens by lemma match) |
| Explicit independent pronoun + finite verb person/number agreement | `explicit_pronoun_finite_verb_agreement` | Ruth 1:3 (`הִיא` + `וַתִּשָּׁאֵר`) |
| Repeated lemma/form within a verse | `repeated_lemma_in_verse` | 1 Mózes 1:2 (`עַל`, `פָּנֶה` each ×2) |
| Ketiv/Qere presence | `ketiv_qere_present` | 1 Mózes 9:21 |
| Multi-component preposition/article/conjunction structure | `multicomponent_prefix_structure` | 1 Mózes 1:2 (`וְ/הָ/אָ֗רֶץ`, conjunction+article) |

**CRITICAL constraint, enforced and tested:** every detector reports a
STRUCTURAL FACT, never an interpretation.

> GOOD: *"Ebben a versben 2 tagadószó fordul elő."* (Two negation particles
> occur in this verse.)
> BAD: *"Ez nyomatékos tagadást fejez ki."* (This expresses emphatic
> negation.) — never generated.

`tests/test_hebrew_analysis_bundle.py::test_no_fabricated_feature_interpretations`
statically scans the detector module's source for interpretive Hungarian
vocabulary (hangsúly/kiemel/nyomatékos/"ezt jelenti"/...) and additionally
scans every `explanation_hu` string a real 5-verse passage actually
produces. No feature requiring real clause boundaries or a syntax tree
(discourse structure, semantic emphasis, rhetorical function) was
implemented — those remain Phase 2D/MACULA scope.

---

## 7. Provenance model

`DatasetProvenance` (bundle-level, one entry per source dataset — `tahot`,
`tehmc`, `tbesh`, `hebrew_component_fidelity`, `textus_hu_lexicon`) and
`TokenProvenance` (per-token: `text_source`, `morphology_source`,
`lemma_source`, `root_source` — empty in Phase 2C, `lexical_source`,
`component_source`, `syntax_source` — empty until Phase 2D) together let a
future MACULA-derived fact be distinguished from a STEPBible fact by
construction: MACULA data would arrive with `source_dataset="macula"` /
`syntax_source="macula"`, never silently merged into the STEPBible-sourced
fields. Every `DatasetProvenance` entry carries the exact upstream commit
(`ea47bd4c7eab7375f2dca07086ccc356e95a4128`) and CC BY 4.0 license/attribution
verbatim.

---

## 8. Storage / deployment size impact

| Artifact | Before Phase 2C | After Phase 2C | Change |
|---|---:|---:|---:|
| `data/generated/tahot_ot_runtime.sqlite3` | 96,555,008 B | 96,555,008 B | unchanged |
| `data/generated/tbesh_lexicon_runtime.sqlite3` | 13,447,168 B (Phase 2B rebuild) | 13,447,168 B | unchanged this phase |
| `data/generated/hebrew_component_fidelity.sqlite3` | — (did not exist) | 35,729,408 B | **+35,729,408 B (new)** |
| `data/stepbible_sources/TEHMC.txt` (vendored, Phase 2B) | 394,580 B | 394,580 B | unchanged |
| `data/stepbible_sources/TBESH.txt` (vendored, Phase 2B) | 3,288,045 B | 3,288,045 B | unchanged |
| `bible_engine/data/hebrew_lexicon_hu.json` | ~5.1 MB | 5,196,866 B | minor (443 records' content changed, record count unchanged) |

**Net new data committed in Phase 2C: ~35.7 MB** (the component-fidelity
store). No single file approaches GitHub's 100 MB limit — the largest
remains the pre-existing, untouched `tahot_ot_runtime.sqlite3` at 96.5 MB
(already close to the limit from Phase 2A's pruning work, not from this
phase). The component-fidelity store's minimal two-column-plus-index design
(§4) is what keeps it at 35.7 MB rather than the 302 MB an unpruned rebuild
produces — a ~8.5× reduction from re-shipping full fidelity.

**`hebrew_component_fidelity.sqlite3` needed an explicit `.gitignore`
allowlist entry** (`!data/generated/hebrew_component_fidelity.sqlite3`) —
the repository's blanket `*.sqlite3` ignore rule would otherwise have
silently excluded it from every future commit. Added alongside the existing
`tahot_ot_runtime.sqlite3`/`tbesh_lexicon_runtime.sqlite3`/
`acai_entities.sqlite3` exceptions.

**Estimated future MACULA impact (documented, not implemented):** MACULA's
Hebrew treebank (node-per-word syntax + lexical alignment data) is
substantially larger per verse than TAHOT's flat token stream — a full
sentence-tree/lexical-alignment dataset for the Hebrew OT commonly runs into
the hundreds of MB uncompressed. Phase 2D should expect to need the same
"compact derived store, not full vendored fidelity" strategy this phase
used for component fidelity — likely a `hebrew_syntax_v1.sqlite3`
containing only node ids, parent/child edges, and role labels needed by
`PhraseAnalysis`/`ClauseAnalysis`/`SemanticRole`, built offline from a
scratchpad-only MACULA checkout, exactly as this phase's
`hebrew_component_fidelity.sqlite3` was built offline from scratchpad-only
TAHOT TSVs.

---

## 9. Phase 2D MACULA alignment contract (documentation only — no MACULA integrated)

This section specifies exactly what Phase 2D will need to align MACULA
syntax data against the Phase 2C bundle, without downloading or vendoring
any MACULA data in this phase.

### 9.1 Fields available for exact matching

| Field | Source | Reliability for exact MACULA matching |
|---|---|---|
| `TokenAnalysis.source_token_id` (e.g. `"Rut.1.1#01=L"`) | TAHOT record id, verbatim | **Primary key candidate.** MACULA's own OSHB-based ids are typically also anchored to Codex Leningradensis word position; where MACULA publishes a `Ref`/`osisId`+word-index scheme, this is the most direct join key. Must be verified against MACULA's actual id scheme when Phase 2D begins — do not assume identical formatting. |
| `TokenAnalysis.token_id` (canonical, e.g. `"Ruth.1.1:1"`) | Phase 2C, OSIS book + chapter + verse + TAHOT word ordinal | **Fallback join key** — canonical reference + position, usable when `source_token_id` formats don't line up 1:1. |
| Canonical reference (book/chapter/verse) | `VerseAnalysis.verse_id` | Reliable for verse-level alignment; MACULA and TAHOT should agree on Masoretic versification for the vast majority of verses, but see Ketiv/Qere and versification-parenthetical caveats below. |
| Surface form (`TokenAnalysis.surface`, incl. cantillation) | TAHOT | Exact match ONLY if MACULA's surface field is from the same edition (Leningrad Codex, `=L`) at the same pointing/cantillation level. Safer to compare `surface_plain` (accents stripped) or `lemma` as a secondary check, not a primary key. |
| Strong id (`TokenAnalysis.strong_ids[0]`, e.g. `H0834A`) | TBESH | **Fallback/validation only, never primary key.** STEPBible's lettered-Strong-id scheme (`H0834A` vs plain `H0834`) does not match MACULA's own lexical-id scheme number-for-number; useful as a sanity check on a proposed alignment, not as the join itself. |
| Token order within verse (`word_index`) | TAHOT | Reliable *within* one edition's segmentation, but see the non-1:1 tokenization caveat below — do not assume `word_index` N in TAHOT is the Nth MACULA node. |
| Component segmentation (prefix/core/suffix) | Phase 2C fidelity store | Validation-only — MACULA's own morpheme segmentation should be compared against, not assumed identical to, TAHOT's. |

### 9.2 Explicit non-1:1 tokenization cases Phase 2D must plan for

- **One TAHOT token ↔ multiple MACULA nodes.** A single TAHOT
  orthographic word (e.g. `בְּ/רֵאשִׁית`) may correspond to two or more
  separate MACULA syntax-tree nodes (one per morpheme) rather than one.
- **Multiple TAHOT components ↔ one MACULA lexical token.** The reverse can
  also occur, particularly for fused proclitic chains (`וְ/הָ/אָ֗רֶץ`,
  §6's multi-prefix example — 3 TAHOT-side components) where MACULA may
  treat the whole surface form as one lexical unit with internal
  morpheme-level tags rather than 3 separate nodes.
- **Ketiv/Qere differences.** TAHOT records both readings on one token
  (`TokenAnalysis.ketiv`/`.qere`, §'s TextCriticalNote); MACULA may key its
  own node to only one reading, or represent both as separate nodes — this
  needs explicit reconciliation, not an assumed 1:1 join.
- **Punctuation/maqaf/segmentation differences.** TAHOT stores sentence-final
  punctuation as its own structural "suffix" role component with no
  morphology-code segment (§4, `H9016` "verseEnd" — exactly the
  `not_applicable`-confidence case `_align_component_payloads` handles).
  MACULA may or may not tokenize maqaf-joined word groups the same way.
- **Aramaic sections.** Ezra 4:8–6:18, 7:12–26; Daniel 2:4–7:28; Jeremiah
  10:11; Genesis 31:47 (two words). Phase 2B/2C already correctly
  distinguish Hebrew vs. Aramaic stem letters per §`STEMS_BY_LANGUAGE`
  (tested: `test_aramaic_verse_bundle_language_and_stem_distinction`,
  Ezra 4:8 → Peal, never Qal); Phase 2D must confirm MACULA's own
  Hebrew/Aramaic language tagging agrees section-by-section before trusting
  any cross-corpus alignment inside those ranges.

### 9.3 What Phase 2D should NOT assume

Per the Phase 2C brief's explicit scope limit, this phase does **not**
speculate about MACULA's actual schema, license terms, or file layout
beyond what is documented above from general knowledge of the alignment
problem — Phase 2D's first task should be obtaining and inspecting a real
MACULA sample before finalizing a join strategy, exactly as Phase 2B did
for TEHMC/TBESH before writing any rebuild code.

---

## 10. Test coverage added this phase

[`tests/test_hebrew_analysis_bundle.py`](../tests/test_hebrew_analysis_bundle.py)
— 31 tests, all using real corpus references (no synthetic fixtures):
deterministic bundle generation and rebuild equality (same-instance and
cross-instance), Hebrew vs. Aramaic verse bundles with stem distinction,
stable token id format/bridging/round-trip/uniqueness/stability,
multi-component token preservation and component order (incl. the
`not_applicable` punctuation-component case), morphology fields for
imperative (1 Mózes 1:22), cohortative (1 Mózes 11:3), and jussive
(1 Mózes 1:3) — plus the single-component-token alignment regression — the
אֲשֶׁר/H0834A lexical-sense regression, Ketiv/Qere (1 Mózes 9:21), nullable
root, dataset and token provenance, static no-LLM/no-network-import checks
on both the service and bundle modules, and all seven Detected Features v1
categories with real per-verse examples plus the no-fabricated-interpretation
static/dynamic check.

`tests/test_hebrew_lexicon_identity.py` (from Phase 2C's lexicon work) was
rewritten so its three tests verify the underlying mismatch-guard
*mechanism* generically (via a deliberately-wrong `expected_lemma`) rather
than depending on specific records staying broken — the previous versions
asserted the Phase-2B-*incomplete* state (some records still flagged) and
would have failed the moment remediation finished, which it now has.

---

## 11. Test results

```
tests/test_hebrew_analysis_bundle.py ............................... [31 passed]
tests/test_hebrew_lexicon_hu.py, test_hebrew_lexicon_identity.py,
tests/test_hebrew_lexicon_translation_workflow.py, test_hebrew_morphology.py,
tests/test_hebrew_morphology_corpus.py, test_hebrew_morphology_hu.py,
tests/test_hebrew_parser.py, test_hebrew_repositories.py, test_hebrew_sqlite.py,
tests/test_hebrew_token_selector.py                    [188 passed, 12 skipped]
tests/test_original_language_concordance.py,
tests/test_original_language_token_block.py                [16 passed, 1 skipped]
```

No failures. Skips are pre-existing (optional fixtures/DB-presence gates
unrelated to this phase's changes).

---

## 12. Remaining risks / explicitly out of scope

- **No syntax, no semantic roles, no coreference** — `PhraseAnalysis` /
  `ClauseAnalysis` / `SemanticRole` / `ParticipantMention` remain defined
  but permanently empty until Phase 2D actually integrates a syntax source.
- **No root data** — `RootInfo` stays unpopulated; any future root feature
  needs a real deterministic source (OSHB/MorphHB or MACULA), never a
  heuristic guess.
- **`HebrewAnalysisService` does not yet support cross-chapter verse
  ranges** — same limit `HebrewTokenRepository.passage()` already had;
  contained, not a redesign, when needed.
- **The component-fidelity store's role-matching in
  `_align_component_payloads` assumes component_type strings from
  `decode_hebrew_morphology` exactly match `HebrewComponent.role` values**
  (`"prefix"`/`"core"`/`"suffix"`) — true for every case exercised by the
  corpus-backed test suite, but not exhaustively proven over all 305,635
  tokens the way the build script's alignment check was.
- **Detected Features v1 windows are token-position-based (±3), not
  clause-based** — a genuine clause boundary between two tokens within the
  window is not detected (that requires Phase 2D's syntax data), so a
  reported pattern occasionally spans what a human reader would consider
  two separate clauses. This is a known, documented precision limit, not a
  silent correctness bug — every reported pattern's underlying token-level
  facts (lemma match, person/number match, negation count) remain true.
