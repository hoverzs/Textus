# Hebrew Analysis v2 — Phase 2E: Live Gemini 2.5 Flash Quality Smoke Test

**Status: DEVELOPMENT SMOKE TEST ONLY. Not an expert linguistic review.**
No Hebrew/Aramaic scholar has reviewed any output below. Scores in this
document are my (the implementing engineer's) own structural/policy
assessment against the Phase 2E grounding rules — not a linguistic
correctness certification. See
[`docs/hebrew_analysis_v2_phase2e.md`](hebrew_analysis_v2_phase2e.md) §15
for the still-unreviewed developer regression fixture framework this test
draws its verse selection from.

**Date:** 2026-09-09 · **Branch:** `claude/hebrew-analysis-v2-audit-efc152`
· **Code under test:** HEAD `b6dec7c971f2037dd138fc35b4405239f443a999`
(Phase 2E + construction-grounding verification fix) — **no code was
changed during or because of this test run.**

---

## 1. Credential and connectivity verification

- Credential-resolution path confirmed by code inspection:
  `app.py::_load_builtin_api_key()` → `os.environ["GEMINI_API_KEY"]` →
  project `.streamlit/secrets.toml` → `st.secrets`. No value was ever
  printed, logged, or written to any file by this test; only presence and
  a masked prefix (`AIzaSy***…`, the app's own existing debug-log masking)
  appeared in console output.
- The user's `secrets.toml` was found at the **main repo checkout root**
  (`C:\Users\Hover\Textus\.streamlit\secrets.toml`), not this worktree's
  own `.streamlit\` directory — worktrees don't share untracked files. The
  key was read once, in-process, directly into `os.environ["GEMINI_API_KEY"]`
  (the normal env-var credential path) for this test process only; the
  secrets file itself was never modified.
- Model path confirmed: `GEMINI_MODEL_BY_TAB_LABEL["Eredeti szöveg
  tanulmányozása"] = LOCKED_MODEL = "gemini-2.5-flash"`.
- **Minimal connectivity call: succeeded.** `status=200_OK`, `auth_ok=True`,
  `model=gemini-2.5-flash`, response `"Kezdetben"` (correct Hungarian for
  "In the beginning") for a trivial prompt about Gen 1:1.
- **Full quality smoke test then proceeded** through the real production
  path: `HebrewAnalysisService` → `build_hebrew_contextual_analysis_prompt`
  → `app.generate_hebrew_contextual_analysis_text` (the real `app.py`
  wrapper around `generate_text()`, unmodified) →
  `request_hebrew_contextual_analysis` / `get_or_request_hebrew_
  contextual_analysis` (unmodified Phase 2E service/cache code).

---

## 2. Test setup

- Deterministic data source: the real full local Phase 2D.1 corpus store
  (868 MB, session-scratchpad only, not committed) via
  `LocalHebrewAnalysisRepository` — the same store validated in Phase
  2D.2's parity check.
- 12 verses selected from the developer regression categories (§15 of the
  Phase 2E doc), using real Hungarian-style references through the
  production `HebrewAnalysisService.get_hebrew_analysis()` path.
- Every call used `bypass_cooldown=True` (an existing, supported
  `generate_text()` parameter — not a code change) to run the 12 calls
  back-to-back without the normal 8-second UI cooldown; `use_cache=False`
  at the `generate_text()` layer so every verse hit the network fresh.
  The **Phase 2E cache** (`HebrewContextualAnalysisCache`) was tested
  separately (§5).
- `max_output_tokens` was left at the tab's real production default
  (12,000, `DEFAULT_MAX_OUTPUT_TOKENS_BY_TAB["Eredeti szöveg
  tanulmányozása"]`) — not overridden.

---

## 3. Results overview

| # | Category (intended) | Reference | Grounding | Status | Latency |
|---|---|---|---|---|---:|
| 1 | אֲשֶׁר lexical vs. contextual | Ruth 1:16 | FULLY_GROUNDED | ok | 37.9 s |
| 2 | Imperative | Gen 1:22 | FULLY_GROUNDED | ok | 36.1 s |
| 3 | Cohortative | Gen 11:7 | FULLY_GROUNDED | ok | 37.9 s |
| 4 | Piel/Hitpael | Ps 51:12 | FULLY_GROUNDED | ok | 36.0 s |
| 5 | Construct chain | Gen 1:1 | FULLY_GROUNDED | ok | 19.5 s |
| 6 | Infinitive absolute + finite verb | Gen 2:17 | FULLY_GROUNDED | ok | 33.8 s |
| 7 | Multiple negation* | Ex 20:3 | FULLY_GROUNDED | ok | 29.0 s |
| 8 | Ketiv/Qere | Ruth 1:8 | FULLY_GROUNDED | ok | 47.4 s |
| 9 | Aramaic | Ezra 4:8 | FULLY_GROUNDED | ok | 28.8 s |
| 10 | Partially grounded syntax | Gen 36:5 | **PARTIALLY_GROUNDED** | ok | 31.3 s |
| 11 | No noteworthy construction* | Ruth 1:2 | FULLY_GROUNDED | ok | 35.6 s |
| 12 | Multi-component morphology | Gen 22:2 | FULLY_GROUNDED | **invalid_response** | 50.6 s |

`*` — verse-selection caveat, see §7.4. **11/12 verses produced a valid,
schema-conformant structured result; 1/12 failed closed (no fabricated
output) on a real `MAX_TOKENS` truncation** (§7.1) — this is the app's
existing fail-closed JSON-parse behavior working correctly, not a
grounding violation.

**API usage:** 13 real network calls total (12 verses + 1 extra call used
only to prove cache reuse, see §5) + 1 earlier minimal connectivity call =
14 calls this session. Model was `gemini-2.5-flash` on every single call,
with zero exceptions. Approximate token usage (character-count/4 estimate
— `app.py` does not itself log Gemini's real `usageMetadata`, so this is a
rough proxy, not an exact measurement): prompts ranged ~9.4–18.9k chars
(~2,350–4,700 tokens), successful responses ~4.2–13.6k chars (~1,050–3,400
tokens). Total estimated input ≈ 44k tokens, output ≈ 21k tokens across the
13 real calls.

---

## 4. Scoring (0 = incorrect/problematic, 1 = acceptable/needs improvement, 2 = good)

| # | Reference | Grammar | Contextual | Construction | Terminology | Restraint |
|---|---|:---:|:---:|:---:|:---:|:---:|
| 1 | Ruth 1:16 | 2 | 2 | 2 | 2 | 2 |
| 2 | Gen 1:22 | 2 | 2 | 2 | 2 | 2 |
| 3 | Gen 11:7 | 2 | 2 | 1 | 2 | 1 |
| 4 | Ps 51:12 | 2 | 2 | 1 | 2 | 1 |
| 5 | Gen 1:1 | 2 | 2 | 2 | 2 | 2 |
| 6 | Gen 2:17 | 2 | 2 | 2 | 2 | 2 |
| 7 | Ex 20:3 | 2 | 2 | 2 | 2 | 1 |
| 8 | Ruth 1:8 | 2 | 2 | 2 | 2 | 1 |
| 9 | Ezra 4:8 | 2 | 2 | 2 | 2 | 2 |
| 10 | Gen 36:5 | 2 | 2 | 2 | 2 | 2 |
| 11 | Ruth 1:2 | 2 | 2 | 2 | 2 | 2 |
| 12 | Gen 22:2 | — | — | — | — | — (no output delivered) |

**Grammar and Terminology: 22/22 (perfect)** across every verse that
completed. **Contextual: 22/22.** **Construction: 20/22** (2 verses marked
1 — not because a wrong construction reached the user, but because the
model *attempted* an ungrounded one that the server correctly discarded;
see §7.2). **Restraint: 16/22** (5 verses marked 1 for the same reason —
this is the field the recurring issue below shows up in most directly).

**No 0s anywhere.** No hard failure (as defined in the test brief) occurred
on any delivered output.

---

## 5. Cache-reuse proof (§14 of the Phase 2E brief, verified live)

Called `get_or_request_hebrew_contextual_analysis()` twice for Gen 1:1,
same verse/dataset-version/model:

```json
{
  "first_status": "ok",
  "second_status": "ok",
  "same_object": true,
  "network_calls_for_first": 1,
  "network_calls_for_second": 0
}
```

The second call returned the **exact same object**, with **zero**
additional network calls. This is the strongest possible live confirmation
of "one verse-level AI call serves word/construction/syntax UI."

---

## 6. Hard-failure check (per the test brief's definition)

Checked every delivered word note, construction note, and syntax summary
across all 11 completed verses for:

| Check | Result |
|---|---|
| Invented morphology/stem/conjugation | **None found.** Every stem/form label matched the supplied deterministic data (e.g. Gen 1:22's imperatives correctly labeled `imperativus` — the exact form the original Phase 2A `weqatal`-mislabeling regression concerned) |
| Invented syntax relationship | **None found.** Every `syntax_explanation_hu` traced to a real supplied `macula:edge`/`macula:role`/`macula:phrase`/`macula:clause`/`macula:participant`/`macula:coref` id |
| Invented construction existence | **None reached the user.** 5 attempts were made and all 5 were rejected server-side (§7.2) — the mechanism worked exactly as designed |
| Invented textual witness (LXX/DSS/SP/BHS/BHQ) | **None found**, including on both Ketiv/Qere verses (Ruth 1:8, Gen 36:5) — both explanations stayed strictly to the written/read form pair, one even explicitly noting the difference is "elsősorban fonológiai, és nem befolyásolja érdemben a jelentést" (primarily phonological, doesn't materially affect meaning) rather than inflating it |
| Unsupported emphasis claim from word order | **None found.** No output anywhere discussed word order or emphasis at all — consistent with the prompt's word-order-data-absence rule actually holding |
| Lexical vs. contextual meaning conflated | **None found.** Every word note kept the two fields distinct (e.g. Ruth 1:16's פָּגַע: lexical "ráront", contextual "ne sürgess, ne zaklass, ne erőltess" — clearly separated, not overwritten) |
| Fabricated Hungarian gloss for a missing lexicon entry | **None found.** Every token without a Hungarian lexical entry left `lexical_basic_meaning_hu` empty rather than inventing one (frequent in the Aramaic verse and on proper names, as expected) |
| Grounding status self-reported by the model, not the bundle | N/A to check output-side (enforced structurally, already unit-tested) — no discrepancy observed |
| Valid structured JSON contract | **11/12 valid.** 1/12 failed to parse due to truncation (§7.1), correctly surfaced as `invalid_response`, never as fabricated content |

**Zero hard failures.**

---

## 7. Recurring quality problems

### 7.1 Truncation on longer/denser verses (real limitation, most important finding)

Gen 22:2 (25 tokens — the largest verse in this test set, and among the
longest single verses in Hebrew narrative prose) produced a
`200_TRUNCATED` HTTP-level response: `prompt_chars=18869`,
`resp_chars=8407`, hitting the 12,000-token output ceiling before the JSON
closed. `request_hebrew_contextual_analysis()`'s JSON parser correctly
detected the malformed JSON and returned `invalid_response` — **no
fabricated or partial content was ever produced**, but no analysis was
delivered either.

Likely cause (documented in `app.py`'s own existing comments on Gemini 2.5
"thinking" token behavior, lines ~6260–6262): Gemini 2.5 Flash's internal
reasoning ("thinking") tokens are drawn from the **same** `maxOutputTokens`
budget as the visible JSON output unless a separate thinking budget is
configured — a token-rich verse needing more reasoning can exhaust the
budget before finishing the visible answer. This is a known, already-
documented characteristic of this model family in this codebase, not a
new discovery specific to Phase 2E.

**Not fixed in this test run, per instruction.** Candidate future
mitigations (not applied): raise `max_output_tokens` for this tab
specifically, or split very long verses' analysis into batched requests.
Real `usageMetadata` (thinking-token vs. candidate-token split) is not
currently captured by `app.py`'s debug logging, so the exact budget split
that caused this specific truncation cannot be confirmed further without
either a code change or manual inspection of the raw HTTP response.

### 7.2 The model frequently proposes constructions the bundle doesn't support — and the rejection mechanism catches every one of them

5 of 11 completed verses (Gen 11:7, Ps 51:12 ×2, Ex 20:3, Ruth 1:8 ×2 — 6
individual attempts total) included at least one `construction_notes`
entry the model proposed that `construction_note_evidence()` correctly
rejected — e.g. "Cohortativus igék kapcsolódása" between two cohortative
verbs with no real phrase/clause/relation linking them, or "Főnévi
frázisok párhuzama" across four tokens with no supplied grouping. Every
single one of these was caught and dropped before reaching the delivered
`HebrewContextualAnalysis` — **this is the grounding-verification fix from
the prior turn working exactly as intended, confirmed against real model
output for the first time.** It also means the fix was not merely
theoretically necessary — the live model genuinely does over-propose
constructions at a meaningful rate (roughly half of tested verses), so the
server-side check is carrying real weight, not guarding against a
hypothetical.

This is reported as a quality observation, not a defect: the architecture
is doing its job. It does mean a portion of every call's generated content
is discarded — a minor cost-efficiency note, not a correctness problem,
and not something to prompt-tune in this pass per instruction.

### 7.3 Latency

Successful calls ranged 19.5–47.4 s (mean ≈ 34 s). This is slow for an
interactive UI click-and-wait — a real UX consideration for a future pass,
not addressed here.

### 7.4 Verse-selection caveats in this test (my error, not a model issue)

- Ex 20:3 alone contains only **one** negation particle (`לֹא`), not
  "multiple" — I mis-selected a single-verse span from the fixture's
  multi-verse rationale (Ex 20:1-3). The model correctly did **not**
  invent a double-negation claim for this verse (there was genuinely only
  one negator) — appropriate restraint, but it means this run did not
  actually exercise a real double-negation case. A future run should use
  a verse where `multiple_negation_particles` actually fires (e.g. a verse
  with 2+ `לֹא`/`אַל` tokens — none of my 12 picks happened to trigger it).
- Ruth 1:2, picked as a "no noteworthy construction" control, in fact
  triggered 3 real detected patterns (a construct chain, two repeated
  lemmas) — every verse in this 12-verse sample that completed had at
  least one genuine deterministic pattern. I did not find or verify a
  truly pattern-free verse in this pass; that check remains open.

---

## 8. Representative examples

**Best-quality output (Gen 36:5, PARTIALLY_GROUNDED_SYNTAX)** — this is
the single most important structural proof in the whole test: the two
genuinely `UNRESOLVED` tokens (Gen.36.5:5, Gen.36.5:7) both received
`"syntax_explanation_hu": ""` (correctly blanked), and the model's own
`syntax_summary.summary_hu` explicitly and correctly named which two
tokens have no syntax data — matching the deterministic bundle exactly,
with no invented mondattani claim on either uncovered token.

**Good lexical/contextual separation (Ruth 1:16:4, פָּגַע):**
```
lexical_basic_meaning_hu: "ráront"
contextual_meaning_hu: "ne sürgess, ne zaklass, ne erőltess"
translation_note_hu: "A פָּגַע ige alapjelentése 'ráront, ráesik', de ebben
  a kontextusban 'zaklat, sürget, erőltet' árnyalatot kap..."
```

**Correct Aramaic-specific terminology (Ezra 4:8:6):** `"Ige, Peal
igetörzs, perfectum igealak..."` — Peal, not Qal, matching the Aramaic
binyan system correctly (the exact distinction the Phase 2E brief's
Aramaic terminology rule required).

**A caught, rejected overreach (Ps 51:12, from the warnings, never shown
to a user):** `"Szerkezet-megfigyelés eldobva (nincs determinisztikus
alátámasztás...): Főnévi frázisok párhuzama"` — the model proposed a
parallelism construction across 4 tokens with no supporting phrase/clause
grouping; the service discarded it before it ever reached
`HebrewContextualAnalysis.construction_notes`.

**The one incomplete result (Gen 22:2):** no content — `status:
"invalid_response"`, `analysis: null`. Deterministic word/morphology data
for this verse remains fully available elsewhere in the app regardless
(unaffected by this AI-layer truncation, per the existing fallback
contract).

---

## 9. Answers to the brief's specific verification questions

- **Lexical/basic meaning stays distinct from contextual meaning:** yes,
  confirmed across every completed verse.
- **Construction notes have deterministic evidence:** yes — verified both
  structurally (the code enforces it) and empirically (6 ungrounded
  attempts across the live run, 6 rejections, 0 leaks).
- **Partial/no-grounding restricts claims correctly:** yes, confirmed live
  on Gen 36:5 (the only `PARTIALLY_GROUNDED_SYNTAX` verse tested) — exact,
  correct per-token restriction.
- **Ketiv/Qere does not trigger invented LXX/DSS/Samaritan/BHS/BHQ
  claims:** confirmed on both Ketiv/Qere verses tested (Ruth 1:8, Gen
  36:5) — neither mentioned any manuscript tradition beyond the supplied
  written/read pair.
- **Missing Hungarian gloss does not cause fabricated dictionary data:**
  confirmed — every token without a Hungarian lexicon entry left the field
  empty rather than inventing a gloss.
- **The structured JSON contract is valid:** valid on 11/12 calls; the
  12th failed closed (truncation), never producing invalid-but-accepted
  content.

---

## Final summary

- **Live Gemini access: succeeded**, on every one of 14 real calls this
  session (13 quality-test calls + 1 connectivity check).
- **Model used: `gemini-2.5-flash`, confirmed on every call** — no
  fallback, no substitution, matches the app's locked production model
  path.
- **Verses tested: 12** (11 completed with a valid structured result, 1
  failed closed on truncation).
- **Scores: Grammar 22/22, Contextual 22/22, Construction 20/22, Terminology
  22/22, Restraint 16/22** (all deductions from caught-and-rejected
  overreach attempts, never from delivered content).
- **Hard failures: zero.**
- **Recurring issues:** (1) longer/denser verses can exhaust the current
  12,000-token output budget and fail closed rather than deliver partial
  content — a real, reportable limitation, not fixed in this pass; (2) the
  model proposes ungrounded constructions at a real, non-trivial rate,
  entirely absorbed by the existing server-side rejection — a
  cost-efficiency note, not a correctness problem.
- **Approximate cost/usage:** ~14 calls, ~44k input / ~21k output tokens
  estimated (character-count proxy, not exact `usageMetadata`).
- **Is Gemini 2.5 Flash suitable as the default model?** For grounding
  compliance and Hungarian output quality: **yes, based on this sample** —
  zero hard failures, strong terminology accuracy, correct restraint on
  everything that reached the user. For **reliability on longer verses at
  the current token budget: not yet** — the truncation failure mode needs
  either a larger budget or a length-aware fallback before this can be
  called production-ready for the full breadth of the Hebrew Bible's verse
  lengths.
- **Ready to send for expert review?** The deterministic grounding
  architecture is now validated against real model output, not just
  hand-built test cases — that is a meaningful readiness signal. However,
  I would recommend fixing the truncation failure mode first (so an expert
  reviewer doesn't hit unexplained blank results on longer verses) and
  re-running this smoke test on a corrected verse list (real multiple-
  negation case, a verified pattern-free verse) before formal expert
  review begins. Neither of those was done in this pass, per instruction.

---
---

# HARDENING FOLLOW-UP (narrow quality pass, same day)

**The section above is the historical first-run record — left unchanged.**
This section documents a targeted follow-up pass that tightened the output
contract and re-ran a smaller live regression set. Model, provider, and
`max_output_tokens` (12,000, unchanged) are the same as above — **only the
prompt, response schema, and server-side validation changed.**
**Code under test:** worktree state after this hardening pass (not yet
committed at the time of this test run).

## H1. Genesis 22:2 truncation — root cause

Reproduced the original failure's exact prompt once more before changing
anything. On this repeat attempt the SAME prompt actually returned a
**complete, valid** JSON response (`status: 200_OK`, `resp_chars: 12160`,
parsed cleanly) — confirming the original truncation was **probabilistic**
(model-generation variance in how much internal "thinking" Gemini 2.5 Flash
spent before writing visible output), not a deterministic bug reproducible
on demand.

Inspecting that complete 12,160-character response directly (saved and
read in full) identified the real, fixable cause of excessive size — **not
a runaway/repeating bug, but systematic over-coverage**:

- **25 word_notes for 25 tokens — one per token, no selectivity.** Three of
  them, for the bare object-marker particle (`אֵת`) at different token
  positions, were **near-byte-identical boilerplate**:
  `contextual_meaning_hu: "tárgyjelölő"`, `grammar_explanation_hu:
  "Tárgyjelölő partikula."`, `syntax_explanation_hu: "Egy főnévi frázis
  része."` — repeated three times for zero additional information.
- Every one of the 25 notes carried an empty `"translation_note_hu": ""`
  key regardless — required-field boilerplate for a field that was never
  useful once.
- `construction_notes` (4 entries) and `syntax_summary` were NOT
  pathologically long individually — the size problem was concentrated
  almost entirely in `word_notes`' exhaustive, low-selectivity coverage.

**Conclusion:** the fix is not "the model went haywire on this verse" — it
is "the prompt never told the model it was allowed to skip trivial
tokens," combined with thinking-token budget variance (documented
in `app.py`'s own existing comments on Gemini 2.5 behavior) occasionally
tipping a token-heavy, low-selectivity generation over the edge. Reducing
the NEEDED output (§H2) directly reduces this risk without touching the
token ceiling, matching the instruction not to raise `max_output_tokens`
as the primary fix.

## H2. Output-contract changes

`bible_engine/hebrew_contextual_analysis.py` (`CONTEXTUAL_ANALYSIS_
PROMPT_VERSION` / `CONTEXTUAL_ANALYSIS_SCHEMA_VERSION` bumped `2e.0.0` →
`2e.1.0`, which naturally invalidates any old AI-result cache entries):

- New **TÖMÖRSÉG** ("brevity") instruction block: `word_notes` should
  cover only tokens with genuinely non-trivial content; repeated trivial
  function-word occurrences (bare object markers, plain conjunctions) get
  at most one representative note, not one per occurrence; each note
  should be 1-3 sentences across all its fields combined; grammar
  explanations should not just restate morphology labels already visible
  on the deterministic word card; `translation_note_hu` only when
  genuinely useful; `construction_notes` 1-3 sentences, no generic
  grammar mini-lectures; `syntax_summary` one concise paragraph, not a
  clause-by-clause narration; `exegetical_notes` empty-by-default.
- Server-side (`hebrew_contextual_analysis_service.py`): differentiated,
  tighter list caps — `_MAX_WORD_NOTES = 15` (was a shared cap of 10 for
  everything), `_MAX_CONSTRUCTION_NOTES = 6`, `_MAX_STRING_LIST_ITEMS = 5`
  (translation/exegetical notes) — plus a new soft per-field length
  backstop (`_truncate()`, ~320 chars for word/construction fields, ~700
  for the syntax summary) that trims an overlong field with a `…` and a
  recorded warning **instead of** rejecting the whole note. This is a
  mechanical safety net, not the primary mechanism — the primary fix is
  the prompt asking the model to be selective in the first place.

## H3. Construction-evidence catalog

Implements the brief's evidence-id design using ids the payload **already
prints** — no new prompt content, no size increase from this part of the
change:

- `ConstructionNote.token_ids` (server-derived, unchanged for consumers)
  stays; `evidence_pattern_ids` renamed to **`evidence_ids`** (broader
  semantics — the citable id space is now every existing catalog category,
  not just detected patterns).
- Response schema: `construction_notes[].token_ids` → `evidence_ids`
  (array of strings) — the model no longer proposes a token grouping at
  all; it can only cite ids from the FELISMERT SZERKEZETEK / FRÁZISOK /
  TAGMONDATOK / MONDATTANI VISZONYOK / SZEMANTIKAI SZEREPEK / RÉSZTVEVŐK
  blocks it already received.
- New `build_construction_evidence_index(verse)` — maps every citable id
  (`pattern_id`, `phrase_id`, `clause_id`, `relation_id`, `role_id`,
  `participant_id`) to its `token_ids`.
- New `resolve_construction_evidence(evidence_ids, index)` — validates
  every cited id, returns only the ones that actually resolve plus the
  union of their token_ids; a note with **zero** resolvable ids is
  rejected outright (partial validity — some valid, some hallucinated ids
  — keeps the note, using only the valid ones, with a warning).
- `_MAX_LIST_ITEMS`/`construction_note_evidence()` (the old token-overlap
  heuristic) were retired in favor of this direct id-citation mechanism —
  strictly more precise, since the model must name *which* fact grounds a
  claim rather than the server inferring it from token overlap after the
  fact.

Word-level notes were deliberately **not** given an evidence-id
requirement (§4 of the brief: "do not overcorrect") — they may still use
any supplied morphology/lexical/phrase/clause data freely.

## H4. Tests added/changed

| File | Change |
|---|---|
| `tests/test_hebrew_contextual_analysis.py` | 5 existing construction-note tests rewritten for the `evidence_ids` contract; **11 new tests**: partial-validity evidence citation, sparse word notes accepted, word/construction-note count caps, overlong-field truncation (word note + syntax summary), `build_construction_evidence_index` covering all 6 id types, `resolve_construction_evidence` dedup/invalid-id handling (2 tests), instruction-text assertions for the new evidence-id and brevity rules |

Net: **39 tests** in this file now (was 28), all passing. Full Phase 2E
scope (`test_hebrew_contextual_analysis*.py`, `test_hebrew_contextual_
golden_fixtures.py`, `test_hebrew_analysis_cache.py`): **80 passed**. Full
Hebrew regression (`pytest tests/ -k hebrew --ignore=tests/
test_textus_kb`): **354 passed, 36 skipped** (pre-existing, unrelated), 0
failed — confirms no regression in PARTIAL/NONE grounding enforcement, the
`אֲשֶׁר`/root/textual-witness safety rules (all untouched by this pass), or
UI rendering (which only ever read `title_hu`/`explanation_hu`/
`translation_significance_hu` from a construction note — never
`token_ids`/`evidence_ids` — so it needed no change at all).

## H5. Live regression results (7 verses, same production path)

| Verse | Category | Grounding | Status | Tokens | Latency | Word notes | Construction notes | Unsupported attempts | Output chars |
|---|---|---|---|---:|---:|---:|---:|---:|---:|
| Gen 22:2 | Truncation case | FULLY_GROUNDED | ok | 25 | 29.9 s | 10 | 3 | 1 | 6,818 |
| Gen 1:1 | Simple verse | FULLY_GROUNDED | ok | 7 | 30.2 s | 6 | 2 | 0 | 5,074 |
| Ruth 1:2 | Construct chain | FULLY_GROUNDED | ok | 20 | 21.3 s | 9 | 3 | 0 | 6,631 |
| Ex 20:3 | Negation | FULLY_GROUNDED | ok | 7 | 21.2 s | 5 | 4 | 1 | 5,866 |
| Gen 1:22 | Verbal stem (imperative) | FULLY_GROUNDED | ok | 13 | 33.9 s | 7 | 5 | 0 | 8,351 |
| Gen 36:5 | **PARTIALLY_GROUNDED** | PARTIALLY_GROUNDED | ok | 16 | 40.4 s | 8 | 4 | 0 | 8,246 |
| Ezra 4:8 | Aramaic | FULLY_GROUNDED | ok | 13 | 22.4 s | 12 | 3 | 0 | 6,867 |

**7/7 valid structured outputs. 0 truncations. 0 grounding failures.**
Model was `gemini-2.5-flash` on every call, `max_output_tokens` left at the
unchanged production default of 12,000.

**Genesis 22:2, the original failure case, now completes cleanly** with
6,818 output characters (down from the complete-but-narrowly-successful
12,160-character run in §H1, and it previously truncated in the original
smoke test at the same prompt) — 10 word notes instead of 25, with the
model correctly skipping the repeated bare object-marker occurrences that
padded the original response.

**Output size vs. the brief's targets** (§5: ordinary verse well below
2,500 output tokens, complex verse below 4,000): every one of the 7 test
verses' output (5,074–8,351 chars, ≈1,270–2,090 tokens at a 4-chars/token
estimate) falls comfortably under the "ordinary verse" target — including
the two most token-dense verses tested (Gen 22:2 at 25 tokens, Ruth 1:2 at
20 tokens).

**Unsupported construction attempts: 2 across 7 verses** (Gen 22:2: 1 —
the model cited a raw token id, `"Gen.22.2:17"`, where an evidence catalog
id was required, correctly rejected; Ex 20:3: 1 — similarly cited two raw
token ids instead of a catalog id). Rate ≈29% of verses, down from the
first run's ≈45% (6 attempts across 11 verses) — a real but modest
reduction; the mechanism that actually matters (rejection) worked
perfectly in both runs. A new, more granular signal this pass also
surfaced: **4 "partially invalid" citations** (a note kept some valid
evidence ids while one cited id didn't resolve — e.g. citing a
`macula:coref:` coreference-link id, which is visible in the prompt's
KOREFERENCIA block but was deliberately not added to the evidence
catalog). This is more informative than the old binary accept/reject
signal and is itself evidence the new mechanism is working as designed —
these citations were still correctly handled (partial credit, not full
rejection, since other valid ids remained).

**The soft length-truncation backstop fired 4 times** (2 on Gen 1:22, 2 on
Gen 36:5), each trimming a field that ran mildly over its 320/700-char
cap (e.g. 391→318, 714→689 chars) — confirming it is a real, active
safety net without needing to catch anything close to a runaway case in
this run.

**Latency:** 21.2–40.4 s (mean ≈28.5 s) — essentially unchanged from the
first run (mean ≈34 s then), if anything marginally better on average.
**Prompt size grew** (12,926–22,313 chars, vs. 9,482–18,869 before) —
the added TÖMÖRSÉG + evidence-id instruction text has a real, honest fixed
cost on every call. This is an accepted, deliberate trade: input tokens
don't compete with the output/thinking budget that caused the original
truncation, so a larger, more constraining prompt in exchange for a
substantially smaller, more disciplined output is the intended direction.

## H6. Remaining limitations (unchanged or newly observed)

1. The model still occasionally (2/7 verses here) attempts a construction
   note grounded on a raw token id or a coreference-link id instead of a
   valid evidence catalog id — always caught and rejected, never a
   correctness risk, but a residual prompt-clarity gap that a future pass
   could reduce further (e.g. adding coreference to the evidence catalog,
   or a sharper worked example in the instructions).
2. `app.py` still does not capture real Gemini `usageMetadata` (thinking
   vs. candidate token split) — all size figures in this document remain
   character-count estimates, not exact token counts.
3. Truncation risk is reduced, not mathematically eliminated — this was a
   probabilistic failure mode (§H1) and the fix reduces the odds by
   shrinking typical/worst-case needed output, not by capping or measuring
   the model's internal thinking-token consumption directly.
4. Live output remains developer-reviewed only — no Hebrew/Aramaic expert
   has reviewed either run's content. The hardening pass changed length
   and structure, not linguistic claims themselves; §4 of the original
   run's findings (zero hard grounding failures) is expected to still
   hold and was spot-checked in this run's warnings/evidence data, but a
   full manual per-verse content re-review (equivalent to §4 of the
   original run) was not repeated for all 7 verses here, per the
   instruction to keep this a narrow, non-repetitive follow-up.

## H7. Hardening pass — final summary

- **Genesis 22:2 root cause:** probabilistic thinking-token budget
  contention during generation, amplified by exhaustive, low-selectivity
  `word_notes` coverage (one entry per token, including near-duplicate
  boilerplate for repeated trivial function words) — not a deterministic
  bug, not a grounding violation.
- **Output-contract changes:** brevity-focused prompt instructions,
  differentiated list caps, evidence-id-based construction grounding, a
  soft per-field length backstop. Schema/prompt version bumped to
  `2e.1.0`.
- **Construction-evidence catalog:** reuses existing payload ids (no new
  prompt bulk from this part) — model cites, service independently
  re-validates and computes `token_ids` server-side.
- **Unsupported construction attempts:** 6/11 verses (55%*) → 2/7 verses
  (29%) — *the original report's own ratio was 5/11 verses with at least
  one attempt (6 total attempts); both remain fully absorbed by
  server-side rejection in every run.
- **Live verses tested:** 7 (Gen 22:2, Gen 1:1, Ruth 1:2, Ex 20:3, Gen
  1:22, Gen 36:5, Ezra 4:8).
- **Valid outputs:** 7/7 (100%, up from 11/12 ≈92%).
- **Truncations:** 0 (down from 1/12).
- **Output size:** 5,074–8,351 chars (≈1,270–2,090 tokens estimated) —
  well under the brief's "ordinary verse" 2,500-token target for every
  verse tested, including the two densest (25 and 20 tokens).
- **Latency:** 21.2–40.4 s, mean ≈28.5 s (comparable to the first run).
- **Grounding failures:** 0 — PARTIALLY_GROUNDED_SYNTAX (Gen 36:5) still
  completed cleanly; no hard failure category was triggered.
- **Tests:** 16 new/changed in `test_hebrew_contextual_analysis.py`;
  354 passed / 36 skipped (pre-existing) across the full Hebrew scope.
- **Files changed:** `bible_engine/hebrew_contextual_analysis.py`,
  `bible_engine/hebrew_contextual_analysis_service.py`,
  `tests/test_hebrew_contextual_analysis.py`,
  `docs/hebrew_analysis_v2_flash_quality_smoke_test.md` (this file).
- **Does Gemini 2.5 Flash now appear more suitable for expert review?**
  Yes, meaningfully more so than after the first run: the specific failure
  mode that would have produced an unexplained blank result for an expert
  reviewer (Genesis 22:2-style truncation) is now addressed at its actual
  root cause, output is substantially more compact and readable, and the
  construction-grounding mechanism is demonstrably even harder to fool
  (evidence-id citation instead of token-overlap inference). Recommend:
  proceed to expert review readiness prep (docs/hebrew_analysis_v2_
  phase2e.md §19) with this hardened prompt version; the residual
  raw-token/coreference-id citation gap (§H6.1) is minor and does not
  block that.
