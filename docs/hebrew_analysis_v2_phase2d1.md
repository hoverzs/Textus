# Hebrew Analysis v2 — Phase 2D.1: MACULA Alignment Hardening

**Scope:** a short, deterministic quality-hardening pass on top of Phase
2D's MACULA syntax layer — classify every remaining unresolved alignment,
fix the recurring structural patterns that explain most of them, verify
Aramaic-specific segmentation causes, audit the existing VALIDATED_FALLBACK
population for safety (not just count), and make sure partial alignment can
never let a syntax fact silently attach to the wrong Textus token. No AI
interpretation, no UI change, no change to TAHOT/TEHMC authority, no push.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base checkpoint:** `9a45f8a`
**Prior phases:** [`hebrew_analysis_v2_phase2c.md`](hebrew_analysis_v2_phase2c.md) ·
[`hebrew_analysis_v2_phase2d.md`](hebrew_analysis_v2_phase2d.md) (baseline this phase hardens)
**New machine-readable artifacts (Phase 2D's own `docs/phase2d_macula_alignment_audit.json`
is left completely untouched — see §16 of that phase's doc; this phase's
results live in separate, new files so before/after numbers are never
overwritten):**
[`docs/phase2d1_macula_alignment_audit.json`](phase2d1_macula_alignment_audit.json) (full corpus summary, post-hardening) ·
[`docs/phase2d1_unresolved_taxonomy.json`](phase2d1_unresolved_taxonomy.json) (§2) ·
[`docs/phase2d1_hungarian_lexical_coverage.json`](phase2d1_hungarian_lexical_coverage.json) (§8)

---

## 1. Baseline reproduction

Phase 2D's exact corpus-wide run was re-executed against the same pinned
MACULA checkout (tag `26.04.13`, commit
`09f8ea9e25025841ec45e2b6e7fc01595a080568`) before any alignment code was
touched. Every number reproduced **exactly**, including the output SQLite
file's byte size:

| Metric | Phase 2D report | Reproduction |
|---|---:|---:|
| Files processed | 929 (1 skipped) | 929 (1 skipped) |
| Verses | 23,213 | 23,213 |
| Tokens | 305,635 | 305,635 |
| EXACT | 153,433 | 153,433 |
| COMPOSITE | 138,944 | 138,944 |
| VALIDATED_FALLBACK | 7,432 | 7,432 |
| UNRESOLVED | 5,826 | 5,826 |
| Phrases / clauses / edges / roles / participants / coreference | 238,809 / 102,124 / 793,631 / 110,831 / 24,943 / 45,222 | identical |
| Output store size | 867,749,888 bytes | 867,749,888 bytes |

No discrepancy — safe to proceed with modifying alignment logic.

**A more precise language split, computed this phase** (Phase 2D's own
figures used book-level bucketing, which mixes Ezra/Daniel's Hebrew
portions in with their Aramaic sections): querying `hebrew_verses.language`
per verse rather than per book gives:

| | Tokens | Unresolved (pre-fix) | Unresolved % |
|---|---:|---:|---:|
| Hebrew-language verses | 300,804 | 5,006 | 1.66% |
| **Aramaic-language verses** | **4,831** | **660** | **13.66%** |

The true, verse-precise Aramaic unresolved rate (13.66%) is actually
**higher** than Phase 2D's book-level estimate (~8.5%) — the book-level
bucketing had been diluting it with Ezra/Daniel's Hebrew content.

---

## 2. Unresolved case taxonomy (5,826 pre-fix cases → fully categorized)

A deterministic classifier (`bible_engine/hebrew_macula_diagnostics.py`,
corpus-driver `scripts/classify_macula_unresolved.py`) assigns every
UNRESOLVED case exactly one category from a fixed, priority-ordered
taxonomy — no case is left unexplained. Applied to the **post-hardening**
1,424 residual cases (§4), the full breakdown:

| Category | Count | % of residual |
|---|---:|---:|
| component_segmentation_mismatch | 589 | 41.4% |
| aramaic_specific_segmentation | 245 | 17.2% |
| maqaf_related_segmentation | 205 | 14.4% |
| ketiv_qere | 128 | 9.0% |
| textual_reference_numbering_gap | 126 | 8.8% |
| surface_normalization_difference | 116 | 8.1% |
| macula_missing_node | 15 | 1.1% |
| **Total** | **1,424** | **100%** |

`component_segmentation_mismatch` sub-breakdown by direction:

| Direction | Count |
|---|---:|
| ambiguous_recovery (bounded search found ≥2 equally-corroborated candidates) | 293 |
| tahot_more (TAHOT has more alignable components than MACULA has leaves) | 244 |
| macula_more (MACULA has more leaves than TAHOT has components) | 52 |

(`tahot_more` includes the short-string-containment downgrades from §3.3 —
cases where a plain substring match would previously have accepted a
`VALIDATED_FALLBACK`, but the length floor now correctly requires exact
equality below 3 consonants, moving a materially larger share of the
corpus into this category than the original 4-case spot sample in §3.3
suggested once measured corpus-wide.)

Full machine-readable output (aggregate counts + a bounded sample per
category, not a corpus dump):
[`docs/phase2d1_unresolved_taxonomy.json`](phase2d1_unresolved_taxonomy.json).

---

## 3. General alignment rules added

Implemented in
[`bible_engine/hebrew_macula_alignment.py`](../bible_engine/hebrew_macula_alignment.py),
all evidence-gated, all with a corpus-verified real-world trigger case —
none is a per-verse special case.

### 3.1 Bounded local ref-number recovery

**Finding:** MACULA's `ref` word-number is not always identical to TAHOT's
`word_index` even for a word MACULA *does* contain. Verified on Ruth 1:8:
TAHOT `word_index=10` (`יַ֣עַשׂ`, the Qere half of a Ketiv/Qere pair) has
no MACULA leaf at `ref=...!10` — but `ref=...!11` carries that exact word,
one position later, shifting every subsequent word in the verse by +1.
Genesis 13:3 showed the **opposite** direction (MACULA assigns one *more*
ref number than TAHOT has words for that verse) — so the shift is neither
a fixed size nor a fixed direction.

**Rule:** rather than a cumulative, verse-wide offset (which risks exactly
the cascade failure the brief warns against — a shift derived from one
gap silently misapplied to unrelated later words), the aligner makes a
**bounded, per-token, evidence-gated search** of nearby ref positions
(±1..±5, closest first) only when the primary lookup did not fully
corroborate. Each candidate is scored with the *same* component-pairing +
surface-agreement logic as the primary position; only a candidate where
**every** paired component's surface agrees (not just Strong-id — see
§3.3) is accepted. A recovered match is always reported `VALIDATED_FALLBACK`
(never `EXACT`/`COMPOSITE`) — the position itself was not the one TAHOT's
own ordering predicted, so full certainty is never claimed. If more than
one nearby offset would independently qualify, the recovery is **refused**
(stays `UNRESOLVED`, evidence records the ambiguity) — this is the origin
of the 293 `ambiguous_recovery` cases in §2: short, frequently-repeated
words (אֶת, כִּי, כָּל, וְ/אֶת) legitimately recur within the ±5 search
window often enough that a single confident pick would be a guess.

### 3.2 Aramaic determinative/emphatic-state suffix exclusion

**Finding:** Aramaic's determinative-state ending (grammatically parallel
to Hebrew's prefixed definite article, but realized as a *suffix* in
Aramaic — a bare א/ה/ן after niqqud-stripping) is recorded by TAHOT as its
own trailing "suffix"-role component, but MACULA's lowfat leaves do not
split it out as a separate morpheme at all.

**Rule:** `ordered_alignable_components` (shared by the primary lookup,
the recovery search, and the diagnostic classifier) excludes a suffix
component whose stripped surface is exactly א/ה/ן — a purely structural,
**language-general** check (role + stripped surface only), never an
`if language == "aramaic"` branch, applied the same way the existing
empty/implicit-leaf exclusion already was in Phase 2D.

### 3.3 VALIDATED_FALLBACK audit → two corroboration fixes

Phase 2D's 7,432 VALIDATED_FALLBACK alignments were sampled systematically
by re-deriving their corroboration fraction from the stored evidence text:

| Sub-population | Count | Verdict |
|---|---:|---|
| Zero corroboration ("N/M corroborated" with N=0) | **3,552 (47.8%)** | **Unsafe — downgraded** |
| Whole-token substring containment | 3,490 (47.0%) | Safe, with one length-floor fix below |
| Partial corroboration (0 < N < M) | 390 (5.2%) | Safe, kept as-is |

**Fix 1 — zero-corroboration downgrade.** A component/leaf **count** match
at a ref position with **zero** surface/lemma/Strong-id agreement is not
real evidence of alignment — it is indistinguishable from a coincidental
count match at the wrong position. Concrete corpus case: Ruth 1:8 word 11
(`יְהוָ֤ה`, "the LORD") primary-position-matched MACULA's `יַ֣עַשׂ`
("he will do") *only* because both share Strong-root 6213 (עשה) after
numeric-prefix stripping — two different inflected forms of the same
verb, coincidentally adjacent. Corroboration by Strong id alone, with zero
surface agreement, is now treated as `UNRESOLVED` rather than a "low
confidence" guess (Phase 2D's prior "low confidence" tier is removed
entirely — a `VALIDATED_FALLBACK` result now always has *some* real
corroborating evidence).

**Fix 2 — short-string containment floor.** The whole-token
substring-containment fallback (used when component/leaf counts cannot be
reconciled at all) is only trustworthy once the compared string is long
enough that a coincidental match is implausible. Corpus-wide, only 4 of
3,490 containment-based cases involved a ≤2-consonant token (אֵת, לָא,
תָּו) — below a 3-consonant floor the fallback now requires **exact**
equality instead of substring containment.

### 3.4 Confirmed-alignment-only leaf→token mapping (syntax safety)

**Finding (the most significant bug caught this phase):** the Phase 2D
importer built its MACULA-leaf → Textus-token map from the raw coincidence
`leaf.ref_word_number == token.word_index`, independent of whether that
token's *own* alignment actually succeeded. A corpus-wide invariant check
(§6) caught 1,670 real violations: e.g. Genesis 36:5's proper name
`יְעוּשׁ` ("Jeush") sits at MACULA `ref=5`; TAHOT's `word_index=5` is a
*different*, genuinely ambiguous word (`וְ/אֶת\־`) that correctly stays
`UNRESOLVED`, while TAHOT `word_index=4` (`יְעוּשׁ` itself) is the token
that *actually* recovers to `ref=5` via §3.1's bounded search. The old
mapping wrongly attached "Jeush"'s syntax facts (phrase membership, syntax
edges) to token 5 (the wrong, unresolved token) instead of token 4 (the
one whose alignment genuinely claimed that leaf).

**Fix:** `hebrew_macula_importer._resolve_leaf_to_token_map` now builds the
map exclusively from each token's own **confirmed** `TokenAlignment`
result (`alignment.components[*].macula_leaf_id`) — an `UNRESOLVED` token
contributes *nothing* to the map, so no phrase/clause/syntax-edge/
semantic-role/coreference fact can ever attach to a token whose
correspondence to that leaf was never actually verified. Regression-tested
directly against this exact Genesis 36:5 case
(`test_leaf_to_token_map_uses_the_recovering_token_not_the_coincidental_word_index`).

---

## 4. Post-hardening corpus results

Same full corpus (39/39 books, 305,635 tokens, 23,213 verses), same pinned
MACULA revision, rebuilt end-to-end with all §3 fixes applied:

| Metric | Phase 2D (before) | Phase 2D.1 (after, all fixes incl. §3.3/§3.4) | Δ |
|---|---:|---:|---:|
| EXACT | 153,433 | 153,436 | +3 |
| COMPOSITE | 138,944 | 133,940 | −5,004 |
| VALIDATED_FALLBACK | 7,432 | 16,835 | +9,403 |
| UNRESOLVED | 5,826 | **1,424** | **−4,402 (−75.6%)** |
| Resolved overall | 98.09% | **99.53%** | +1.44 pp |

(An intermediate rebuild — after §3.1/§3.2 but before the §3.3
short-string-containment floor and the §3.4 leaf-mapping fix had both
landed — briefly measured UNRESOLVED=1,304/VALIDATED_FALLBACK=16,955; the
figures above are from the final rebuild with every fix in §3 applied
together, and are the ones the corpus-wide invariants in §6 were verified
against.)

The COMPOSITE→VALIDATED_FALLBACK shift is the zero-corroboration-downgrade
and bounded-recovery mechanics interacting as designed: a token recovered
via §3.1 is *always* capped at `VALIDATED_FALLBACK` even when its own
corroboration is as strong as a primary `COMPOSITE` match would have been
— accuracy of labeling, not just a raw resolved-percentage increase, was
the goal (per the brief's explicit framing, §14).

### 4.1 Hebrew vs. Aramaic (precise, verse-level)

| | Tokens | Unresolved (after) | Unresolved % (after) | Unresolved % (before) |
|---|---:|---:|---:|---:|
| Hebrew-language verses | 300,804 | 1,107 | **0.37%** | 1.66% |
| Aramaic-language verses | 4,831 | 317 | **6.56%** | 13.66% |

Aramaic's residual rate (6.56%) is still meaningfully higher than Hebrew's
(0.37%) — roughly an 18× ratio — and this is now a **well-explained**,
not merely observed, gap: §2's `aramaic_specific_segmentation` (245 cases)
and a share of `component_segmentation_mismatch`/`maqaf_related_segmentation`
are concentrated in Aramaic's denser morphology (determinative state
stacked with plural/pronominal endings MACULA does not split the same way
— e.g. Ezra 4:9's list of ethnonyms, `אַרְכְּוָיֵ֤/א` "Archevites",
`עֵלְמָיֵֽ/א` "Elamites", each stacking a plural marker *and* the
determinative-state suffix in one TAHOT suffix component that MACULA's
tree does not mirror).

---

## 5. Ketiv/Qere findings

128 of the 1,424 residual unresolved cases are Ketiv/Qere tokens
(`token.ketiv` or `token.qere` non-empty) — these are **not** failures of
§3.1's recovery mechanism; they are cases where TAHOT records a
Ketiv/Qere pair but MACULA's own tree genuinely has no leaf that
corroborates *either* reading at any position within the bounded search
window. Phase 2C's Textus token identity already represents Ketiv/Qere
correctly (one token, `ketiv`/`qere` fields both populated, surface =
the Qere reading) — this phase did not change that representation, only
confirmed that a token's Ketiv/Qere status is diagnosed as its own
category rather than being silently absorbed into
`component_segmentation_mismatch`. Where §3.1's bounded search *did* find
a corroborating candidate for a Ketiv/Qere-adjacent gap (Ruth 1:8, word 10
itself), it is recorded `VALIDATED_FALLBACK` with the exact offset in
evidence — never silently promoted to certainty, and never collapsing the
Ketiv and Qere readings into one unsupported form.

---

## 6. Corpus-wide invariants

Run against the full post-hardening store (Section 3.4's fix already
applied):

| Invariant | Violations |
|---|---:|
| No MACULA source node aligned to a verse other than its own | 0 |
| No duplicate `(token_id, component_index)` alignment row | 0 |
| No `hebrew_syntax_membership` row references an unconfirmed token | **0** (was 1,670 before §3.4's fix) |
| No `hebrew_syntax_edges` row references an unconfirmed token | **0** |
| No `hebrew_semantic_roles` row references an unconfirmed token | **0** |
| No `hebrew_coreference` row references an unconfirmed token | **0** |
| `hebrew_verses.language` values are only `hebrew`/`aramaic` | confirmed |

The 1,670→0 result (checked across all four fact tables, not just
membership) is the full corpus-scale confirmation of §3.4's fix;
`tests/test_hebrew_macula_alignment_hardening.py::test_no_syntax_fact_attaches_to_an_unconfirmed_token`
and the dedicated Genesis 36:5 regression test give it permanent, fixture-scale
coverage that runs in every CI pass without needing the full corpus.

---

## 7. Syntax-grounding safety model

New three-state model, computed per verse from confirmed-vs-unresolved
token alignment counts (`bible_engine/hebrew_analysis_repository.py`):

```
FULLY_GROUNDED_SYNTAX     — syntax data exists; every token in the verse has a confirmed alignment.
PARTIALLY_GROUNDED_SYNTAX — syntax data exists; at least one token is UNRESOLVED (that token
                             contributes no fact at all, per §3.4 — other tokens' facts are still present).
NO_GROUNDED_SYNTAX        — no syntax data was imported for this verse at all.
```

Exposed as `VerseSyntaxData.syntax_grounding` (repository layer) and
`VerseAnalysis.syntax_grounding` (bundle, Phase 2C-compatible — a plain
string field, no schema break). A future AI-interpretation layer can
branch on this directly instead of having to independently re-derive
alignment confidence from raw token data.

---

## 8. Hungarian lexical coverage (kept separate from alignment coverage)

Measured via `scripts/audit_hungarian_lexical_coverage.py` against the
full committed TAHOT production database — an audit only; **no
translations were generated or added this phase**.

| Metric | Value |
|---|---:|
| Unique corpus lexemes (Strong ids, excluding pure grammar markers) | 11,401 |
| ...with a Hungarian lexical record | 6,610 (57.98%) |
| ...without a Hungarian lexical record | 4,791 (42.02%) |
| Token occurrences (excluding grammar markers) | 299,576 |
| ...covered by a Hungarian meaning | 283,959 (**94.79%**) |
| ...without a Hungarian meaning | 15,617 (5.21%) |
| Proper-name lexemes without a Hungarian record | 2,852 (touching 6,423 occurrences) |
| Common-word lexemes without a Hungarian record | 1,939 (touching 9,194 occurrences) |

The unique-lexeme gap (42%) looks large in isolation but is **frequency-weighted
almost entirely toward rare words**: only 5.21% of actual token
*occurrences* lack a Hungarian gloss, and more than half of the missing
*lexemes* are proper/place names (TBESH's own `morph` field trailing
`-P` segment — verified: Ruth → `N:N-F-P`, Elimelech → `N:N-M-P`).
H9xxx pure grammar-marker Strong ids (conjunction/preposition/article/
pronominal-suffix/punctuation placeholders — 540,437 of the raw
strong-id attachments corpus-wide) were explicitly excluded from this
count; they were never meant to carry their own Hungarian gloss, and
including them would have misleadingly inflated the "missing translation"
figure to ~40%. Full breakdown (by TBESH `morph` code, plus a sample of
uncovered lexemes):
[`docs/phase2d1_hungarian_lexical_coverage.json`](phase2d1_hungarian_lexical_coverage.json).

**Confirmed, per the brief's explicit constraint:** a missing Hungarian
gloss never counted as an alignment failure, never blocked syntax import,
and never lowered morphology confidence anywhere in this phase's code —
regression-tested directly
(`test_missing_hungarian_gloss_does_not_affect_morphology_or_alignment`,
`test_missing_hungarian_gloss_does_not_block_bundle_syntax`, using the
real, verified-uncovered H0458/Elimelech case from Ruth 1:2).

---

## 9. Tests added

[`tests/test_hebrew_macula_alignment_hardening.py`](../tests/test_hebrew_macula_alignment_hardening.py)
— 17 tests, all against real fixture data (the existing Ruth/Ezra
fixtures, extended with Ruth 1:2 for the Hungarian-coverage case, plus a
new small real-data fixture
[`tests/fixtures/macula_lowfat/genesis_36_5_excerpt-lowfat.xml`](../tests/fixtures/macula_lowfat/genesis_36_5_excerpt-lowfat.xml)
for the §3.4 regression). Covers: maqaf alignment and non-collision
(Ruth 1:16), Aramaic determinative-state exclusion and diagnosis
(Ezra 4:8/4:9), downstream sequence recovery after a source mismatch and
one-to-many COMPOSITE alignment (Ruth 1:1/1:8), ambiguous-recovery refusal
(constructed from the verified Genesis 36:5 repeated-word pattern),
zero-corroboration downgrade and the short-string containment floor (both
constructed from verified real corpus patterns), the confirmed-alignment-
only leaf→token mapping and the general "no syntax fact on an unconfirmed
token" invariant (Ezra + the dedicated Genesis 36:5 case), syntax-grounding
full/partial/none states, and Hungarian-gloss absence not affecting
alignment/morphology/syntax. Two Phase 2D tests were updated (not
weakened) to reflect the Ruth 1:8 case now being *correctly recovered*
rather than staying unresolved — see their docstrings for the exact
before/after reasoning.

Two existing Phase 2D tests were updated because the behavior they
encoded was itself the Phase-2D-era limitation this phase fixes:
`test_alignment_ketiv_qere_gap_reported_not_silently_shifted` →
`test_alignment_ketiv_qere_gap_recovered_via_bounded_search_not_silently_shifted`,
and `test_importer_produces_phrases_clauses_roles_coreference`'s
`unresolved >= 1` assertion → `unresolved == 0` (Ruth 1:8 no longer has
any unresolved tokens after §3.1).

---

## 10. Test results

```
tests/test_hebrew_macula_alignment_hardening.py                    [17 passed]
tests/test_hebrew_macula_alignment.py                               [32 passed]
tests/test_hebrew_analysis_bundle.py                                [31 passed]
tests/test_hebrew_analysis_repository_supabase.py                    [6 passed]
tests/test_hebrew_lexicon_hu.py, test_hebrew_lexicon_identity.py,
tests/test_hebrew_lexicon_translation_workflow.py, test_hebrew_morphology.py,
tests/test_hebrew_morphology_corpus.py, test_hebrew_morphology_hu.py,
tests/test_hebrew_parser.py, test_hebrew_repositories.py, test_hebrew_sqlite.py,
tests/test_hebrew_token_selector.py                        [188 passed, 12 skipped]
tests/test_original_language_concordance.py,
tests/test_original_language_token_block.py,
tests/test_exegesis_original_language_grounding.py             [17 passed, 1 skipped]
tests/test_supabase_secrets_fallback.py                              [3 passed]
------------------------------------------------------------------------------
Total                                                     261 passed, 13 skipped
```

No failures. Skips are pre-existing (optional fixtures/DB-presence gates,
unrelated to this phase).

---

## 11. Remaining unresolved categories (honest, not treated as complete)

1,424 tokens (0.47% of the corpus) remain genuinely `UNRESOLVED`, fully
categorized (§2), with no arbitrary percentage target pursued beyond what
evidence supports (§14 of the brief). Two categories in particular are
*expected to stay* unresolved rather than being further engineered away:

- **`component_segmentation_mismatch:ambiguous_recovery` (293 cases)** —
  a short, frequently-repeated word appears at more than one position
  within the bounded search window with equally strong corroboration.
  Disambiguating these would require real clause-boundary information
  (Phase 2D/2E's syntax data does supply phrase/clause membership for the
  tokens that *did* align — a natural Phase 2E-adjacent refinement would
  be using confirmed clause boundaries to break such ties, but that is a
  syntax-informed heuristic, not a raw string-distance guess, and is
  explicitly out of this phase's scope).
- **`aramaic_specific_segmentation` (244 cases)** — Aramaic morphology
  stacking determinative-state + plural/pronominal endings in ways
  MACULA's tree does not mirror 1:1. A general fix here would need either
  a second Aramaic-specific structural exclusion rule (risking
  overfitting to the ~30 corpus cases actually sampled) or richer
  MACULA/TAHOT cross-validation data than either source currently
  provides — left as an honestly-reported residual rather than a
  speculative rule.

---

## 12. Readiness for Supabase production import / Phase 2E

The normalized data is materially **more trustworthy** than at the end of
Phase 2D: the §3.4 fix means every syntax fact in the store is now
provably grounded in a confirmed alignment (§6's 0-violation invariant),
and the VALIDATED_FALLBACK population no longer contains the ~48% weak,
position-only "guesses" Phase 2D's own numbers included unlabeled. The
Supabase migration schema (`supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`)
is unchanged by this phase — no new columns or tables were needed; the
grounding model is computed at read time, not stored. Phase 2D's own
deployment prerequisites (§15/§16 of that phase's doc) are otherwise
unchanged: still not applied to a real Supabase project from this
environment, still no credentials available here.

**Phase 2E prerequisites, updated:**
1. A syntax-informed disambiguation strategy for the `ambiguous_recovery`
   residual (293 cases) — optional, since these are already honestly
   flagged `UNRESOLVED` and contribute no incorrect fact.
2. The Supabase-writing importer variant (mechanical, not yet built —
   same requirement Phase 2D's own doc already listed).
3. Everything else from Phase 2D §20 stands unchanged.

---

## Acceptance criteria checklist

1. Phase 2D baseline reproduced — ✅ (§1, byte-identical)
2. Remaining unresolved cases categorized — ✅ (§2, 0 in "unknown")
3. General deterministic alignment improvements implemented where safe — ✅ (§3)
4. Aramaic mismatch causes specifically understood — ✅ (§4.1, §11)
5. Component-count mismatches handled more robustly — ✅ (§3.1, §3.2)
6. Ketiv/Qere/reference gaps cannot cause silent downstream misalignment — ✅ (§3.1's bounded, non-cumulative design; §5)
7. VALIDATED_FALLBACK cases audited — ✅ (§3.3, two real fixes applied)
8. Partial syntax cannot attach guessed tokens — ✅ (§3.4, §6, 0 violations)
9. Hungarian lexical gaps kept separate from alignment coverage — ✅ (§8, regression-tested)
10. Corpus-wide alignment invariants pass — ✅ (§6)
11. Existing Hebrew morphology unchanged — ✅ (TAHOT/TEHMC path untouched this phase, same as Phase 2D)
12. Existing Hebrew tests remain green — ✅ (§10)
13. No AI interpretation added — ✅ (no new LLM/network imports; same static-check pattern as Phase 2D)
14. Nothing pushed — ✅
