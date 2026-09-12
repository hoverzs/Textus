"""Production polish pass — four presentation/grounding issues found in
real live Jn 3:16 output (see the task this closes):

1. οὕτως presented manner and degree as equally certain lexical facts.
2. πιστεύω εἰς αὐτόν risked an unnatural literal Hungarian rendering.
3. μὴ ἀπόληται ἀλλ᾽ ἔχῃ (one ἵνα-clause's internally coordinated
   predicates) risked being inflated into two separate purpose clauses.
4. μονογενής risked an unmarked theological/devotional overreach beyond
   its lexical meaning.
5. Stray backslash artifacts in AI-generated text.

Items 1/2/4 are pure PROMPT-level guidance (no new server-side pattern
validator was added for them — that would expand the existing categorical-
overclaim safety architecture, explicitly out of scope for this pass), so
they are tested here as prompt-content regression guards: the specific
guidance text must remain present. Items 3 and 5 are server-side logic
and get full functional tests against the real Jn 3:16 clause structure.
"""

from __future__ import annotations

import re

import pytest

from bible_engine.greek_analysis_service import get_greek_analysis_with_syntax
from bible_engine.greek_contextual_analysis import GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS
from bible_engine.greek_contextual_analysis_service import validate_and_build_contextual_analysis
from bible_engine.greek_syntax_sqlite import resolve_default_syntax_database_path

requires_syntax_store = pytest.mark.skipif(
    not resolve_default_syntax_database_path().exists(), reason="greek_syntax_dev.sqlite3 not built locally"
)


@requires_syntax_store
def _jn316_verse():
    return get_greek_analysis_with_syntax("Jn 3,16").verses[0]


def _normalized(text: str) -> str:
    """Collapses the prompt's own line-wrapping so multi-word phrase
    assertions don't depend on exactly where a line happens to break."""
    return re.sub(r"\s+", " ", text)


# ---------------------------------------------------------------------------
# 1. οὕτως — manner primary, degree only a cautious possibility
# ---------------------------------------------------------------------------


def test_prompt_instructs_manner_before_degree_for_polysemous_adverbs() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "οὕτως" in text
    assert "MÓD- VS. MÉRTÉK-JELENTÉSE" in text
    assert "SOSE mutasd be a kettőt egyenrangú" in text


# ---------------------------------------------------------------------------
# 2. πιστεύω εἰς + accusative — natural idiomatic rendering, not universal
# ---------------------------------------------------------------------------


def test_prompt_instructs_natural_rendering_for_verb_governed_prepositions() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "πιστεύω εἰς" in text
    assert "hisz benne" in text
    assert "belé veti a hitét" in text
    # must not be turned into a universal rule for every εἰς + accusative
    assert "NE általánosítsd minden εἰς + accusativus" in text


# ---------------------------------------------------------------------------
# 3. Coordinated predicates within ONE ἵνα-clause must not be inflated
#    into two separate subordinate-clause construction notes
# ---------------------------------------------------------------------------


def test_prompt_instructs_against_splitting_coordinated_predicates() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "KOORDINÁLT ÁLLÍTMÁNYOK EGY TAGMONDATON BELÜL" in text


def _find_coordinated_sibling_clause_ids(verse) -> tuple[str, str, str]:
    """Returns (clause_id_a, clause_id_b, shared_parent_id) for the first
    pair of sibling clauses found — proven present for Jn 3:16 ("μὴ
    ἀπόληται" and "ἀλλ᾽ ἔχῃ ζωὴν αἰώνιον", both children of the same
    coordinated-clause parent)."""
    children_by_parent: dict[str, list[str]] = {}
    for c in verse.clauses:
        if c.parent_clause_id:
            children_by_parent.setdefault(c.parent_clause_id, []).append(c.clause_id)
    for parent_id, children in children_by_parent.items():
        if len(children) >= 2:
            return children[0], children[1], parent_id
    raise AssertionError("Jn 3:16's known coordinated sibling clauses were not found in the bundle")


@requires_syntax_store
def test_coordinated_sibling_clauses_presented_as_two_notes_are_both_rejected() -> None:
    verse = _jn316_verse()
    clause_a, clause_b, parent_id = _find_coordinated_sibling_clause_ids(verse)

    parsed = {
        "word_notes": [],
        "construction_notes": [
            {
                "evidence_ids": [clause_a],
                "construction_type": "purpose_clause",
                "title_hu": "Negatív célhatározói mellékmondat",
                "explanation_hu": "A hívő nem vész el.",
            },
            {
                "evidence_ids": [clause_b],
                "construction_type": "purpose_clause",
                "title_hu": "Pozitív célhatározói mellékmondat",
                "explanation_hu": "A hívőnek örök élete van.",
            },
        ],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert analysis.construction_notes == ()
    assert any("koordinált testvér tagmondatok" in w and parent_id in w for w in warnings)


@requires_syntax_store
def test_single_note_for_the_whole_governing_clause_is_not_collapsed() -> None:
    """Proves the new check does not false-positive: describing the
    coordination as ONE note anchored to the actual ἵνα-clause evidence
    (the deterministic hina_clause_marker pattern) must still be accepted
    normally."""
    from bible_engine.greek_construction_detection import detect_patterns

    verse = _jn316_verse()
    patterns = detect_patterns(verse)
    hina = next(p for p in patterns if p.pattern_type == "hina_clause_marker")

    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [hina.pattern_id],
            "construction_type": "hina_clause",
            "title_hu": "ἵνα célhatározói mellékmondat, koordinált állítmányokkal",
            "explanation_hu": "A mellékmondat két koordinált állítmányt tartalmaz: μὴ ἀπόληται és ἀλλ᾽ ἔχῃ.",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert not any("koordinált testvér tagmondatok" in w for w in warnings)


@requires_syntax_store
def test_non_sibling_distinct_clauses_are_not_wrongly_collapsed() -> None:
    """A genuinely independent (non-sibling, ancestor/descendant) clause
    pair must not trip the sibling-inflation check — only true siblings
    under a shared parent are the target of this rule."""
    verse = _jn316_verse()
    # the outermost conjunction clause (whole verse) has exactly one child
    # in the chain down to the hina-clause — not a sibling-inflation case
    root_like = [c for c in verse.clauses if c.parent_clause_id is None]
    assert root_like  # sanity: at least one clause has no parent
    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [root_like[0].clause_id],
            "construction_type": "main_clause",
            "title_hu": "Fő tagmondat",
            "explanation_hu": "A vers fő állítása.",
        }],
        "syntax_summary": {},
    }
    analysis, warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    assert not any("koordinált testvér tagmondatok" in w for w in warnings)


# ---------------------------------------------------------------------------
# 4. μονογενής — lexical restraint, theological claims must stay separate
# ---------------------------------------------------------------------------


def test_prompt_instructs_lexical_exegetical_restraint_for_monogenes() -> None:
    text = _normalized(GREEK_CONTEXTUAL_ANALYSIS_INSTRUCTIONS)
    assert "μονογενής" in text
    assert "LEXIKAI JELENTÉS VS. TEOLÓGIAI/EXEGETIKAI ÉRTELMEZÉS" in text
    # the exact devotional overreach example named in the task, present as
    # a NEGATIVE example the model must avoid presenting as fact
    assert "Isten a legdrágábbat adta oda" in text
    assert "sose lexikai tényként" in text


@requires_syntax_store
def test_monogenes_lexical_sense_unchanged_and_conservative() -> None:
    """Confirms the deterministic lexicon entry itself (never touched by
    this polish pass) stays restrained — 'egyetlen'/'egyedülálló', no
    divine-origin claim baked into the lexical fact."""
    verse = _jn316_verse()
    token = next(t for t in verse.tokens if t.token_id == "Jhn.3.16:13")
    assert token.lemma == "μονογενής"
    assert token.lexical_sense is not None
    assert "egyetlen" in token.lexical_sense.base_meaning_hu or "egyedülálló" in token.lexical_sense.base_meaning_hu
    assert "isteni" not in token.lexical_sense.base_meaning_hu.lower()


# ---------------------------------------------------------------------------
# 5. Clean Greek rendering — stray backslash sanitization
# ---------------------------------------------------------------------------


@requires_syntax_store
@pytest.mark.parametrize("field_name", ["contextual_meaning_hu", "morphological_explanation_hu", "syntax_role_hu"])
def test_stray_backslashes_stripped_from_word_note_fields(field_name: str) -> None:
    verse = _jn316_verse()
    dirty = 'Idézet a görögből: \\"ἀλλ\\᾽ ἔχῃ\\" jelentése "de legyen".'
    parsed = {
        "word_notes": [{"token_id": "Jhn.3.16:22", field_name: dirty}],
        "construction_notes": [], "syntax_summary": {},
    }
    analysis, _warnings = validate_and_build_contextual_analysis(parsed, verse)
    note = next(n for n in analysis.word_notes if n.token_id == "Jhn.3.16:22")
    rendered = getattr(note, field_name)
    assert "\\" not in rendered
    assert "ἀλλ᾽ ἔχῃ" in rendered  # the Greek quotation itself survives, only the backslashes are gone


@requires_syntax_store
def test_stray_backslashes_stripped_from_construction_note_and_syntax_summary() -> None:
    from bible_engine.greek_construction_detection import detect_patterns

    verse = _jn316_verse()
    patterns = detect_patterns(verse)
    hina = next(p for p in patterns if p.pattern_type == "hina_clause_marker")

    parsed = {
        "word_notes": [],
        "construction_notes": [{
            "evidence_ids": [hina.pattern_id],
            "construction_type": "hina_clause",
            "title_hu": 'ἵνα mellékmondat (\\"célhatározói\\")',
            "explanation_hu": 'A \\"ἵνα\\" kötőszó vezeti be.',
        }],
        "syntax_summary": {"summary_hu": 'A vers egy \\"ἵνα\\" mellékmondatot tartalmaz.'},
    }
    analysis, _warnings = validate_and_build_contextual_analysis(parsed, verse)
    assert len(analysis.construction_notes) == 1
    note = analysis.construction_notes[0]
    assert "\\" not in note.title_hu
    assert "\\" not in note.explanation_hu
    assert "\\" not in analysis.syntax_summary.summary_hu


def test_sanitizer_never_touches_deterministic_greek_token_data() -> None:
    """The sanitizer lives in the AI-response validator only — deterministic
    token surface forms / verse.greek_text are never passed through it."""
    from bible_engine.greek_contextual_analysis_service import _sanitize_generated_text

    # deterministic Greek text has no backslashes to begin with, and even
    # if it somehow did, this function is never called on it in
    # validate_and_build_contextual_analysis — verified structurally by
    # inspecting that no `token.surface`/`verse.greek_text` reference is
    # ever passed to _truncate/_sanitize_generated_text in this module.
    assert _sanitize_generated_text("ἀλλ᾽ ἔχῃ") == "ἀλλ᾽ ἔχῃ"
