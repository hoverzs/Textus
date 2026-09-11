# Greek Analysis v2 — Repository Inventory and Architecture Audit

**Status:** Audit only. No production code, data, prompt, UI, dependency or test was modified.
**Date:** 2026-09-11
**Branch:** `greek-analysis-v2-audit`
**HEAD at audit time:** `8c0d72818c88cecd3cf75c07cec0052a31c4a9c9`
**Scope:** Discovery and measurement only. No new dataset (e.g. MACULA Greek) was downloaded, vendored or integrated. Hebrew Analysis v2 was not touched. Supabase production data was not touched.

---

## 1. Executive summary

Greek original-language support in Textus is a **deterministic-only, single-source system with zero AI grammatical interpretation in production today.** This is a materially simpler and lower-risk starting point than Hebrew was before its own v2 hardening: the morphology decoder resolves **100% of the corpus with no unresolved codes**, the Hungarian lexicon has **99.98% effective token coverage**, and there is no equivalent of the Hebrew TEHMC `v`-code defect uncovered during the Hebrew audit — nothing this audit found corrupts a *large* slice of the corpus.

However, three findings are serious enough to be called blockers or near-blockers before any AI layer is built on top, and they are different in kind from anything found in the Hebrew audit:

1. **The entire Hungarian Greek lexicon (5,959 lexemes, ~130,900 token occurrences) is machine-translated and 0% human-reviewed** (`review_status: "draft"` on every single record — see §5.2). Hebrew Analysis v2 had *some* reviewed content to anchor against; Greek has none.
2. **There is zero deterministic syntax data** — no phrases, clauses, dependency relations, semantic roles, or participant tracking (§7). Every one of the "construction types" the user wants for Greek (genitive absolute, ἵνα clauses, article+participle, etc.) requires data that does not exist yet.
3. **The `tbesg_lexicon.sqlite3` database referenced by the English-lexicon fallback path does not exist in this checkout** and is not committed to the repository (§2.4). The fallback code path (`TBESGDatabaseUnavailableError`) is real, tested, and currently live in production for the ~0.02% of tokens the Hungarian lexicon doesn't cover directly.

None of these blockers require re-importing corpus text or morphology — they are lexicon-review, syntax-data, and one-file-provisioning problems, not corpus-integrity problems. Recommendation is given in §14.

### 1.2 What already exists that Hebrew Analysis v2 did *not* have to build twice

Unlike Hebrew, Greek analysis was never funneled exclusively through a dedicated per-word AI panel. There has been a **whole-passage, DB-grounded AI summary generator since before Phase 2E existed** (`bible_engine/original_language_analysis.py`, shared between Hebrew and Greek, §9.1) with its own prompt-discipline grounding rules and a **separate post-hoc hallucination scanner** (`bible_engine/original_language_grounding_check.py`, §9.2). This is architecturally distinct from the Hebrew Phase 2E pattern (structured JSON + server-side field validation) — it is free-prose + regex-based vocabulary matching. Any "Greek Analysis v2" work needs to decide explicitly whether it *replaces* this older system or lives alongside it (§11).

---

## 2. Current Greek implementation — production path map

### 2.1 UI entry points

| Entry point | File:line | Status |
|---|---|---|
| "Eredeti szöveg tanulmányozása" tab (main app) | `app.py:7812` → `render_greek_analysis_block(...)` | **Production**, live for every passage with a resolved reference |
| Igehely tab (bible text editor), 3 call sites | `bible_text_ui.py:801,811,887` → `render_greek_analysis_block(...)` | **Production** |
| Whole-passage AI summary button ("Eredeti szöveg tanulmányozása" button) | `app.py:7820` → `bible_engine.original_language_analysis.run_original_language_analysis(...)` | **Production**, separate AI system, shared Hebrew+Greek |
| Standalone demo page | `greek_text_demo.py` | **Demo/prototype only** — `st.set_page_config(page_title="Görög szövegelemzés - prototípus")`, not linked from `app.py` navigation. Re-exports symbols from `greek_analysis_ui.py`; not dead code (has 17 of its own tests) but not a production route. |
| Concordance jump | `original_language_concordance.py` via `_render_concordance_jump_button` in `greek_analysis_ui.py:706` | **Production** |
| Sermon-workshop knowledge base | `textus_kb/adapters/tagnt.py` (`TagntAdapter`, read-only) | **Production**, feeds grounded-study modules (e.g. Exegézis) with Greek token citations, not a separate AI-authoring surface |

`render_greek_analysis_block()` (`bible_engine/greek_analysis_ui.py:145`) is the single production dispatcher: it inspects the reference, and if the book resolves to the Old Testament it **delegates entirely to the Hebrew word-panel** (`hebrew_text_demo.render_hebrew_original_language_reference`, line 179) rather than rendering anything Greek-specific. This means the `hebrew_contextual_analysis_generate_fn` parameter threaded through this file exists *only* to serve that OT fallback branch — it is never invoked for an actual Greek/NT token. **Confirmed by reading the full 1,277-line file: there is no Gemini call anywhere in the genuine Greek (NT) rendering path.**

### 2.2 Repositories / services

| Module | Responsibility |
|---|---|
| `bible_engine/tagnt_parser.py` (179 lines) | Parses one raw TAGNT TSV row into a `GreekToken` dataclass; `get_verse_tokens()` reads directly from a TSV file (used only by the JHN 3:16 fixture / demo path) |
| `bible_engine/tagnt_sqlite.py` | SQLite schema + importer for the full NT (`create_schema`, `import_tagnt_new_testament`); read helpers `get_sqlite_verse_tokens`, `find_greek_tokens_by_lemma`, `find_greek_tokens_by_strong_id` |
| `bible_engine/greek_token_repository.py` (171 lines) | Resolves the runtime DB path (env var → Streamlit secret → default `data/generated/tagnt_nt.sqlite3`), diagnostics, `load_greek_passage_tokens()` |
| `bible_engine/tagnt_books.py` | Book-code table (STEPBible 3-letter codes ↔ RUF/Hungarian book names), reference parsing (`parse_tagnt_bible_reference`) |
| `bible_engine/tbesg_parser.py` / `bible_engine/tbesg_sqlite.py` (408 lines) | English lexicon (TBESG) TSV parser + SQLite importer/reader |
| `bible_engine/greek_lexicon_repository.py` (54 lines) | Resolves the TBESG DB path, raises `TBESGDatabaseUnavailableError` if the file is missing |
| `bible_engine/lexicon_hu.py` (227 lines) | Hungarian lexicon loader/validator, Strong-ID alias resolution (direct hit → alias → give up) |
| `bible_engine/morphology_hu.py` (485 lines) | **Shared** Hungarian morphology decoder — used by Greek (Robinson/STEPBible-style codes, e.g. `V-AAI-3S`) via the same public API Hebrew would use for its own separate code table. Not Greek-specific by name, but its `_decode_verb`/`_decode_nominal`/`_decode_pronoun` logic is Greek-code-shaped; Hebrew has its own separate `hebrew_morphology_hu.py` |
| `bible_engine/original_language_analysis.py` (760 lines) | Whole-passage AI summary generator (Hebrew+Greek shared), §9.1 |
| `bible_engine/original_language_grounding_check.py` (428 lines) | Post-hoc hallucination scanner for that AI output, §9.2 |
| `components/greek_token_selector/` | Streamlit custom component for inline click-to-select Greek word rendering |
| `textus_kb/adapters/tagnt.py` | Read-only KB adapter (sermon-workshop retrieval), wraps `load_greek_passage_tokens` |

### 2.3 Import / build scripts

| Script | Purpose | Raw source required |
|---|---|---|
| `scripts/build_tagnt_nt_db.py` | Builds `tagnt_nt.sqlite3` from official TAGNT Mat–Jhn and Act–Rev TSVs | **Not present in this repo** (see §2.4) |
| `scripts/build_tagnt_john_db.py` | Same, John-only (demo fixture support) | Same |
| `scripts/build_tbesg_lexicon_db.py` | Builds `tbesg_lexicon.sqlite3` from the official TBESG TSV | **Not present in this repo** |
| `scripts/audit_nt_lexicon_coverage.py` | Produces `data/generated/nt_lexicon_coverage_report.json` | Runs against the committed `tagnt_nt.sqlite3` + `lexicon_hu.json` |
| `scripts/audit_missing_tagnt_strong_ids.py` | Produces `missing_tagnt_strong_id_audit.json` + `tagnt_strong_alias_candidates.json` | Same |
| `scripts/export_nt_missing_lexicon_batch.py`, `scripts/export_missing_alias_target_lexicon_batch.py`, `scripts/export_lexicon_translation_batch.py` | Export batches of missing/alias-target lexemes for (apparently AI-assisted) translation | — |

### 2.4 Generated SQLite files — what's actually shipped

```
$ git ls-files data/generated/ | grep -Ei "tagnt|tbesg|greek"
data/generated/missing_tagnt_strong_id_audit.json
data/generated/nt_lexicon_coverage_report.json
data/generated/tagnt_nt.sqlite3                 <- 34.7 MB, COMMITTED
data/generated/tagnt_strong_alias_candidates.json
```

`.gitignore` blanket-ignores `*.sqlite3` and then explicitly un-ignores four files by name (lines 81–84): `tahot_ot_runtime.sqlite3`, `tbesh_lexicon_runtime.sqlite3`, `acai_entities.sqlite3`, `hebrew_component_fidelity.sqlite3` — **all four are Hebrew/OT**. `tagnt_nt.sqlite3` is tracked anyway (added by an explicit `git add`, commit `fa8d7ac` "data: add production TAGNT New Testament database", 2026-07-28), but **`tbesg_lexicon.sqlite3` is neither in the whitelist nor tracked, and does not exist on disk in this worktree.** Every call to `get_tbesg_lexicon_entry()` in a fresh checkout will raise `TBESGDatabaseUnavailableError` and the UI will show "Az angol lexikai adatbázis még nincs előkészítve." This is a real, currently-live gap for the ~0.02% of tokens not covered by the Hungarian lexicon (and the entire fallback code path is consequently exercised only by mocked tests, never against the real file, in this environment).

Neither the raw TAGNT TSVs nor the raw TBESG TSV are present anywhere in the repository (`data/stepbible_sources/` holds only `TBESH.txt` and `TEHMC.txt`, both Hebrew). **`tagnt_nt.sqlite3` cannot currently be rebuilt from source inside this repo** — it exists only as a committed binary artifact whose source-of-truth is external (STEPBible's GitHub, per its own embedded provenance, §2.5).

### 2.5 Supabase dependency

**None.** `resolve_tagnt_database_path()` and `resolve_tbesg_database_path()` only ever resolve to an env var, a Streamlit secret path override, or the local `data/generated/` file — there is no `supabase_client` import anywhere in the Greek code path, and `grep`ing `supabase/migrations/` for `greek|tagnt|tbesg` returns nothing. Greek analysis is **100% local-SQLite/local-JSON**, unlike Hebrew, which now has an optional Supabase-backed syntax layer.

### 2.6 Caching

`@st.cache_data` on: `load_john_3_16_tokens`, `_load_cached_hungarian_lexicon` (keyed on file mtime), `_load_cached_strong_aliases` (same pattern), `load_tbesg_lexicon_entry`. All are read-through caches over static local files — there is no verse-level "expensive AI call" cache analogous to Hebrew's `HebrewContextualAnalysisCache`, because there is no AI call in this path to cache.

### 2.7 Tests

Directly Greek/TAGNT/TBESG-specific: `test_greek_analysis_ui.py` (43), `test_greek_token_repository.py` (18), `test_greek_lexicon_repository.py` (8), `test_greek_text_demo.py` (17), `test_tagnt_parser.py` (14), `test_tagnt_sqlite.py` (18), `test_tagnt_books.py` (2), `test_tagnt_nt_import.py` (16), `test_tbesg_parser.py` (13), `test_tbesg_sqlite.py` (12), `test_lexicon_hu.py` (22), `test_missing_tagnt_strong_audit.py` (4), `test_nt_lexicon_coverage.py` (6), `test_morphology_hu.py` (14, shared decoder) — **≈207 tests** on the deterministic layer alone. Plus the shared AI-summary system: `test_original_language_ai_fallback.py` (9), `test_original_language_commentary.py` (12), `test_original_language_concordance.py` (14), `test_original_language_post_hoc_validation.py` (29), `test_original_language_token_block.py` (3) — **≈67 more**. Total direct Greek-relevant test surface: **≈274 tests**, all passing at the audited HEAD (not re-run in this audit; existing CI state, not verified here — see §14 blockers if this matters before implementation).

### 2.8 Legacy / demo / dead code

- `greek_text_demo.py` — demo page, not dead (tested, but not routed from `app.py`'s navigation).
- `bible_engine/tagnt_parser.py::get_verse_tokens()` — TSV-file-direct reader, used only by the demo fixture path (`tests/fixtures/tagnt_jhn_3_16_sample.tsv`); the real production path always goes through the SQLite repository. Not dead, but narrow-purpose.
- No other dead Greek code was found. The module surface is small and every file traced has at least one live caller.

---

## 3. Authoritative data sources

| Source | File / DB | License | Version/commit | What it supplies | Production-authoritative? |
|---|---|---|---|---|---|
| **STEPBible TAGNT** (Translators Amalgamated Greek NT) | `data/generated/tagnt_nt.sqlite3` (committed, 34.7 MB) | CC BY 4.0 (STEPBible.org; confirmed already in `docs/textus_knowledge_base_audit.md:850` and `docs/hebrew_ot_architecture_audit.md:37`) | `source_version = "STEPBible GitHub raw 2026-07-27"`, imported 2026-07-28 (commit `fa8d7ac`); source files `TAGNT_Mat-Jhn_raw.txt` / `TAGNT_Act-Rev_raw.txt` | Greek surface form, lemma, raw Robinson-style morph code, Strong ID, edition flags — **the sole source of truth for every deterministic Greek fact in the app** | **Yes** |
| **STEPBible TBESG** (Translators Brief lexicon of Extended Strongs for Greek) | `data/generated/tbesg_lexicon.sqlite3` — **not present in this repo/checkout** | CC BY 4.0 (attribution string already in code: `TBESG_SOURCE_NOTE = "Lexikai adat: STEPBible TBESG, CC BY 4.0."`) | Unknown — no source TSV or built DB in-repo to inspect | English gloss, lemma, brief morph note, references — **fallback only**, and currently non-functional in this checkout (§2.4) | Fallback only, and currently broken here |
| **Hungarian Greek lexicon** (in-house, TBESG-derived) | `bible_engine/data/lexicon_hu.json` (5,959 entries, all G-prefixed), `strong_aliases.json` (alias resolution table) | Internal (Textus), derivative of TBESG | Added 2026-07-28 (commit `3eaa03a`); no further version marker | Hungarian `primary_gloss` + `senses` per lexeme | **Yes — primary lexical source in the UI** (`_render_hungarian_lexicon_section`, tried before TBESG) |
| MorphGNT | — | — | — | — | **Not used anywhere in the codebase** (no references found) |
| MACULA Greek | — | — | — | — | **Not used anywhere in the codebase** (no references found; only Hebrew MACULA exists — `macula_lowfat_parser.py`, `import_macula_to_supabase.py`) |
| Gemini-generated lexical material | `lexicon_hu.json` records, `source` field | — | — | The Hungarian glosses themselves are machine-translated from TBESG English (see `source` values below) — see §5.2 for review-status detail | Yes, and this is the central risk of §5 |

`lexicon_hu.json` source-field breakdown (measured directly, not assumed):

| `source` value | Count |
|---|---|
| "STEPBible TBESG alapján készített magyar munkaváltozat" | 5,883 |
| "STEPBible TBESG via TAGNT alias targets alapján készített magyar munkaváltozat" | 75 |
| "STEPBible TBESG via final unresolved TAGNT audit alapján készített magyar munkaváltozat" | 1 |

All three phrasings say the same thing: machine-produced Hungarian ("munkaváltozat" = working draft) derived from the English TBESG gloss, never from Greek directly and never human-reviewed (confirmed by `review_status`, §5.2). This file is **not** the same file Hebrew uses (`lexicon_hu.json` here contains zero H-prefixed entries) — it is Greek-only despite the generic name.

---

## 4. Morphology audit

### 4.1 Decoder and coverage

`bible_engine/morphology_hu.py::parse_morphology_hu()` decodes raw Robinson/STEPBible-style codes (e.g. `V-2AAI-3S`, `N-NSM`, `A-GSF-C`) into a `HungarianMorphology` dataclass with: `part_of_speech`, `tense`, `voice`, `mood`, `verb_form` (participle/infinitive kept **separate** from `mood` — linguistically correct), `person`, `number`, `case`, `gender`, `degree`, `pronoun_type`, `name_type`, `extra` (indeclinable, abbreviated, Attic form, interrogative, negative, numeral, Hebrew-transliterated), and an `unresolved` tuple for anything it cannot map.

**Measured against the full 142,096-token production corpus: 0 tokens have any unresolved morphology component (0.00%).** This is a materially stronger starting position than Hebrew had (the Hebrew audit found a mislabeled `v`-code affecting 4,305 imperatives before Phase 2A). No equivalent defect was found here — every raw code in the actual corpus maps to a value in the code tables.

### 4.2 Category coverage checklist (against the user's list)

| Category | Represented? | Detail |
|---|---|---|
| Lemma | ✅ | `GreekToken.lemma`, NFC-normalized |
| Part of speech | ✅ | `_FUNCTIONS` table, 16 tags |
| Case | ✅ | Nominative/Genitive/Dative/Accusative/Vocative |
| Number | ✅ | Singular/Plural |
| Gender | ✅ | Masc/Fem/Neuter |
| Person | ✅ | 1st/2nd/3rd |
| Tense | ✅ | Present, Imperfect, Future, 2nd Future, Aorist, 2nd Aorist, Perfect, 2nd Perfect, Pluperfect, 2nd Pluperfect (10 forms) — labeled "idő" (time), see §5 for the terminology risk |
| **Aspect** | ❌ | **Not represented as a separate field anywhere.** Tense-form is the only category; there is no structural distinction between time and aspect |
| Voice | ✅ | Active/Middle/Passive/Middle-or-Passive **and, distinctly, Middle Deponent/Passive Deponent/Middle-or-Passive Deponent** — STEPBible's own edition already separates true middle/passive from deponent at the code level, which the decoder preserves. This is a genuine strength (§5.2) |
| Mood | ✅ | Indicative/Imperative/Subjunctive/Optative |
| Participle | ✅ | `verb_form == "participle"`, decoded with its own case/number/gender via `_decode_case_number_gender` |
| Infinitive | ✅ | `verb_form == "infinitive"` |
| Degree | ✅ | Comparative/Superlative (`C`/`S` extra codes) |
| Pronoun type | ✅ | `pronoun_type` field, populated for D/I/K/Q/R/X/C/P/F/S prefixes |
| Article | ✅ (as POS) | Decoded as `T` → "határozott névelő"; **no articular/anarthrous fact is tracked at the phrase or clause level** — this is purely a per-token POS tag, not a syntax fact (relevant to Granville Sharp-type constructions, §8) |
| Conjunction/particle/preposition | ✅ (as POS labels only) | `CONJ`/`PRT`/`PREP`/`COND`/`ADV`/`INJ`/`ARAM` all map to a bare Hungarian label with no valency or case-government data attached — "preposition + case" as a *construction* does not exist yet (only the two facts separately: the preposition token, and the following noun's case) |
| Proper names | ✅ | `name_type` decodes STEPBible's own P/L/LG/G/PG/T codes into Individual/Location/Location-Gentilic/Gentilic/Person-Gentilic/Title |

### 4.3 Quantitative distribution (measured against the full corpus, 28,576 verb components)

| Voice | Tokens | % of verbs |
|---|---|---|
| Active | 21,026 | 73.6% |
| Passive | 3,179 | 11.1% |
| Middle-or-Passive Deponent | 1,694 | 5.9% |
| Middle Deponent | 1,545 | 5.4% |
| Middle | 746 | 2.6% |
| Passive Deponent | 339 | 1.2% |
| Middle-or-Passive | 47 | 0.2% |

**Deponent forms (all three deponent categories combined) = 3,578 tokens, 12.5% of all verbs.** This is the quantitative backing for the §5 terminology risk: over one in eight verb occurrences is a form where "middle voice" or "passive morphology" cannot be read as semantically reflexive/passive without care — and the data already flags which ones, which is good news for whatever prompt or UI text gets written next.

| Tense-form | Tokens | % of verbs |
|---|---|---|
| Present | 11,802 | 41.3% |
| Aorist | 6,683 | 23.4% |
| 2nd Aorist | 5,082 | 17.8% |
| Imperfect | 1,711 | 6.0% |
| Future | 1,612 | 5.6% |
| Perfect | 1,393 | 4.9% |
| 2nd Perfect | 171 | 0.6% |
| 2nd Pluperfect | 47 | 0.2% |
| Pluperfect | 39 | 0.1% |
| 2nd Future | 36 | 0.1% |

| Verb form | Tokens | % of verbs |
|---|---|---|
| Finite (indicative/imperative/subjunctive/optative) | 19,429 | 68.0% |
| Participle | 6,811 | 23.8% |
| Infinitive | 2,336 | 8.2% |

Participles are almost a quarter of every verb occurrence in the NT — this is the single highest-value deterministic-to-construction target for a future v2 (§8).

### 4.4 Where raw codes reach the UI, and where AI is expected to infer

`token_analysis()` (`greek_analysis_ui.py:361`) sends **both** the raw code (`token.morph_code`, labeled "Morfológiai kód") **and** the decoded Hungarian string (`format_morphology_hu(...)`, labeled "Nyelvtani alak") directly to the UI — the raw STEPBible code is shown to end users verbatim, unexplained (e.g. `V-2AAI-3S`). There is currently no AI involved in this path at all (§9), so there is no place today where "AI is expected to infer deterministic morphology" for Greek — the entire morphology story is deterministic-only. This is worth stating plainly because it means the risk profile for a v2 AI layer is "does the new AI respect data that already exists and is already correct," not "does the new AI need to paper over gaps in an unreliable decoder."

---

## 5. Terminological quality

### 5.1 Simplification risks found in the current (deterministic-only) system

Because there is no AI prose today, these are **not yet live production bugs** — they are risks that a future AI-explanation layer would inherit if it naively re-used the current Hungarian morphology labels as-is (i.e. exactly the situation the user's brief describes for the Hebrew Phase 2E hardening pass, but here found *before* any AI was built rather than after):

| Risk | Where it would enter | Evidence |
|---|---|---|
| **Aorist labeled as if it were simply a past-tense form** ("aorisztoszi") | `_TENSES["A"] = "aorisztoszi"` | No aspect field exists at all (§4.2); "aorisztoszi" as a bare adjective doesn't itself claim "past," but nothing in the data model distinguishes aspectual (non-indicative) aorist from temporal (indicative) aorist — a future prompt describing an aorist participle's "time" would be inventing a fact the decoder does not supply |
| **Imperfect labeled generically** ("imperfektum") | `_TENSES["I"] = "imperfektum"` | Same structural gap — no continuous/iterative/inceptive distinction is tracked, so any AI text asserting one of those readings would be adding un-grounded nuance |
| **Middle voice risk of automatic "reflexive" reading** | `_VOICES["M"] = "mediális igenem"` | Mitigated by the code table itself: genuine middle (746 tokens, 2.6%) is **already kept separate** from all three deponent categories (3,578 tokens, 12.5%, §4.3). A future prompt must be told to use this distinction, not re-derive it |
| **Passive morphology ≠ always semantic passive** | `_VOICES["P"]`, `"O"` (passive deponent) | Same mitigation as above — 339 tokens (1.2%) are already flagged `passzív deponens` distinctly from the 3,179 genuine passive tokens (11.1%) |
| **Participle function inferred from morphology alone** | `verb_form == "participle"`, decoded case/number/gender only | The decoder supplies **form** (tense/voice/case/number/gender) but nothing about **syntactic function** (attributive/adverbial/circumstantial/substantival) — that fact does not exist anywhere in the current data (§7); any future text asserting a participle's function is asserting a fact with zero deterministic backing today |
| **Deponent treated as simple lexical category without context** | `_VOICES["D"/"O"/"N"]` | The code table treats deponent purely as a voice-slot value, which is exactly right for *this* data model — the risk is downstream, if a future prompt treats "deponent" as meaning "grammatically middle-form but semantically active" in *every* case without checking whether the individual lexeme is genuinely deponent-only vs. has a live active counterpart. That distinction is not in TAGNT and would need lexical annotation |

### 5.2 The most serious terminology/quality risk: the Hungarian lexicon is 100% unreviewed

Measured directly against `bible_engine/data/lexicon_hu.json`:

```
total entries:        5,959
review_status="draft":    5,959   (100.0%)
review_status="reviewed":     0   (0.0%)
```

**Every single Hungarian Greek lexeme gloss in production has never been marked as reviewed.** `VALID_REVIEW_STATUSES = frozenset({"draft", "reviewed"})` exists in `lexicon_hu.py` and the UI already renders `review_status` to the user ("Ellenőrzési állapot: munkaváltozat" — see `REVIEW_STATUS_LABELS` in `greek_analysis_ui.py:90`), so the app is **honestly labeling** every gloss as unreviewed today; this is not a hidden problem. But it means that **the single most-consumed piece of Greek linguistic content in the app (130,869 token occurrences, §6.2) has never had a second pass**, in contrast to Hebrew where the audit found *some* content trustworthy enough to build on and some specifically broken. Any Greek AI layer that treats `primary_gloss`/`senses` as ground truth the way Hebrew Phase 2E treats `lexical_sense.base_meaning_hu` would be building server-side "authoritative override" logic on top of content the app itself labels as a draft.

---

## 6. Lexical layer audit

### 6.1 Coverage (from `data/generated/nt_lexicon_coverage_report.json`, corroborated against a live query of `tagnt_nt.sqlite3` — the report's `tagnt_total_tokens: 142096` matches the DB exactly, so the report is current, not stale)

| Metric | Value |
|---|---|
| TAGNT total tokens | 142,096 |
| TAGNT unique Strong IDs (lexemes) | 5,580 |
| Tokens without a Strong ID | 0 |
| Strong IDs with **direct** Hungarian coverage | 5,310 / 5,580 lexemes (95.16%) → 130,869 / 142,096 tokens (92.10%) |
| Strong IDs covered **only via alias** (a suffix-letter variant resolving to a base Strong ID) | 269 lexemes, 11,202 tokens (7.88% of tokens) |
| **Effective** coverage (direct + alias) | **99.98% of tokens, 99.98% of lexemes** |
| Genuinely unresolved | 1 Strong ID, 25 token occurrences |

The 1 unresolved Strong ID is flagged `needs_manual_review` in `missing_tagnt_strong_id_audit.json` (`genuinely_missing_lexeme_count: 0` — every other missing ID resolved to an existing lexeme via alias, `alias_candidate_count: 266` at ≥0.99 confidence, `token_frequency: 11194`).

### 6.2 Basic vs. contextual meaning

**There is no contextual-meaning concept in the current Greek lexical layer at all.** `HungarianLexiconEntry` has exactly one `primary_gloss` plus a `senses` tuple (possible meanings) **per lexeme** (keyed by Strong ID) — there is no per-token, per-verse contextual sense field anywhere, and no AI is involved to produce one (§9). This is the single largest structural gap relative to what Hebrew Phase 2E built (`lexical_sense.base_meaning_hu` as deterministic floor + AI `contextual_meaning_hu` layered on top, server-validated). A Greek v2 following the same pattern would need to add this layer from scratch — nothing to reuse or migrate.

### 6.3 Proper names

Measured directly: **3,976 proper-name tokens** (name-type code present on the token or a component), covering **584 unique names**. Hungarian coverage: **100%** (1,850 direct, 2,126 via alias, 0 uncovered). Proper names are not a coverage gap.

### 6.4 Overwriting / duplicate entries

`load_hungarian_lexicon()` (`lexicon_hu.py:84`) raises `ValueError` on any duplicate `strong_id` at load time — this is enforced by a loader-level invariant, not just convention, so silent overwrite cannot currently happen in production (the file loads successfully, so no duplicates exist in the shipped data).

### 6.5 Rare words

Not separately measured beyond the aggregate coverage numbers above — "rare" isn't a distinct axis of the current data (no frequency-banded coverage report exists). The 1 genuinely-unresolved Strong ID (25 occurrences) is the only concrete "rare and uncovered" case identified.

---

## 7. Token identity / alignment

**Single source, single flat table — no cross-dataset alignment problem exists today, because there is only one Greek dataset.** Every field (surface form, lemma, morph code, Strong ID, edition flags) lives on one row of `greek_tokens`, keyed by `(book, chapter, verse, word_index)` with a `UNIQUE(book, chapter, verse, word_index, edition_flags)` constraint. `word_index` (a simple 1-based position within the verse) is the identity used consistently end-to-end: by the SQLite schema, by `GreekToken.word_index`, by the UI selection state (`TokenSelection.key` = `f"{book}:{chapter}:{verse}:{word_index}"`), and by the custom Streamlit component (`greek_token_selector`).

This is **fragile positional matching in the sense that it would not survive introducing a second Greek dataset** (e.g. MACULA Greek) without an explicit alignment step — MACULA nodes have their own IDs, and nothing currently maps TAGNT's `word_index` to any external identifier. This is exactly the kind of problem Hebrew Analysis v2 had to solve for its own MACULA alignment (`bible_engine/macula_lowfat_parser.py` + `hebrew_component_fidelity.sqlite3`), and Greek would face the same class of problem, just not yet, because nothing has been layered on top of TAGNT yet.

---

## 8. Current syntax capabilities

**None.** The `greek_tokens` schema has no phrase, clause, dependency, semantic-role, or participant/coreference tables — confirmed both by reading `create_schema()` in full and by confirming there is no second Greek-related table anywhere in the SQLite file or migrations. `grep`ing the entire codebase for "macula" case-insensitively returns only Hebrew-related files (`macula_lowfat_parser.py`, `import_macula_to_supabase.py`, `build_macula_alignment_store.py`, `classify_macula_unresolved.py`); there is no Greek MACULA usage of any kind, confirming the user's framing that MACULA Greek is an appropriate future candidate, not something to build against today.

### 8.1 Deterministic construction candidates for a future phase (planning only, per instructions — no heuristic theological interpretation attempted)

Ranked roughly by how directly the *existing* TAGNT morphology alone (no new dataset) could support detection, vs. what genuinely needs MACULA Greek-class syntax data:

| Construction | Detectable from TAGNT morphology alone? | Notes |
|---|---|---|
| Repeated lemma | ✅ Yes | Same technique as the Hebrew `repeated_lemma_in_verse` detector — pure lemma/token-position matching, no new data needed |
| Article + participle | Partially | Article (POS=`T`) and participle (`verb_form=="participle"`) are both known per-token; **adjacency/agreement** (same case/number/gender, article immediately preceding) is checkable today. Whether the article's *referent* is the participle (vs. an intervening noun) needs phrase-level data to be reliable at scale |
| Preposition + case | ✅ Yes | Preposition token + following noun's case are both known; simple positional-adjacency detection is directly buildable from existing data |
| Negation patterns | ✅ Yes | `_EXTRAS["N"] = "tagadó jelölés"` already exists per-token; aggregating negation markers per clause needs clause boundaries (not yet available) to be precise, but simple co-occurrence-in-verse is buildable now |
| Repeated/coordinated structures (καί-chains) | Partially | Conjunction POS is known; true coordination *structure* (what exactly is being coordinated) needs phrase/clause data |
| Infinitival constructions | Partially | Infinitive tokens are directly flagged (`verb_form=="infinitive"`, 2,336 tokens); which noun/verb governs the infinitive needs dependency data |
| Participial constructions (attributive/circumstantial) | ❌ No | Needs syntactic function, which is not in TAGNT at all — genuinely requires MACULA Greek or equivalent |
| **Genitive absolute** | ❌ No | Requires detecting a genitive noun + genitive participle **not grammatically connected to the main clause** — case/POS alone cannot distinguish this from an ordinary genitive-noun-plus-participle phrase; needs clause-boundary/dependency data |
| Conditional clauses (εἰ/ἐάν + mood pattern) | Partially | The conjunction (`COND` POS, or lemma `εἰ`/`ἐάν`) and the following verb's mood are both known per-token; classifying which of the four traditional conditional "classes" applies needs the two clauses' boundaries, which TAGNT doesn't provide |
| ἵνα clauses | Partially | Lemma `ἵνα` + following subjunctive mood are directly detectable; clause *extent* (where the ἵνα-clause ends) is not |
| ὅτι clauses | Partially | Same shape as ἵνα — lemma detection is trivial, clause extent is not |
| Relative clauses | Partially | Relative pronoun POS (`R`) is known; antecedent identification needs dependency/coreference data |
| Predicate nominative / article patterns (Granville Sharp-type, anarthrous predicate nominative) | ❌ No | Needs phrase-level subject/predicate identification — pure token morphology cannot distinguish "ὁ λόγος ἦν θεός" as predicate-nominative-anarthrous from any other adjacent-noun pattern without clause structure |

**Bottom line for §8:** roughly half the requested construction types (repeated lemma, preposition+case, negation, simple co-occurrence versions of ἵνα/ὅτι/conditional-marker detection) are buildable directly from the data already in production. The other half — genuinely the more linguistically interesting half (genitive absolute, participle function, predicate-nominative article patterns, relative-clause antecedents) — requires clause/phrase/dependency data that does not exist and that only a MACULA-Greek-class import would supply.

---

## 9. AI boundary audit

### 9.1 System A — whole-passage AI summary (`bible_engine/original_language_analysis.py`, shared Hebrew+Greek, pre-dates Phase 2E)

Triggered by the "Eredeti szöveg tanulmányozása" button (`app.py:7820`). Two modes:

- **`STATUS_GROUNDED`** (`ORIGINAL_TEXT_BASE_PROMPT`): local DB tokens (Greek via `load_greek_passage_tokens`, Hebrew via `HebrewTokenRepository`) are formatted into a `TOKEN_BLOCK_HEADER`-prefixed list and given to Gemini as the **exclusive** source ("EREDETI NYELVI TOKENEK... kizárólagos forrás"). The prompt already forbids: inventing tokens/lemmas/forms not in the list, citing token numbers, using Latin/English grammatical terminology in the output ("aoristus", "genitivus" etc. explicitly named as forbidden), asserting disputed-identity theological claims not directly evidenced, over-extending etymology beyond the lexical data given, and homiletical/application conclusions. Limited to ≤5 highlighted words, ≤3 sentences each (4 in narrow, data-justified exceptions).
- **`STATUS_AI_FALLBACK`** (`ORIGINAL_TEXT_AI_FALLBACK_PROMPT`): used only when local tokens are entirely unavailable for the passage. Falls back to the model's own knowledge, but is explicitly forbidden from claiming DB provenance or citing token/evidence IDs — and the UI shows `AI_FALLBACK_USER_NOTICE` ("...ezért az elemzés AI-alapú...") so the user is told when this happened.

A **secondary, deliberately smaller** commentary integration (Calvin/JFB/Henry via `textus_kb`) is attached, but explicitly ranked below the token data and only in the grounded path, never the fallback path (`ORIGINAL_TEXT_COMMENTARY_RULE`).

**Where this is weaker than the Hebrew Phase 2E pattern:** grounding is enforced entirely through prompt instructions (what the model is told not to do) plus a post-hoc regex scan (§9.2) — there is no structured JSON schema, no per-field server-side validator, and no mechanism analogous to Hebrew's closed-world morphology-claim rejection (`_text_claims_unsupported_state`). The prompt already independently arrived at several of the same principles Hebrew Phase 2E had to add later by hardening (forbid unsupported etymology, forbid unsupported theological-identity claims, forbid inventing evidence) — but enforces them by instruction only, not by parsing the output and rejecting non-conforming claims field-by-field.

### 9.2 Post-hoc grounding check (`bible_engine/original_language_grounding_check.py`)

A **regex-based hallucination scanner**, not a grammatical-fact validator: it extracts Greek/Hebrew word runs and Strong-ID citations from the AI's output text and classifies each as `PASSAGE_MATCH` / `GLOBAL_OTHER_PASSAGE` (the word/Strong ID is real but not from this verse) / `UNKNOWN` (not found anywhere in either corpus) / `INVALID_STRONG_ID`. It does **not** check morphological, tense/voice/mood, or syntactic claims — it can catch "the AI cited a Greek word that isn't in this verse" but cannot catch "the AI called an active-voice verb passive" or "the AI asserted a genitive absolute that isn't one." This is the direct Greek/shared analogue of the gap Hebrew Phase 2E's closed-world validator was built to close, and it does not yet exist for grammatical claims in this system.

### 9.3 System B — Phase 2E word-click panel (`bible_engine/hebrew_contextual_analysis*.py`)

**Hebrew-only.** Confirmed by full reads of `greek_analysis_ui.py` and `greek_text_demo.py`: the only place Phase 2E machinery appears in a Greek-adjacent file is the OT-fallback branch inside `render_greek_analysis_block`, which forwards the Hebrew generate-function through **unused for genuine Greek tokens**. **There is no per-word structured AI explanation for Greek today at all.**

### 9.4 Facts vs. generative explanation — the rule to carry forward

Per the user's stated target rule (deterministic facts closed to AI invention; AI may explain and discuss cautiously), the current deterministic inventory that any future Greek AI must treat as closed-world is: lemma, part of speech, case, number, gender, person, tense-form, voice (including deponent-vs-genuine distinction), mood, verb_form (participle/infinitive), degree, pronoun type, article (as POS only), name_type, edition_flags (raw, unexplained), Hungarian gloss/senses (**with the important caveat that this "fact" is itself 100% unreviewed draft content, §5.2**). Everything in §8's "not detectable from TAGNT alone" column (participle syntactic function, genitive absolute, clause-level negation scope, relative-clause antecedents, predicate-nominative patterns) is **not yet a fact in the system at all** — it cannot be "protected from AI invention" because it doesn't exist to invent *incorrectly against*; any AI claim about it today would be 100% AI-sourced with zero deterministic grounding available to check it against, which is a stronger version of the same risk, not a smaller one.

---

## 10. Textual criticism

**No deterministic textual-variant feature exists.** What *is* present:

- `edition_flags` (e.g. `"NKO"`, `"K"`, `"N(k)O"`) — raw STEPBible edition-inclusion sigla, stored per token, displayed verbatim in the UI under the label "Kiadásjelölés" with **zero explanation of what the letters mean** (no legend, no tooltip, no apparatus). A user sees the raw code with no interpretive aid.
- Double-square-bracket markers (`[[`/`]]`, STEPBible's own notation for disputed-authenticity passages such as John 7:53–8:11) are **deliberately preserved** in the `greek_form` field by `_clean_greek_form()` (only the pilcrow `¶` formatting artifact is stripped, per an explicit code comment) — but again, nothing in the UI explains to the user what these brackets mean; they appear as literal bracket characters in the rendered Greek text.

**No NA28/UBS/SBL apparatus, no manuscript-level variant claims, and no textual-criticism feature of any kind exists in the UI.** Per instructions, this audit does not recommend adding one — TAGNT's own edition flags are the only variant-adjacent data present, and per §2.4/§3, TAGNT's license (CC BY 4.0) is already established, so surfacing and *explaining* the existing `edition_flags` (rather than adding a new external dataset) would be the lowest-risk future improvement if this is ever prioritized — noted here only as an observation, not a phase proposal, per the "do not add" instruction.

---

## 11. Production / data architecture — what generalizes vs. what's Greek-specific

### COMMON ORIGINAL-LANGUAGE INFRASTRUCTURE (already shared or cleanly shareable)

- `bible_engine/morphology_hu.py` — the *pattern* (raw-code → dataclass → Hungarian formatter) is shared conceptually with Hebrew's own decoder, though the code tables are entirely different and cannot be merged, only the shape can.
- `bible_engine/original_language_analysis.py` + `original_language_grounding_check.py` — **already literally shared** between Hebrew and Greek today (Hebrew's `_format_hebrew_token_line` and Greek's `_format_greek_token_line` sit side by side in the same file, dispatched on which repository resolved tokens).
- `render_greek_analysis_block()`'s dispatch pattern (book code → language routing) is the existing precedent for how a unified original-language entry point can route between engines — any Greek v2 word-click panel should probably be *added as a new branch inside this same dispatcher*, not a parallel one.
- The **general shape** of Hebrew's repository protocol, dataset versioning, caching pattern, structured contextual-analysis contract (`schema_version`, evidence IDs, grounding validation) is a reasonable template to imitate for Greek's *eventual* Phase-2E-equivalent — but see below, this is a template to imitate, not code to literally reuse, because the underlying data shapes differ.

### GREEK-SPECIFIC LINGUISTIC LOGIC (must be built fresh, cannot be inherited)

- The morphology code tables themselves (Robinson-style Greek codes vs. STEPBible Hebrew codes) — completely different alphabets, no shared table.
- The lexicon data model — Greek currently has no per-token contextual-meaning concept at all (§6.2); Hebrew's `lexical_sense.base_meaning_hu` + AI `contextual_meaning_hu` split would need to be built from scratch for Greek, and critically, **the underlying Hungarian glosses to build it on top of are unreviewed draft content** (§5.2) — a Hebrew-style "deterministic lexical override always wins over the model" rule would currently mean "an unreviewed machine translation always wins over the model," which is not obviously an improvement and needs a human decision, not an engineering one.
- Any construction detector (§8) — Hebrew's detectors (`_detect_construct_with_article_anomaly`, `_detect_infinitive_absolute_with_finite_verb`, etc.) are written against Hebrew's `TokenAnalysis`/`ComponentAnalysis` shape and Hebrew-specific grammatical categories (construct state has no Greek equivalent); none of this code transfers, only the *pattern* of "flag anomalies, never silently override the primary source" transfers.
- Supabase backend — Hebrew has one (optional, syntax layer); Greek has none and would need one built if MACULA Greek syntax is ever imported at Hebrew's scale (currently 142K Greek tokens vs. Hebrew's ~305K OT tokens — a comparable order of magnitude, so the same "batched RPC, not per-row REST" lessons from the Hebrew import-performance work would very likely apply again).

### Explicitly not refactored in this audit, per instructions

No shared-architecture refactor was attempted or proposed as code. The above is a classification of what *could* generalize, not a plan to do so yet.

---

## 12. Representative regression verses

Chosen to exercise the phenomena requested, using TAGNT's own 3-letter book codes. No goldens created — verse selection only, per instructions.

| # | Reference (TAGNT code) | Phenomenon |
|---|---|---|
| 1 | Jhn 3:16 | ἵνα clause (ἵνα... μὴ ἀπόληται), aorist (ἠγάπησεν, ἔδωκεν) |
| 2 | Jhn 1:1 | Article usage / anarthrous predicate nominative (θεὸς ἦν ὁ λόγος), imperfect (ἦν) |
| 3 | Jhn 1:14 | Aorist (ἐσκήνωσεν), participial construction candidate |
| 4 | Jhn 19:30 | Perfect (τετέλεσται) |
| 5 | Mat 28:19–20 | Chained participles + finite imperative (πορευθέντες... μαθητεύσατε, βαπτίζοντες, διδάσκοντες) |
| 6 | Mat 9:18 | Genitive absolute (ταῦτα αὐτοῦ λαλοῦντος) |
| 7 | Php 1:21 | Articular infinitives (τὸ ζῆν, τὸ ἀποθανεῖν) |
| 8 | 1Co 15:13–14 | First-class conditional chain (εἰ + indicative, repeated) |
| 9 | Rom 5:1 | Aorist passive participle (δικαιωθέντες) — genuine passive, not deponent |
| 10 | 1Ti 3:1 | Middle voice, non-reflexive-but-not-passive reading (ὀρέγεται) |
| 11 | Mrk 1:9–11 | Deponent aorist forms (ἀπεκρίθη-class), voice-label risk case |
| 12 | Rom 5:12 | Difficult/disputed syntax (ἐφ' ᾧ) |
| 13 | 2Pe 1:1 | Article + coordinated nouns (Granville-Sharp-shaped construction) |
| 14 | Rom 3:24–25 | Preposition + case chain (διὰ + genitive, διὰ + accusative) |
| 15 | Luk 10:25–37 | Longer passage with mixed relative clauses, participles, and conditional-like constructions — useful as a multi-verse stress case beyond single-verse phenomena |

---

## 13. Concrete blockers before implementation

1. **`tbesg_lexicon.sqlite3` is not provisioned in this repository.** The English-lexicon fallback path is currently dead in any fresh checkout (§2.4). Needs either: the raw TBESG TSV added to `data/stepbible_sources/` and the DB built via the existing `scripts/build_tbesg_lexicon_db.py`, or the built DB committed the same way `tagnt_nt.sqlite3` was. Small, mechanical, not a design question.
2. **The Hungarian lexicon is 100% unreviewed draft content** (§5.2). Before any server-side "lexical fact always wins" rule (the Hebrew Phase 2E pattern) is built for Greek, a human decision is needed: is unreviewed-but-source-traceable content acceptable as the deterministic floor, or does some review pass need to happen first? This is a product/editorial decision, not something this audit can resolve.
3. **Zero deterministic syntax data.** Roughly half of the user's requested construction types (§8) cannot be built at all without new data (genitive absolute, participle function, predicate-nominative patterns, clause-scoped negation, relative-clause antecedents). A MACULA-Greek-class import — explicitly not started here, per instructions — is a prerequisite for that half, not an optional enhancement.
4. **No raw TAGNT/TBESG source files are reproducible in-repo.** `tagnt_nt.sqlite3` cannot currently be rebuilt from source inside this repository if it were ever lost or needed a re-import for a newer STEPBible release; only the committed binary exists. Worth a provenance/reproducibility fix at some point, not urgent.
5. **Two independent, architecturally different AI systems already touch this space** (whole-passage free-prose grounding, §9.1, vs. the Hebrew Phase 2E structured-validation pattern the user wants to emulate). A Greek v2 design needs an explicit decision on whether it replaces System A for Greek, extends it, or adds a genuinely new System C alongside it — this is a design question for the next phase, not something to resolve in an audit.

None of these blockers require touching Supabase, re-running any import, or modifying Hebrew Analysis v2 to resolve — all five are scoped entirely to the Greek surface area.

---

## 14. Recommendation

**AUDIT FOUND BLOCKERS — (1) `tbesg_lexicon.sqlite3` is unprovisioned/unbuildable in this repo; (2) the entire Hungarian Greek lexicon (5,959 lexemes) is unreviewed draft content and needs an explicit editorial decision before being treated as a deterministic "always wins over AI" source; (3) zero deterministic syntax data exists, blocking roughly half of the requested future construction types until a MACULA-Greek-class import is planned and executed; (4) no in-repo reproducibility path exists for the two core STEPBible source files; (5) the relationship between the existing whole-passage AI system (§9.1) and any new Phase-2E-style Greek system needs an explicit design decision, not an accretion.**

None of these are corpus-integrity defects of the kind found in the Hebrew pre-Phase-2A audit — the morphology decoder is 100%-resolved and the lexical coverage is 99.98% effective. The blockers here are provisioning, editorial-review, and syntax-data-availability problems, all addressable without touching what is currently in production. Phase 1 of a "Greek Analysis v2" track should be scoped to closing blockers 1 and 4 (mechanical) and getting explicit human decisions on blockers 2, 3, and 5 (product/editorial), before any AI-facing prompt or schema work begins.
