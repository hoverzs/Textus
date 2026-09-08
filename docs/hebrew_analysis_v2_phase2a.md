# Hebrew Analysis v2 — Phase 2A: Deterministic Correctness Hardening

**Scope:** deterministic morphology and lexical correctness only. No MACULA, no
syntax, no new AI interpretation, no UI redesign.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base:** `f1ec60e`
**Baseline document:** [`docs/hebrew_analysis_v2_inventory.md`](hebrew_analysis_v2_inventory.md)

---

## 1. What was fixed

| # | Defect | Before | After |
|---|---|---|---|
| 1 | TEHMC form code `v` mapped to Consecutive Perfect | **4,305 imperatives labelled `weqatal`**, marked *fully resolved* | 4,305 imperatives labelled `imperativus` |
| 2 | TEHMC form code `c` not disambiguated | **534 cohortatives labelled `infinitivus constructus`** while carrying a person | 534 cohortatives labelled `cohortativus` |
| 3 | Unverifiable stem codes given invented names | `D/u/M/Q/e/a/i` asserted as Nithpael/Hitpael/… | reported as unresolved (`verb-stem:X`) |
| 4 | Dead mappings (`m`, `n`) masked real codes | present, zero corpus occurrences | removed |
| 5 | Confidence was meaningless | any `H…`/`A…` code was `fully_decoded` | full confidence requires verified decoding |
| 6 | Preposition tail silently swallowed | `Rd` accepted, never surfaced | decoded as "elöljárószó, határozott névelővel" |
| 7 | TBESH `uStrong` treated as identity | **1,056 Strong keys held by the wrong record** | importer keys by identity; runtime labels cross-references |
| 8 | אֲשֶׁר presented a 1% temporal gloss as its base meaning | "amint / ahogyan / amikor", lemma כַּאֲשֶׁר | "aki, amely, ami", lemma אֲשֶׁר |
| 9 | Decoded grammar discarded before the AI | raw TEHMC code + English POS | full decoded morphology in Hungarian |
| 10 | `COMPONENT_ROLE_HU["core"] == "lexikai mag"` | misleading | `"alapszó"` — **not** `"gyök"`, see §6 |
| 11 | Tests asserted the defects as correct | `HVqv3ms → weqatal`, `lexikai mag` | corrected against real corpus rows |

---

## 2. Authoritative mapping source

**The STEPBible TEHMC expansion file is not present in this repository and could
not be obtained within this phase's constraints.** `load_tehmc_expansions()`
exists but is never called with data at runtime; the scratchpad is empty; no
TAHOT/TBESH/TEHMC source TSV is committed.

Rather than guess, every mapping was verified against **the shipped TAHOT corpus
itself** (`data/generated/tahot_ot_runtime.sqlite3`, 305,635 tokens), using two
independent kinds of evidence:

1. **STEPBible's own `english_gloss` column** — editorial data shipped with the
   corpus, not an inference of ours.
2. **Structural constraints** — which persons, genders, numbers and states a
   code actually co-occurs with across the whole Old Testament.

This is weaker than the TEHMC table for *naming* rare stems, and §5 records
exactly where it therefore refuses to decide. It is *stronger* than TEHMC for
catching the imperative defect, because it is grounded in how the codes are
actually used in the shipped data.

> **Phase 2B action:** obtain
> `Morphology codes/TEHMC - Translators Expansion of Hebrew Morphology Codes -
> STEPBible.org CC BY.txt`, commit it (it is small and CC BY 4.0), and run
> `scripts/validate_hebrew_morphology.py` against it to close §5.

---

## 3. Verified morphology mappings

### 3.1 Verb forms (all 11 codes occurring in the corpus)

| Code | Tokens | Decoded | Hungarian | Evidence |
|---|---:|---|---|---|
| `w` | 14,978 | Consecutive Imperfect | wayyiqtol | person tail; "he said", "there was" |
| `p` | 14,791 | Perfect | perfectum | person tail; "he created" |
| `i` | 13,471 | Imperfect | imperfectum | person tail; "you will eat" |
| `r` | 8,419 | Participle | participium | gender+number+state, no person |
| `c` | 6,758 | Infinitive Construct | infinitivus constructus | state tail `c`; "to rule", "saying" |
| `c`+person | 534 | **Cohortative** | cohortativus | **100% first person** (1cs 358, 1cp 176); "let us go down" (Gen 11:7), "let me bless" (Gen 12:3) |
| `q` | 6,344 | Consecutive Perfect | weqatal | persons 3/2/1 = 3666/1555/1123; follows lowercase-`c` waw |
| **`v`** | **4,305** | **Imperative** | **imperativus** | **100% second person** (2ms 2338, 2mp 1630, 2fs 315, 2fp 22); "be fruitful" (Gen 1:22), "take" (Gen 22:2), "listen to" (Gen 4:23) |
| `s` | 1,280 | Passive Participle | passzív participium | gender+number+state; "[be] blessed" |
| `j` | 1,099 | Jussive | jussivus | person tail; "let it be" |
| `u` | 999 | Conjunction Imperfect | kötőszós imperfectum | **occurs only after an uppercase-`C` waw, 999/999**; "so that I may bless" |
| `a` | 749 | Infinitive Absolute | infinitivus absolutus | tail always `a`; "certainly <to die>" |

**Why `v` is decisive.** A consecutive perfect inflects in all three persons —
and `q` demonstrably does. A form attested 4,305 times and *exclusively* in the
second person, whose STEPBible glosses are bare commands, is the imperative. The
previously "correct" imperative code `m` occurs **zero** times in the corpus.

**`u` was cleared, not changed.** The audit flagged it as suspect. Corpus
evidence supports the existing label: `u` never occurs bare (999/999 follow an
ordinary uppercase-`C` waw) and `i` never follows one, so the two are in
complementary distribution. Its volitional glosses are a semantic nuance, not
grounds for renaming it.

### 3.2 Verb stems

**Verified (9):** `q` Qal 50,831 · `h` Hiphil 9,576 · `p` Piel 6,906 ·
`N` Niphal 4,148 · `t` Hithpael 1,001 · `P` Pual 517 · `H` Hophal 431 ·
`v` Hishtaphel 133 (lemma שָׁחָה "he bowed down") · `c` Tiphil 3 (lemmas
תִּרְגַּל / תַּחָרָה).

### 3.3 Other codes

`Rd` (12,176 tokens) is a fused preposition + definite article, verified because
`d` is the article marker in the particle code `Td` (23,947 tokens). It is now
decoded and rendered as *"elöljárószó, határozott névelővel"* — the
"preposition + article" construction the professional review asked about.
Conjunction (`C` 30,518 / `c` 21,324) and adverb (`D` 4,440) codes carry no tail
anywhere in the corpus; a non-empty tail is now reported rather than swallowed.

---

## 4. Corpus validation

`scripts/validate_hebrew_morphology.py` (also run as tests in
`tests/test_hebrew_morphology_corpus.py`) checks, over all 3,081 distinct codes:

* status of every code; frequency census of every stem and form code;
* **no dead mappings** (mapped but never attested) — the failure mode that hid
  the imperative defect;
* **no unmapped corpus codes** outside the explicitly unverified set;
* **person constraints**: imperative ⇒ second person only, cohortative ⇒ first
  person only, and infinitives/participles never carry a person.

```
unique morphology codes : 3081        tokens : 305635
status by code          : {'fully_decoded': 3013, 'partially_decoded': 67, 'malformed': 1}
status by token         : {'fully_decoded': 305440, 'partially_decoded': 181, 'malformed': 14}

Imperative                4305   persons={'Second': 4305}
Cohortative                534   persons={'First': 534}
Consecutive Perfect       6344   persons={'Third': 3666, 'Second': 1555, 'First': 1123}
Participle                8419   persons={'<none>': 8419}
Infinitive Construct      6758   persons={'<none>': 6758}

No problems detected.
```

Before Phase 2A the same corpus decoded to **0 imperatives and 0 cohortatives** —
an impossibility for the Hebrew Bible, and the single clearest signal that the
tables were wrong.

The 14 `malformed` tokens are pre-existing empty morphology codes, unchanged.

---

## 5. Remaining unresolved codes

Seven stem codes are attested but **not named**, because no source available to
this repository can establish their TEHMC names:

| Code | Tokens | Language | Previous (unverified) name | Why refused |
|---|---:|---|---|---|
| `Q` | 65 | Aramaic | Peil | passive Aramaic; name unprovable |
| `u` | 61 | 53 Aramaic / 8 Hebrew | Hitpael | Aramaic-dominant passive — a *Hebrew* Hitpael label is contradicted |
| `M` | 30 | Aramaic | Hitpaal | unprovable |
| `e` | 15 | Aramaic | Peal | **actively contradicted**: every token's lemma is שֵׁיזִב / שֵׁיצִי, Shaphel verbs |
| `a` | 4 | Aramaic | Aphel | unprovable |
| `D` | 3 | Hebrew | Nithpael | unprovable |
| `i` | 3 | Aramaic | Ithpeel | unprovable |

Total **181 tokens = 0.059%** of the corpus. These now decode with
`verb_stem == ""`, `status == "partially_decoded"` and
`unresolved_parts == ("verb-stem:X",)`; person, gender, number and the Hungarian
rendering are still produced, and the raw code is preserved. Users see *"részben
feloldott morfológia"* instead of a possibly-wrong stem name.

---

## 6. Root vs "core" — terminology decision

**`COMPONENT_ROLE_HU["core"]` was changed from `"lexikai mag"` to `"alapszó"` —
deliberately *not* to `"gyök"`.**

`hebrew_parser._core_index()` defines "core" as the component whose TAHOT
`dStrong` field carries a brace-wrapped `{Hxxxx}` Strong number: the
**lexeme-bearing part of the surface word**, stripped of attached prefixes (waw,
preposition, article) and suffixes (pronominal/object). For `בְּ/רֵאשִׁ֖ית` the
core is רֵאשִׁית — a fully inflected noun, **not** the root ר־א־שׁ.

Labelling that `gyök` would replace one error with a worse one. The professional
request for "gyök" is legitimate but requires a **new, separate normalized
field**, not a rename.

**Is a reliable Hebrew root source already available? No.** Verified: no `root`
field on `HebrewToken`, `HebrewComponent` or `HebrewMorphology`; no `root` column
in any schema; no root key in the Hungarian lexicon; TAHOT ships no root column;
TBESH's `morph` column is a part-of-speech code (`H:V`, `N:N-M-P`), not a root.
A root source (OSHB/MorphHB or MACULA) must be imported in a later phase, and the
root must never be derived heuristically or by the AI.

---

## 7. Lexicon findings — the defect was in the algorithm

### 7.1 Root cause

TBESH's `uStrong` column is a **cross-reference** to the lexeme a record is
derived from, never the record's own identity. The importer looped over
`entry.strong_ids` — which harvests eStrong **+ dStrong + uStrong** — and used
`INSERT OR REPLACE`. Derived records therefore *claimed and destroyed* the entry
of the word they merely pointed at.

The real TBESH row behind the reported bug:

```
eStrong  H0834d
dStrong  H0834D = combination of      <- this record IS H0834D (כַּאֲשֶׁר)
uStrong  H0834A (H9004+H0834A)        <- it only POINTS AT H0834A (אֲשֶׁר)
```

It was written to key `H0834A`, overwriting the genuine relative particle.

### 7.2 Blast radius — far wider than אֲשֶׁר

| Measure | Value |
|---|---|
| TBESH keys held by a cross-reference record | **1,056 of 12,521** |
| Corpus token references resolving through them | **292,282 of 540,437 (54%)** |
| Hungarian records whose lemma disagrees with the corpus | **299** |
| Corpus tokens behind those records | **134,232** |
| Of those, explained by the hijack | **281 of 299 (94%)** |

Relation types responsible: "in Aramaic of" 381 · "a Name of" 186 · "a Spelling
of" 151 · "a Meaning of" 112 · "a group of" 109 · "a Part of" 49 · "a form of"
15 · "combination of" 14.

Worst affected, all user-visible:

| Strong | Tokens | Corpus word | Record actually shown |
|---|---:|---|---|
| `H0853` | 21,890 | אֵת object marker | Aramaic יָת |
| `H3068G` | 13,052 | **יהוה, the divine name** | שָׁלוֹם — *"béke; teljesség"* |
| `H5921A` | 11,526 | עַל | Aramaic עֵלָּא |
| `H1121A` | 6,106 | בֵּן "son" | Aramaic בַּר |
| `H3478` | 5,016 | **יִשְׂרָאֵל** | יְשֻׁרוּן "Jesurún" |
| `H0834A` | 4,935 | אֲשֶׁר | כַּאֲשֶׁר "amint" |
| `H0376G` | 2,096 | אִישׁ "man" | אִישׁ־טוֹב "Ís-Tób" |

### 7.3 What was fixed

1. **`HebrewLexiconEntry`** gained `identity_strong_ids`, `reference_strong_ids`
   and `claims_strong_id()`. `strong_ids` is unchanged for coverage audits.
2. **`import_tbesh_lexicon()`** is now two-pass: identity keys first, then
   uStrong-only keys as a last resort that can never overwrite a genuine record.
   *Future builds cannot reproduce the defect.*
3. **`HebrewLexiconRepository.lookup()`** returns
   `resolution_type="cross_reference"` when the stored row does not claim the
   requested id — needed because the **shipped database still contains the
   1,056 hijacked rows** and cannot be rebuilt without the TBESH source TSV.
4. **`HebrewHungarianLexiconRepository.lookup()`** accepts `expected_lemma` (the
   UI passes the token's TAHOT lemma) and warns when the record describes a
   different word. This covers all 299 contaminated records without rewriting
   them.
5. **`scripts/audit_hebrew_lexicon_lemma_consistency.py`** enumerates the
   remaining damage for Phase 2B.

### 7.4 אֲשֶׁר specifically

STEPBible's own glosses for the 4,805 `HTr` (relative particle) tokens:

```
which 2569 · who 684 · that 618 · whom 303 · where 209 · [that] which 165 · when 49
```

"when" is **1.0%**. The record now reads:

| | Before | After |
|---|---|---|
| lemma | כַּאֲשֶׁר | אֲשֶׁר |
| transliteration | ka.a.sher | a.sher |
| base_meaning_hu | **amint** | **aki, amely, ami** |
| possible_meanings_hu | amint, ahogyan, amikor | aki, amely, ami, amit, ahol, amikor |
| translation_method | ai_assisted | human |

The contextual renderings are retained as *possibilities*, never as the base
meaning, and `lexical_note_hu` now states explicitly that temporal/local
readings come from sentence structure or from the compounds
בַּאֲשֶׁר / כַּאֲשֶׁר / מֵאֲשֶׁר — the lexical/contextual distinction the
target architecture requires.

`review_status` remains `draft`: this is an evidence-grounded editorial
correction, **not** expert sign-off.

A plain `H0834` record was **not** added — no corpus token uses that id.

---

## 8. AI boundary change

`_format_hebrew_token_line()` previously emitted:

```
[1] וַ/יֹּ֥אמֶר | lemma: אָמַר | morf: Hc/Vqw3ms (Conjunction + Verb) | Strong: H9002+H0559
```

It computed stem, conjugation, person, gender, number and state — then threw
them away, forcing the model to re-parse Hebrew grammar Textus already knew, and
leaking an **English** part of speech into a Hungarian prompt. Now:

```
[2] קַח\־ | lemma: לָקַח | szófaj: ige | igetörzs: qal | igealak: imperativus |
    személy: második személy | nem: hímnem | szám: egyes szám |
    Strong: H3947G+H9014 | morf-kód: HVqv2ms
```

Stem and conjugation are supplied as **separate labelled dimensions**, ketiv/qere
is included when they differ, and a token whose morphology is not fully resolved
carries an explicit `megbízhatóság:` marker so the model is told what is
uncertain. The raw code is retained only for traceability. The exegesis prompt
reuses the same block and inherits the improvement.

**Not changed:** `_format_greek_token_line()` still emits the old shape. Greek is
out of Phase 2A scope; it should get the same treatment in Phase 2B.

---

## 9. Confidence / unresolved behaviour

`_status()` previously returned `fully_decoded` whenever the code began with a
known language letter *or* a TEHMC expansion string happened to exist —
regardless of whether anything was actually decoded. Full confidence now requires
that the **verified** tables produced grammatical content, so:

* an unknown code cannot be `fully_decoded`;
* an expansion string alone cannot upgrade a code the decoder cannot parse;
* an unverified stem yields `partially_decoded` with an explicit
  `verb-stem:X` marker.

---

## 10. Database pruning

Verified and **documented, not redesigned** (per scope). `scripts/prune_tahot_runtime_db.py`
removes `token_components`, `lexicon_entries`, `strong_aliases`, and the
`raw_fields_json` / `expanded_strong_tags` / `source_token_id` columns, so at
runtime prefix/suffix surfaces are empty, every component carries the *composite*
morphology code, and component glosses are lost — exactly the data Phase 2B/2C
needs for compound constructions.

The loss is **recoverable**: pruning truncates only the output, and
`hebrew_parser._build_components()` reconstructs all of it from the four official
TAHOT TSVs. The script's docstring now carries an explicit rebuild contract
(obtain sources → `build_hebrew_prototype_db.py` → prune only the committed
display copy). **No production database was modified in this phase**; both files
are byte-identical in size (96,555,008 and 14,041,088 bytes).

---

## 11. Tests

**Added** — `tests/test_hebrew_morphology_corpus.py` (42) and
`tests/test_hebrew_lexicon_identity.py` (12), covering imperative decoding,
cohortative disambiguation, stem/conjugation separation across every verified
form code, the unresolved/confidence contract, preposition+article, the root/core
terminology rule, uStrong-vs-identity, the אֲשֶׁר base meaning, lemma-mismatch
warnings, and decoded morphology surviving into the prompt. Corpus-dependent
tests skip cleanly when the database is absent. **No test calls an LLM.**

**Corrected** (each asserted a defect as correct behaviour):

| Test | Was asserting | Now |
|---|---|---|
| `test_hebrew_morphology_hu.py::test_formats_common_verbal_stems_and_forms` | `HVqv3ms → weqatal` (impossible: `v` is always 2nd person) and `HVqm2ms → imperativus` (`m` never occurs) | real codes `HVqq3ms`, `HVqv2ms`, `HVqc1cs` |
| `test_hebrew_morphology_hu.py::test_common_former_partial_patterns_are_fully_hungarian` | unverified stems are `fully_decoded` | those four are `partially_decoded`; Hungarian still leak-free |
| `test_hebrew_morphology.py::test_decodes_common_stems_and_nonverbs` | `D/u/M` → Nithpael/Hitpael/Hitpaal | unresolved with `verb-stem:` marker |
| `test_hebrew_repositories.py::test_demo_view_model_receives_full_decoded_morphology` | `role_label == "lexikai mag"` | `"alapszó"` |
| `test_hebrew_lexicon_translation_workflow.py::test_priority_flags_proper_name_hebrew_and_aramaic` | an Aramaic record appears — only possible via the hijack, since the fixture is Ruth+Psalms, **178 tokens, all Hebrew** | asserts no Aramaic record |
| `test_original_language_token_block.py` / `test_exegesis_original_language_grounding.py` | `"morf:"` | **strengthened** to require `igetörzs:`, `igealak:`, `személy:` and `morf-kód:` |

### Results

```
Hebrew / original-language suite:   207 passed, 18 failed, 5 skipped
Pristine HEAD baseline (same set):  148 passed, 18 failed, 5 skipped
```

**All 18 failures are pre-existing and identical to the baseline**, verified by
running the same tests in a throwaway `git worktree` at `f1ec60e`. They are
missing untracked artifacts, not logic errors:

* 13 × `test_hebrew_lexicon_translation_workflow.py` — read
  `data/hebrew_translation_batches/*.json`, a directory that **has never existed
  in git history**;
* 4 × `test_hebrew_lexicon_hu.py` — read `data/generated/hebrew_*_audit.json`;
* 1 × `test_original_language_concordance.py`.

**Zero new failures.** Fixing this artifact dependency remains a Phase 2B
prerequisite so the suite can go green on a clean clone.

---

## 12. Remaining risks

1. **The shipped TBESH database still contains 1,056 hijacked keys.** The
   importer is fixed but the artifact cannot be rebuilt without the source TSV.
   Mitigated at runtime by the cross-reference guard and lemma-mismatch warning.
2. **299 Hungarian records still describe the wrong word** (134,232 tokens),
   including the divine name. They are now *flagged*, not corrected.
3. **7 stem codes remain unnamed** until TEHMC is obtained (181 tokens).
4. **No Hebrew root exists**; "gyök" cannot be delivered without a new source.
5. Greek still discards decoded morphology at the AI boundary.
6. The Hebrew suite cannot go green on a clean clone (pre-existing).
7. Deployment size is unchanged, so the 96.5 MB / 100 MB constraint from the
   audit still blocks Phase 2C.

---

## 13. Readiness criteria for Phase 2B

Phase 2B (normalize the store; restore per-component fidelity) may start when:

1. ✅ Morphology decoding is corpus-verified and validated in CI.
2. ✅ Stem and conjugation are separate normalized fields.
3. ✅ Unverified codes cannot present as fully resolved.
4. ✅ Decoded grammar reaches the AI instead of raw codes.
5. ✅ The Strong-id identity/cross-reference distinction is enforced at import.
6. ⬜ **TEHMC obtained and committed**, closing the 7 unresolved stems.
7. ⬜ **TBESH source obtained** so the lexicon database can be rebuilt without
   hijacked keys — this is the blocker for the 299 contaminated records.
8. ⬜ Test artifact dependency removed so the suite is green on a clean clone.
9. ⬜ A root source (OSHB/MorphHB or MACULA) selected for `gyök`.

Items 6–8 are all "obtain a small CC BY file and re-run an existing script"; none
requires new architecture.

---

## 14. Files changed

**Production code**
`bible_engine/hebrew_morphology.py` · `hebrew_morphology_hu.py` ·
`hebrew_lexicon_hu.py` · `hebrew_lexicon_repository.py` · `tbesh_parser.py` ·
`hebrew_sqlite.py` · `original_language_analysis.py` · `hebrew_text_demo.py`

**Data** `bible_engine/data/hebrew_lexicon_hu.json` (one record: H0834A)

**Scripts** `scripts/validate_hebrew_morphology.py` (new) ·
`scripts/audit_hebrew_lexicon_lemma_consistency.py` (new) ·
`scripts/prune_tahot_runtime_db.py` (docstring only)

**Tests** `tests/test_hebrew_morphology_corpus.py` (new) ·
`tests/test_hebrew_lexicon_identity.py` (new) · plus the six corrected files
listed in §11

**Unchanged:** every generated database, all prompts, the UI layout, dependencies.
