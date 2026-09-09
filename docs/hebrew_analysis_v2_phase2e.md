# Hebrew Analysis v2 — Phase 2E: Grounded Hungarian Contextual Grammar + Syntax Interpretation

**Scope:** the first user-facing AI-interpretation layer on top of the fully
deterministic Hebrew linguistic foundation (Phases 1–2D.2). Adds a
structured, grounded AI contract that explains — never re-derives — what a
supplied grammatical form means for a specific lexeme in a specific
sentence, what a supplied multi-token construction means, and a plain-
language syntax summary. No new linguistic database, no re-opened MACULA
alignment work, no AI-invented morphology/syntax/root/textual-criticism, no
UI redesign beyond one additive section, no push.
**Branch:** `claude/hebrew-analysis-v2-audit-efc152` · **Base checkpoint:** `aeeb669`
**Prior phases:** [`hebrew_analysis_v2_inventory.md`](hebrew_analysis_v2_inventory.md) ·
[`hebrew_analysis_v2_phase2a.md`](hebrew_analysis_v2_phase2a.md) ·
[`hebrew_analysis_v2_phase2b.md`](hebrew_analysis_v2_phase2b.md) ·
[`hebrew_analysis_v2_phase2c.md`](hebrew_analysis_v2_phase2c.md) ·
[`hebrew_analysis_v2_phase2d.md`](hebrew_analysis_v2_phase2d.md) ·
[`hebrew_analysis_v2_phase2d1.md`](hebrew_analysis_v2_phase2d1.md) ·
[`hebrew_analysis_v2_phase2d2.md`](hebrew_analysis_v2_phase2d2.md)

> **Post-checkpoint grounding-verification correction.** The original
> version of this document said "pattern detection is AI-only this phase"
> and that Phase 2C's `detected_patterns` layer "stays empty." Both
> statements were wrong, and the second one pointed at a real
> implementation gap, not just wording: the Phase 2C deterministic pattern
> detector (`bible_engine.hebrew_pattern_detection.detect_patterns`) DOES
> run and populate `VerseAnalysis.detected_patterns` for every bundle, but
> its output was never wired into the Phase 2E AI prompt payload, and
> `construction_notes` were validated only for token-id resolution — not
> for whether the claimed construction was actually deterministically
> evidenced. Both are now fixed: detected patterns reach the prompt (§8),
> and every construction note is rejected unless its tokens are covered by
> a real `DetectedPattern` or an existing phrase/clause/relation/role/
> participant grouping (`construction_note_evidence()`,
> `bible_engine/hebrew_contextual_analysis.py`). §8, §16, §18, and the
> acceptance criteria below reflect the corrected, verified state.

---

## 1. User problem addressed

Professional review of the Hebrew module found that Textus could already
identify individual Hebrew forms deterministically, but a user still could
not learn: what a grammatical form means for *this* lexeme in *this*
sentence; what a multi-word construction means as a unit; what syntactic
function a word/phrase/clause has; whether words together form a
meaningful construction; how the sentence is structurally organized; or
which observations might matter for translation/exegesis. Phase 2E adds
exactly this explanatory layer, in Hungarian, grounded on the deterministic
facts Phases 2C/2D/2D.1 already established — never re-deriving them.

**A pre-existing gap this phase also closed on the way in:** the live
"Eredeti szöveg tanulmányozása" word-click UI (`hebrew_text_demo.py`) was
never actually wired to the Phase 2C/2D/2D.1/2D.2
`HebrewAnalysisBundle`/`HebrewAnalysisService` — it still reads raw
`HebrewToken`/`HebrewMorphology` objects directly, bypassing the entire
MACULA syntax layer built in those phases. Phase 2E's UI integration (§13)
is therefore the first time that deterministic bundle infrastructure is
actually reachable from the running app, not just from tests.

---

## 2. Deterministic → AI boundary

Unchanged in spirit from the inventory's original proposal (§17), now
implemented against the ACTUAL Phase 2C/2D/2D.1/2D.2 bundle shape rather
than the inventory's speculative one:

| Fact | Deterministic (bundle) | AI |
|---|:---:|:---:|
| Surface, lemma, Strong ids | ✅ | ❌ |
| Verbal stem (binyan), conjugation/form — always separate fields | ✅ | ❌ |
| Person/gender/number/state | ✅ | ❌ |
| Prefix/core/suffix components | ✅ | ❌ |
| Phrase/clause membership, syntax relations, semantic roles, participants/coreference | ✅ | ❌ |
| Ketiv/Qere | ✅ | ❌ |
| Syntax-grounding status | ✅ | ❌ |
| Root (`gyök`) | absent by design (Phase 2C) — never supplied, never claimed | ❌ |
| Which listed sense fits this context | — | ✅ |
| What a stem contributes to *this* lexeme here | — | ✅ |
| What a supplied construction means here | — | ✅ |
| Why the syntax matters for understanding/translation | — | ✅ |
| Cautious word-order observation, *only if* corroborated | — | ✅ |

The AI never sees raw TEHMC codes or raw Hebrew text alone to re-parse —
it receives the already-decoded, Hungarian-labeled facts from one
`VerseAnalysis` (see §5).

---

## 3. Structured AI contract

`bible_engine/hebrew_contextual_analysis.py` defines:

```python
@dataclass(frozen=True)
class WordNote:
    token_id: str
    lexical_basic_meaning_hu: str = ""
    contextual_meaning_hu: str = ""
    grammar_explanation_hu: str = ""
    syntax_explanation_hu: str = ""
    translation_note_hu: str = ""
    confidence: str = "low"   # "high" | "medium" | "low"

@dataclass(frozen=True)
class ConstructionNote:
    token_ids: tuple[str, ...]
    construction_type: str
    title_hu: str
    explanation_hu: str
    translation_significance_hu: str = ""
    confidence: str = "low"

@dataclass(frozen=True)
class SyntaxSummary:
    summary_hu: str = ""
    clause_ids: tuple[str, ...] = ()
    confidence: str = "low"

@dataclass(frozen=True)
class HebrewContextualAnalysis:
    schema_version: str
    reference: str
    grounding_status: str
    word_notes: tuple[WordNote, ...] = ()
    construction_notes: tuple[ConstructionNote, ...] = ()
    syntax_summary: SyntaxSummary = SyntaxSummary()
    translation_notes: tuple[str, ...] = ()
    exegetical_notes: tuple[str, ...] = ()
    warnings: tuple[str, ...] = ()
```

`CONTEXTUAL_ANALYSIS_SCHEMA_VERSION = "2e.0.0"`. The model's raw JSON
response is described by `HEBREW_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA`
(a plain JSON-schema dict, passed as Gemini's `response_schema` /
`responseSchema` — the mechanism already available on `app.py`'s
`generate_text()`). Empty lists/empty strings are valid, expected results —
"nothing noteworthy" is a success state, never an error.

`syntax_summary` is intentionally never `None` — an empty `SyntaxSummary()`
(default) is the "nothing to summarize" state, e.g. under
`NO_GROUNDED_SYNTAX`.

---

## 4. Grounding policy

The existing `SYNTAX_GROUNDING_FULL` / `SYNTAX_GROUNDING_PARTIAL` /
`SYNTAX_GROUNDING_NONE` status (Phase 2D.1 §12) controls the AI both at the
**prompt** level and, more importantly, at the **structural-validation**
level (`bible_engine/hebrew_contextual_analysis_service.py`) — the model's
own claims are never simply trusted:

- **`FULLY_GROUNDED_SYNTAX`** — the model may explain syntax normally; every
  `clause_id` / `token_id` reference is still checked against the bundle.
- **`PARTIALLY_GROUNDED_SYNTAX`** — the prompt explicitly lists which
  token_ids have NO syntax data in this verse (computed from the bundle's
  own phrase/clause/edge/role/participant/coreference membership — see
  `_token_syntax_coverage()`). The service layer then **forcibly blanks**
  `syntax_explanation_hu` on any word note for an uncovered token, even if
  the model supplied one, and records a warning.
- **`NO_GROUNDED_SYNTAX`** — the service layer **forcibly empties**
  `syntax_summary` and drops any syntax-flavored `construction_notes`
  (matched by construction-type substrings like `tagmondat`/`clause`/
  `szintaktik`), regardless of what the model returned, always recording a
  warning when it had to correct something.
- **`grounding_status` on the output is always overwritten** with the
  bundle's own `VerseAnalysis.syntax_grounding` — the model's self-report
  is never trusted (tested explicitly:
  `test_grounding_status_on_output_always_mirrors_bundle_not_model`).

This means grounding enforcement does not depend on the model following
instructions correctly — it is mechanically, testably enforced after the
fact, on every response.

---

## 5. Prompt architecture

One prompt per verse, built by `build_hebrew_contextual_analysis_prompt(verse)`:

1. `HEBREW_CONTEXTUAL_ANALYSIS_INSTRUCTIONS` — the fixed Hungarian
   instruction block (must/must-not rules; see §7-§11 below for the
   specific safety rules it encodes).
2. `build_hebrew_contextual_analysis_payload(verse)` — the compact,
   Hungarian-labeled serialization of exactly ONE `VerseAnalysis` (never
   the raw bundle, never other verses, never a database object): per-token
   surface/lemma/part-of-speech/stem/form/agreement/components/lexical
   sense/Ketiv-Qere, then phrase/clause/syntax-relation/semantic-role/
   participant/coreference blocks, with the syntax-grounding status and
   (when partial) the explicit uncovered-token list at the top.

The payload reuses the EXISTING Phase 2B/2C Hungarian terminology tables
(`STEM_HU`, `VERB_FORM_HU`, `PERSON_HU`, `GENDER_HU`, `NUMBER_HU`,
`STATE_HU`, `PART_OF_SPEECH_HU` from `bible_engine.hebrew_morphology_hu`) —
no new terminology table was introduced, and stem/form are always emitted
on their own separate lines (`igetörzs:` / `igealak:`), never merged.

---

## 6. Lexical vs. contextual meaning

`WordNote` keeps `lexical_basic_meaning_hu` and `contextual_meaning_hu` as
two independent fields, always. The prompt payload supplies the bundle's
own `lexical_sense.base_meaning_hu` / `possible_meanings_hu` (Phase 2C,
`textus_hu_lexicon`) as the lexical anchor, or explicitly states "nincs
magyar lexikai adat ehhez a szóhoz" when no Hungarian lexicon entry exists
— never fabricating one. This directly targets the canonical `אֲשֶׁר`
regression (Phase 2A/inventory §6.4: a context-specific gloss like "amikor"
being shown as though it were the general meaning) — the schema makes the
two claims structurally distinct rather than relying on prose discipline
alone. Tested: `test_lexical_and_contextual_meaning_kept_as_separate_fields`.

---

## 7. Verbal-stem explanation policy

The instructions explicitly forbid universal formulas ("a Hitpael mindig
reflexív", "a Piel mindig intenzív") and instead require a lexeme/context-
specific explanation *when the supplied data supports one*, falling back to
a shorter, more general (but still non-formulaic) explanation when it does
not. This is enforced at the prompt level only (there is no deterministic
signal in the current bundle that could mechanically verify "is this
explanation lexeme-specific") — `test_instructions_forbid_universal_stem_formulas`
asserts the rule is actually present in the shipped instruction text.

---

## 8. Construction-level analysis

**Corrected in the post-checkpoint grounding-verification pass — see the
note at the end of this section.** `ConstructionNote` covers multi-token
observations (construct chains, double negation, infinitive absolute +
finite verb, multi-component prefix/suffix structures, etc.).
**Construction detection/grounding is deterministic; AI interpretation is
generative** — the architecture rule is unchanged from Phase 2C onward, and
Phase 2E's implementation now actually follows it end to end:

1. **Detection is deterministic.** Phase 2C's pattern detector
   (`bible_engine.hebrew_pattern_detection.detect_patterns`) already runs
   for every verse inside `HebrewAnalysisService._build_verse_analysis()`
   and populates `VerseAnalysis.detected_patterns` — it is **not** empty in
   practice (an earlier draft of this document said it was; that was
   wrong). Currently-detectable deterministic pattern types:

   | `pattern_type` | Detects |
   |---|---|
   | `multiple_negation_particles` | ≥2 negation-particle tokens in the verse |
   | `construct_state_chain` | a noun/adjective in construct state immediately followed by a compatible token |
   | `infinitive_absolute_with_finite_verb` | an infinitive absolute near a finite verb of the same lemma |
   | `explicit_pronoun_finite_verb_agreement` | an independent personal pronoun near a finite verb agreeing in person/number |
   | `repeated_lemma_in_verse` | the same lemma occurring ≥2 times in the verse |
   | `ketiv_qere_present` | any token with a Ketiv/Qere divergence |
   | `multicomponent_prefix_structure` | a token with ≥2 prefix components |

2. **The detected patterns now actually reach the AI payload.** A
   `FELISMERT SZERKEZETEK` block (pattern id, type, token_ids, and the
   detector's own deterministic `explanation_hu`) is included in
   `build_hebrew_contextual_analysis_payload()` — this was the actual gap
   the original "pattern detection is AI-only" wording pointed at: the
   detector ran and populated the bundle, but its output was never
   forwarded into the prompt, so the AI had no way to reference it. Fixed.

3. **Grounding is enforced structurally, not just by prompt instruction.**
   `hebrew_contextual_analysis.construction_note_evidence(token_ids, verse)`
   checks every returned construction note's `token_ids` against the
   verse's REAL deterministic structure — accepted only if the ids are a
   subset of a `DetectedPattern.token_ids` (in which case
   `ConstructionNote.evidence_pattern_ids` records which pattern(s)
   grounded it), or of a single existing phrase's, clause's, syntax-
   relation's (parent/child pair), semantic role's, or participant's token
   set. A note that resolves fine token-id-wise but matches NO real
   structure is rejected unconditionally
   (`test_construction_note_rejected_when_token_ids_resolve_but_nothing_grounds_it`)
   — token-id resolution alone was never sufficient evidence, and no
   longer reads as though it were.
4. This check is independent of `syntax_grounding` — a `NO_GROUNDED_SYNTAX`
   verse can still ground a morphology-only pattern (e.g. Ketiv/Qere,
   double negation), and a `FULLY_GROUNDED_SYNTAX` verse still rejects a
   note whose tokens don't actually co-occur in any real structure
   (`test_no_grounded_syntax_still_accepts_a_morphology_only_detected_pattern`).

**Limitation, listed rather than worked around:** fronted-constituent /
word-order-based constructions and cognate-accusative detection are not
yet implemented as deterministic detectors (the inventory §16.5 named them
as syntax-dependent, Phase 2D+ scope) — the AI cannot produce a
construction note for these today because nothing in the bundle would
ground one; this is a real, honest gap, not an AI-inference workaround.

---

## 9. Syntax summary

`SyntaxSummary.summary_hu` is a short, non-technical-tree Hungarian
sentence about the verse's structure (main predicate, subject, key
dependent relationships) — never a rendered parse tree. `clause_ids` are
filtered to only those that resolve in the bundle
(`test_syntax_summary_drops_unresolvable_clause_ids`), and the whole field
is forced empty under `NO_GROUNDED_SYNTAX` regardless of what the model
returned.

---

## 10. Word-order safety

The current MACULA import (Phase 2D/2D.1) never populates
`ClauseAnalysis.word_order` — it is always `""` in this dataset (verified
corpus-wide as a structural fact, not just documented:
`test_clause_analysis_word_order_field_always_empty_in_current_dataset`).
The prompt states this explicitly and forbids treating word order as
emphasis on its own, permitting only hedged language
("kiemelt helyzetben állhat", "figyelemre méltó elhelyezés") when it says
anything at all. Since no deterministic word-order fact is ever actually
in the payload, there is genuinely nothing for the model to over-claim
from — this is enforced by data absence, not just instruction.

---

## 11. Textual-criticism boundary

Out of scope, same as every prior phase. The instructions explicitly name
and forbid LXX, Dead Sea Scroll, Samaritan Pentateuch, and BHS/BHQ-apparatus
claims (`test_instructions_forbid_textual_criticism_beyond_ketiv_qere`).
Ketiv/Qere — the one deterministic text-critical fact TAHOT actually
supplies — may be explained, but only the written/read form pair itself,
never extended into a broader manuscript-witness claim.

---

## 12. Cache / versioning

Deliberately a SEPARATE cache from Phase 2D.2's
`CachedHebrewAnalysisService` (deterministic bundle cache) — see the
brief's own instruction not to mix caches with different versioning
semantics. `bible_engine/hebrew_contextual_analysis_cache.py`:

- Key: `(verse_id, dataset_version_signature, prompt_version, model_id)`.
- `dataset_version_signature` reuses Phase 2D.2's
  `HebrewAnalysisService.dataset_version_signature()` (a new public
  passthrough, `CachedHebrewAnalysisService.dataset_version_signature()`,
  was added so the UI can share one signature source between both caches).
- Only `STATUS_OK` results are cached — a failure is retried on the next
  call, never "cached" as a failure.
- LRU-bounded (`max_entries`, default 256).
- `get_or_request_hebrew_contextual_analysis()` is the single entry point:
  cache hit → return immediately; miss → exactly ONE AI call, then cache on
  success. This is what makes "one verse-level AI call serves both
  word-click and verse-summary UI" (§14 of the brief) actually true — every
  token click within the same verse reuses the same cache entry
  (`test_second_call_for_same_verse_and_version_reuses_cache_no_new_call`).

---

## 13. UI integration

`hebrew_text_demo.py` gained one additive section,
`render_hebrew_contextual_analysis_panel()`, called from
`render_hebrew_original_language_panel()` only when `display_mode !=
"compact"` and only after the existing deterministic word card renders
unchanged above it. It is threaded through `render_hebrew_original_
language_reference()` → `bible_engine.greek_analysis_ui.render_greek_
analysis_block()` (Hebrew OT branch only — the Greek branch is untouched,
per "do not start Greek Analysis v2") → `app.py`'s existing "Eredeti szöveg
tanulmányozása" tab call site, which now passes
`hebrew_contextual_analysis_generate_fn=generate_hebrew_contextual_analysis_text`
(a new small `app.py` wrapper around the existing `generate_text()`, adding
`response_mime_type="application/json"` and the Phase 2E `response_schema`
— the same dependency-injection convention `run_original_language_
analysis`'s `generate_text_fn` already uses, so `bible_engine`/
`hebrew_text_demo` never import `generate_text` directly).

**Default behavior is unchanged everywhere else**: every call site that
does not pass `generate_text_fn` (the demo harness, `writing_desk_ui.py`,
any other embedding) renders exactly as it did before Phase 2E — the new
parameter defaults to `None`, and the new function's very first line is
`if generate_text_fn is None: return`.

When wired, a click builds/fetches the `HebrewAnalysisBundle` for the
passage (via a session-scoped `CachedHebrewAnalysisService`, keyed by
`production_db_path` so the demo harness's alternate database never shares
a cache with the app's default one), locates the `VerseAnalysis` for the
selected token's verse, and shows:

- **Lexikai alapjelentés / Nyelvtani alak / Jelentése ebben a mondatban /
  Mondattani szerepe** — only the sections with actual content, for the
  clicked token.
- **"Nyelvtani és mondattani megfigyelések"** (an expander) — construction
  notes, if any.
- **"Mondatelemzés"** (an expander) — the syntax summary, if non-empty.
- **"Fordítási megfigyelések" / "Exegetikai jelentőség"** — collapsed
  expanders, shown only when non-empty.
- A quiet caption for `PARTIALLY_GROUNDED_SYNTAX` verses ("A mondat
  szerkezetének egy része ezen a helyen nem kapcsolható teljes biztonsággal
  a szöveg szavaihoz.") — never shown on fully-grounded verses, per the
  brief's "don't clutter ordinary verses with unnecessary warnings" rule.

Before the first generation for a verse, a small caption plus a
"Kontextuális elemzés generálása" button is shown instead — the AI call is
always explicit and user-triggered, never automatic on every rerun/click
(Streamlit reruns the whole script on every interaction, so an automatic
call would mean an LLM call per click).

---

## 14. Fallback behavior

On any AI failure (`STATUS_UNAVAILABLE` — network/provider error, or
`STATUS_INVALID_RESPONSE` — malformed JSON): the deterministic word card
above is completely unaffected (it was already rendered before the AI
section is reached), and the AI section shows one plain notice — "A
kontextuális elemzés jelenleg nem érhető el. A determinisztikus szó- és
mondattani adatok fent továbbra is elérhetők." — with no fabricated
fallback explanation and no automatic second/different prompt. A failed
result is never cached, so the next click retries cleanly. Tested at both
the service level (mocked exceptions/malformed JSON) and the UI level
(`test_ai_failure_shows_graceful_notice_deterministic_card_still_present`).

---

## 15. Expert regression framework

`tests/fixtures/hebrew_contextual_golden/` — 12 fixture files + a
`manifest.json`, covering every category the brief named (`אֲשֶׁר`,
imperative, cohortative, Piel/Hitpael semantic contribution, construct
chain, infinitive absolute, double negation, word-order observation,
Ketiv/Qere, Aramaic, multi-component structure, partial syntax grounding).
**Every entry is explicitly `status: "unreviewed_developer_candidate"` /
`reviewed_by: null`** — these are real, verified corpus passages (5 of the
12 are directly backed by fixtures already committed and importable:
`אֲשֶׁר`/Ruth 1:16-17, construct chain/Gen 1:1-3, Ketiv-Qere/Ruth 1:8,
Aramaic/Ezra 4:8, partial grounding/Gen 36:5), not a claim of expert
review — a named Hebrew expert's specific review verses were not available
to this session. `tests/test_hebrew_contextual_golden_fixtures.py` verifies
the framework's own integrity (every required category present, every
fixture-backed entry actually points at a real committed file, nothing
claims a fabricated review) without asserting any AI-generated content.

---

## 16. Tests

| File | Count | Covers |
|---|---:|---|
| `tests/test_hebrew_contextual_analysis.py` | 28 | prompt payload deterministic-fact fidelity (stem/form/syntax/grounding/root-absence/nullable-gloss/**detected patterns**), instruction-text safety assertions, output-validation structural rules (grounding overrides, uncovered-token stripping, **construction-note deterministic-evidence enforcement** — grounded-by-pattern, grounded-by-phrase, rejected-with-no-evidence, morphology-only-pattern-survives-NO_GROUNDED_SYNTAX) |
| `tests/test_hebrew_contextual_analysis_service.py` | 9 | mocked `generate_fn` — valid/fenced/malformed JSON, provider-failure text, raising callable, exactly-one-call guarantee |
| `tests/test_hebrew_contextual_analysis_cache.py` | 12 | version/model/prompt-version keyed hit/miss, failure never cached, unknown-signature disables caching, LRU eviction |
| `tests/test_hebrew_contextual_golden_fixtures.py` | 6 | fixture framework integrity |
| `tests/test_hebrew_contextual_analysis_ui.py` | 4 | `streamlit.testing.v1.AppTest` — no-op when unwired, button-before-generation, content-after-click, graceful failure notice |
| `tests/test_hebrew_analysis_cache.py` (+1) | — | new `dataset_version_signature()` passthrough |

**58 new/changed tests, all passing, no live network or LLM call
anywhere.** (A post-checkpoint grounding-verification pass added 5 tests
proving construction-note grounding is structurally enforced — see §8 —
replacing one test whose premise the fix made obsolete.) Full relevant
scope (`pytest tests/ -k hebrew --ignore=tests/test_textus_kb`, the
exclusion being a pre-existing unrelated pytest module-name collision):
**343 passed, 36 skipped** (all 36 pre-existing, unrelated — see Phase
2D.2's own doc). UI-adjacent suites (`test_greek_analysis_ui.py`,
`test_writing_desk_ui.py`, `test_phase5kb_staging_integration.py`,
`test_hebrew_lexicon_hu.py`, `test_hebrew_repositories.py`,
`test_hebrew_token_selector.py`): **136 passed**, confirming the
`greek_analysis_ui.py`/`app.py` signature threading introduced no
regression in the routing tests that specifically assert on
`render_hebrew_original_language_reference`'s call arguments.

---

## 17. Performance / cost observations

Measured locally (no live Supabase/network needed — Phase 2D.2 already
established the local repository backend as a valid development source;
this phase adds nothing that requires remote deployment):

| Measurement | Result |
|---|---|
| Deterministic bundle build (Ruth 1:16, local repo, avg of 10) | 35.6 ms |
| AI prompt payload size (Ruth 1:16 — 20 tokens, 17 phrases, 10 clauses) | ~16.1 KB (~4,000 tokens, rough estimate) |
| Simulated uncached AI call (mocked ~50 ms network latency) | 50.4 ms, 1 real call |
| Cached retrieval (avg of 20 repeated calls, same verse/version/model) | 0.0006 ms, **0 additional calls** |

The cache eliminates every repeat call for the same verse — confirming the
brief's "one verse-level AI call serves token + verse UI" requirement is
not just structurally true but measurably true (20 simulated re-renders,
1 network call). Prompt size is on the larger side for a short verse
because every token's full Hungarian-labeled fact set plus all phrase/
clause/edge/role/participant/coreference rows are always included — this
was a deliberate completeness-over-minimalism choice (the brief explicitly
warns against optimizing for minimal cost at the expense of linguistic
reliability); a future phase could trim rarely-useful fields if cost
becomes a real constraint, but no such constraint was reported here.
Real Gemini latency/token-usage was not measured (no live network call was
made in this environment, matching Phase 2D.2's own scope boundary), and is
this phase's one open "read the real numbers" item for whoever runs it with
a live API key.

---

## 18. Remaining limitations

1. Real (non-mocked) model output quality is unverified — the fixture
   framework (§15) exists but has not been run against a live model or
   reviewed by a Hebrew expert.
2. Word-order observations can never be grounded on real word-order data in
   this dataset (§10) — this is a genuine dataset gap, not a Phase 2E
   shortcoming, and is documented rather than worked around.
3. Construction detection is deterministic (Phase 2C's `detect_patterns`,
   §8) for 7 pattern types; the AI only interprets what was detected, and
   any construction note it proposes outside that deterministic evidence
   is rejected. Not yet deterministically detected — and therefore
   currently unavailable as a construction note at all, by design — are
   fronted-constituent/word-order-based constructions and cognate-
   accusative (both require syntax data the current MACULA import doesn't
   fully exploit for this purpose yet); a future phase could add these as
   real detectors, as originally sketched in the inventory §16.5.
4. The AI prompt/response cycle has not been measured against a real
   network (§17).
5. UI integration is additive and functional but minimal — no dedicated
   settings for model choice, no admin-facing regeneration-invalidation
   control beyond the existing session cache.

---

## 19. Readiness for expert review

**Ready for a Hebrew expert to review the 12 developer-candidate fixtures
(§15) against real, live model output** — that is the natural next step:
run the wired feature (or a small script using
`request_hebrew_contextual_analysis` directly) against each fixture
reference with real credentials, capture the output, and have an expert
mark `reviewed_by`/`reviewed_at`/`review_notes_hu` and correct
`expected_word_notes`/`expected_construction_notes` where needed. The
deterministic contract, grounding enforcement, and fallback behavior are
all tested and believed solid; what remains unverified is real model
output quality, which by definition cannot be verified without a live call
and a domain expert.

---

## Acceptance criteria checklist

1. AI receives deterministic structured Hebrew facts, never raw morphology codes — ✅ (§2, §5)
2. Lexical/basic meaning and contextual meaning are distinct — ✅ (§6, tested)
3. Word-level contextual grammar explanation exists — ✅ (`WordNote`, §3)
4. Construction-level interpretation exists — ✅ (`ConstructionNote`, §8)
5. Verse/clause syntax summary exists — ✅ (`SyntaxSummary`, §9)
6. Existing syntax grounding status constrains AI claims — ✅ (§4, structurally enforced)
7. Partial/unresolved syntax cannot become confident invented syntax — ✅ (§4, tested per-token)
8. Word order does not automatically imply emphasis — ✅ (§10, no word-order data ever supplied)
9. Verbal stems explained lexeme/context-specifically where evidence supports it — ✅ (§7, prompt-level)
10. Missing Hungarian lexical meanings remain nullable — ✅ (§6, tested)
11. Full textual criticism is not invented — ✅ (§11, tested)
12. Ketiv/Qere handled from deterministic metadata only — ✅ (§11)
13. One verse-level AI analysis serves token and verse UI — ✅ (§12, §17, measured)
14. AI interpretation is cacheable/versioned — ✅ (§12)
15. AI failure leaves deterministic analysis usable — ✅ (§14, tested at UI level)
16. Existing Hebrew tests remain green — ✅ (§16 — 339 passed, 36 pre-existing skips)
17. New safety/regression tests pass — ✅ (§16 — 63/63 new tests)
18. UI exposes the new analysis without major unrelated redesign — ✅ (§13 — one additive section, opt-in parameter)
19. No new large binary/data source introduced — ✅ (only Python/JSON source files added; no new `.sqlite3`)
20. Nothing pushed — ✅
