# Greek Analysis v2 — Phase 2A: Deterministic Foundation and Source Hardening

**Scope:** pin/verify authoritative Greek sources; restore the broken TBESG
fallback path; expose and screen Hungarian lexicon provenance/quality; build
a normalized `GreekAnalysisBundle`; verify Greek-specific terminology rules;
establish stable token identity; formalize 15 regression fixtures. **No
MACULA Greek import. No Gemini/AI contextual-analysis layer. Hebrew
Analysis v2 untouched. No production Supabase data touched.**
**Branch:** `greek-analysis-v2-audit` · **Base:** `8c0d728` (main)
**Prior phase:** [`greek_analysis_v2_inventory.md`](greek_analysis_v2_inventory.md) (audit)

---

## 1. Pinned and verified authoritative Greek sources

| | TAGNT | TBESG | TEGMC |
|---|---|---|---|
| Upstream repository | `STEPBible/STEPBible-Data` | `STEPBible/STEPBible-Data` | `STEPBible/STEPBible-Data` |
| Upstream path | `Translators Amalgamated OT+NT/TAGNT {Mat-Jhn,Act-Rev} - ... - STEPBible.org CC-BY.txt` | `Lexicons/TBESG - Translators Brief lexicon of Extended Strongs for Greek - STEPBible.org CC BY.txt` | `Morphology codes/TEGMC - Translators Expansion of Greek Morphhology Codes - STEPBible.org CC BY.txt` |
| Upstream commit | `ae39711d7843b2902d54993e432de9c12d6a4b9a` | same | same |
| Retrieved | 2026-09-11 | 2026-09-11 | 2026-09-11 |
| Vendored at | **Not vendored** — see §1.1 | `data/stepbible_sources/TBESG.txt` | `data/stepbible_sources/TEGMC.txt` |
| Size | 14,189,032 + 15,939,932 bytes | 4,736,912 bytes | 467,056 bytes |
| SHA-256 | `ab8eaaeb68e17a1dcfa34e1e9350358f22f03bc2a97244d848750ad81044bc8e` (Mat-Jhn) / `524e32375361e6d3fa2f7ef00b87605fdc4317a762f395651a05fdc31ad031b7` (Act-Rev) — recorded, not committed | `312f723d7b8ef263bbdfb0451c9b8057125804dfff390b6f8544cff2a84b57f4` | `5f0416f7617019a6082285214903bde569a980d5fd3b88b8d7020d944e94de82` |
| Licence | CC BY 4.0 | CC BY 4.0 | CC BY 4.0 |
| Attribution | "Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)" | Same | Same |

### 1.1 TAGNT: verified reproducible, deliberately not re-vendored

Per the task's "do not commit unnecessarily large generated databases if
avoidable," and mirroring the Hebrew Phase 2B precedent (the four TAHOT
source TSVs were verified-but-not-vendored for the same reason): the
already-committed `data/generated/tagnt_nt.sqlite3` (34.7 MB, added
2026-07-28, commit `fa8d7ac`) was **independently rebuilt from the freshly
downloaded, pinned-commit TAGNT source** and compared row-for-row:

```
committed rows: 142096
rebuilt rows:   142096
rows only in committed (missing from rebuild): 0
rows only in rebuild (not in committed):       0
```

**Byte-for-byte identical on every field** (book, chapter, verse, word_index,
greek_form, lemma, morph_code, strong_id, edition_flags). This closes the
audit's blocker #4 ("no in-repo reproducibility path") without doubling the
repository's storage: the 30 MB combined raw TAGNT text was downloaded,
used for this verification, and then discarded (not committed) — its
checksums above are sufficient for anyone to re-fetch and re-verify.

### 1.2 TBESG and TEGMC: vendored (small, and genuinely needed)

Both are small enough to commit outright (matching the Hebrew TBESH/TEHMC
precedent) and were **actually needed** this phase — TBESG to rebuild the
missing fallback database (§2), TEGMC to cross-check the existing Greek
morphology decoder's terminology choices (§7).

---

## 2. TBESG canonical-key rebuild — a real defect found and fixed, not just a missing file

### 2.1 The audit understated the problem

The Phase 1 audit found `tbesg_lexicon.sqlite3` simply absent from the
checkout. Investigating the actual import pipeline (per this phase's
instruction to "restore the authoritative English lexicon path", not just
re-run the existing importer) found a **second, independent defect**: the
importer keyed the SQLite `greek_lexicon` table by TBESG's bare `eStrong`
column — but `eStrong` is a BASE number **shared by every disambiguated
sense of a word** (e.g. `G0001` is the base for both "Alpha" and the
interjection "ah!"). `UNIQUE(strong_id)` + `INSERT OR IGNORE` on that
column meant only the first-encountered sense of any ambiguous base number
survived, and — critically — **the disambiguated ids TAGNT tokens and
`lexicon_hu.json` actually use for every real lookup** (e.g. `G0001G`,
`G0001H`) were never stored at all. Even after rebuilding the missing file
with the pre-existing importer, every suffixed lookup would have returned
`None`.

```
Before fix (pre-existing importer, run against the real vendored source):
  rows_read=11035, rows_imported=10847, duplicate_rows=188
  strong_id column: 0 of 10847 rows carry any letter suffix
  G0001G lookup -> None   G0001H lookup -> None   (both silently unfindable)
```

### 2.2 The fix

`bible_engine/tbesg_parser.py::GreekLexiconEntry.canonical_strong_id`
derives the row's real identity from the leading Strong-shaped token
embedded in the `dStrong` column (e.g. `"G0001G ="` → `G0001G`), falling
back to `eStrong` only when `dStrong` adds no distinct suffix — mirroring
(in spirit, not code) the Hebrew TBESH fix's identity/cross-reference
split (`claims_strong_id`, `reference_strong_ids` added for parity and
future-proofing, matching the Hebrew hijack-prevention pattern the task
asked for). `bible_engine/tbesg_sqlite.py`'s importer now keys every row
by `canonical_strong_id`.

```
After fix (python scripts/rebuild_tbesg_lexicon.py --apply):
  source checksum OK: 312f723d...
  rows read=11035, rows imported=11035, duplicate rows=0
  distinct final keys: 11035
  unclaimed (hijacked) keys: 0
  corpus Strong ids checked: 5580, lemma mismatches vs corpus: 47 (0.84% — see §2.3)

  G0001  -> None   (bare, undisambiguated — correctly unclaimed; no real
                     caller ever looks this up)
  G0001G -> ('G0001G', 'α, Ἀλφα', 'Alpha')
  G0001H -> ('G0001H', 'ἆ', 'ah!')
```

**Zero data loss** (11,035 vs 10,847), **zero collisions**, and every
disambiguated lookup a real caller performs now resolves correctly —
verified end to end via `bible_engine.greek_lexicon_repository
.get_tbesg_lexicon_entry("G2264G")` → `Ἡρώδης "Herod"`.

`scripts/rebuild_tbesg_lexicon.py` mirrors `scripts/rebuild_tbesh_lexicon.py`
exactly: checksum-gated (fails loudly on a source mismatch unless
`--skip-checksum`), dry-run by default, `--apply` required to touch the
production path, and validates the corpus-wide "every row claims its own
key" invariant on every run (`validate_every_row_claims_its_own_key` —
would fail loudly if a future regression reintroduces cross-reference
keying).

### 2.3 Residual: 47 lemma mismatches, unrelated to the key fix

Comparable in nature and smaller in proportion than Hebrew's own 102/11,450
(0.89%) residual — mostly dictionary-citation-form-vs-inflected-form
differences (`εἶναι` infinitive citation vs `εἰμί` lexical citation) and a
handful of TBESG-internal formatting artifacts (`Ἕλλην=Ἕλλην`, a literal
`=` embedded in the Greek field itself — unrelated to the key derivation).
Sampled, not hand-patched, per instruction. `data/generated/
tbesg_lexicon.sqlite3` (14,569,472 bytes) is now committed (added to the
`.gitignore` whitelist alongside the existing Hebrew runtime databases).

---

## 3. Hungarian lexicon: provenance classification and coverage (A vs B)

### 3.1 Provenance was already partially present, but invisible at runtime

Investigating before writing a migration script found the production
`bible_engine/data/lexicon_hu.json` **already carries**
`translation_method`/`source_name`/`source_version` on 5,956 of its 5,959
records — `bible_engine/lexicon_translation_workflow.py`'s batch-import
path has written these fields for some time. The actual gap: **`bible_engine
.lexicon_hu.HungarianLexiconEntry` never declared these fields**, so the
loader silently dropped them and no runtime code (nor the AI-facing bundle
in §9) could ever see them. Fixed by adding the three fields to the
dataclass (defaulted, so the minimal `lexicon_hu_sample.json` fixture is
unaffected) and to the JSON loader. `scripts/backfill_greek_lexicon_
provenance.py` then backfilled the only 3 records genuinely missing the
fields (`G0025`, `G2889`, `G3779` — hand-added illustrative examples that
predate the batch-import workflow), matching the value every other record
already carries rather than inventing a new one.

```
$ python scripts/backfill_greek_lexicon_provenance.py --apply
total entries: 5959 | already had all 3 fields: 5956 | backfilled: 3
```

### 3.2 Classification (measured, not assumed)

| Category | Lexeme count |
|---|---|
| `review_status == "reviewed"` (human-reviewed) | **0** |
| `review_status == "draft"` (`translation_method == "ai_assisted"` on all 5,959) | 5,579 (of the 5,580 corpus lexemes with any Hungarian entry) |
| Missing (no Hungarian entry, direct or alias) | 1 |
| Proper-name / transliteration candidates (majority of token occurrences name-tagged) | 573 |

**Coverage is not quality**, per instruction — every one of the 5,579
covered lexemes is still a machine-translated draft; §4 measures the
quality risk directly rather than treating this count as sufficient.

### 3.3 Coverage measured on two separate axes

| | A — lexeme-entry coverage | B — token-occurrence coverage |
|---|---|---|
| Corpus total | 5,580 unique lexemes | 142,096 tokens |
| Direct | 5,310 (95.16%) | 130,869 (92.10%) |
| Effective (direct + alias) | 5,579 (99.98%) | 142,071 (99.98%) |

Numbers match the Phase 1 audit exactly (cross-verified against the live
`tagnt_nt.sqlite3`, confirming both the audit's report and this phase's
independent re-measurement agree).

---

## 4. Automated lexical quality screen

`scripts/audit_greek_lexicon_quality.py` — deterministic, offline, produces
`data/generated/greek_lexicon_quality_report.json` (counts + up to 12
representative examples per category; **never rewrites a flagged entry**).

```
identical_to_english_source        : 545   (mostly legitimate — see below)
suspiciously_long_gloss            : 3
empty_or_placeholder_gloss         : 0
formatting_corruption              : 10    (genuine — see below)
gloss_inconsistent_with_part_of_speech : 30
canonical_lemma_mismatch           : 39
proper_name_as_common_noun         : 3     (after majority-vote fix — see below)
function_word_context_specific_gloss   : 30
```

**Honest caveats on precision, not silently tuned away:**

- `identical_to_english_source` (545) is dominated by **legitimately
  identical proper names** (`Aaron`→`Aaron`, `Abaddon`→`Abaddon`) — correct
  behavior, not a translation gap, for transliterated names. The check is
  still useful for the non-name remainder; this phase did not attempt to
  separate the two subsets further.
- `formatting_corruption` (10) found genuine data-pipeline artifacts, e.g.
  `G1421`: `"kemény; nehéz  értelmez; fordít"` — a double space and what
  looks like two distinct senses concatenated without proper separation.
  Real, worth a future targeted fix; not touched here.
- `proper_name_as_common_noun` initially flagged 10 entries using an
  "any occurrence is name-tagged" rule; switching to **majority-vote**
  (`is_name` only when >50% of a lexeme's own token occurrences carry a
  name-type code) dropped 7 false positives (common nouns like ὄρος
  "mountain" that occasionally participate in a toponym, e.g. "Mount X")
  and left 3 genuine-looking flags, one of which (`G3091` Λώτ "Lot" glossed
  as "sorsvetés; osztályrész" — "lot/portion", i.e. a different word
  entirely) looks like an actual mistranslation worth a future look. One
  remaining flag (`G5018` "Ταρσεύς" → "tarzuszi") is a **known false-positive
  class**: Hungarian gentilic/demonym adjectives are correctly lowercase
  (unlike English "Tarsian"), which this heuristic does not yet account for.
- `gloss_inconsistent_with_part_of_speech`/`function_word_context_specific_gloss`
  (30 each, same underlying set) flags multi-word glosses for
  prepositions/conjunctions/particles — but several examples (e.g. `G0575`
  "-tól, -től; el" for ἀπό) are **reasonable**, since Hungarian expresses
  many Greek prepositions via case-suffix alternatives rather than one
  word. This heuristic has a real false-positive rate for this specific
  reason; kept as-is (a human reviewer, not the script, should adjudicate)
  rather than tuned to hide true positives.

None of the above were hand-patched — every number above is the script's
literal, reproducible output.

---

## 5. High-frequency priority review set

Not a plan to review all 5,959 entries now — a tractable layer whose
quality matters most in actual use, per instruction.

```
function words (all prepositions/conjunctions/particles)  : 135
top 300 lexemes by corpus token frequency                 : 300
lexemes occurring in the 15 regression verses (§11)        : 154
QA-flagged lexemes (§4)                                     : 621
union (deduplicated)                                        : 1,014
```

1,014 of 5,580 corpus lexemes (18.2%) — the concrete, actionable subset a
future human-review pass should prioritize before any of it is treated as
an AI-facing "authoritative override" the way Hebrew's `lexical_sense
.base_meaning_hu` is.

---

## 6/9. Normalized Greek morphology model and `GreekAnalysisBundle`

`bible_engine/greek_analysis_bundle.py` (dataclasses) +
`bible_engine/greek_analysis_service.py::get_greek_analysis()` (the sole
builder — mirrors Hebrew's `HebrewAnalysisBundle`/`get_hebrew_analysis()`
shape without copying Hebrew-specific categories).

`GreekMorphologyFacts` fields, each populated only when the source
genuinely encodes it (verified against the full corpus, not assumed):
`part_of_speech, case, number, gender, person, tense, voice, mood,
verb_form, degree, pronoun_type, name_type, extra` — plus `raw_code` and
`normalized`/`summary_hu`. **`aspect` is a declared field, permanently
empty in Phase 2A** — neither TAGNT nor TEGMC represent verbal aspect
separately from tense-form (§7); the field exists so a future phase that
DOES have an aspect-bearing source can populate it without a schema
change, and so nothing downstream can mistake its permanent absence for an
oversight.

`GreekTokenAnalysis` carries `token_id` (§8), `surface`, `lemma`,
`strong_id` (already the canonical disambiguated form — TAGNT's own field,
confirmed unaffected by the §2 TBESG-only bug), `edition_flags`,
`morphology`, and `lexical_sense: GreekLexicalSense | None` — the latter
carrying `review_status`/`translation_method`/`source_name`/
`source_version` on every populated record, never silently dropped (§10).

`GreekVerseAnalysis.phrases/clauses/syntax_relations/semantic_roles/
participants/detected_patterns` are declared, always empty tuples in Phase
2A, `syntax_grounding` defaults to `"NO_GROUNDED_SYNTAX"` — structurally
forward-compatible with a future MACULA Greek import, never synthesized.

**Verified working end to end** (Jn 3:16 → 26/26 tokens, all
`fully_decoded`, lexical senses attached with full provenance):

```
Jhn.3.16:3 ἠγάπησεν ἀγαπάω G0025 fully_decoded ige
  ige, aorisztoszi, kijelentő mód, aktív igenem, egyes szám harmadik személy
  lex: szeret | draft | ai_assisted
```

---

## 7. Terminology rules — verified against TEGMC, tested

The audit's §4.1/§5.1 findings were about a RISK the Hungarian labels
*would* pose if naively reused for future AI prose — investigating the
actual `_TENSES`/`_VOICES` code tables in `bible_engine/morphology_hu.py`
confirms **the existing labels already avoid every specific overreach the
task calls out**, and this phase locks that in with tests
(`tests/test_greek_terminology_rules.py`, 8 tests) rather than rewriting
anything:

| Rule | Existing label | Verified |
|---|---|---|
| Aorist ≠ universal "múlt idő" | `"aorisztoszi"` | ✅ no "múlt idő"/"múlt" substring |
| Imperfect ≠ universal "folyamatos múlt" | `"imperfektum"` | ✅ |
| Middle ≠ universal "visszaható" | `"mediális igenem"` | ✅ |
| Deponent ≠ collapsed into genuine middle/passive | `"mediális deponens"` / `"passzív deponens"` distinct from `"mediális igenem"` / `"passzív igenem"` | ✅ (and quantitatively material: 3,578/28,576 = **12.5%** of all verb occurrences are deponent — not a rare edge case) |
| Participle form ≠ syntactic function | No field on `HungarianMorphology` claims attributive/adverbial/circumstantial/substantival function | ✅ (confirmed absent, not just untested) |
| Aspect never synthesized | `GreekMorphologyFacts.aspect` always `""` | ✅ |

No prompt/AI-explanation work exists yet to audit for *usage* of these
labels (§9/§10 of the Phase 1 audit — there is no Greek AI layer in
production); this phase verifies the **labels themselves**, which is the
ground floor any future prompt would inherit.

---

## 8. Stable token identity

`bible_engine.greek_analysis_service.greek_token_id(book, chapter, verse,
word_index) -> f"{book}.{chapter}.{verse}:{word_index}"` (e.g.
`"Jhn.3.16:5"`) — deliberately mirrors Hebrew's own `token_id` shape
(dotted book.chapter.verse, colon before word index), and closely mirrors
TAGNT's own native reference notation (`Jhn.3.16#5`, `.` for the reference,
`#` for the word index — this format substitutes `:` for `#` and is
otherwise identical).

**Verified stable and unique**: a corpus-wide test
(`test_corpus_wide_token_identity_is_unique`) confirms all 142,096
generated ids are unique. **Verified NOT fragile against Hungarian-facing
reordering**: token order within a verse is fixed by `word_index`
ascending — a corpus-wide + regression-fixture test confirms this.

**Documented limitation, not solved here** (audit §7, unchanged): this
identity is stable *within TAGNT itself* (fixed by the source file, never
recomputed), but a future MACULA Greek import will introduce its own node
identifiers with no existing crosswalk to `word_index` — exactly the class
of problem Hebrew's own MACULA alignment layer
(`hebrew_component_fidelity.sqlite3`) had to solve, and Greek will need an
equivalent explicit alignment step, not an assumption that `word_index`
positions line up.

---

## 10. AI boundary

No prompt or Gemini call was added this phase (explicitly out of scope).
What was verified: `GreekAnalysisBundle`/`GreekTokenAnalysis` already
carry fully-decoded, structured values for every field a future prompt
would otherwise need to reparse from a raw morph code — `case`, `gender`,
`number`, `tense`, `voice`, `mood`, `lemma`, and lexical identity are all
present as plain strings on the dataclass, never requiring downstream code
to touch `raw_code` directly. A static test
(`test_no_ai_or_network_dependency_in_deterministic_bundle_build`) confirms
`bible_engine/greek_analysis_service.py` imports no `requests`, no Gemini
call, no `st.secrets`, and no Supabase client — the bundle build that ran
throughout this phase never touched the network.

---

## 11. Regression verses — formalized as developer fixtures

`scripts/export_greek_regression_fixtures.py` exports the audit's 15
verses through the real `get_greek_analysis()` builder into
`tests/fixtures/greek_analysis_v2_regression_verses.json` (1.53 MB; every
record carries `"reviewed": false` and an explicit `review_note` — **not
expert goldens**, per instruction). `tests/test_greek_regression_fixtures.py`
(6 tests) verifies the file loads, every verse is marked unreviewed, every
required phenomenon (aorist, imperfect, perfect, middle, participle,
infinitive, genitive absolute, conditional, ἵνα, article, preposition+case,
difficult syntax) is represented, and token ordering is intact.

---

## 12. Tests

New/changed test files this phase, all passing:

| File | Tests | Purpose |
|---|---|---|
| `tests/test_tbesg_parser.py` | 30 (+5 new) | `canonical_strong_id`/`claims_strong_id`/`reference_strong_ids` |
| `tests/test_tbesg_sqlite.py` | (+1 new) | Disambiguated-sense collision regression (§2) |
| `tests/test_lexicon_hu.py` | 23 (+1 new) | Provenance fields exposed, no record missing `translation_method` |
| `tests/test_greek_analysis_bundle.py` | 10 (new) | Bundle construction, token order/identity, empty-syntax invariant, no-AI-dependency, corpus-wide 142,096-token/0-unresolved/unique-identity invariants |
| `tests/test_greek_terminology_rules.py` | 8 (new) | §7 label rules, incl. quantitative deponent-share anchor |
| `tests/test_greek_regression_fixtures.py` | 6 (new) | §11 fixture integrity |
| `tests/test_audit_greek_lexicon_quality.py` | 9 (new) | QA-screen/classification pure-function unit tests |

```
$ pytest tests/test_greek_*.py tests/test_tagnt_*.py tests/test_tbesg_*.py \
         tests/test_lexicon_*.py tests/test_morphology_hu.py \
         tests/test_nt_lexicon_coverage.py tests/test_missing_tagnt_strong_audit.py \
         tests/test_original_language_*.py tests/test_audit_greek_lexicon_quality.py
418 passed, 6 skipped in 68.23s
```

The 6 skips are pre-existing and environmental (commentary database not
built locally; RÚF 2014 licensed text intentionally not committed) —
unrelated to this phase.

Full-repo regression check (`pytest tests/ --ignore=tests/test_textus_kb`,
the same pre-existing collection collision noted in the earlier Hebrew
session): **3,142 passed, 266 skipped, 14 failed** — all 14 failures
independently confirmed to touch none of this phase's files (Jude e2e/RUF
fetch fixtures, biblical-map UI, concept concordance, outline synthesis —
pre-existing, unrelated to Greek work). One side effect caught and
reverted before committing: running the full suite mutates 8
`data/biblical_places/enrichment_research/*.json` cache files as a
pre-existing test side effect unrelated to this phase; reverted via `git
checkout --` before finalizing this checkpoint.

---

## 13. Remaining blockers before Phase 2B (syntax integration)

None of the following block STARTING a MACULA Greek import — they are
either already resolved or are independent, parallel-track work:

1. **0% of the Hungarian lexicon is human-reviewed** (unchanged fact,
   now precisely measured and provenance-tracked). Phase 2A built the
   infrastructure (QA screen + 1,014-lexeme priority set) to make review
   tractable; the review itself is future, human, offline work — not a
   syntax-integration blocker.
2. **Heuristic QA checks have known, documented false-positive classes**
   (§4) — real but bounded; a human reviewer, not further heuristic tuning,
   should adjudicate the flagged set.
3. **Token identity is not yet crosswalked to any external node scheme**
   (§8) — this IS directly relevant to Phase 2B: the first concrete task of
   a MACULA Greek import will be building that alignment, exactly as
   Hebrew's `hebrew_component_fidelity.sqlite3` did.
4. **The TBESG formatting-corruption findings (10 entries) and the
   Λώτ-style proper-name mistranslation are not fixed** — sampled and
   documented, not hand-patched, per instruction.

---

## 14. Conclusion

**READY FOR PHASE 2B — GREEK SYNTAX INTEGRATION.**

The deterministic foundation is now verified end to end: sources pinned
and checksummed (TAGNT reproducibility proven byte-for-byte; TBESG/TEGMC
vendored), the TBESG fallback path's actual defect (not just its absence)
found and fixed with zero data loss, Hungarian lexicon provenance restored
to runtime visibility with an honest 0%-reviewed measurement (not hidden
behind a 99.98% coverage number), a normalized `GreekAnalysisBundle` built
and tested with a clean, AI-ready structured boundary and correctly-empty
syntax placeholders, Greek-specific terminology rules verified against the
authoritative TEGMC source and locked in with tests, and 15 regression
verses formalized as clearly-unreviewed developer fixtures. Blocker #3
above (token-identity crosswalk) is Phase 2B's own first task, not a
prerequisite to starting it.
