# Hebrew Analysis v2 — Phase 2B: Authoritative Data Rebuild and Baseline Hardening

**Scope:** replace corpus-inferred/contaminated data with authoritative STEPBible
source data; rebuild the deterministic Hebrew lexical/morphological layer;
leave a trustworthy, honest clean-test baseline. No MACULA, no syntax, no UI
changes, no new AI interpretation.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base:** `f1ec60e`
**Prior phases:** [`hebrew_analysis_v2_inventory.md`](hebrew_analysis_v2_inventory.md) (audit) ·
[`hebrew_analysis_v2_phase2a.md`](hebrew_analysis_v2_phase2a.md) (corpus-inferred corrections)

---

## 1. Authoritative STEPBible sources obtained

Phase 2A could not authoritatively verify TEHMC because the source file was
absent from the repository. This phase explicitly permitted external
acquisition; both required files were fetched and vendored.

| | TEHMC | TBESH |
|---|---|---|
| Upstream repository | `STEPBible/STEPBible-Data` | `STEPBible/STEPBible-Data` |
| Upstream path | `Morphology codes/TEHMC - Translators Expansion of Hebrew Morphology Codes - STEPBible.org CC BY.txt` | `Lexicons/TBESH - Translators Brief lexicon of Extended Strongs for Hebrew - STEPBible.org CC BY.txt` |
| Upstream commit | `ea47bd4c7eab7375f2dca07086ccc356e95a4128` | `ea47bd4c7eab7375f2dca07086ccc356e95a4128` |
| Retrieved | 2026-09-08 | 2026-09-08 |
| Vendored at | `data/stepbible_sources/TEHMC.txt` | `data/stepbible_sources/TBESH.txt` |
| Size | 394,580 bytes | 3,288,045 bytes |
| SHA-256 | `78779bea824b31d4467dec0161d547481c86f266bc39def12cd11dc7dcbe6da7` | `464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591` |
| Licence | CC BY 4.0 | CC BY 4.0 |
| Attribution | "Data created by www.STEPBible.org based on work at Tyndale House Cambridge (CC BY 4.0)" | Same; TBESH's own header additionally notes: "based on Abridged BDB by Online Bible, ... provided for guidance only" |

**Strategy chosen: vendor (option A), not a fetch script.** Both files are
small (3.6 MB combined), so committing them keeps clean-clone rebuilds
reproducible with **no network access at production runtime or at test time**
— every script in this phase (`parse_tehmc.py`,
`compare_morphology_against_tehmc.py`, `rebuild_tbesh_lexicon.py`) reads only
the vendored copy and verifies its checksum before use.

**Files not yet obtained:** the four TAHOT source TSVs (`Gen-Deu`, `Jos-Est`,
`Job-Sng`, `Isa-Mal`) were not fetched in this phase — they were not required
for either the morphology-code verification (done against the *shipped*
TAHOT-derived corpus + TEHMC) or the TBESH rebuild (done directly from the
vendored TBESH source, independent of TAHOT). `scripts/build_hebrew_prototype_db.py`
remains the path to a full TAHOT+TBESH rebuild once those four files are
vendored too; see §12 readiness.

---

## 2. TEHMC authoritative validation

`scripts/parse_tehmc.py` parses both the BRIEF lexical and FULL morphology
sections of TEHMC into a structured `{code: TehmcEntry}` table (921 entries:
670 Verb, 84 Noun, 80 Adjective, 40 Suffix, 22 Pronoun, 16 Particle, 4
Preposition, 3 Conjunction, 2 Adverb). `scripts/compare_morphology_against_tehmc.py`
then splits every one of the 734 distinct code segments occurring in the
shipped 305,635-token corpus and cross-checks each against this table.

### 2.1 Corrections confirmed and applied

| Finding | Before | After | Tokens | Authority |
|---|---|---|---|---|
| Verb stems are **language-dependent** | one flat `STEMS` dict applied Hebrew names to Aramaic tokens | `STEMS_BY_LANGUAGE` — Hebrew and Aramaic tables kept separate | **939 Aramaic tokens** across letters `q,h,p,P,u,v` | TEHMC full codes (e.g. `AVqp3ms` → Peal, `HVqp3ms` → Qal) |
| Particle `Tc` | "Conjunction" | "Conditional" | 6,047 | TEHMC `HTc`/`ATc`; corroborated by corpus glosses "that"/"for" (כִּי, דִּי) |
| Particle `Tm` | "Interrogative" | "Demonstrative" | 2,664 | TEHMC `HTm`/`ATm`; corroborated by corpus glosses "these"/"this" (אֵלֶּה, זֶה, זֹאת) |
| Suffix `Sn` | "Emphatic" | "Paragogic Nun" | 309 | TEHMC `Sn` |
| Suffix `Sh` | unmapped (silently empty, still `fully_decoded`) | "Paragogic Hé" | 407 | TEHMC `Sh` |
| Preposition `Rd` | Phase 2A ad hoc "With article" | TEHMC's own term "Definite" | 12,176 | TEHMC `HRd`/`ARd` |
| Stem `D` (Hebrew) | Phase 2A: unresolved | **Nithpael** | 3 | TEHMC `HVDp3ms` etc. |
| Stem `M` (Aramaic) | Phase 2A: unresolved | **Hitpaal** | 30 | TEHMC `AVMi3fs` etc. |
| Stem `Q` (Aramaic) | Phase 2A: unresolved | **Peil** | 65 | TEHMC `AVQp3ms` etc. |
| Stem `e` (Aramaic) | Phase 2A: unresolved (pre-2A wrongly "Peal") | **Shaphel** | 15 | TEHMC `AVecc` etc.; confirms Phase 2A's corpus-based rejection of "Peal" |
| Stem `a` (Aramaic) | Phase 2A: unresolved | **Aphel** | 4 | TEHMC `AVacc` etc. |
| Stem `i` (Aramaic) | Phase 2A: unresolved | **Hitpeel** | 3 | TEHMC `AVip3fs` etc. |
| Stem `u` | Phase 2A: unresolved (all 61 tokens) | **language-dependent**: Aramaic → Hitpael, Hebrew → Hothpaal | 53 Aramaic / 8 Hebrew | TEHMC `AVucc` (Hitpael) vs `HVucc` (Hothpaal) — genuinely different binyanim, not a spelling variant |

**All seven Phase 2A `UNVERIFIED_STEM_CODES` are now authoritatively
resolved** (`AUTHORITATIVELY_RESOLVED`). `UNVERIFIED_STEM_CODES` is now the
empty frozenset — kept in the code only as a place a future genuinely
unnameable code could land.

### 2.2 Confirmed correct, no change needed

Every remaining verified-in-2A code checks out against TEHMC exactly:
`v`→Imperative, `c`+person→Cohortative (TEHMC models this as Imperfect +
Mood=Cohortative; kept as a distinct top-level Form name — see §2.4), `q`→
Consecutive Perfect, `w`→Consecutive Imperfect, `j`→Jussive, `u`(form)→
Conjunction Imperfect, all seven Hebrew stems Phase 2A had already verified
from the corpus (Qal, Niphal, Piel, Pual, Hiphil, Hophal, Hithpael,
Hishtaphel, Tiphil).

### 2.3 Two documented TEHMC-internal inconsistencies (not decoder bugs)

Per this phase's instruction to document rather than silently resolve a
source-version mismatch:

1. **`AVvi3mp`** (2 tokens, lemma-bearing form of Hishtaphel/Ishtaphel):
   TEHMC's own entry gives `Form=Perfect`, but every other `i`-form code in
   the 670-entry verb table is `Imperfect`, and the corpus gloss ("they will
   be finished") is future-tense, matching Imperfect. Kept as **Imperfect**.
2. **`AVPp3ms` / `AVPp3mp` / `AVPj3mp`** (4 tokens): TEHMC labels these
   `Stem=Pual`, contradicting its own `AVPi3ms`/`AVPi3mp` = `Stem=Hitpeel` for
   the identical letter combination. All five tokens share the diagnostic
   ת-infixed Hitpeel/Hitpaal surface pattern (אֶשְׁתַּ.../יִשְׁתַּ...) and
   passive/reflexive glosses ("it was changed", "they took counsel
   together"). Kept as **Hitpeel**, matching the majority TEHMC reading and
   the corpus evidence.

Both are allow-listed by name in `compare_morphology_against_tehmc.py` so a
genuinely new discrepancy cannot silently hide behind them.

### 2.4 A deliberate, TEHMC-verified modeling choice (not a disagreement)

TEHMC internally represents Jussive, Cohortative, and Conjunction-Imperfect as
`Form=Imperfect` plus a separate `Mood=` sub-field, not as distinct top-level
Forms. This decoder promotes them to distinct Form **names**
(`"Jussive"`, `"Cohortative"`, `"Conjunction Imperfect"`) to match how
traditional Hebrew grammar — and the Hungarian terms `jussivus`/`cohortativus`
already used throughout this codebase — treat them as their own paradigms.
This was verified against TEHMC's own `Mood=` field per code (not asserted):
`j` is *always* `Mood=Jussive`; `c`+person is *always* `Mood=Cohortative`;
plain `i` carries `Mood=Indicative/jussive` or `Indicative/cohortative`
**ambiguously** (TEHMC's own documented category for forms it cannot itself
disambiguate) — so `i` is correctly left as plain "Imperfect" rather than
guessing a mood TEHMC itself declines to commit to.

### 2.5 Corpus validation after authoritative rebuild

```
unique morphology codes  : 3081        tokens : 305635
status by code            : {'fully_decoded': 3080, 'malformed': 1}
status by token            : {'fully_decoded': 305621, 'malformed': 14}

Consecutive Imperfect   14978   persons={Third:13965, First:700, Second:313}
Perfect                 14791   persons={Third:10878, First:2343, Second:1570}
Imperfect               13471   persons={Third:8680, First:1974, Second:2817}
Participle               8419   persons={<none>:8419}
Infinitive Construct     6758   persons={<none>:6758}
Consecutive Perfect      6344   persons={Third:3666, Second:1555, First:1123}
Imperative                4305   persons={Second:4305}
Passive Participle       1280   persons={<none>:1280}
Jussive                  1099   persons={Third:532, Second:557, First:10}
Conjunction Imperfect      999   persons={Third:648, First:280, Second:71}
Infinitive Absolute        749   persons={<none>:749}
Cohortative                534   persons={First:534}

unresolved parts        : {'empty': 14}     (pre-existing empty codes, unrelated)
unverified stem codes   : []
No problems detected.
```

**181 partially-decoded tokens → 0.** The only shortfall left is the 14
pre-existing empty morphology codes (unrelated to stems/forms). Compared to
the Phase 2A baseline (`fully_decoded: 305440, partially_decoded: 181`), this
is a complete closure: `fully_decoded: 305621, partially_decoded: 0`.

### 2.6 No dead mappings, both directions

`STEMS_BY_LANGUAGE` now contains exactly the stem letters attested by the
corpus, per language, with one deliberate exception: Hebrew `O` (Polal) is
TEHMC-defined but unattested in this particular TAHOT edition — reported
separately as "TEHMC-verified but locally unattested," not as a dead mapping,
since (unlike Phase 2A's dead mappings) it is not a guess.

---

## 3. Hand-maintained morphology drift removed

Per the instruction "prefer TEHMC-generated/validated data over a
developer-maintained interpretation table": `STEMS_BY_LANGUAGE`,
`VERB_FORMS`, `PARTICLE_FORMS`, and `SUFFIX_TYPES` in
`bible_engine/hebrew_morphology.py` are now **line-by-line derived from and
verified against** the vendored TEHMC table (`scripts/compare_morphology_against_tehmc.py`
is the derivation record — rerun it after any future TEHMC version bump).

**Not switched to runtime TEHMC parsing**, deliberately: the production
decoder (`decode_hebrew_morphology`) still uses a compact, committed Python
dict, not a 921-entry file parsed on every request. This keeps the runtime
path fast, dependency-free, and independent of the vendored file's exact
on-disk format — the same "compact generated mapping committed with tests"
approach the task explicitly permits, now backed by a verification script
instead of guesswork.

```
TEHMC source (vendored, data/stepbible_sources/TEHMC.txt)
    ↓  scripts/parse_tehmc.py (structured extraction)
    ↓  scripts/compare_morphology_against_tehmc.py (derivation + verification)
STEMS_BY_LANGUAGE / VERB_FORMS / PARTICLE_FORMS / SUFFIX_TYPES
    (committed Python dicts in bible_engine/hebrew_morphology.py)
    ↓  decode_hebrew_morphology() — pure, fast, no I/O
HebrewMorphology
```

---

## 4. TBESH lexicon rebuilt from the authoritative source

### 4.1 Root cause, restated precisely

Phase 2A's `hebrew_sqlite.import_tbesh_lexicon()` fix (two-pass, identity
before reference) was already correct. What Phase 2A could not do is rebuild
the *data* — the shipped `tbesh_lexicon_runtime.sqlite3` still contained the
1,056 keys hijacked by the pre-fix single-pass `INSERT OR REPLACE` importer.
Phase 2B obtained the authoritative TBESH source and ran the fixed importer
against it for the first time.

### 4.2 Rebuild statistics

```
$ python scripts/rebuild_tbesh_lexicon.py --apply
source checksum OK: 464dccadd95fd8620dd05fa0d7a4caba58ec3c4d5db3ebf38e43d046ca25b591
total insert operations  : 14868
distinct final keys      : 12521
hijacked (cross-ref) keys: 0
corpus Strong ids checked : 11450
lemma mismatches vs corpus: 102     (0.89% — see §4.4)
```

`tbesh_lexicon_runtime.sqlite3`: **14,041,088 → 13,447,168 bytes** (−594 KB;
same 12,521 keys, corrected content). Verified byte-for-byte reproducible:
rebuilding independently into a temp path and diffing against the applied
production file shows identical rows.

### 4.3 Regression anchors verified end to end

| Strong id | Before (hijacked) | After (rebuilt) |
|---|---|---|
| `H0834A` | כַּאֲשֶׁר "as which" (the compound overwrote the particle) | **אֲשֶׁר** "which" |
| `H0834D` | (this compound's own row had been overwritten by the above) | **כַּאֲשֶׁר** "as which" — its own separate identity |
| `H3068G` | שָׁלוֹם "peace" | **יְהֹוָה** "LORD" |
| `H0853` | יָת (Aramaic, 21,890 tokens affected — the largest single instance) | **אֵת** "[Obj.]" |
| `H3487` | (had been overwritten by the row above) | **יָת** "whom" — its own separate identity |
| `H3478` | יְשֻׁרוּן "Jeshurun" | **יִשְׂרָאֵל** "Israel" |
| `H3484` | (had been overwritten by the row above) | **יְשֻׁרוּן** "Jeshurun" — its own separate identity |

All confirmed `resolution_type == "direct"` with zero cross-reference keys
remaining anywhere in the database (`test_tbesh_rebuild_has_zero_cross_reference_keys`).

### 4.4 Residual: 102 TBESH lemma mismatches unrelated to the hijack

The rebuild script's built-in corpus cross-check (§4.2) finds 102 remaining
disagreements between TBESH's `hebrew` field and the TAHOT corpus lemma, out
of 11,450 Strong ids checked (0.89%). Sampled and categorized:

- **Multi-form corpus lemma fields**: TAHOT sometimes concatenates alternate
  spellings in one lemma field (e.g. `H0589` corpus lemma
  `"אֲנִי, אָֽנֹכִ֫י"`, TBESH `"אֲנִי"` alone) — a lemma-field convention
  difference, not a wrong identity.
- **Compound/place-name records** (`H0935H`/`H0935O`, `H1769H`/`H1769I`):
  TBESH records the fuller construct form; TAHOT's corpus lemma sometimes
  points at the base verb/noun instead.
- **A small number of genuinely separate mismatches** (e.g. `H1419A`/`H1419K`
  "great" vs. corpus "heap") not explained by the hijack mechanism and not
  investigated further in this phase — out of scope per the instruction not
  to hand-patch every remaining edge case; flagged for Phase 2C.

This is a different, much smaller defect class than the 1,056-key hijack
(now fully closed) and does not block Phase 2B's acceptance criteria, which
target the hijack specifically.

---

## 5. Hungarian lexicon contamination — targeted remediation, not a full rewrite

### 5.1 Why rebuilding TBESH did not fix the Hungarian JSON

`bible_engine/data/hebrew_lexicon_hu.json` was generated by an **offline** AI
translation pass over the *old, hijacked* TBESH database. Fixing the
database does not retroactively fix the already-materialized Hungarian text —
it was translated once and committed as static JSON.

### 5.2 Targeted identification, not a full 6,493-entry regeneration

`scripts/remediate_hungarian_lexicon_contamination.py` compares every
Hungarian record's `lemma` against the TBESH `hebrew` field for the same
Strong id, **before and after** the rebuild:

```
hungarian entries scanned      : 6493
traced to the TBESH hijack     : 443
```

A record is flagged **only** when its stored `lemma` matches the *old*
(contaminated) TBESH value and the *new* value differs — i.e. only when it is
demonstrably attributable to the hijack, not merely "different from the
corpus for some other reason."

### 5.3 SOURCE_CORRECTED vs HUMAN_REVIEWED — kept distinct, as required

Each of the 443 flagged records gained one new entry in its existing
`warnings` array: `"source_corrected_pending_retranslation"`. **Nothing else
was changed** — `lemma`, `base_meaning_hu`, `possible_meanings_hu`,
`translation_method` (`"ai_assisted"`), and `review_status` (`"draft"`) are
all left exactly as they were.

This was a deliberate choice, not an oversight:

- **`lemma` was left uncorrected on purpose.** "Fixing" only the lemma field
  to match the corpus (without re-translating the meaning) would have made a
  still-wrong record *look* consistent, silencing the very guard that
  protects against it (§5.4) — the opposite of the goal.
- **`translation_method` stays `"ai_assisted"`, never promoted to
  `"human"`.** Only `H0834A` (an actual, individually verified Phase 2A
  correction) carries `translation_method: "human"`. The task's explicit
  instruction — *"do NOT mark AI-assisted Hungarian lexicon entries as
  expert-reviewed merely because their English source is now correct"* — is
  satisfied by construction: the flagging script only ever *appends a
  warning*, never touches `translation_method` or `review_status`.

### 5.4 The safety net was already complete — verified, not assumed

Before writing a single flag, the Phase 2A runtime guard
(`HebrewHungarianLexiconRepository.lookup(expected_lemma=...)`) was checked
against **all 299** corpus-relevant lemma mismatches still present after the
TBESH rebuild (not just the 443 hijack-traced ones): **0 uncovered**. The
guard compares the record's lemma against the token's actual corpus lemma at
lookup time, so it fires regardless of *why* they disagree. This means the
task's "at minimum" bar — *the affected entries must no longer silently serve
known-wrong lexical meanings* — was already met for all 299 before the bulk
flag was even applied; the flag adds transparent, inspectable provenance
tracking on top of an already-functioning safety net, not a replacement for
it.

```
corpus-relevant lemma mismatches (unchanged by TBESH rebuild): 299
covered by the Phase 2A runtime guard:                         299 / 299
of those, traced to the TBESH hijack and flagged:               279 / 299
remainder (grammar-marker pseudo-lemmas, multi-form lemma
  fields, or genuinely separate pre-existing issues):            20 / 299
```

The 20-record remainder was inspected individually: most (`H9030`–`H9039`)
are STEPBible grammar-marker pseudo-Strongs where the *corpus* lemma field is
itself a code (`"Os1c"`, `"Os3m"`) rather than real orthography — a false
positive of the comparison method, not a lexical error — plus a handful of
genuinely separate, low-frequency mismatches unrelated to the hijack,
deferred to Phase 2C rather than hand-patched here.

### 5.5 No live LLM calls

Every step above is deterministic: JSON diffing, SQLite comparison, string
matching. No translation was regenerated by calling a model. Actual
retranslation of the 443 flagged records remains a separate, future,
offline-pipeline task (`hebrew_lexicon_translation_workflow.py` — the
existing batch export/import machinery, unchanged), explicitly out of this
phase's scope.

---

## 6. אֲשֶׁר verified end to end (both records, separately)

| | Resolution | Hebrew | Lemma match |
|---|---|---|---|
| `H0834A` (plain relative particle) | `direct` | אֲשֶׁר | ✔ matches the corpus lemma for all 4,935 relative-particle tokens |
| `H0834D` (the compound כַּאֲשֶׁר) | `direct` | כַּאֲשֶׁר | its own, separate, no-longer-overwritten identity |

The Hungarian record for `H0834A` (corrected by hand in Phase 2A, re-verified
here) reads *"aki, amely, ami"* as the base meaning — the relative function —
with the temporal/comparative renderings (*"amikor", "amint"*, from
STEPBible's 49-of-4,805 "when" gloss share) demoted to `possible_meanings_hu`
and never presented as the base meaning. `H0834D` is a genuinely different
lexeme (the compound) and is not conflated with it.

---

## 7. Root source — confirmed absent from both obtained sources

Neither authoritative file contains a Hebrew triliteral-root field:

- **TEHMC**: zero matches for "root" anywhere in the file — it is purely a
  morphology-code expansion table (Function/Stem/Form/Person/Gender/
  Number/State), with no lexical content at all.
- **TBESH**: "root" appears only inside English *gloss text*, as an ordinary
  dictionary sense (e.g. שֹׁרֶשׁ *she.resh* "root [of a tree]"), never as a
  structured field cross-referencing a word to its own consonantal root.
  TBESH's schema is `eStrong / dStrong / uStrong / Hebrew / Transliteration /
  Morph / Gloss / Meaning` — no root column.

**Conclusion — unchanged from Phase 2A, now confirmed against the actual
authoritative sources rather than inferred from their absence:** a reliable
Hebrew root is not available from any STEPBible dataset currently obtained.
`HebrewAnalysisBundle.root` must wait for **OSHB/MorphHB or MACULA** in a
later, syntax-oriented phase. It continues to be correct that `"core"` is
**not** renamed to `"gyök"` — that would still be a linguistic error, since
"core" names the lexeme-bearing surface component, not the triliteral root.
No heuristic root derivation was implemented, per instruction.

---

## 8. Deterministic rebuild / reproducibility

`scripts/rebuild_tbesh_lexicon.py` is the authoritative, checksummed,
network-free rebuild path for the TBESH database:

- **Fails clearly** when the source is missing (exit 2) or its checksum does
  not match the recorded value (exit 3), rather than silently building from
  an unverified file.
- **Validates zero hijacked keys** after every build (exit 1 if any are
  found — impossible by construction with the two-pass importer, but checked
  so a future importer regression cannot silently reintroduce the defect).
- **Reports** insert counts, distinct final key counts, and — when the TAHOT
  corpus is present — a full lemma-mismatch cross-check against it.
- **Dry-run by default**; `--apply` is required to touch the production path.

`scripts/prune_tahot_runtime_db.py`'s Phase 2A rebuild-contract docstring
(documenting how the TAHOT/morphology side can be regenerated from the four
official source TSVs once vendored) is unchanged and still accurate.

---

## 9. Pre-existing test baseline — fixed, not hidden

Phase 2A proved 18 failures were pre-existing (identical at pristine
`f1ec60e`), caused by untracked development-time artifacts. Phase 2B
resolves all 18, using three different strategies depending on what each
test was actually able to verify:

### 9.1 Rewritten against currently-committed data (5 tests, now pass)

`test_hebrew_lexicon_hu.py`'s four failures and
`test_hebrew_lexicon_translation_workflow.py`'s
`test_english_sentence_detector_accepts_current_pilot_hungarian_notes` all
turned out to check facts **fully derivable from the already-committed**
`hebrew_lexicon_hu.json` / `hebrew_strong_aliases.json` — the missing files
were intermediate historical snapshots of already-shipped data, not the only
evidence for it. Every specific claim (particular Strong ids resolving
directly, particular Hungarian meanings, the `H0430J→H0430G` alias, language
counts) was individually re-verified against current committed state before
rewriting — nothing was invented. `test_all_imported_pilot_records_are_runtime_direct_hits`
is now *stronger* than the original (checks all 6,493 production records,
not one 100-record historical sample).

### 9.2 Explicit, individually-reasoned skips (13 tests)

Two categories of test read files that are **genuinely not reconstructible**
from current state without either fabricating data or making a live LLM
call:

- **12 tests** in `test_hebrew_lexicon_translation_workflow.py` read
  `data/hebrew_translation_batches/hebrew_lexicon_batch_000{1..5}.json` (and
  `_hu.json` variants) — point-in-time process journals from the one-time
  historical campaign that built the production lexicon. Re-running the
  exporter today would not reproduce the same "batch N excludes batch N−1"
  narrative, because production is now essentially complete (6,493 of
  TBESH's ~12,500 entries) — a fresh export would just report today's much
  smaller residual, not replay history. Regenerating synthetic batches to
  force a green run would fabricate a record that never existed, which is
  worse than an honest skip. `requires_historical_batch_artifacts` documents
  exactly this reasoning at the point of definition (not a blanket
  file-level ignore) and is applied per-test.
- **1 test** (`test_search_original_attaches_hungarian_context_by_default`)
  requires the RÚF 2014 Hungarian Bible text, which is under a restrictive
  Hungarian Bible Society licence and is *explicitly, permanently* excluded
  from git by the project's own `.gitignore` (with its own dedicated warning
  comment) — unrelated to the Hebrew lexicon work entirely.  A
  `requires_ruf_database` skip documents this.

Neither category hides a correctness defect: in both, the skip condition is
checked at collection time (`pytest.mark.skipif`), visible in `pytest -rs`
output, and documented inline with the specific reason.

### 9.3 Result

```
Before (Phase 2A baseline, confirmed identical to pristine f1ec60e):
  148 passed, 18 failed, 5 skipped

After Phase 2B:
  226 passed, 0 failed, 18 skipped
```

A clean checkout now has **zero unexplained failures**. Every skip has a
specific, inline, individually-verified reason.

---

## 10. Tests added/changed this phase

**New:** `scripts/parse_tehmc.py`, `scripts/compare_morphology_against_tehmc.py`
(development/derivation scripts, not part of the test suite but the record of
how every §2 mapping was derived) · `scripts/rebuild_tbesh_lexicon.py` ·
`scripts/remediate_hungarian_lexicon_contamination.py`.

**Test files changed:**

- `tests/test_hebrew_morphology.py` — stem assertions updated to the
  authoritative, language-aware TEHMC mappings.
- `tests/test_hebrew_morphology_hu.py` — the four previously-"unverified"
  codes now assert `fully_decoded`.
- `tests/test_hebrew_morphology_corpus.py` — `UNVERIFIED_STEM_CODES`
  parametrized test replaced with explicit TEHMC-resolution assertions for
  each of the seven codes, plus a new language-dependence test
  (`test_stem_letters_are_language_dependent`) and a safety-mechanism test
  using a genuinely fictitious letter; preposition/confidence numbers
  updated to the new, fully-resolved corpus totals.
- `tests/test_hebrew_lexicon_identity.py` — `H0853`'s cross-reference test
  replaced with a *positive* regression anchor (it is now `"direct"`) plus a
  unit-level synthetic test proving the cross-reference *mechanism* itself
  still works; added `test_tbesh_identity_regression_anchors`
  (parametrized over all six §4.3 anchors), `test_tbesh_rebuild_has_zero_cross_reference_keys`,
  `test_source_corrected_records_are_flagged_but_not_marked_human_reviewed`,
  `test_flagged_records_still_trigger_the_lemma_mismatch_guard`.
- `tests/test_hebrew_lexicon_hu.py` — four tests rewritten per §9.1.
- `tests/test_hebrew_lexicon_translation_workflow.py` — twelve tests
  skip-marked per §9.2; one rewritten per §9.1.
- `tests/test_original_language_concordance.py` — one test skip-marked per
  §9.2.

No test in this phase calls an LLM.

---

## 11. Deployment / source size

| | Before Phase 2B | After Phase 2B | Δ |
|---|---|---|---|
| `data/generated/tahot_ot_runtime.sqlite3` (production, git-tracked) | 96,555,008 B | 96,555,008 B | unchanged |
| `data/generated/tbesh_lexicon_runtime.sqlite3` (production, git-tracked) | 14,041,088 B | 13,447,168 B | **−594,720 B** |
| `bible_engine/data/hebrew_lexicon_hu.json` (production, git-tracked) | ~5.17 MB | ~5.19 MB | +443 short warning strings |
| `data/stepbible_sources/TEHMC.txt` (new, vendored source — not yet staged) | — | 394,580 B | +0.39 MB |
| `data/stepbible_sources/TBESH.txt` (new, vendored source — not yet staged) | — | 3,288,045 B | +3.29 MB |

The 96.5 MB TAHOT database remains the binding constraint identified in the
audit (§13.9 of `hebrew_analysis_v2_inventory.md`) — untouched by this phase,
since no TAHOT rebuild occurred. The two newly vendored source files
(`data/stepbible_sources/`) are new, untracked, and were **not staged or
committed** by this phase — they are ready for the user to review and commit.
MACULA was not added; nothing else grew.

---

## 12. Remaining issues

1. **102 residual TBESH lemma mismatches** (§4.4), unrelated to the hijack —
   small, sampled, categorized, deferred to Phase 2C.
2. **443 Hungarian records flagged, not retranslated** (§5) — the safety net
   is verified complete (§5.4); actual retranslation is future offline-pipeline
   work.
3. **20 of the 299 corpus-relevant lemma mismatches are not hijack-traced**
   (§5.4) — covered by the same runtime guard, individually uninvestigated
   beyond a first-pass classification.
4. **Two documented TEHMC-internal inconsistencies** (§2.3) — resolved by
   corroborating evidence, not by TEHMC alone; allow-listed by name so a
   real future regression cannot hide behind them.
5. **No Hebrew root source** (§7) — requires OSHB/MorphHB or MACULA.
6. **The four TAHOT source TSVs were not vendored** — the TAHOT/morphology
   *text* corpus itself was not rebuilt this phase (only cross-verified
   against it); a full from-source TAHOT rebuild remains available via
   `scripts/build_hebrew_prototype_db.py` once those four files are
   obtained.
7. **Newly vendored sources are uncommitted** — `data/stepbible_sources/`
   exists on disk but was not `git add`ed by this phase.

---

## 13. Readiness for the normalized `HebrewAnalysisBundle` / MACULA phase

| Criterion (from the audit's Phase 2 recommendation) | Status |
|---|---|
| Deterministic morphology corpus-verified and TEHMC-verified | ✅ Done (§2) |
| Stem and conjugation separate normalized fields | ✅ Already true since Phase 2A; unaffected |
| Language-dependent facts modeled correctly | ✅ New this phase (§2.1) — was silently wrong before |
| Strong-id identity vs cross-reference enforced at import | ✅ Phase 2A importer + Phase 2B data rebuild (§4) |
| Lexical safety net covers all known contamination | ✅ Verified complete, not assumed (§5.4) |
| Clean-clone test baseline | ✅ Zero unexplained failures (§9.3) |
| Root source identified | ❌ Confirmed absent from TAHOT/TBESH/TEHMC; needs OSHB/MorphHB or MACULA |
| TAHOT text/morphology corpus itself rebuilt from source | ❌ Not this phase — cross-verified only |
| Deployment size headroom for a syntax layer | ❌ Unchanged; the audit's §15.3 split-store recommendation still applies |

**Recommended next phase (2C):** normalize the store (restore per-component
fidelity per the audit's §2.3 finding, adopt the split-store strategy), then
begin the offline MACULA import — with morphology and the TBESH/Hungarian
lexical layer now on a verified, honest foundation rather than an inferred
one.
