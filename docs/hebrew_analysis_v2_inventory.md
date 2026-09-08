# Hebrew Analysis v2 — Repository Inventory and Architecture Audit

**Status:** Audit only. No production code, data, prompt, UI, dependency or test was modified.
**Date:** 2026-09-08
**Branch:** `claude/hebrew-analysis-v2-audit-efc152`
**HEAD at audit time:** `f1ec60e1257d342a9a6d08266b10dd76a285495b`
**Scope:** Discovery and proposal only. No dataset was downloaded, vendored or integrated.

> ### Phase 2A follow-up — verified corrections to this audit
>
> Implementation ([`docs/hebrew_analysis_v2_phase2a.md`](hebrew_analysis_v2_phase2a.md))
> confirmed the headline findings and corrected four points:
>
> 1. **§5.4 understated the damage.** A *second* form-code defect was found:
>    TEHMC overloads `c`, so **534 cohortatives** ("let us go down", Gen 11:7)
>    were labelled *infinitivus constructus* while carrying a person. Before
>    Phase 2A the corpus decoded to **0 imperatives and 0 cohortatives**.
> 2. **§5.4's suspicion of `u` was wrong.** Corpus evidence clears it: `u`
>    occurs only after an ordinary uppercase-`C` waw (999/999) and `i` never
>    does, so "Conjunction Imperfect" is correct. The genuinely unverifiable
>    codes are the stems `Q/u/M/e/a/D/i` (181 tokens), now reported unresolved.
> 3. **§6.4's root cause was wrong in an important way.** The `אֲשֶׁר` defect
>    was *not* an AI mis-scoping an identifier during translation. TBESH's
>    `uStrong` column is a cross-reference, and the importer indexed records
>    under it with `INSERT OR REPLACE`, so derived rows overwrote the lexemes
>    they pointed at. The AI faithfully translated a hijacked record.
> 4. **The lexical damage is far wider than §6.4 suggested.** 1,056 TBESH keys
>    (54% of all corpus Strong references) and **299 Hungarian records**
>    (134,232 tokens) describe the wrong word — including `H3068G`, the divine
>    name, rendered *"béke; teljesség"*. 94% is explained by the hijack.
>
> Everything else in this document stands as written.

---

## 1. Executive summary

### 1.1 The headline answer

> **Can we preserve the current Hebrew morphology implementation and add syntax/contextual interpretation on top of it, or does the internal representation need normalization first?**

**Answer: The *structure* is reusable and genuinely good. The *content* is not currently trustworthy and must be corrected and re-validated before anything is layered on top.**

This is a deliberately split verdict, because the two halves point in opposite directions and the repository evidence is unambiguous about both.

**Reusable — keep it (structural verdict).**
`bible_engine/hebrew_morphology.py` already exposes `verb_stem` and `verb_conjugation` as *separate normalized dataclass fields* (`HebrewMorphology`, lines 24–25), alongside `person`, `gender`, `number`, `state`, `suffix_*`, plus a per-component breakdown for slash-separated composite codes and an explicit four-value confidence `status`. The decoder is pure, deterministic, Streamlit-free and unit-tested. The `HebrewAnalysisBundle` token schema proposed in §16 is close to a field-by-field rename of what this dataclass already produces. There is no architectural reason to rewrite it.

**Blocking — fix it first (content verdict).**
The decoder's TEHMC code tables contain at least one demonstrably wrong mapping that corrupts a large, theologically important slice of the Hebrew Bible, and the existing test suite *asserts the wrong behaviour as correct*, which is why it has survived:

- **`VERB_FORMS["v"]` is mapped to `"Consecutive Perfect"` → Hungarian `weqatal`.** In the STEPBible/OSHB morphology standard `v` is the **imperative**.
- Measured against the shipped runtime database (`data/generated/tahot_ot_runtime.sqlite3`, 305,635 surface words): the form code `v` occurs **4,305 times and is 100% second person** — the signature of an imperative and impossible for a weqatal. The dataset's own English glosses confirm it: `HVqv2mp` on `פְּר֣וּ` = *"be fruitful"* (Gen 1:22, 1:28), `HVqv2ms` on `קַח` = *"take"* (Gen 22:2), `עֲשֵׂ֤ה` = *"make"* (Gen 6:14).
- The genuine weqatal code `q` occurs 6,344 times and is spread across 1st/2nd/3rd person (3666/1555/1123) exactly as a consecutive perfect should be.
- The code `m`, which the decoder *does* map to `"Imperative"`, occurs **zero times** in the entire Old Testament.
- Net effect: **every Hebrew imperative in the Old Testament is currently displayed to the user in Hungarian as `weqatal`**, and is flagged `status="fully_decoded"` — wrong *and* confidently wrong.
- `tests/test_hebrew_morphology_hu.py:73` asserts `"HVqv3ms": "qal törzs, weqatal"`. That code combination (`v` + 3rd person) **cannot occur in the corpus**. Line 74 tests imperatives via `HVqm2ms`, a code that does not exist in the data. The golden tests were written against invented codes rather than real TAHOT rows, which is precisely why the defect was never caught.

A syntax and contextual-interpretation layer built on a morphology layer that mislabels 4,305 imperatives would propagate the error into AI prose, into any future MACULA alignment, and into the expert regression fixtures themselves.

**Therefore the recommended sequence is: correct and re-validate the deterministic morphology tables against the real corpus (small, days-scale) → normalize into an explicit bundle → only then add syntax and AI interpretation.** This is not a rewrite. It is a targeted correction plus a normalization pass over a structure that is otherwise sound.

### 1.2 Secondary findings, in order of severity

| # | Finding | Evidence |
|---|---|---|
| 1 | 4,305 imperatives mislabelled `weqatal`; tests encode the bug | §5.4 |
| 2 | The reported `אֲשֶׁר` gloss defect is real, reproduced exactly, and root-caused | §6.4 |
| 3 | 100% of the 6,493-entry Hungarian Hebrew lexicon is `ai_assisted` + `draft`; zero human review | §6.3 |
| 4 | The AI receives raw TEHMC codes, not decoded grammar — it re-parses morphology today | §7.2 |
| 5 | Per-component surface, morphology and gloss are destroyed by the DB size-pruning step | §2.3 |
| 6 | No root (`gyök`) concept exists anywhere in the codebase | §6.1 |
| 7 | Two parallel, non-interoperating reference models | §8 |
| 8 | Zero persistent cache for Hebrew analysis; `use_cache=False` is hard-coded | §9 |
| 9 | 96.5 MB SQLite committed to git; ~3.4 MB of headroom under the 100 MB limit | §13.9, §21 |
| 10 | `COMPONENT_ROLE_HU["core"] == "lexikai mag"` — the exact term flagged for replacement | §6.2 |
| 11 | Component/analysis index misalignment on every maqaf-joined token | §5.5 |
| 12 | 4 pre-existing test failures from untracked generated artifacts | §11.3 |

### 1.3 What is genuinely strong

It is worth being explicit that this codebase is in far better shape than the problem report implies:

- The **deterministic/AI boundary the target architecture asks for largely already exists**. `bible_engine/original_language_analysis.py` implements an explicit DB-first / AI-fallback / unavailable state machine with three named statuses, a user-visible fallback notice, and a hard prohibition on the AI claiming database provenance.
- **The Hungarian lexicon translation pipeline is already fully offline.** `bible_engine/hebrew_lexicon_translation_workflow.py` is invoked only from `scripts/` (export batch → external model → import batch, with validation). No LLM call occurs at request time in the lexicon path.
- **A post-hoc grounding cross-check already exists** (`bible_engine/original_language_grounding_check.py`), classifying AI-emitted Hebrew forms against the local corpus with deliberately cautious categories.
- **A precedent for exactly the offline-import architecture §15 proposes already ships**: `data/generated/acai_entities.sqlite3` (ACAI, Clear Bible/Aquifer, 5,700 entities, 98,649 passage links) with a model provenance schema recording `upstream_repository`, `upstream_commit`, `source_version`, `license`, `license_url`, `attribution` and `content_hash`.
- **Ketiv/Qere is already deterministically captured**: 1,323 records, 1,013 ketiv, 1,309 qere, with `Q(K)`/`Q(k)` source-edition markers.

The v2 work is a correction-and-extension project, not a greenfield rebuild.

---

## 2. Current Hebrew analysis architecture

### 2.1 Module map

| Layer | Module | Lines | Role |
|---|---|---|---|
| Reference | `bible_engine/hebrew_books.py` | 152 | 39 OT books; RÚF↔TAHOT code mapping; `parse_hebrew_reference()` |
| Source parsing | `bible_engine/hebrew_parser.py` | 205 | TAHOT TSV row → `HebrewToken` / `HebrewComponent` |
| Storage | `bible_engine/hebrew_sqlite.py` | 929 | Schema, importer, atomic build, read queries |
| Repository | `bible_engine/hebrew_token_repository.py` | 97 | `HebrewTokenRepository` facade + diagnostics |
| Morphology | `bible_engine/hebrew_morphology.py` | 534 | TEHMC code → `HebrewMorphology` dataclass |
| Terminology | `bible_engine/hebrew_morphology_hu.py` | 396 | English morphology terms → Hungarian |
| Lexicon (EN) | `bible_engine/tbesh_parser.py` | 76 | TBESH TSV → `HebrewLexiconEntry` |
| Lexicon (EN) repo | `bible_engine/hebrew_lexicon_repository.py` | 227 | Strong normalization, alias resolution |
| Lexicon (HU) | `bible_engine/hebrew_lexicon_hu.py` | 195 | Hungarian lexicon load + 3-tier resolution |
| Lexicon pipeline | `bible_engine/hebrew_lexicon_translation_workflow.py` | 1336 | **Offline** batch export/import + audits |
| Analysis service | `bible_engine/original_language_analysis.py` | 725 | DB-first/AI-fallback planner, prompts |
| Grounding | `bible_engine/original_language_grounding_check.py` | 428 | Post-hoc AI grounding cross-check |
| UI (Hebrew) | `hebrew_text_demo.py` | 893 | View model, token selector, analysis card |
| UI (dispatch) | `bible_engine/greek_analysis_ui.py` | 1267 | `render_greek_analysis_block()` → routes OT to Hebrew |
| Concordance | `original_language_concordance.py` | 221 | Lemma/Strong search across Hebrew + Greek |
| App | `app.py` | ~9000 | Streamlit tab, `generate_text()`, session state |

### 2.2 Runtime data stores

| File | Size | Tracked in git? |
|---|---|---|
| `data/generated/tahot_ot_runtime.sqlite3` | **96.5 MB** | **Yes** (explicit `.gitignore` negation, line 81) |
| `data/generated/tbesh_lexicon_runtime.sqlite3` | 14.0 MB | Yes (line 82) |
| `data/generated/acai_entities.sqlite3` | 36.9 MB | Yes (line 83) |
| `bible_engine/data/hebrew_lexicon_hu.json` | 6,493 entries | Yes |
| `bible_engine/data/hebrew_strong_aliases.json` | 127 aliases | Yes |

`.gitignore` blanket-ignores `*.sqlite3` (line 77) and then re-includes these three by name. Total tracked Hebrew/Greek/KB binary payload ≈ **147 MB**.

### 2.3 The pruning step and what it destroys

`scripts/prune_tahot_runtime_db.py` exists solely to keep the runtime database committable under GitHub's 100 MB hard limit. Its docstring is candid about this. It:

- **drops the tables** `token_components`, `lexicon_entries`, `strong_aliases`;
- **drops the columns** `raw_fields_json`, `expanded_strong_tags`, `source_token_id`;
- rewrites `token_strong_ids` to a `WITHOUT ROWID` table joined on integer `token_id`, with single-character role codes (`t`/`c`/`p`/`s`) and an explicit `seq` column to preserve component order.

Verified against the live database — the shipped schema is exactly the pruned form:

```
TABLES:      metadata, books, ketiv_qere, tokens, token_strong_ids
tokens cols: token_id, stable_token_key, book, chapter, verse, word_index, token_index,
             surface, surface_without_accents, transliteration, english_gloss, lemma,
             morphology_code, language, ketiv, qere, punctuation, maqaf,
             source_edition, meaning_variant, spelling_variant
tsi cols:    token_id, strong_id, role, seq
```

**The consequence is a silent, significant data-fidelity loss.** Because `token_components` is gone, `_token_from_normalized_row()` (`bible_engine/hebrew_sqlite.py:558`) must *fabricate* `HebrewComponent` objects from `token_strong_ids` alone:

```python
components = tuple(
    HebrewComponent(
        surface=row["surface"] if role == "core" else "",   # prefix/suffix surface LOST
        strong_id=item["strong_id"],
        morphology_code=row["morphology_code"] or "",        # composite code on EVERY component
        role=role,
    )
    ...
)
```

Reproduced live on Gen 1:1 `בְּ/רֵאשִׁ֖ית`:

```
prefixes: (HebrewComponent(surface='', strong_id='H9003', morphology_code='HR/Ncfsa', role='prefix', gloss=''),)
core:      HebrewComponent(surface='בְּ/רֵאשִׁ֖ית', strong_id='H7225G', morphology_code='HR/Ncfsa', role='core', gloss='')
```

Three defects visible in four lines:

1. the **prefix surface is empty** — the parser knew it was `בְּ`;
2. the **core surface is the whole token including the prefix and the `/` separator**, not the core segment `רֵאשִׁית`;
3. **every component carries the full composite code** `HR/Ncfsa` rather than its own segment (`HR` and `Ncfsa`), and **`gloss` is unconditionally empty**.

`bible_engine/hebrew_parser.py` produces all of this correctly at import time via `_build_components()`. The runtime simply cannot see it.

**This is the single most direct argument for normalization before extension.** The compound-construction explanations the problem report asks for (preposition + article, pronominal suffix constructions, construct chains) require exactly the per-component surface/morphology/gloss triple that the current runtime store has thrown away. The information exists upstream; it is discarded for file-size reasons.

Partial mitigation: `HebrewMorphology.components` (from decoding the composite code) *does* carry correct per-segment analysis. So per-segment *grammar* survives; per-segment *surface text and gloss* do not.

---

## 3. Current data sources and provenance

### 3.1 Hebrew text and morphology — STEPBible TAHOT

Confirmed from the repository (`docs/hebrew_ot_architecture_audit.md`, the parser's `_REF_RE`, and the live `metadata` table). **Not** OSHB/MorphHB directly, **not** MACULA, **not** ETCBC.

| Property | Value |
|---|---|
| Dataset | `TAHOT` — Translators Amalgamated Hebrew Old Testament |
| Upstream | `STEPBible/STEPBible-Data` |
| Files | 4 TSV: `TAHOT Gen-Deu`, `Jos-Est`, `Job-Sng`, `Isa-Mal` |
| Format | Tab-separated, ≥12 columns |
| Record ID | `Book.chapter.verse#word=sourceEdition`, e.g. `Rut.1.1#01=L`, `Rut.3.14#02=Q(K)` |
| Base text | WLC via OpenScriptures, corrected by Tyndale House / STEPBible |
| Licence | CC BY 4.0 |
| Attribution | "STEP Bible; www.STEPBible.org" |
| Storage | Local SQLite, built offline; **source TSVs are not in the repository** |

Live metadata:

```
dataset_name         = TAHOT Hebrew/Aramaic OT
source_version       = STEPBible-Data master snapshot
license              = CC BY 4.0
attribution          = STEP Bible; www.STEPBible.org
built_at             = 2026-08-08T17:33:15+00:00
books/chapters/verses = 39 / 929 / 23213
surface_words        = 305635   (Hebrew 300808 / Aramaic 4827)
component_tokens     = 540438
ketiv_qere           = 1323
```

**Provenance gap:** `source_version` is the vague string `"STEPBible-Data master snapshot"` with **no upstream commit SHA**, and `source_files` records absolute paths inside a local Windows temp directory (`C:\Users\Hover\AppData\Local\Temp\claude\...`). SHA-256 checksums of the four inputs *are* recorded, which is good, but the build is not reproducible from the repository alone. Contrast with the ACAI store (§3.4), which does this correctly.

### 3.2 Morphology codes — STEPBible TEHMC

`TEHMC` (Translators Expansion of Hebrew Morphology Codes), same upstream, same CC BY 4.0 licence.

**Critically: the TEHMC expansion file is not shipped and is not loaded at runtime.** `load_tehmc_expansions()` exists in `hebrew_morphology.py:110`, but `HebrewTokenRepository.morphology()` calls `decode_hebrew_morphology(token.morphology_code, expansions or {})` with an **empty dict**. All runtime decoding therefore relies on the hand-written `STEMS` / `VERB_FORMS` / `PERSON` / `GENDER` / `NUMBER` / `STATE` tables inside `hebrew_morphology.py`, with `english_expansion` always empty.

That is the mechanism by which the imperative bug (§5.4) went unnoticed: **the authoritative code table is not consulted, and the hand-written substitute is never cross-checked against it.**

### 3.3 Lexicon — STEPBible TBESH

`TBESH` (Translators Brief lexicon of Extended Strongs for Hebrew), CC BY 4.0, 16,913 unique entries upstream, 13,742 in the runtime store. Its meanings derive from **Abridged BDB by Online Bible**. The existing audit doc correctly warns it must not be presented as an internally authored Hungarian lexicon.

### 3.4 Adjacent, already-imported: ACAI

`data/generated/acai_entities.sqlite3` — not currently wired into the Hebrew module, but highly relevant to the participant/coreference requirement and an exemplary provenance model:

```
source_id            = acai
source_version       = 2025-07-23
upstream_repository  = https://github.com/BibleAquifer/ACAI
upstream_commit      = 7e6a2d6674910aedb0888493ebbe6684d374ae5c
license              = CC-BY-SA-4.0
attribution          = ACAI ... © 2025 Mission Mutual. Licensed under CC BY-SA 4.0.
content_hash         = 5a121bb86af21ba5de6b320dc8d8572cbcedb41aab659080ad8244ef752c235d
entity_count         = 5700    entity_passage_links = 98649
import_mode          = full    schema_version = 1
```

Tables: `store_metadata`, `entities`, `entity_aliases`, `entity_passage_links`, `entity_external_ids`, `entity_dictionary_links`. Accessed via `textus_kb/adapters/acai_entities.py`, keyed by `CanonicalReference`.

Two things follow. First, **the offline-import → normalized-SQLite → typed-adapter pattern §15 proposes is already proven in this repository.** Second, ACAI is from Clear Bible / Aquifer, the same ecosystem as MACULA — an integration path likely already partly solved.

**Licence caution:** ACAI is CC BY-**SA** 4.0 (share-alike), a stronger obligation than TAHOT/TBESH's CC BY 4.0. See §14.

---

## 4. Current data flow

### 4.1 Passage → rendered Hebrew analysis (traced end to end)

```
1. User enters a reference on the "Igehely" tab
     → app.py session state: igehely_input / last_igehely

2. "Eredeti szöveg tanulmányozása" tab renders
     → app.py:7721  render_greek_analysis_block(reference, key_prefix=...)

3. bible_engine/greek_analysis_ui.py:158  greek_reference_status(reference)
     → "old_testament"
     → :173 imports hebrew_text_demo.render_hebrew_original_language_reference

4. hebrew_text_demo.py:734  render_hebrew_original_language_reference()
     → :603 parse_hebrew_original_reference()
        → bible_engine/hebrew_books.py:78 parse_hebrew_reference()
        → returns a bare tuple (book, chapter, verse_start, verse_end)

5. hebrew_text_demo.py:607  render_hebrew_original_language_panel()
     → HebrewTokenRepository(database_path)
     → .diagnostics()   [PRAGMA integrity_check, ~2 s, cached per instance]
     → .passage(book, chapter, verse_start, verse_end)
        → hebrew_sqlite.get_hebrew_passage_tokens()
        → _tokens_from_database_rows() → _token_from_normalized_row()
           [component surface/morph/gloss degraded here — see §2.3]

6. User clicks a Hebrew word (component or selectbox fallback)
     → session_state[selected_state_key] = token.stable_key   ("Gen:1:1:1")
     → st.rerun()

7. hebrew_text_demo.py:189  build_hebrew_token_view_model(token, morphology, lookup)
     → repository.morphology(token)
        → hebrew_morphology.decode_hebrew_morphology(code, {})   [no TEHMC expansions]
     → hebrew_morphology_hu.format_hebrew_morphology_rows_hu()
     → hebrew_morphology_hu.format_hebrew_morphology_hu()
     → hebrew_text_demo.morphology_groups()   [Alapadatok / Igei... / Különleges]
     → HebrewHungarianLexiconRepository.lookup(strong_id)
        → direct → alias → tbesh_fallback → missing

8. hebrew_text_demo.py:294  render_hebrew_analysis_card()
     → _render_morphology_groups() / _render_component_group() / _render_special_group()
     → render_lexical_panel()
     → st.json(asdict(morphology)) inside "Technikai morfológiai részletek"
```

**Steps 1–8 involve no LLM call whatsoever.** The word-click path is fully deterministic. This is a genuine architectural strength.

### 4.2 Passage → AI prose (the separate button)

```
app.py:7726  st.button("Eredeti szöveg tanulmányozása")
  → app.py:7744  run_original_language_analysis(reference, passage_text=..., generate_text_fn=generate_text,
                    tab_label="Eredeti szöveg tanulmányozása",
                    system_bundle=KEY_EXPRESSIONS_SYSTEM_PROMPT)
     → plan_original_language_analysis()
        → inspect_original_language_tokens()
           → HebrewTokenRepository.passage()
           → _format_hebrew_token_line() per token          ← see §7.2
        → has_authoritative_tokens → build_grounded_original_text_prompt()
             = ORIGINAL_TEXT_BASE_PROMPT + passage text + token block
               + optional build_original_text_commentary_block()
     → generate_text(prompt, use_cache=False, ...)          ← app.py:6689
     → check_original_language_grounding(output, reference)  [non-blocking warnings]
  → session_state["original_text"], ["original_text_language_status"], ...
```

---

## 5. Morphology implementation

### 5.1 Where morphology comes from

The `morphology_code` TSV column of TAHOT, stored verbatim in `tokens.morphology_code` and decoded at request time. **There is no persisted decoded-morphology table.** Decoding is pure, fast and deterministic, so this is a reasonable choice — but it means a table fix propagates instantly (good for §22 remediation) and that no decoded output is ever validated at import time (bad — it is why §5.4 shipped).

### 5.2 Code system

TEHMC. Shape: `<Language><Function><details>`, slash-separated per component, e.g.:

| Code | Meaning |
|---|---|
| `HVqp3ms` | Hebrew, Verb, Qal, Perfect, 3ms |
| `Hc/Vqw3ms` | Hebrew conjunction + Qal wayyiqtol 3ms |
| `HR/Ncfsa` | Hebrew preposition + common noun fem sg absolute |
| `HNcmsc/Sp2ms` | Noun masc sg construct + pronominal suffix 2ms |
| `HC/Vqv2mp/Sp3fs` | Conjunction + Qal **imperative** 2mp + suffix 3fs |

`_split_morphology_components()` (line 289) handles **language-code inheritance**: in `Hc/Vqw3ms` the second segment `Vqw3ms` inherits `H`. This is correct and non-trivial, and is exactly the kind of logic worth preserving.

### 5.3 Determinism and honesty

Fully deterministic — a pure function of `(code, expansions)`. Four explicit statuses: `fully_decoded`, `partially_decoded`, `unresolved`, `malformed`, with unrecognised fragments preserved in `unresolved_parts` rather than guessed at. The design intent — *never invent terminology for undocumented fragments* — is sound. The failure in §5.4 is not a failure of that principle; it is a wrong entry in a hand-written table that the principle cannot catch, because a wrong-but-known code decodes "successfully".

### 5.4 The imperative defect (blocking)

Full census of verb stem and form codes across all 305,635 tokens, decoded through the repository's own `_split_morphology_components()` so that language inheritance is honoured:

**Verb form codes (position after the stem):**

| Code | Count | Current mapping | Assessment |
|---|---:|---|---|
| `w` | 14,978 | Consecutive Imperfect (`wayyiqtol`) | correct |
| `p` | 14,791 | Perfect (`perfectum`) | correct |
| `i` | 13,471 | Imperfect (`imperfectum`) | correct |
| `r` | 8,419 | Participle (`participium`) | correct |
| `c` | 7,292 | Infinitive Construct | correct |
| `q` | 6,344 | Consecutive Perfect (`weqatal`) | correct |
| **`v`** | **4,305** | **Consecutive Perfect (`weqatal`)** | **WRONG → Imperative** |
| `s` | 1,280 | Passive Participle | correct |
| `j` | 1,099 | Jussive (`jussivus`) | correct |
| `u` | 999 | Conjunction Imperfect | **suspect** — see below |
| `a` | 749 | Infinitive Absolute | correct |
| `m` | **0** | Imperative (`imperativus`) | **dead mapping** |

**Proof that `v` is the imperative:**

```
person distribution for form code v: {'2': 4305}      ← 100% second person
person distribution for form code q: {'3': 3666, '2': 1555, '1': 1123}
occurrences of form code m in whole OT: 0
```

A consecutive perfect appears in all three persons; the `q` distribution shows exactly that. A form that is *exclusively* second person across 4,305 attestations is an imperative. The corpus glosses settle it beyond doubt:

```
Gen 1:22  פְּר֣וּ          HVqv2mp    gloss = be fruitful
Gen 1:22  וּ/רְב֗וּ        HC/Vqv2mp  gloss = and/ multiply
Gen 1:28  וְ/כִבְשֻׁ֑/הָ   HC/Vqv2mp/Sp3fs  gloss = and/ subdue/ it
Gen 4:23  שְׁמַ֣עַן        HVqv2fp    gloss = listen to
Gen 6:14  עֲשֵׂ֤ה          HVqv2ms    gloss = make
Gen 22:2  קַח\־           HVqv2ms    gloss = take
```

versus genuine weqatal under `q`:

```
Gen 1:14  וְ/הָי֤וּ        Hc/Vqq3cp  gloss = and/ they will become
Gen 2:24  וְ/דָבַ֣ק        Hc/Vqq3ms  gloss = and/ he cleaves
```

**What the user sees today** (`format_hebrew_morphology_rows_hu`):

```
HVqv2mp  →  {'Szófaj': 'ige', 'Igetörzs': 'qal', 'Igealak': 'weqatal',
             'Személy': 'második személy', 'Nem': 'hímnem', 'Szám': 'többes szám',
             'Státusz': 'teljesen feloldott morfológia'}
```

`פְּר֣וּ` ("be fruitful!", Gen 1:22) — a Qal imperative — is presented as `weqatal`, marked *fully resolved*. The internal contradiction (a weqatal that is always 2nd person) is never surfaced.

**Why the tests did not catch it** — `tests/test_hebrew_morphology_hu.py:69–83`:

```python
"HVqv3ms": "qal törzs, weqatal",      # ← v + 3rd person: impossible in the corpus
"HVqm2ms": "qal törzs, imperativus",  # ← m never occurs in the corpus
```

The golden expectations were authored against synthesised codes, not sampled TAHOT rows. This is a **test-methodology finding as much as a code finding**, and it directly shapes the §20 regression strategy: fixtures must be drawn from real corpus rows.

**Secondary suspects in the same tables (not yet proven, must be validated against TEHMC):**

- `u` (999) → `"Conjunction Imperfect"` / `kötőszós imperfectum`. Samples read as **cohortative/volitional**: `וְ/תֵרָאֶ֖ה` "and let it appear" (Gen 1:9), `וְ/נַֽעֲשֶׂה` "and we may make" (Gen 11:4), `וְ/אֶֽעֶשְׂ/ךָ֙` "so I may make you" (Gen 12:2). A cohortative label is likely more accurate; `Cohortative` already exists in `VERB_FORM_HU` but is unreachable because no code maps to it.
- `STEMS` contains near-duplicates that collapse in Hungarian: `t`→Hithpael, `u`→Hitpael, `M`→Hitpaal, `D`→Nithpael, and `STEM_HU` maps both "Hithpael" and "Hitpael" to `hitpael`. The stem code `u` occurs 61 times and `M` 30 times; both need TEHMC verification.
- `Q`→Peil and `E`→Peil are both mapped to the same Aramaic stem.

**Bounded scope.** Everything else in both tables checks out against the corpus, including all seven principal binyanim (Qal 50,831 / Hiphil 9,576 / Piel 6,906 / Niphal 4,148 / Hithpael 1,001 / Pual 517 / Hophal 431) and the eight uncontested form codes. **The defect is one wrong row plus two-to-four unverified rows — not a broken decoder.**

### 5.5 Component/analysis index misalignment

`build_hebrew_token_view_model()` zips two independently derived lists:

```python
analyses        = component_analyses(morphology)     # from the slash-split morphology code
token_components = ordered_token_components(token)   # from token_strong_ids
...
analysis = analyses[index] if index < len(analyses) else {}   # silent truncation
```

These lengths diverge whenever a token carries a STEPBible grammar pseudo-Strong that has no morphology segment — chiefly maqaf `H9014` and punctuation `H9015`. Measured on Gen 1:3 and Gen 22:2:

```
Gen 1:3  #5  וַֽ/יְהִי\־   Hc/Vqw3ms  ncomp 3  nanaly 2   ← MISALIGN
Gen 1:3  #6  אֽוֹר\׃       HNcfsa     ncomp 2  nanaly 1   ← MISALIGN
Gen 22:2 #2  קַח\־        HVqv2ms    ncomp 2  nanaly 1   ← MISALIGN
Gen 22:2 #4  אֶת\־        HTo        ncomp 2  nanaly 1   ← MISALIGN
Gen 22:2 #8  אֲשֶׁר\־      HTr        ncomp 2  nanaly 1   ← MISALIGN
```

Maqaf is extremely common, so this affects a large fraction of tokens. It degrades rather than crashes: the trailing component receives `{}`, so its `analysis_summary` is empty. It also breaks `_core_part_of_speech_label()`, which reads `components[core]["analysis"]["part_of_speech"]` and returns `""` when the core row was the one truncated — silently blanking the part-of-speech label used in the compact card and in `_display_lexical_note()`.

### 5.6 Verdict for §4 of the audit brief

| Question | Answer |
|---|---|
| Where does morphology come from? | TAHOT `morphology_code` column, decoded at request time |
| Code system? | STEPBible TEHMC |
| Where parsed? | `bible_engine/hebrew_morphology.py:196` `decode_hebrew_morphology()` |
| Deterministic? | Yes — pure function, no I/O, no randomness, no LLM |
| P/G/N/state/stem/form represented? | Yes — separate typed fields on `HebrewMorphology` |
| Stems/conjugations correct internally even if the UI is poor? | **Stems yes. Conjugations no** — `v` (4,305 imperatives) is wrong at the data layer, not the presentation layer |

---

## 6. Lemma / root / gloss implementation

### 6.1 Root (`gyök`) — does not exist

**There is no root concept anywhere in the codebase.** A repository-wide search across `bible_engine/hebrew*.py` and `hebrew_text_demo.py` for `gyök`, `root`, `"root"` returns exactly one hit — the string `"root value must be a list"` in a JSON validation error message (`hebrew_lexicon_hu.py:62`). Unrelated.

There is no `root` field on `HebrewToken`, none on `HebrewComponent`, none on `HebrewMorphology`, no `root` column in the SQLite schema, and no root key in the Hungarian lexicon JSON. TAHOT does not supply a triliteral-root column, and nothing derives one.

**Implication for v2:** "use `gyök` rather than `lexikai mag`" is not a rename. Root is a genuinely **new deterministic field** requiring a new source (OSHB/MorphHB, MACULA, or a STEPBible lexical field). It must not be inferred by the AI.

### 6.2 Lemma, and the `lexikai mag` terminology defect

Lemma is real and populated. In the full-fidelity import path it is extracted by `_lemma_from_expanded()` (`hebrew_parser.py:157`) from the TAHOT expanded-Strong-tags column; in the pruned runtime path it is read from `tokens.lemma`. Verified: Gen 1:1 `בְּ/רֵאשִׁ֖ית` → lemma `רֵאשִׁית`; `בָּרָ֣א` → `בָּרָא`.

**The exact flagged term is present**, `bible_engine/hebrew_morphology_hu.py:96`:

```python
COMPONENT_ROLE_HU = {"prefix": "prefixum", "core": "lexikai mag",
                     "suffix": "suffixum", "composite": "összetett alak"}
```

Consumed at `hebrew_text_demo.py:220` as `role_label` and rendered under the "Szóösszetétel" group. Note that `lexikai mag` currently labels the **core component role**, which is a different concept from a triliteral root — so replacing it with `gyök` would be *semantically wrong*. The correct fix is: rename the role label to something accurate (e.g. `törzs`/`alapszó`), and introduce `gyök` as a genuinely new field once a root source exists.

**Better news on the other terminology point:** `igetörzs` and `igealak` are **already correctly separated** — `format_hebrew_morphology_rows_hu()` (`hebrew_morphology_hu.py:230–231`) emits them as distinct labelled rows, and `morphology_groups()` (`hebrew_text_demo.py:270–271`) renders them as separate lines under "Igei vagy névszói morfológia". The reviewer's complaint here is a **presentation-prominence** issue, not a data-model gap — with the important caveat that the *value* in the `Igealak` row is wrong for all 4,305 imperatives (§5.4). The field is right; the content is not.

Note also the compact summary path `_shape_details()` joins them with commas — `"qal törzs, weqatal"` — which reads as one run-on attribute rather than two dimensions. That is the cosmetic half of the complaint and is genuinely worth addressing.

### 6.3 Glosses — where each one comes from

| Layer | Source | Generated by | Persisted | Reviewed |
|---|---|---|---|---|
| English token gloss | TAHOT `english_gloss` column | STEPBible editors | `tokens.english_gloss` | upstream |
| English component gloss | TAHOT expanded tags | STEPBible | **lost at runtime** (§2.3) | upstream |
| English lexicon gloss/meaning | TBESH (Abridged BDB) | Online Bible / STEPBible | `tbesh_lexicon_runtime.sqlite3` | upstream |
| **Hungarian lexical meaning** | **LLM translation of TBESH** | **AI, offline batch** | `bible_engine/data/hebrew_lexicon_hu.json` | **none** |

Measured over all 6,493 Hungarian entries:

```
review_status:      {'draft': 6493}          ← 100% draft, 0 reviewed
translation_method: {'ai_assisted': 6493}    ← 100% AI, 0 human
sources: 6481 "STEPBible TBESH alapján készített magyar munkaváltozat"
           12 "TAHOT unresolved Strong/STEP IDs alapján ..."  (mojibake in source string)
```

Direct coverage of token Strong references: **323,706 / 540,437 = 59.9%**. The remainder falls through to alias resolution, then TBESH English, then "no data".

Two important qualifications, in fairness to the existing design:

- The pipeline is **fully offline**. `hebrew_lexicon_translation_workflow.py` is reachable only from `scripts/export_hebrew_lexicon_batch.py` and `scripts/import_hebrew_lexicon_batch.py`. No LLM call happens at request time.
- The import path **validates**: `_reject_bad_hu_text()`, `_appears_to_be_english_sentence()`, normalized-Strong enforcement, duplicate detection, non-empty `possible_meanings_hu`.
- The UI **discloses provenance**: `hebrew_text_demo.py:450` prints *"Forrás: STEP Bible TBESH alapján készült magyar lexikai munkaváltozat"* and shows the review status.

So the architecture is honest. The problem is that **the entire Hungarian lexical surface of the application is unreviewed machine translation**, and §6.4 shows what that costs.

### 6.4 The `אֲשֶׁר` defect — reproduced exactly, and root-caused

The reported symptom was that `אֲשֶׁר` is shown with a contextual gloss such as *"amikor/amint"* as though it were the general lexical meaning. **This reproduces precisely, and the cause is more specific and more fixable than a generic "AI wrote a contextual gloss" story.**

Every plain relative-particle `אֲשֶׁר` token in TAHOT carries extended Strong **`H0834A`**:

```
Strong IDs used for lemma אֲשֶׁר:
  ('H0834A', 'HTr')     4805     ← relative particle, morphology correct
  ('H0834A', 'HC/Tr')    107
  ('H0834A', 'HR/Tr')     23
```

The Hungarian lexicon record for `H0834A` is:

```json
{
  "strong_id": "H0834A",
  "lemma": "כַּאֲשֶׁר",
  "transliteration": "ka.a.sher",
  "base_meaning_hu": "amint",
  "possible_meanings_hu": ["amint", "ahogyan", "amikor"],
  "source_gloss_en": "as which",
  "source_note_en": "conj 1) according as, as, when 1a) ... 1c) with a temporal force: when",
  "translation_method": "ai_assisted",
  "review_status": "draft"
}
```

Note the `lemma` field: **`כַּאֲשֶׁר`** (*ka-asher*), which is a different lexeme from the `אֲשֶׁר` that actually carries this Strong ID in every one of its 4,935 attestations.

End-to-end resolution trace:

```
H0834  -> missing        (plain אֲשֶׁר has NO Hungarian record at all)
H0834A -> direct         base_meaning_hu = "amint"   lemma = כַּאֲשֶׁר
```

So clicking any `אֲשֶׁר` token yields **`Alapjelentés: amint`** and **`Lehetséges jelentések: amint · ahogyan · amikor`** — exactly the reported wording — while the morphology row simultaneously and correctly reads `vonatkozó partikula`. The two panels contradict each other on screen.

**Root cause — corrected by Phase 2A.** This audit originally attributed the defect to the AI mis-scoping the extended-Strong suffix during translation. That was wrong, and the truth is both more mechanical and more serious: TBESH's `uStrong` column is a *cross-reference* to the lexeme a record derives from, and `import_tbesh_lexicon()` indexed every record under it with `INSERT OR REPLACE`. The genuine row here is `H0834D` (`dStrong = "H0834D = combination of"`, `uStrong = "H0834A (H9004+H0834A)"`), i.e. כַּאֲשֶׁר merely *pointing at* אֲשֶׁר — and it overwrote אֲשֶׁר's own entry. The AI then faithfully translated the hijacked record. See §7 of the Phase 2A document; the same mechanism corrupted 1,056 keys and 299 Hungarian records.

**This is diagnostically valuable**, because it means the defect class is *systematic and detectable*, not random. Any extended-Strong record whose Hungarian `lemma` does not match the surface lemma of the tokens that actually carry that ID is suspect, and that check is mechanical. A sweep of all 6,493 entries against corpus lemmas should be a Phase 2 deliverable (§22).

Two related observations from the same probe:

- `H3808` has `lemma: לָא` (the Aramaic spelling) with `base_meaning_hu: "nem"` — plausibly the same extended-Strong scoping issue applied to Hebrew `לֹא` vs Aramaic `לָא`. **Directly relevant to the double-negation requirement**, since `לֹא` is the primary Hebrew negator.
- `H0430G` (`אֱלֹהִים`) carries `base_meaning_hu: "Isten; istenek"` — a semicolon-joined double gloss that is also duplicated inside `possible_meanings_hu`. It does carry a review warning, which is the system working as intended.

### 6.5 Lexical vs contextual meaning — not distinguished

There is **no field anywhere** that separates a lexeme's basic lexical function from its meaning in the present clause. `HebrewHungarianLexiconEntry` offers `base_meaning_hu`, `possible_meanings_hu` and `lexical_note_hu`, all context-free and all rendered under the heading *"Alapjelentés"*. `possible_meanings_hu` is an undifferentiated list with no indication of which applies here.

`_display_lexical_note()` (`hebrew_text_demo.py:524`) makes a partial gesture at this by prefixing the note with the language and part of speech and appending *"a felsorolt jelentések közül a szövegkörnyezet alapján választandó ki a megfelelő árnyalat"* — it tells the user to choose, but supplies nothing to choose with.

**Answer to the brief's question "may a single context-specific gloss currently be presented as though it were the primary lexical meaning?" — Yes, demonstrably, at scale.** §6.4 is the proof. This is the strongest single argument for the §17 lexical/contextual split.

---

## 7. Current AI usage

### 7.1 Complete inventory of LLM calls touching Hebrew

| # | Call site | Model | Input | Output | Cached | Infers grammar? |
|---|---|---|---|---|---|---|
| 1 | `app.py:7744` → `run_original_language_analysis` | `gemini-2.5-flash` | Hungarian prompt + token block + optional commentary | Hungarian prose, ≤5 words | **No** (`use_cache=False`) | **Yes** |
| 2 | `app.py:4359` → exegesis prompt | tab-dependent | Same token block, embedded in the exegesis prompt | Exegesis prose | tab-dependent | **Yes** |
| 3 | `app.py:7815` `refinement_chat("Eredeti szöveg…")` | tab-dependent | Prior output + user turn | Revised prose | No | **Yes** |
| 4 | `scripts/export_hebrew_lexicon_batch.py` → external model → `import_hebrew_lexicon_batch.py` | external | TBESH English records | Hungarian lexicon JSON | Persisted to JSON | Lexical only |
| — | **Word-click / morphology / lexicon display** | **none** | — | — | — | **No** |

Provider details: `generate_text()` at `app.py:6689` targets the Google Gemini `generateContent` endpoint. `"Eredeti szöveg tanulmányozása"` is pinned to `LOCKED_MODEL = "gemini-2.5-flash"` (`app.py:288`) with `DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB = 12000` (`app.py:6263`); the legacy `"Eredeti szöveg"` label maps to 6144. Temperature defaults to 0.3. `system_bundle=KEY_EXPRESSIONS_SYSTEM_PROMPT`. A global cooldown (`GEMINI_COOLDOWN_S`) guards call rate.

### 7.2 The central AI-layer finding: the AI re-parses morphology today

`_format_hebrew_token_line()` (`bible_engine/original_language_analysis.py:258`) is the **entire** deterministic payload the model receives per token:

```python
def _format_hebrew_token_line(token, repository) -> str:
    pos = repository.morphology(token).part_of_speech or "?"
    strong = "+".join(token.strong_ids) if token.strong_ids else "nincs"
    return (f"[{token.word_index}] {token.surface} | lemma: {token.lemma} | "
            f"morf: {token.morphology_code or '?'} ({pos}) | Strong: {strong}")
```

Producing lines such as:

```
[1] וַ/יֹּ֥אמֶר | lemma: אָמַר | morf: Hc/Vqw3ms (Conjunction + Verb) | Strong: H9002+H0559
```

The decoder computed `verb_stem="Qal"`, `verb_conjugation="Consecutive Imperfect"`, `person="Third"`, `gender="Masculine"`, `number="Singular"` and per-component analyses — **and then discarded all of it, forwarding only `part_of_speech` and the raw code string.**

Consequences, each of which the target architecture explicitly forbids:

1. **The AI must decode `Hc/Vqw3ms` itself** to say anything about stem or aspect. That is exactly "the AI determining basic Hebrew grammatical facts when those facts can come from structured linguistic datasets".
2. `part_of_speech` is passed as an **English** string (`"Conjunction + Verb"`) into a Hungarian prompt, even though `hebrew_morphology_hu.py` exists precisely to translate it.
3. Nothing about prefixes, suffixes, ketiv/qere, state, or component structure reaches the model — so it cannot explain compound constructions even in principle.
4. The prompt then **forbids naming grammatical categories** in the output (`ORIGINAL_TEXT_BASE_PROMPT`: *"NE nevezd meg a nyelvtani/morfológiai adatot szakkifejezéssel"*), on the stated rationale that the word view already shows them. Combined with (1), the model is asked to silently re-derive grammar it was not given and then not name it.
5. **The bad `weqatal` label does not currently reach the AI** (only the raw code does) — but it *does* reach the user through the word-click card, and it *would* reach the AI the moment decoded fields start being forwarded. Fixing §5.4 is therefore a prerequisite for the §17 boundary, not an independent cleanup.

### 7.3 Deterministic facts currently produced by AI that should move out

| Fact | Today | Should be |
|---|---|---|
| Verbal stem (binyan) | AI infers from raw code | Deterministic field |
| Conjugation / verbal form | AI infers from raw code | Deterministic field |
| Person / gender / number / state | AI infers from raw code | Deterministic field |
| Prefix / suffix segmentation | Not supplied at all | Deterministic field |
| Compound construction identity | AI infers, or omits | Deterministic pattern detector |
| Hungarian grammatical terminology | AI improvises | `hebrew_morphology_hu.py` |
| Contextual sense selection | AI, ungrounded | AI, but grounded on a supplied sense inventory |
| Syntax / clause structure | Absent | Deterministic (MACULA), then AI explains |

### 7.4 Existing safeguards worth preserving

- **Explicit provenance state machine** — `STATUS_GROUNDED` / `STATUS_AI_FALLBACK` / `STATUS_UNAVAILABLE`, with a user-visible notice on fallback and an explicit prompt-level ban on the fallback path claiming database provenance.
- **Post-hoc grounding cross-check** — `check_original_language_grounding()` extracts Hebrew forms and Strong IDs from the AI output and classifies them `PASSAGE_MATCH` / `GLOBAL_OTHER_PASSAGE` / `UNKNOWN` / `INVALID_STRONG_ID`. Deliberately non-blocking and careful not to call an unknown form a hallucination.
- **Anti-overreach prompt rules** — the base prompt already forbids deciding contested identity questions on linguistic grounds, and forbids inflating etymology (with a worked `שׂרה` counter-example).
- **Commentary strictly subordinated** — classical commentary is capped at 2 items / 220 chars, attached only to the grounded path, never the fallback, and carries an explicit rule that it is interpretation, not linguistic fact.

These are good instincts and should carry forward into the v2 AI contract essentially unchanged.

---

## 8. Reference and token identity model

### 8.1 Two parallel reference models

**Model A — `textus_kb/canonical_reference.py` (the good one):**

```python
@dataclass(frozen=True)
class CanonicalReference:
    book_id: str            # OSIS-like stable id
    start_chapter: int
    start_verse: int
    end_chapter: int
    end_verse: int
    versification_scheme: str | None = None
```

With `canonical_string()` (`John.4.1-42`), `parse()`, `is_single_verse`, `ruf_book_code`, cross-chapter spans, and a documented hook for ENG/ORG/RUF versification mapping. Used throughout `textus_kb`, including the ACAI adapter.

**Model B — `bible_engine/hebrew_books.py` (what Hebrew actually uses):**

```python
def parse_hebrew_reference(reference: str) -> tuple[str, int, int, int]:
    # returns a bare (tahot_book_code, chapter, verse_start, verse_end)
```

with TAHOT 3-letter codes (`Gen`, `Psa`, `1Sa`) and a separate 39-book `OT_BOOKS` table carrying `ruf_code`, `tahot_code`, `abbr_hu`, `name_hu`, `aliases`.

**A repository-wide search confirms `canonical_reference` is never imported by any Hebrew, Greek or original-language module.** The two models do not interoperate: different book identifiers (OSIS vs TAHOT), different return types (dataclass vs tuple), and Model B cannot express a cross-chapter span at all — its regex requires a single chapter, mirroring the Greek `cross_chapter` restriction.

### 8.2 Versification — handled, and worth preserving

`hebrew_parser.py:76–86` contains a carefully reasoned piece of logic: TAHOT's `Chapter.Verse(AltChapter.AltVerse)` form parenthesises the *Masoretic* numbering when it diverges from English/NRSV (typically Psalm superscriptions, e.g. `Psa.69.1(69.2)`). Because RÚF follows the Hebrew tradition, the code prefers the parenthesised pair. The comment notes that without this an entire chapter silently fails to align.

This is real, load-bearing domain knowledge. **It must survive any v2 refactor**, and it is precisely what `CanonicalReference.versification_scheme` was designed to carry.

### 8.3 Token identity

Stable key format: `book:chapter:verse:word_index` — e.g. `Gen:1:1:1`. Defined as `HebrewToken.stable_key` (`hebrew_parser.py:53`), stored as `tokens.stable_token_key` with a UNIQUE constraint, and used as the UI selection key.

**Stability assessment:**

- Deterministic and human-readable. ✔
- Encodes TAHOT book codes and TAHOT versification, so it is **source-coupled** — an OSHB or MACULA import with different versification would produce different keys for the same word. ✘
- Contains **no component index**, so a sub-word component (a prefix, a pronominal suffix) is **not addressable**. The prototype decision to make the whole surface word the clickable unit is documented in `docs/hebrew_ot_architecture_audit.md`. ✘ for v2.
- 14 duplicate keys from `X`-edition rows are skipped at import with audit warnings rather than given synthetic keys — a deliberate, correct choice that preserves the key contract. ✔
- `source_token_id` (the original TAHOT `Rut.1.1#01=L` identifier) **is dropped by the pruning step**, removing the only link back to the exact upstream row. ✘ — this materially complicates future cross-dataset alignment.

---

## 9. Cache and persistence

| Question | Finding |
|---|---|
| How are AI analyses cached? | `st.session_state["_call_cache"]`, an in-memory dict inside `generate_text()` (`app.py:6770`) |
| Cache key | `_hash_prompt(prompt, extra=f"{model}\|{temperature}\|{system_key}\|{brevity}\|{max_tokens}\|{trunc_key}")` |
| Is the Hebrew module cached? | **No.** `original_language_analysis.py:634` hard-codes `"use_cache": False` |
| Lifetime | Streamlit session only — lost on rerun-with-new-session, tab close, or server restart |
| Backend | Python dict in session state. No SQLite, no Supabase, no disk |
| Granularity | Whole-passage prose blob |
| Versioning | None. No dataset version, no prompt version, no schema version in the key |
| Invalidation | None. Implicit only, via prompt-hash change |
| Token/word-level caching | None — and none needed today, since that path never calls an LLM |

`bible_engine/hebrew_token_repository.py:31` documents one deliberate micro-optimisation: `PRAGMA integrity_check` takes ~2 s at current file size and is memoised per repository instance (it had previously run up to 3× per `passage()` call). It is explicitly *not* durable — every Streamlit rerun constructs a fresh repository and re-runs the check.

Elsewhere the project *does* use durable stores (Supabase-backed commentary, `data/generated/*.sqlite3`), so the infrastructure and the institutional knowledge exist.

**Assessment:** the existing cache is **not reusable** for Hebrew Analysis v2 as-is. A `HebrewAnalysisBundle` is a structured object, not a prompt string; it is expensive to assemble; and it is stable for a given (reference, dataset version) pair. It needs a durable, versioned, content-addressed cache. But this is an *addition*, not a migration — nothing must be untangled first, because the Hebrew path currently caches nothing at all.

---

## 10. Current UI integration

### 10.1 Component inventory

| Concern | Location |
|---|---|
| Tab shell | `app.py:7691` `render_work_section("Eredeti szöveg tanulmányozása")` |
| Entry point | `app.py:7721` `render_greek_analysis_block(reference, key_prefix=...)` |
| OT dispatch | `bible_engine/greek_analysis_ui.py:167–186` |
| Hebrew panel | `hebrew_text_demo.py:607` `render_hebrew_original_language_panel()` |
| Token selector | `components/hebrew_token_selector` (custom component) + `st.selectbox` fallback |
| View model | `hebrew_text_demo.py:189` `build_hebrew_token_view_model()` |
| Field grouping | `hebrew_text_demo.py:256` `morphology_groups()` |
| Analysis card | `hebrew_text_demo.py:294` `render_hebrew_analysis_card()` |
| Compact card | `hebrew_text_demo.py:330` `_render_compact_hebrew_analysis_card()` |
| Lexical panel | `hebrew_text_demo.py:432` `render_lexical_panel()` |
| Concordance jump | `hebrew_text_demo.py:398` |
| Styles | `hebrew_text_demo.py:754` `_ensure_hebrew_analysis_styles()` |
| Attribution | `hebrew_text_demo.py:731` STEP Bible / CC BY 4.0 caption |
| Dev harness | `hebrew_text_demo.py:876` `render_hebrew_demo()` |

Three field groups are rendered:

- **Alapadatok** — Lemma, Transzliteráció, Strong/STEP, Nyelv, Szófaj
- **Igei vagy névszói morfológia** — **Igetörzs**, **Igealak**, Személy, Nem, Szám, Állapot, Suffixum
- **Különleges adatok** — Ketív, Qeré, Kiadásjelölés, Maqaf

Plus **Szóösszetétel** (component rows) and a **Lexikai adatok** panel, with the full decoded morphology dumped as JSON under an expander.

### 10.2 UI-level observations

1. **The structure the reviewer asked for already exists.** `Igetörzs` and `Igealak` are already separate labelled rows. The gap is prominence and value-correctness, not layout.
2. **Terminology is duplicated inside the UI.** `_core_part_of_speech_label()` (`hebrew_text_demo.py:543`) hard-codes its own English→Hungarian part-of-speech dict, duplicating `PART_OF_SPEECH_HU` in `hebrew_morphology_hu.py`. Two sources of truth that can drift.
3. **The compact summary conflates dimensions.** `_shape_details()` yields `"qal törzs, weqatal"` — a comma-joined run that reads as one attribute rather than two orthogonal grammatical dimensions.
4. **Component rows are degraded** by §2.3 (empty prefix/suffix surfaces, composite morphology on every row, no gloss) and by §5.5 (empty analysis on maqaf tokens).
5. **Ketiv/Qere is displayed** but not explained — raw forms under "Különleges adatok" with no note on what the divergence signifies.
6. **Attribution is correctly present**, both in the panel and the demo harness.
7. **No syntactic display exists at any level** — no phrase, clause, dependency or constituent view, in the UI or the data model.

---

## 11. Existing tests and fixtures

### 11.1 Hebrew-relevant test files

| File | Tests | Covers |
|---|---:|---|
| `tests/test_hebrew_morphology.py` | 12 | TEHMC decoding, slash components, language inheritance, partial/malformed states |
| `tests/test_hebrew_morphology_hu.py` | 12 | Hungarian terminology, technical-leak detection |
| `tests/test_hebrew_parser.py` | 7 | TAHOT row parsing, components, ketiv/qere, accent stripping |
| `tests/test_hebrew_repositories.py` | 18 | Repository facade, diagnostics, lookups |
| `tests/test_hebrew_sqlite.py` | 9 | Schema, import, atomic replace, queries |
| `tests/test_hebrew_lexicon_hu.py` | 12 | HU lexicon load/validate/resolve (**4 failing**) |
| `tests/test_hebrew_token_selector.py` | 2 | Token click behaviour |
| `tests/test_hebrew_lexicon_translation_workflow.py` | — | Offline batch export/import |
| `tests/test_original_language_token_block.py` | 3 | Token block construction |
| `tests/test_original_language_ai_fallback.py` | 9 | DB-first / fallback / unavailable state machine |
| `tests/test_original_language_post_hoc_validation.py` | — | Grounding checker |
| `tests/test_original_language_commentary.py` | — | Commentary block |
| `tests/test_original_language_concordance.py` | — | Lemma/Strong search |
| `tests/test_exegesis_original_language_grounding.py` | — | Token block in exegesis prompt |

### 11.2 Fixtures

- `tests/fixtures/tahot_ruth_psa_sample.tsv` — 178 lines
- `tests/fixtures/tbesh_ruth_psa_sample.tsv` — 248 lines

Both are real upstream excerpts (Ruth + Psalms). The fixture-first pattern is sound and is the right foundation for §20 — the problem is that the *morphology* tests bypass these fixtures and use synthesised codes (§5.4).

### 11.3 Baseline test state (unchanged by this audit)

```
python -m pytest tests/test_hebrew_*.py tests/test_original_language_*.py -q
→ 4 failed, 80 passed in 22.21s
```

All four failures are in `tests/test_hebrew_lexicon_hu.py` and share one cause: the tests read generated audit artifacts that are not tracked in git.

```
FileNotFoundError: data/generated/hebrew_runtime_coverage_after_missing_translation_0001.json
  also: data/generated/hebrew_missing_ids_after_aliases_0008.json
        data/generated/hebrew_lexicon_missing_ids_0001_translation_audit.json
```

These are **pre-existing** — this audit modified nothing. But it means the Hebrew suite cannot go green on a clean clone, which undermines its value as a v2 regression gate. Fixing this (commit the small audit JSONs, or generate them in a fixture, or skip cleanly when absent) is a cheap Phase 2 prerequisite.

### 11.4 Reusability for v2

| Reusable as-is | Reusable with correction | Must be new |
|---|---|---|
| Parser tests | Morphology tests — must move to real corpus rows | Syntax/phrase/clause tests |
| SQLite import/schema tests | `test_hebrew_morphology_hu.py:73` asserts the bug and must be **fixed, not preserved** | Bundle assembly tests |
| Repository/diagnostics tests | Lexicon tests — repair the artifact dependency | Pattern detector tests |
| Fixture-first methodology | | Expert-reviewed golden fixtures (§20) |
| Grounding-checker tests | | AI contract schema tests |
| AI fallback state-machine tests | | Lexical vs contextual sense tests |

---

## 12. Reusable components (verified from code, not assumed)

| Component | Verdict | Evidence |
|---|---|---|
| `bible_engine/hebrew_parser.py` | **Reuse** | Correct component split, versification handling, ketiv/qere, accent stripping. Best-quality module in the Hebrew stack |
| `bible_engine/hebrew_morphology.py` (structure) | **Reuse** | Separate `verb_stem`/`verb_conjugation`; per-component decode; explicit status; pure function |
| `bible_engine/hebrew_morphology.py` (code tables) | **Fix first** | §5.4 — `v` mapping wrong; `u`, `M`, `D`, `Q`/`E` unverified; TEHMC never loaded |
| `bible_engine/hebrew_morphology_hu.py` | **Reuse + amend** | Terminology layer is well-factored; `lexikai mag` must change; leak detection is a genuinely good idea |
| `bible_engine/hebrew_token_repository.py` | **Reuse** | Clean facade, honest status codes, sensible diagnostics memoisation |
| `bible_engine/hebrew_sqlite.py` (schema/import) | **Extend** | Atomic build, checksums, audit validation, Windows retry. Add root/phrase/clause/provenance tables |
| Pruned runtime schema | **Revisit** | §2.3 — loses per-component data the v2 requirements need |
| `bible_engine/hebrew_books.py` | **Reuse, then bridge** | Book table and alias folding are solid; must map to `CanonicalReference` |
| `textus_kb/canonical_reference.py` | **Adopt** | Already the right model; Hebrew simply does not use it yet |
| `bible_engine/original_language_analysis.py` (state machine) | **Reuse** | Grounded/fallback/unavailable is exactly right |
| `_format_hebrew_token_line()` | **Replace** | §7.2 — discards decoded morphology |
| `original_language_grounding_check.py` | **Reuse + extend** | Extend to syntax claims and construction claims |
| `hebrew_lexicon_translation_workflow.py` | **Reuse** | Correct offline batch pattern; add a lemma-consistency sweep (§6.4) |
| Hungarian lexicon JSON | **Audit before reuse** | 100% AI draft; at least one systematic defect class proven |
| `hebrew_text_demo.py` view model | **Refactor** | Sound shape; must carry phrases/clauses/constructions and fix §5.5 |
| Token selector component | **Reuse** | Works; needs sub-word addressing for component-level selection |
| ACAI adapter pattern | **Reuse as template** | Provenance schema is the model for MACULA/OSHB imports |
| Ketiv/Qere data | **Reuse** | 1,323 records already deterministic |
| Greek/Hebrew shared code | **Keep separate** | Existing advice in `docs/hebrew_ot_architecture_audit.md` — do not generalise prematurely — remains correct |

---

## 13. Problems and technical debt

**13.1 Wrong morphology mapping, asserted as correct by tests (blocking).** §5.4. 4,305 imperatives → `weqatal`, flagged `fully_decoded`. `tests/test_hebrew_morphology_hu.py:73` enshrines it.

**13.2 Authoritative code table never loaded.** `load_tehmc_expansions()` exists but TEHMC is not shipped and `decode_hebrew_morphology` is always called with `{}`. The hand-written substitute tables have no cross-check. This is the systemic cause of 13.1.

**13.3 Per-component data destroyed for file size.** §2.3. Prefix/suffix surfaces empty, composite morphology on every component, glosses gone. Directly blocks compound-construction explanation.

**13.4 Lexical layer is unreviewed machine translation.** §6.3. 6,493/6,493 `ai_assisted` + `draft`. §6.4 proves a systematic, mechanically detectable defect class (extended-Strong mis-scoping).

**13.5 Contextual gloss presented as lexical meaning.** §6.5. No field separates the two; `H0834A` shows "amint" for the relative particle across ~4,935 tokens.

**13.6 No root concept.** §6.1. Requires a new source; must not be AI-inferred.

**13.7 Two parallel reference models.** §8.1. `CanonicalReference` exists and is unused by Hebrew; TAHOT codes vs OSIS; tuple vs dataclass; no cross-chapter support in the Hebrew path.

**13.8 Deterministic facts delegated to the AI.** §7.2. Decoded stem/form/person/gender/number/state computed and then thrown away before prompting.

**13.9 Deployment size at the edge of a hard limit.** `tahot_ot_runtime.sqlite3` is 96,555,008 bytes — **~3.4 MB below GitHub's 100 MB per-file hard limit**, and only there because a dedicated pruning script deletes real data. Total tracked binary payload ≈147 MB. Streamlit Cloud clones the repository on deploy. **Adding MACULA syntax to this file is not possible without a different distribution strategy.** This is the sharpest constraint on Phase 2 and is addressed in §21.

**13.10 Terminology hard-coded in UI.** `_core_part_of_speech_label()` duplicates `PART_OF_SPEECH_HU`.

**13.11 Component/analysis misalignment.** §5.5. Every maqaf-joined token silently loses one component's analysis, and can blank the part-of-speech label.

**13.12 Source token ID dropped.** `source_token_id` (`Rut.1.1#01=L`) removed by pruning — the only link to the exact upstream row, needed for cross-dataset alignment.

**13.13 No persistent cache and no versioning.** §9. Session-dict only, `use_cache=False`, no dataset/prompt/schema version anywhere in the key.

**13.14 Weak build provenance.** §3.1. No upstream commit SHA; `source_files` leaks local Windows temp paths. ACAI does this correctly and is the in-repo counter-example.

**13.15 Tests depend on untracked artifacts.** §11.3. 4 pre-existing failures; suite cannot go green on a clean clone.

**13.16 Cross-chapter unsupported.** Both the Greek path and `parse_hebrew_reference()` reject multi-chapter spans.

**13.17 Streamlit rerun cost.** A fresh `HebrewTokenRepository` per rerun re-runs a ~2 s `PRAGMA integrity_check`. Mitigated within a call, not across reruns.

**13.18 No syntax layer at all.** Nothing in the data model expresses phrase, clause, dependency, constituent or semantic role.

**13.19 Mojibake in shipped data.** 12 lexicon entries carry `"TAHOT unresolved Strong/STEP IDs alapj?n k?sz?tett magyar munkav?ltozat"` — an encoding failure baked into committed JSON.

**13.20 `H9xxx` pseudo-Strongs undocumented in the data model.** `H9002` (waw), `H9003` (preposition), `H9005`, `H9014` (maqaf), `H9015` (punctuation), `H9016`, `H9023` are STEPBible grammar markers, handled implicitly and nowhere modelled. They are the direct cause of 13.11 and will confuse any alignment work.

---

## 14. Licensing and provenance risks

| Dataset | Licence | Status | Risk |
|---|---|---|---|
| STEPBible TAHOT | CC BY 4.0 | In use | **Low.** Commercial use permitted. Attribution present in UI and metadata |
| STEPBible TBESH | CC BY 4.0 | In use | **Low–medium.** Meanings derive from Abridged BDB (Online Bible); must not be presented as internally authored |
| STEPBible TEHMC | CC BY 4.0 | Referenced, not shipped | **Low.** Shipping it would be an improvement |
| ACAI | **CC BY-SA 4.0** | Shipped (36.9 MB) | **Medium.** Share-alike. Derivatives of ACAI content may need to be licensed alike — a live question if ACAI feeds a commercial bundle |
| Hungarian lexicon | Derivative of TBESH | Shipped | **Medium.** A CC BY derivative; attribution obligations flow through. Also 100% unreviewed AI output |
| OSHB / MorphHB | CC BY 4.0 | Candidate | **Low** |
| MACULA Hebrew | CC BY 4.0 | Candidate | **Low** — verify per-file at import time |
| STEPBible (further) | CC BY 4.0 | Candidate | **Low** |
| ETCBC / BHSA | **CC BY-NC** | Candidate | **High for production.** Non-commercial. The brief's instruction to keep it out of the production dependency chain is correct and should be enforced mechanically, not by convention |
| RÚF 2014 | Contractual, restricted | Local only | **High.** `.gitignore:88–93` carries an explicit warning never to commit `ruf_bible.sqlite3`. Correctly handled today |

**Concrete provenance actions for Phase 2:**

1. Record `upstream_commit` and a precise `source_version` for every dataset; adopt the ACAI `store_metadata` schema verbatim.
2. Strip local absolute paths from `source_files`; record basenames + SHA-256 only.
3. Ship a `LICENSES.md` (or per-dataset metadata rows) naming licence, URL and required attribution for each store.
4. Add a build-time assertion that no CC BY-NC-derived data can enter a production store — an explicit allow-list of licence identifiers, failing the import otherwise.
5. Keep the ACAI CC BY-SA boundary explicit in the bundle so share-alike obligations can be reasoned about per-field rather than for the whole artifact.

---

## 15. Proposed Hebrew Analysis v2 architecture

### 15.1 Target shape

```
┌─────────────────────────────────────────────────────────────────┐
│ EXTERNAL SOURCES (never read at request time)                   │
│   STEPBible TAHOT/TBESH/TEHMC · OSHB/MorphHB · MACULA · ACAI    │
└───────────────────────────┬─────────────────────────────────────┘
                            │  offline, versioned, checksummed
┌───────────────────────────▼─────────────────────────────────────┐
│ OFFLINE IMPORT / NORMALIZATION      scripts/build_hebrew_store.py│
│   parse → normalize → cross-align → validate → atomic swap      │
│   emits: store + import audit + provenance (ACAI schema)        │
└───────────────────────────┬─────────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────────┐
│ TEXTUS NORMALIZED HEBREW LINGUISTIC STORE  (SQLite)             │
│   provenance · books · verses · tokens · morphology             │
│   roots · lexemes · senses · phrases · clauses · relations      │
│   semantic_roles · participants · patterns · ketiv_qere         │
└───────────────────────────┬─────────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────────┐
│ HebrewAnalysisService                                           │
│   bundle(CanonicalReference) -> HebrewAnalysisBundle            │
│   pure, deterministic, Streamlit-free, no LLM                   │
└───────────────────────────┬─────────────────────────────────────┘
┌───────────────────────────▼─────────────────────────────────────┐
│ HebrewAnalysisBundle   (typed, versioned, serializable)         │
└──────────┬──────────────────────────────────────┬───────────────┘
           │                                      │
┌──────────▼───────────────┐        ┌─────────────▼────────────────┐
│ UI FACTS  (no LLM)       │        │ AI INTERPRETATION LAYER      │
│  word card · stem/form   │        │  bundle → JSON contract      │
│  components · syntax     │        │  explains, never re-parses   │
│  constructions · K/Q     │        │  schema-validated output     │
└──────────────────────────┘        └─────────────┬────────────────┘
                                    ┌─────────────▼────────────────┐
                                    │ DURABLE VERSIONED CACHE      │
                                    │ key = ref + dataset_version  │
                                    │     + bundle_schema_version  │
                                    │     + prompt_version + model │
                                    └──────────────────────────────┘
```

### 15.2 Design principles

1. **No source XML/TSV parsing at request time.** Already true today; keep it true.
2. **One canonical reference model** — `CanonicalReference` everywhere, with `versification_scheme` carrying the Masoretic/English divergence logic currently embedded in `hebrew_parser.py`.
3. **Deterministic layer answers "what"; AI answers "what it means".** No overlap.
4. **Everything is versioned** — `dataset_version`, `bundle_schema_version`, `prompt_version`, `model_id` all in the cache key.
5. **Per-field provenance.** Every fact names its source dataset, so a MACULA claim is never confused with a TAHOT claim and licence obligations remain traceable.
6. **Graceful degradation.** MACULA covers less than TAHOT; a bundle with tokens but no clauses is valid and must render.
7. **Confidence is first-class.** Retain and extend the four-state `status` model.
8. **Component-level addressability.** Token IDs must reach sub-word components.

### 15.3 Storage decision

**Recommendation: an offline importer producing a compact normalized SQLite store — yes, and it is already the house pattern** (TAHOT, TBESH, TAGNT, ACAI all follow it).

The unavoidable complication is §13.9: the current file sits ~3.4 MB under a hard limit that is only met by deleting real data. Adding syntax makes the current distribution model untenable. Options, with a recommendation:

| Option | Pros | Cons |
|---|---|---|
| **A. Split into multiple committed stores** (`hebrew_core`, `hebrew_syntax`, `hebrew_lexical`) | Each under 100 MB; independent versioning; syntax optional at runtime | Multiple files to keep in sync; total repo size still grows |
| **B. Git LFS** | Purpose-built; one logical file | New infrastructure; LFS bandwidth quotas; Streamlit Cloud LFS support must be verified |
| **C. Download at first run from a release asset / object store** | Repository stays small; easy version pinning | Runtime network dependency; cold-start latency; needs integrity verification and a failure path |
| **D. Aggressive normalization + compression in place** | No new infrastructure | Buys maybe 2–3× at best; the ceiling returns quickly |

**Recommendation: A + D for Phase 2, with B or C as the Phase 3 escape hatch.** Splitting is low-risk, requires no new infrastructure, matches the existing multi-store convention, and makes the syntax layer independently optional — which is desirable anyway given MACULA's partial coverage. Normalization (interning repeated morphology codes, lemmas and glosses into lookup tables) will recover substantial space in the token table and is worth doing regardless. Crucially, splitting also lets the **restored per-component data** (§2.3) live in a store that is not competing for space with syntax.

---

## 16. Proposed `HebrewAnalysisBundle` schema

Verse-oriented, typed, serializable, versioned. Every element carries provenance. Every optional block may be absent without invalidating the bundle.

### 16.1 Top level

```python
@dataclass(frozen=True)
class HebrewAnalysisBundle:
    bundle_schema_version: str            # "2.0.0"
    reference: CanonicalReference
    reference_display: str                # "1 Mózes 1,1-3"
    verses: tuple[VerseAnalysis, ...]
    datasets: tuple[DatasetProvenance, ...]
    coverage: CoverageReport
    warnings: tuple[BundleWarning, ...]
```

```python
@dataclass(frozen=True)
class DatasetProvenance:
    dataset_id: str            # "tahot" | "oshb" | "macula" | "tbesh" | "acai" | "textus_hu"
    display_name: str
    source_version: str
    upstream_repository: str
    upstream_commit: str
    license: str               # "CC BY 4.0" | "CC BY-SA 4.0"
    license_url: str
    attribution: str
    content_hash: str

@dataclass(frozen=True)
class CoverageReport:
    has_morphology: bool
    has_syntax: bool
    has_semantic_roles: bool
    has_participants: bool
    has_roots: bool
    token_count: int
    fully_decoded_token_count: int
    notes: tuple[str, ...]

@dataclass(frozen=True)
class BundleWarning:
    scope: str                 # "token" | "phrase" | "clause" | "bundle"
    target_id: str
    code: str                  # "morphology_unresolved" | "alignment_ambiguous" | ...
    message_hu: str
```

### 16.2 Verse

```python
@dataclass(frozen=True)
class VerseAnalysis:
    verse_id: str                      # "Gen.1.1"
    chapter: int
    verse: int
    hebrew_text: str                   # accented, display-ready
    hebrew_text_plain: str             # accents stripped
    versification_note: str            # Masoretic/English divergence, if any
    tokens: tuple[TokenAnalysis, ...]
    phrases: tuple[PhraseAnalysis, ...]
    clauses: tuple[ClauseAnalysis, ...]
    participants: tuple[ParticipantMention, ...]
    detected_patterns: tuple[DetectedPattern, ...]
    text_critical: tuple[TextCriticalNote, ...]
```

### 16.3 Token — the heart of the bundle

```python
@dataclass(frozen=True)
class TokenAnalysis:
    token_id: str                      # "Gen.1.1:1"        stable, canonical-ref based
    legacy_stable_key: str             # "Gen:1:1:1"        migration bridge
    source_token_id: str               # "Gen.1.1#01=L"     upstream row link (RESTORE)
    word_index: int

    surface: str
    surface_plain: str
    transliteration: str
    transliteration_hu: str

    lemma: str
    lemma_plain: str
    root: RootInfo | None              # NEW — never AI-derived
    strong_ids: tuple[str, ...]

    part_of_speech: PartOfSpeech       # enum, not free text
    morphology: MorphologyFacts
    components: tuple[ComponentAnalysis, ...]   # RESTORED per-component data

    lexical_sense: LexicalSense | None          # basic/lexical
    contextual_sense: ContextualSense | None    # this occurrence — see §17

    ketiv: str
    qere: str
    source_edition: str
    maqaf: bool
    punctuation: str

    provenance: TokenProvenance
    confidence: str                    # fully_decoded|partially_decoded|unresolved|malformed
    unresolved_parts: tuple[str, ...]
```

```python
@dataclass(frozen=True)
class RootInfo:
    consonants: str                    # "ברא"
    display_hu: str                    # label uses "gyök"
    root_type: str                     # "triliteral"|"biliteral"|"quadriliteral"|"unknown"
    source_dataset: str

@dataclass(frozen=True)
class MorphologyFacts:
    raw_code: str                      # "Hc/Vqw3ms"
    code_system: str                   # "TEHMC"
    language: str                      # "hebrew"|"aramaic"
    verb_stem: str                     # "Qal"           ← ALWAYS separate
    verb_stem_hu: str                  # "qal"
    verb_form: str                     # "Consecutive Imperfect"  ← ALWAYS separate
    verb_form_hu: str                  # "wayyiqtol"
    verb_form_traditional: str         # "wayyiqtol"|"qatal"|"yiqtol"|"weqatal"|"imperative"|...
    person: str
    gender: str
    number: str
    state: str
    noun_type: str
    suffix: SuffixFacts | None
    english_expansion: str             # from TEHMC when loaded
    summary_hu: str                    # pre-rendered Hungarian

@dataclass(frozen=True)
class SuffixFacts:
    suffix_type: str                   # "Pronominal"|"Object"|"Directional"|"Emphatic"
    person: str
    gender: str
    number: str
    summary_hu: str

@dataclass(frozen=True)
class ComponentAnalysis:
    component_id: str                  # "Gen.1.1:1.2"   ← sub-word addressable
    role: str                          # "prefix"|"core"|"suffix"|"punctuation"
    role_label_hu: str                 # NOT "lexikai mag"
    surface: str                       # RESTORED
    strong_id: str
    morphology: MorphologyFacts        # per-segment, not composite
    gloss_en: str                      # RESTORED
    gloss_hu: str
    is_grammar_marker: bool            # H9002/H9003/H9014/H9015/... — §13.20

@dataclass(frozen=True)
class TokenProvenance:
    text_source: str                   # "tahot"
    morphology_source: str             # "tahot"|"oshb"
    lemma_source: str
    root_source: str
    lexical_source: str
    syntax_source: str                 # "macula"|""
```

### 16.4 Phrases, clauses, semantics, participants

```python
@dataclass(frozen=True)
class PhraseAnalysis:
    phrase_id: str                     # "Gen.1.1:p1"
    phrase_type: str                   # "NP"|"VP"|"PP"|"AdvP"|"CP"
    phrase_type_hu: str
    token_ids: tuple[str, ...]
    head_token_id: str | None
    parent_phrase_id: str | None
    function: str                      # "subject"|"object"|"adjunct"|...
    function_hu: str
    source_dataset: str

@dataclass(frozen=True)
class ClauseAnalysis:
    clause_id: str                     # "Gen.1.1:c1"
    clause_type: str                   # "verbal"|"nominal"|"participial"|"infinitival"
    clause_type_hu: str
    token_ids: tuple[str, ...]
    predicate_id: str | None
    subject_id: str | None
    object_ids: tuple[str, ...]
    complement_ids: tuple[str, ...]
    modifier_ids: tuple[str, ...]
    parent_clause_id: str | None
    relation_to_parent: str            # "coordinate"|"subordinate"|"relative"|"purpose"|...
    relation_to_parent_hu: str
    word_order: str                    # "VSO"|"SVO"|"fronted_object"|...   descriptive only
    source_dataset: str

@dataclass(frozen=True)
class SemanticRole:
    role_id: str
    role_type: str                     # "agent"|"patient"|"theme"|"experiencer"
                                       # |"recipient"|"location"|"instrument"|"time"
    role_type_hu: str
    token_ids: tuple[str, ...]
    predicate_id: str
    source_dataset: str

@dataclass(frozen=True)
class ParticipantMention:
    mention_id: str
    token_ids: tuple[str, ...]
    participant_id: str                # cross-verse coreference chain
    entity_id: str | None              # ACAI entity id when resolved
    entity_label_hu: str
    mention_type: str                  # "proper_name"|"pronoun"|"suffix"|"implicit_subject"
    source_dataset: str
```

### 16.5 Mechanically detectable patterns

The key discipline: **each pattern is emitted only when the deterministic layer can prove it from supplied structure. `evidence_token_ids` is mandatory.** An empty tuple is a valid and expected result.

```python
@dataclass(frozen=True)
class DetectedPattern:
    pattern_id: str
    pattern_type: str
    pattern_type_hu: str
    token_ids: tuple[str, ...]
    evidence_token_ids: tuple[str, ...]     # mandatory — what proves it
    detector_version: str
    confidence: str                          # "certain"|"probable"
    explanation_hu: str                      # deterministic template, NOT AI
```

Phase 2 detector set — chosen because each is provable from morphology + component structure alone, without syntax:

| `pattern_type` | Detection basis |
|---|---|
| `construct_chain` | Consecutive nouns, first in `state="Construct"` |
| `infinitive_absolute_with_finite_verb` | `Infinitive Absolute` adjacent to a finite verb of the same root |
| `double_negation` | Two negative particles within one clause |
| `preposition_article_fusion` | Prefix component `R` + article in one token |
| `pronominal_suffix_construction` | Core + `Sp*` suffix component |
| `explicit_pronoun_with_marked_subject` | Independent personal pronoun + finite verb agreeing in person/gender/number |
| `lexical_repetition` | Same lemma ≥2× within the passage |
| `root_repetition` | Same root ≥2× within the passage (**requires root source**) |
| `cognate_accusative` | Verb + object noun sharing a root |
| `waw_consecutive_chain` | ≥3 consecutive `wayyiqtol` forms |
| `fronted_constituent` | Non-verb-initial verbal clause (**requires syntax**) |
| `ketiv_qere_divergence` | Ketiv ≠ Qere on a token |

### 16.6 Text-critical metadata (deliberately minimal)

```python
@dataclass(frozen=True)
class TextCriticalNote:
    note_id: str
    token_id: str
    note_type: str                     # "ketiv_qere"|"spelling_variant"|"meaning_variant"
    ketiv: str
    qere: str
    source_edition: str                # "L"|"Q(K)"|"Q(k)"|"X"|...
    raw_meaning_variant: str
    raw_spelling_variant: str
    source_dataset: str                # "tahot"
```

**Explicitly excluded from Phase 2:** LXX, DSS, Samaritan Pentateuch, critical apparatus. The repository contains no deterministic source for any of them, so per the brief they stay out. Only what TAHOT already provides deterministically (1,323 ketiv/qere records, source-edition markers, raw variant strings) is included.

---

## 17. Proposed deterministic / AI responsibility boundary

### 17.1 The boundary

| Fact | Deterministic | AI |
|---|:---:|:---:|
| Hebrew text, tokenization, segmentation | ✅ | ❌ |
| Lemma, root, Strong IDs | ✅ | ❌ |
| Part of speech | ✅ | ❌ |
| **Verbal stem (binyan)** | ✅ | ❌ |
| **Conjugation / verbal form** | ✅ | ❌ |
| Person / gender / number / state | ✅ | ❌ |
| Prefixes / suffixes / components | ✅ | ❌ |
| Phrase / clause structure | ✅ | ❌ |
| Subject / predicate / object | ✅ | ❌ |
| Semantic roles, participants | ✅ | ❌ |
| Ketiv / Qere | ✅ | ❌ |
| Pattern detection (that a construct chain exists) | ✅ | ❌ |
| Word-order description (that the object is fronted) | ✅ | ❌ |
| Basic lexical meaning | ✅ (curated) | ❌ |
| — | | |
| Which listed sense fits this context | ❌ | ✅ |
| What this stem contributes to *this* lexeme here | ❌ | ✅ |
| What a detected construction means here | ❌ | ✅ |
| Why the syntax matters for understanding | ❌ | ✅ |
| Translation observations | ❌ | ✅ |
| Cautious word-order significance | ❌ | ✅ |
| Limited exegetical relevance | ❌ | ✅ |

### 17.2 The AI's input is the bundle, never raw Hebrew

Replacing `_format_hebrew_token_line()` (§7.2). Illustrative shape:

```
TOKEN Gen.1.1:1
  alak:            בְּ/רֵאשִׁ֖ית
  gyök:            ראש
  lemma:           רֵאשִׁית
  szófaj:          elöljárószó + főnév
  igetörzs:        —
  igealak:         —
  nem/szám/állapot: nőnem, egyes szám, absolutus
  komponensek:
    [prefixum]  בְּ      H9003  elöljárószó          "-ban/-ben"
    [törzs]     רֵאשִׁית  H7225G főnév, nőnem, egyes  "kezdet"
  lexikai alapjelentés:  kezdet, első
  lehetséges jelentések: kezdet | első | legjobb | zsenge
  forrás:  szöveg=TAHOT  morfológia=TAHOT  gyök=MACULA  lexikon=TBESH→HU

TOKEN Gen.1.1:2
  alak:            בָּרָ֣א
  gyök:            ברא
  lemma:           בָּרָא
  szófaj:          ige
  igetörzs:        qal
  igealak:         qatal (perfectum)
  személy/nem/szám: harmadik személy, hímnem, egyes szám
  lexikai alapjelentés: teremt
  ...

TAGMONDAT Gen.1.1:c1  (verbális)
  állítmány: Gen.1.1:2   alany: Gen.1.1:3   tárgy: Gen.1.1:5, Gen.1.1:7
  szórend:   VSO
  forrás:    MACULA

FELISMERT SZERKEZETEK
  [construct_chain] Gen.1.1:5–6  — bizonyíték: Gen.1.1:5 (state=constructus)
```

### 17.3 The output contract

```json
{
  "schema_version": "2.0.0",
  "reference": "Gen.1.1-3",
  "contextual_word_notes": [
    {
      "token_ids": ["Gen.1.1:2"],
      "lexical_meaning_hu": "teremt",
      "contextual_meaning_hu": "...",
      "stem_contribution_hu": "...",
      "grounded_on": ["morphology.verb_stem", "morphology.verb_form", "lexical_sense"],
      "certainty": "high"
    }
  ],
  "important_constructions": [
    {
      "pattern_ids": ["Gen.1.1:pat1"],
      "token_ids": ["Gen.1.1:5", "Gen.1.1:6"],
      "construction_type": "construct_chain",
      "explanation_hu": "...",
      "grounded_on": ["detected_patterns"],
      "certainty": "high"
    }
  ],
  "syntax_summary": {
    "summary_hu": "...",
    "clause_ids": ["Gen.1.1:c1"],
    "grounded_on": ["clauses"],
    "certainty": "medium"
  },
  "word_order_notes": [],
  "translation_notes": [],
  "exegetical_significance": []
}
```

Every element carries `grounded_on` (which bundle fields it rests on) and `certainty`. Every list may be **empty** — that is a success state.

### 17.4 AI instructions (v2 prompt principles)

**Must:**
1. **Explain, never re-parse.** Every grammatical fact is supplied. Never derive one from a raw code or from the Hebrew text.
2. **Separate lexical from contextual meaning** in every word note — both fields, always.
3. **Explain what a stem does to *this* lexeme here.** "Hitpael = reflexive" alone is insufficient; say what it does to this verb in this clause.
4. **Discuss only supplied structures.** If no clause data was supplied, `syntax_summary` stays empty.
5. **State uncertainty** via `certainty`, and in prose where it matters.
6. **Cite grounding** — populate `grounded_on` for every element.
7. **Return an empty list rather than invent a noteworthy feature.**

**Must not:**
1. Invent or correct morphology, stems, conjugations, syntax or clause relations.
2. Invent manuscript variants, textual witnesses, or LXX/DSS/Samaritan readings.
3. Claim emphasis **solely** from unusual word order — only when `word_order` was supplied *and* corroborated by another supplied fact.
4. Present a contextual sense as the lexical meaning (the `H0834A` failure mode, §6.4).
5. Derive meaning from etymology, similar-sounding words, or cognate roots not present in the bundle.
6. Assert contested identity questions on linguistic grounds (preserve the existing rule).
7. Claim database provenance in fallback mode (preserve the existing rule).

### 17.5 Validation

Extend `original_language_grounding_check.py` to validate the structured output:

- schema conformance and required-field presence;
- every `token_ids` / `pattern_ids` / `clause_ids` reference resolves within the bundle;
- every `grounded_on` names a field actually populated in the bundle;
- no grammatical term appears in prose that contradicts the bundle (e.g. prose saying *imperativus* where `verb_form` is `Perfect`);
- existing Hebrew-form and Strong-ID checks, retained.

This turns the current heuristic prose check into a **structural** check — a significant robustness gain that only becomes possible once the AI returns JSON.

---

## 18. Recommended external datasets for Phase 2

| Priority | Dataset | Provides | Licence | Rationale |
|---|---|---|---|---|
| **0** | **STEPBible TEHMC** | Authoritative morphology code expansions | CC BY 4.0 | **Highest value per unit of effort.** Already referenced; `load_tehmc_expansions()` already exists; shipping it would have prevented §5.4 and mechanically validates every code table entry. Small file. Do this first |
| **1** | **Existing TAHOT** (unpruned) | Text, morphology, components, ketiv/qere | CC BY 4.0 | Already correct; restore the per-component data pruning discards (§2.3) |
| **2** | **MACULA Hebrew** | Syntax trees, phrases, clauses, semantic roles, participants | CC BY 4.0 | The only credible source for the entire syntax requirement. Clear Bible — same ecosystem as the already-imported ACAI |
| **3** | **OSHB / MorphHB** | Independent morphology + segmentation; **root data** | CC BY 4.0 | Cross-validation against TAHOT (would have caught §5.4 independently) and a candidate root source |
| **4** | **ACAI** (already present) | Participant/entity references | **CC BY-SA 4.0** | Already imported with 98,649 passage links. Watch the share-alike boundary (§14) |
| **5** | STEPBible TBESH extended | Richer lexical/semantic tagging | CC BY 4.0 | Improves the lexical layer that §6.4 shows needs work |
| **—** | **ETCBC / BHSA** | Research validation only | **CC BY-NC** | **Never a production dependency.** Offline validation only; enforce mechanically (§14) |
| **—** | LXX / DSS / SP / apparatus | Textual criticism | varies | **Out of scope.** Separate later project |

**Alignment is the principal technical risk.** TAHOT, OSHB and MACULA use different tokenizations, different versification and different identifier schemes. `source_token_id` — currently dropped by pruning (§13.12) — is the natural alignment anchor and should be restored before any cross-dataset import begins. Alignment must be an **offline, audited, verifiable** step producing an explicit report of unaligned tokens, exactly as the existing TAHOT importer already does with `_validate_audit()`.

---

## 19. Files and modules likely to change in Phase 2

### 19.1 Change (existing)

| File | Change |
|---|---|
| `bible_engine/hebrew_morphology.py` | **Fix `VERB_FORMS["v"]` → Imperative**; verify `u`/`M`/`D`/`Q`/`E`; load TEHMC; add `verb_form_traditional` |
| `bible_engine/hebrew_morphology_hu.py` | Replace `lexikai mag`; add imperative/cohortative terms; separate stem/form in the compact summary |
| `bible_engine/hebrew_sqlite.py` | New tables (roots, phrases, clauses, relations, semantic_roles, participants, patterns, provenance); restore component fidelity |
| `bible_engine/hebrew_parser.py` | Preserve `source_token_id`; emit root when available |
| `bible_engine/hebrew_token_repository.py` | Expose components, phrases, clauses; keep the facade shape |
| `bible_engine/hebrew_books.py` | Bridge to `CanonicalReference` |
| `bible_engine/original_language_analysis.py` | **Replace `_format_hebrew_token_line()`**; bundle-based prompt; structured output |
| `bible_engine/original_language_grounding_check.py` | Structural validation of the JSON contract |
| `hebrew_text_demo.py` | Fix §5.5 misalignment; remove duplicated terminology; render syntax/constructions; separate stem/form prominently |
| `scripts/prune_tahot_runtime_db.py` | Rework under the §15.3 split-store strategy |
| `app.py` | Wire durable cache; adjust the tab; possibly raise the token budget |
| `tests/test_hebrew_morphology_hu.py` | **Fix the assertions that encode the bug** (lines 73–74) |
| `tests/test_hebrew_morphology.py` | Add real-corpus-derived cases |
| `tests/test_hebrew_lexicon_hu.py` | Repair the untracked-artifact dependency (§11.3) |
| `.gitignore` | Adjust for the new store layout |

### 19.2 Add (new)

| File | Purpose |
|---|---|
| `bible_engine/hebrew_analysis_bundle.py` | Bundle dataclasses (§16) |
| `bible_engine/hebrew_analysis_service.py` | `HebrewAnalysisService.bundle(ref)` |
| `bible_engine/hebrew_pattern_detection.py` | Deterministic detectors (§16.5) |
| `bible_engine/hebrew_syntax_repository.py` | Phrase/clause/role access |
| `bible_engine/hebrew_roots.py` | Root normalization and lookup |
| `bible_engine/hebrew_ai_contract.py` | Output schema + validator |
| `bible_engine/hebrew_analysis_cache.py` | Durable versioned cache |
| `scripts/build_hebrew_linguistic_store.py` | Unified offline importer |
| `scripts/import_macula_hebrew.py` | MACULA import + alignment audit |
| `scripts/import_oshb_morphology.py` | OSHB import + cross-validation |
| `scripts/validate_morphology_against_tehmc.py` | **Would have caught §5.4** |
| `scripts/audit_hebrew_lexicon_lemma_consistency.py` | **Would have caught §6.4** |
| `tests/test_hebrew_analysis_bundle.py` | Bundle assembly |
| `tests/test_hebrew_pattern_detection.py` | Detectors |
| `tests/test_hebrew_ai_contract.py` | Schema/validator |
| `tests/fixtures/hebrew_golden/` | Expert-reviewed fixtures (§20) |
| `docs/hebrew_analysis_v2_architecture.md` | Design record |
| `docs/hebrew_datasets_provenance.md` | Licences and attributions |

### 19.3 Do not change

`textus_kb/canonical_reference.py` (adopt as-is) · `textus_kb/adapters/acai_entities.py` (use as template) · Greek modules (`tagnt_*`, `greek_*`) — keep the language stacks separate per the existing, still-correct guidance · commentary integration · `bible_engine/paths.py`.

---

## 20. Recommended regression tests

### 20.1 Two-track structure

The brief's A/B split is exactly right and should be enforced **structurally**, so that a flaky AI test can never mask a deterministic regression:

```
tests/
  test_hebrew_deterministic_golden.py   # Track A — strict equality, must always pass
  test_hebrew_ai_explanation.py         # Track B — constrained quality, separately marked
  fixtures/hebrew_golden/
    manifest.json
    gen_01_01_03.json      ...
```

### 20.2 Track A — deterministic facts (strict)

Assert exact equality on: token count and IDs; surface and lemma; **root**; part of speech; **verb_stem**; **verb_form**; person/gender/number/state; component role, surface, morphology and gloss; phrase and clause IDs and membership; predicate/subject/object; detected pattern types and `evidence_token_ids`; ketiv/qere; per-field provenance.

**Mandatory anti-regression cases, drawn from this audit:**

```python
# The §5.4 defect — must never return
("Gen.1.22", "פְּר֣וּ",  "HVqv2mp", stem="Qal", form="Imperative", form_hu="imperativus")
("Gen.22.2", "קַח",      "HVqv2ms", stem="Qal", form="Imperative")
("Gen.6.14", "עֲשֵׂ֤ה",   "HVqv2ms", stem="Qal", form="Imperative")
# genuine weqatal must stay weqatal
("Gen.2.24", "וְ/דָבַ֣ק", "Hc/Vqq3ms", stem="Qal", form="Consecutive Perfect")
# invariant: no verb may be BOTH form=Consecutive Perfect AND exclusively 2nd person
# invariant: every code in the corpus must map to a non-empty form label
# invariant: no code absent from the corpus may appear in a golden fixture

# The §6.4 defect — must never return
("H0834A", lemma_matches_corpus_lemma=True)
# invariant: for every lexicon entry, HU lemma == surface lemma of tokens carrying that ID
# invariant: base_meaning_hu is never a purely temporal/contextual sense
#            for a token whose part_of_speech is a relative particle
```

Plus structural invariants: `len(components) == len(component_analyses)` for **every** token in the corpus (§5.5); every component has a non-empty surface (§2.3); every `token_id` in a phrase/clause/pattern resolves.

### 20.3 Track B — constrained AI quality

Never assert exact prose. Assert **constraints**:

- output validates against the JSON schema;
- every referenced ID exists in the bundle;
- every `grounded_on` names a populated field;
- **no grammatical claim contradicts the bundle** (the highest-value automated check);
- no Hebrew form appears that is absent from the bundle (reuse the existing grounding checker);
- empty lists are accepted without penalty;
- **negative controls:** given a bundle with no clause data, `syntax_summary` **must** be empty; given a bundle with no unusual word order, `word_order_notes` **must** be empty. These catch fabrication directly.

Track B should be marked (`@pytest.mark.ai`) and excluded from the default run so CI stays deterministic.

### 20.4 The expert fixture set — 10–20 passages

**Do not create this yet.** Recommended storage and process:

**Format** — one JSON file per passage under `tests/fixtures/hebrew_golden/`:

```json
{
  "fixture_version": "1.0.0",
  "reference": "Gen.1.1-3",
  "reference_hu": "1 Mózes 1,1-3",
  "rationale": "wayyiqtol chain; construct chain; qatal/wayyiqtol contrast",
  "covers": ["wayyiqtol", "construct_chain", "qatal"],
  "dataset_versions": {"tahot": "...", "macula": "...", "oshb": "..."},
  "reviewed_by": "<expert name>",
  "reviewed_at": "2026-XX-XX",
  "review_notes_hu": "...",
  "expected_tokens": [],
  "expected_clauses": [],
  "expected_patterns": [],
  "ai_constraints": {
    "must_mention_token_ids": [],
    "must_not_claim": ["textual variant", "emphasis from word order alone"],
    "must_distinguish_lexical_and_contextual": true
  }
}
```

**Process:**
1. Generate a candidate fixture mechanically from the bundle.
2. A Hebrew expert reviews and corrects it, recording `reviewed_by` / `reviewed_at` / `review_notes_hu`.
3. Only reviewed fixtures gate CI; unreviewed candidates live under `candidates/`.
4. `fixture_version` bumps on any expected-value change, with the reason recorded.
5. Because fixtures pin `dataset_versions`, a dataset upgrade produces a **visible, reviewable diff** rather than a silent behaviour change.

**Proposed coverage (12–16 passages):**

| # | Passage | Covers |
|---|---|---|
| 1 | Gen 1,1–3 | qatal, wayyiqtol, construct chain, `בְּרֵאשִׁית` prefix fusion |
| 2 | Gen 1,22 or 1,28 | **Qal imperative** — the §5.4 anti-regression anchor |
| 3 | Gen 22,1–2 | Imperative, `אֶת` object marker, maqaf, pronominal suffix chain |
| 4 | Gen 32,25–29 | Niphal/Hiphil contrast, root repetition (`שׂרה`), the identity-caution rule |
| 5 | Ex 3,14 | `אֶהְיֶה אֲשֶׁר אֶהְיֶה` — **`אֲשֶׁר` as pure relative** (§6.4 anchor) |
| 6 | Ex 20,1–3 | **Double negation**, `לֹא` — and the `H3808` lemma question (§6.4) |
| 7 | Deut 6,4–5 | Nominal clause, imperative, `וְאָהַבְתָּ` **weqatal** — must stay weqatal |
| 8 | Gen 2,16–17 | **Infinitive absolute + finite verb** (`מוֹת תָּמוּת`) |
| 9 | Ruth 1,16–17 | `אֲשֶׁר` in multiple functions; already covered by the existing fixture |
| 10 | Ruth 3,12–14 | **Ketiv/Qere** — the audit doc names `Rut.3.14#02=Q(K)` |
| 11 | Ps 23,1–3 | Nominal clause, Piel, pronominal suffixes |
| 12 | Ps 51,12–14 | **Piel/Hitpael semantic contrast**, cohortative |
| 13 | Isa 6,1–3 | **Repetition** (`קָדוֹשׁ` ×3), participles, word order |
| 14 | Isa 7,14 | **MT vs modern translation divergence** (`עַלְמָה`) |
| 15 | Jonah 1,1–3 | wayyiqtol chain, infinitive construct, directional suffix |
| 16 | Dan 2,4–5 | **Aramaic** — Peal/Aphel, `language="aramaic"` |

This covers every case the brief lists: Qal/Piel/Hitpael contrasts (4, 12), verbal forms (1, 2, 7, 15), `אֲשֶׁר` (5, 9), double negation (6), construct chains (1, 3), infinitive absolute (8), unusual multi-token constructions (3, 8), word order (13), Ketiv/Qere (10), MT-vs-translation divergence (14) — plus Aramaic coverage (16), which the brief does not mention but which the corpus contains (4,827 tokens).

---

## 21. Migration and deployment risks

| # | Risk | Severity | Mitigation |
|---|---|---|---|
| 1 | **Repository size.** 96.5 MB file, ~3.4 MB under a hard limit, only met by deleting data. MACULA cannot fit | **High** | §15.3 option A+D: split stores + intern repeated strings. Escape hatch: LFS or download-on-first-run |
| 2 | **Streamlit Cloud cold start.** Clone + open ~150 MB of SQLite on every cold start; `PRAGMA integrity_check` ~2 s per rerun | **High** | Cache the repository across reruns; make integrity checks opt-in or startup-only; lazily open the syntax store |
| 3 | **Fixing the imperative bug changes visible output for 4,305 tokens** | Medium | It is a bug fix, and the correct one. Land it early, alone, with its own test; note it in `CHANGELOG.md` |
| 4 | **Token ID migration.** `Gen:1:1:1` → `Gen.1.1:1` breaks saved selections/caches | Medium | Keep `legacy_stable_key` in the bundle; provide a bidirectional mapper; invalidate caches by version bump |
| 5 | **Cross-dataset alignment failures.** Different tokenization/versification | **High** | Restore `source_token_id` first; offline audited alignment with an explicit unaligned-token report; treat unaligned tokens as missing-syntax, never as guesses |
| 6 | **MACULA partial coverage** | Medium | `CoverageReport` + graceful degradation; UI must render a bundle with no syntax |
| 7 | **CC BY-SA contamination via ACAI** | Medium | Per-field provenance; keep the SA boundary explicit; legal review before commercial release |
| 8 | **ETCBC leaking into production** | Medium | Build-time licence allow-list assertion that fails the import |
| 9 | **Prompt regression on rewrite** | Medium | Track B negative controls; keep the old prompt behind a flag for A/B |
| 10 | **Structured JSON output reliability** | Medium | `response_schema` is already a `generate_text()` parameter; validate and retry once; fall back to the current prose path |
| 11 | **Pre-existing red tests mask new failures** | Medium | Fix §11.3 before Phase 2 starts |
| 12 | **Windows SQLite file replacement** | Low | Already solved — `_replace_atomically()` with retry |
| 13 | **Cache invalidation on dataset upgrade** | Medium | Version everything in the key; fixtures pin `dataset_versions` so upgrades diff visibly |
| 14 | **Import runtime and memory** | Low–medium | 305k tokens already import fine; batch MACULA and stream |

---

## 22. Recommended Phase 2 implementation scope

Ordered by evidence, with the riskiest and highest-value correction first and **no AI work until the deterministic layer is trustworthy**.

### Phase 2A — Correct and validate the deterministic morphology *(smallest, highest value)*

1. Fix `VERB_FORMS["v"] → "Imperative"`.
2. Verify `u`, `M`, `D`, `Q`/`E` against TEHMC; add `Cohortative` if warranted.
3. Ship the TEHMC expansion file; load it in `HebrewTokenRepository.morphology()`.
4. Add `scripts/validate_morphology_against_tehmc.py` — assert **every** code occurring in the corpus decodes consistently with TEHMC; wire it into CI.
5. **Fix `tests/test_hebrew_morphology_hu.py:73–74`** and re-derive all morphology test cases from real corpus rows.
6. Add the corpus invariants from §20.2 (no exclusively-2nd-person "consecutive perfect"; no fixture may use a code absent from the corpus).
7. Repair the untracked-artifact test failures (§11.3).

*Deliverable: correct morphology, provably. Days, not weeks. **This is the gate for everything else.***

### Phase 2B — Audit and repair the lexical layer

8. `scripts/audit_hebrew_lexicon_lemma_consistency.py` — flag every entry whose HU lemma disagrees with the corpus lemma of the tokens carrying that ID (**would have caught `H0834A`**).
9. Fix `H0834A`; add a proper `H0834` (`אֲשֶׁר`) record; review `H3808` and `H0430G`.
10. Fix the 12 mojibake source strings.
11. Introduce human review: move the highest-frequency N entries from `draft` to `reviewed`, prioritised by the existing `build_hebrew_lexicon_priority_audit()`.
12. Add `lexical_sense` / `contextual_sense` as **separate fields** in the data model (contextual left unpopulated until 2E).

*Deliverable: the reported `אֲשֶׁר` defect fixed, and its whole defect class made detectable.*

### Phase 2C — Normalize the store and restore lost fidelity

13. Restore per-component surface, morphology and gloss (§2.3) and `source_token_id` (§13.12).
14. Fix the component/analysis misalignment (§5.5); model `H9xxx` grammar markers explicitly (§13.20).
15. Implement the split-store strategy (§15.3 A+D).
16. Adopt the ACAI `store_metadata` provenance schema for all Hebrew stores; strip local paths.
17. Bridge `hebrew_books.py` to `CanonicalReference`, preserving the Masoretic-versification logic.
18. Terminology: replace `lexikai mag`; de-duplicate the UI part-of-speech mapping; separate stem/form in the compact summary.

*Deliverable: a normalized store that can carry syntax, with the data the compound-construction requirement needs.*

### Phase 2D — Deterministic bundle and pattern detection *(still no AI)*

19. `HebrewAnalysisBundle` dataclasses (§16).
20. `HebrewAnalysisService.bundle(CanonicalReference)`.
21. Detectors that need **no** syntax: construct chain, infinitive absolute + finite verb, double negation, preposition/article fusion, pronominal suffix, explicit pronoun with marked subject, lexical repetition, ketiv/qere divergence.
22. Surface bundle facts in the UI — including the deterministic construction explanations.
23. Build the 12–16 expert fixtures (§20.4) and gate CI on Track A.

*Deliverable: measurably better analysis with **zero** additional AI risk. If Phase 2 stopped here it would already address most of the reported problems.*

### Phase 2E — Syntax import *(the first genuinely new dataset)*

24. Offline MACULA import with an audited alignment report.
25. Populate phrases, clauses, relations, semantic roles, participants.
26. Add syntax-dependent detectors (fronted constituent, cognate accusative, root repetition).
27. Optional: OSHB import for root data and independent morphology cross-validation.

### Phase 2F — AI interpretation on the bundle *(last)*

28. Replace `_format_hebrew_token_line()` with bundle serialization.
29. Implement the §17.3 structured contract with `response_schema`.
30. Rewrite the prompt per §17.4.
31. Extend the grounding checker to structural validation (§17.5).
32. Add the durable versioned cache (§9, §15.1).
33. Track B tests with negative controls.

### Recommended cut for a first shippable Phase 2

**2A + 2B + 2C + 2D.** This is defensible on the evidence: it fixes both reproduced user-visible defects (the `weqatal` mislabelling and the `אֲשֶׁר` gloss), restores the per-component data that compound-construction explanation requires, normalizes the model so syntax can be added without another migration, and delivers real user value through deterministic construction detection — all **without** adding a dataset, a dependency, or a single new AI failure mode. 2E and 2F then land on a foundation that is known-correct rather than assumed-correct.

### Is the repository ready for Phase 2?

**Yes — with 2A treated as a hard prerequisite.**

The architecture is genuinely well-suited to this evolution: the deterministic/AI boundary largely exists, the offline-import pattern is proven three times over, the reference model to adopt already exists, the morphology dataclass already has the separate stem/form fields the target design needs, and the test methodology (fixture-first, deterministic modules, Streamlit-free) is sound. What is not ready is the *content* of two hand-maintained tables and one AI-generated lexicon — and both defect classes are now precisely located, reproduced, and mechanically detectable.

Fix the morphology tables first. Everything else follows cleanly.

---

## Appendix A — Audit method

All quantitative claims were produced by read-only queries against the shipped runtime database and by importing the repository's own modules. No file was modified.

- **Corpus census:** all 305,635 tokens of `data/generated/tahot_ot_runtime.sqlite3`, decoded through `bible_engine.hebrew_morphology._split_morphology_components` so that language-code inheritance is honoured.
- **Imperative proof:** person-distribution census for form codes `v` and `q`; occurrence count for `m`; corroboration from the dataset's own `english_gloss` column.
- **`אֲשֶׁר` proof:** Strong-ID census for `lemma = אֲשֶׁר`; end-to-end resolution through `HebrewHungarianLexiconRepository.lookup()`.
- **Component-degradation proof:** live `HebrewTokenRepository.passage("Gen", 1, 1)` inspection.
- **Misalignment proof:** `len(ordered_token_components) != len(component_analyses)` over Gen 1:3 and Gen 22:2.
- **Lexicon statistics:** full scan of `bible_engine/data/hebrew_lexicon_hu.json` (6,493 entries); coverage computed against all 540,437 token Strong references.
- **Test baseline:** `pytest tests/test_hebrew_*.py tests/test_original_language_*.py -q` → 4 failed, 80 passed.

## Appendix B — Files inspected

**Read in full:** `bible_engine/hebrew_parser.py`, `hebrew_morphology.py`, `hebrew_morphology_hu.py`, `hebrew_token_repository.py`, `hebrew_lexicon_hu.py`, `tbesh_parser.py`, `paths.py`, `original_language_analysis.py`, `docs/hebrew_ot_architecture_audit.md`.

**Read in relevant part:** `bible_engine/hebrew_sqlite.py`, `hebrew_books.py`, `hebrew_lexicon_translation_workflow.py`, `original_language_grounding_check.py`, `greek_analysis_ui.py`, `hebrew_text_demo.py`, `app.py`, `textus_kb/canonical_reference.py`, `textus_kb/adapters/acai_entities.py`, `original_language_concordance.py`, `biblical_passage_refs.py`, `scripts/prune_tahot_runtime_db.py`, `tests/test_hebrew_morphology_hu.py`, `.gitignore`, `requirements.txt`.

**Queried:** `data/generated/tahot_ot_runtime.sqlite3`, `tbesh_lexicon_runtime.sqlite3`, `acai_entities.sqlite3`, `bible_engine/data/hebrew_lexicon_hu.json`, `hebrew_strong_aliases.json`.
