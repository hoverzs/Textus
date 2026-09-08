"""Phase 2A/2B regression tests for deterministic Hebrew correctness.

These tests exist because the original morphology golden tests were written
against *synthesised* codes rather than real TAHOT rows, which is how a wrong
table entry ("v" = Consecutive Perfect instead of Imperative) survived while
mislabelling every imperative in the Old Testament (Phase 2A). Phase 2B then
obtained the authoritative STEPBible TEHMC source and cross-verified every
mapping against it — see docs/hebrew_analysis_v2_phase2b.md.

Two layers:

* table-driven unit tests that need no database — every verified TEHMC verbal
  form code, plus the confidence/unresolved contract;
* corpus tests that run only when the production Hebrew database is present,
  asserting the structural invariants a correct morphology must satisfy.

Nothing here calls an LLM.
"""

from __future__ import annotations

import sqlite3

import pytest

from bible_engine.hebrew_morphology import (
    PERSONLESS_VERB_FORMS,
    STEMS_BY_LANGUAGE,
    UNVERIFIED_STEM_CODES,
    VERB_FORM_PERSON_CONSTRAINTS,
    VERB_FORMS,
    decode_hebrew_morphology,
)
from bible_engine.hebrew_morphology_hu import (
    COMPONENT_ROLE_HU,
    format_hebrew_morphology_rows_hu,
    untranslated_terms,
)
from bible_engine.hebrew_sqlite import DEFAULT_TAHOT_DATABASE_PATH

pytestmark = pytest.mark.filterwarnings("ignore")


requires_corpus = pytest.mark.skipif(
    not DEFAULT_TAHOT_DATABASE_PATH.exists(),
    reason="production TAHOT database not available",
)


# --------------------------------------------------------------------------
# A. Imperative decoding — the defect this phase exists to fix.
# --------------------------------------------------------------------------

# Real rows taken from data/generated/tahot_ot_runtime.sqlite3. The English
# gloss is STEPBible's own and is quoted to document why each expectation holds.
IMPERATIVE_CASES = [
    # (code, stem, person, gender, number, STEPBible gloss)
    ("HVqv2mp", "Qal", "Second", "Masculine", "Plural", "be fruitful"),  # Gen 1:22 פְּרוּ
    ("HVqv2ms", "Qal", "Second", "Masculine", "Singular", "take"),  # Gen 22:2 קַח
    ("HVqv2fp", "Qal", "Second", "Feminine", "Plural", "listen to"),  # Gen 4:23 שְׁמַעַן
    ("HVhv2fp", "Hiphil", "Second", "Feminine", "Plural", "give ear to"),  # Gen 4:23
]


@pytest.mark.parametrize("code,stem,person,gender,number,gloss", IMPERATIVE_CASES)
def test_imperative_codes_decode_as_imperative(code, stem, person, gender, number, gloss) -> None:
    decoded = decode_hebrew_morphology(code)

    assert decoded.verb_conjugation == "Imperative", f"{code} ({gloss})"
    assert decoded.verb_stem == stem
    assert decoded.person == person
    assert decoded.gender == gender
    assert decoded.number == number
    assert decoded.status == "fully_decoded"


def test_imperative_is_not_confused_with_weqatal() -> None:
    """"v" is the imperative, "q" is the consecutive perfect — never the same."""
    imperative = decode_hebrew_morphology("HVqv2ms")  # Gen 22:2 קַח "take"
    weqatal = decode_hebrew_morphology("Hc/Vqq3ms")  # Gen 2:24 וְדָבַק "and he cleaves"

    assert imperative.verb_conjugation == "Imperative"
    assert weqatal.verb_conjugation == "Consecutive Perfect"
    assert imperative.verb_conjugation != weqatal.verb_conjugation


def test_imperative_reaches_hungarian_as_imperativus() -> None:
    rows = dict(format_hebrew_morphology_rows_hu(decode_hebrew_morphology("HVqv2mp")))

    assert rows["Igealak"] == "imperativus"
    assert rows["Igetörzs"] == "qal"


def test_cohortative_is_not_reported_as_infinitive_construct() -> None:
    """TEHMC overloads "c"; a person tail marks a cohortative, not an infinitive."""
    cohortative = decode_hebrew_morphology("HVqc1cp")  # Gen 11:7 נֵרְדָה "let us go down"
    infinitive = decode_hebrew_morphology("HVqcc")  # Gen 1:18 לִמְשֹׁל "to rule"

    assert cohortative.verb_conjugation == "Cohortative"
    assert cohortative.person == "First"
    assert infinitive.verb_conjugation == "Infinitive Construct"
    assert infinitive.person == ""


# --------------------------------------------------------------------------
# B. Stem and conjugation stay separate normalized fields.
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "code,stem,form",
    [
        ("HVqp3ms", "Qal", "Perfect"),
        ("Hc/Vqw3ms", "Qal", "Consecutive Imperfect"),
        ("Hc/Vqq3ms", "Qal", "Consecutive Perfect"),
        ("HVqi3ms", "Qal", "Imperfect"),
        ("HVqv2ms", "Qal", "Imperative"),
        ("HVqc1cs", "Qal", "Cohortative"),
        ("HVqj3ms", "Qal", "Jussive"),
        ("HC/Vqu1cs", "Qal", "Conjunction Imperfect"),
        ("HVqcc", "Qal", "Infinitive Construct"),
        ("HVqaa", "Qal", "Infinitive Absolute"),
        ("HVqrmsa", "Qal", "Participle"),
        ("HVqsmsa", "Qal", "Passive Participle"),
        ("HVpp3ms", "Piel", "Perfect"),
        ("HVhv2fp", "Hiphil", "Imperative"),
        ("HVNp3ms", "Niphal", "Perfect"),
        ("HVtp3ms", "Hithpael", "Perfect"),
        ("HVPp3ms", "Pual", "Perfect"),
        ("HVHp3ms", "Hophal", "Perfect"),
    ],
)
def test_stem_and_conjugation_are_separate_fields(code, stem, form) -> None:
    decoded = decode_hebrew_morphology(code)

    assert decoded.verb_stem == stem, code
    assert decoded.verb_conjugation == form, code
    # They must never be collapsed into one another.
    assert decoded.verb_stem != decoded.verb_conjugation

    rows = dict(format_hebrew_morphology_rows_hu(decoded))
    assert rows.get("Igetörzs"), code
    assert rows.get("Igealak"), code
    assert rows["Igetörzs"] != rows["Igealak"], code


def test_every_verified_form_code_is_covered_by_this_file() -> None:
    """Table-driven guard: a new VERB_FORMS entry must gain a test."""
    covered = {
        "Perfect",
        "Consecutive Perfect",
        "Imperfect",
        "Consecutive Imperfect",
        "Conjunction Imperfect",
        "Jussive",
        "Imperative",
        "Infinitive Construct",
        "Infinitive Absolute",
        "Participle",
        "Passive Participle",
    }
    assert set(VERB_FORMS.values()) == covered


# --------------------------------------------------------------------------
# C. Unresolved / confidence contract.
# --------------------------------------------------------------------------


def test_no_stem_codes_remain_unverified_after_tehmc() -> None:
    """Phase 2B obtained the authoritative TEHMC source; it resolves every
    stem code Phase 2A had to leave unnamed (Q, u, M, e, a, D, i)."""
    assert UNVERIFIED_STEM_CODES == frozenset()


@pytest.mark.parametrize(
    "code,language,stem",
    [
        ("HVDq3cp", "Hebrew", "Nithpael"),
        ("AVMi3fs", "Aramaic", "Hitpaal"),
        ("AVQp3ms", "Aramaic", "Peil"),
        ("AVecc", "Aramaic", "Shaphel"),
        ("AVacc", "Aramaic", "Aphel"),
        ("AVip3fs", "Aramaic", "Hitpeel"),
        ("AVui2mp", "Aramaic", "Hitpael"),
        ("HVucc", "Hebrew", "Hothpaal"),
    ],
)
def test_previously_unverified_stem_codes_now_resolve_via_tehmc(code, language, stem) -> None:
    decoded = decode_hebrew_morphology(code)

    assert decoded.language == language, code
    assert decoded.verb_stem == stem, code
    assert decoded.status == "fully_decoded", code
    assert not decoded.unresolved_parts, code


def test_a_genuinely_unnameable_stem_code_still_reports_unresolved() -> None:
    """The safety mechanism itself must still work for a truly unknown letter."""
    decoded = decode_hebrew_morphology("AVzp3ms")

    assert decoded.verb_stem == ""
    assert decoded.status == "partially_decoded"
    assert "z" in decoded.unresolved_parts


def test_stem_letters_are_language_dependent() -> None:
    """The same TEHMC letter can name a different binyan per language — a
    real Phase 2A gap: a flat, language-independent stem table mislabelled
    939 Aramaic tokens with a Hebrew stem name."""
    for letter in ("q", "h", "p", "P", "u", "v"):
        hebrew_name = STEMS_BY_LANGUAGE["H"].get(letter, "")
        aramaic_name = STEMS_BY_LANGUAGE["A"].get(letter, "")
        assert hebrew_name and aramaic_name, letter
        assert hebrew_name != aramaic_name, letter


def test_unknown_code_cannot_be_fully_decoded() -> None:
    """A code the verified tables do not understand must not claim confidence."""
    for code in ("HVqz3ms", "HZzzz", "HRzz", "HCzz"):
        decoded = decode_hebrew_morphology(code)
        assert decoded.status != "fully_decoded", code
        assert decoded.unresolved_parts, code


def test_expansion_string_alone_does_not_grant_full_confidence() -> None:
    """A TEHMC expansion must not upgrade a code the decoder cannot parse."""
    decoded = decode_hebrew_morphology("HVqz3ms", {"HVqz3ms": "Function=Verb ; Stem=Qal"})

    assert decoded.status == "partially_decoded"
    assert decoded.unresolved_parts


def test_preposition_with_article_is_decoded_not_swallowed() -> None:
    decoded = decode_hebrew_morphology("HRd/Ncmsa")
    prefix = decoded.components[0]

    # Phase 2B: TEHMC (HRd/ARd) names this "Definite", not the Phase 2A ad hoc
    # label "With article".
    assert prefix["preposition_type"] == "Definite"
    assert decoded.status == "fully_decoded"
    assert not decoded.unresolved_parts


# --------------------------------------------------------------------------
# D. Terminology: "core" is not the Hebrew root.
# --------------------------------------------------------------------------


def test_core_component_label_does_not_claim_to_be_a_root() -> None:
    label = COMPONENT_ROLE_HU["core"]

    # "gyök" would be a linguistic error: the core component is the
    # lexeme-bearing part of the surface word, not the triliteral root.
    assert "gyök" not in label
    assert label == "alapszó"


def test_hungarian_morphology_has_no_english_leaks() -> None:
    for code in ("HVqv2mp", "HVqc1cp", "HRd/Ncmsa", "HC/Vqv2mp/Sp3fs"):
        rows = format_hebrew_morphology_rows_hu(decode_hebrew_morphology(code))
        for label, value in rows:
            assert not untranslated_terms(value), (code, label, value)


# --------------------------------------------------------------------------
# E. Corpus-level structural invariants.
# --------------------------------------------------------------------------


def _corpus_codes() -> dict[str, int]:
    with sqlite3.connect(DEFAULT_TAHOT_DATABASE_PATH) as connection:
        counts: dict[str, int] = {}
        for (code,) in connection.execute("SELECT morphology_code FROM tokens"):
            counts[code or ""] = counts.get(code or "", 0) + 1
        return counts


@requires_corpus
def test_corpus_person_constraints_hold() -> None:
    """No imperative may be non-second-person; no cohortative non-first-person."""
    violations: list[tuple[str, str, str]] = []
    for code in _corpus_codes():
        decoded = decode_hebrew_morphology(code)
        components = decoded.components or (
            {"verb_conjugation": decoded.verb_conjugation, "person": decoded.person},
        )
        for component in components:
            form = str(component.get("verb_conjugation") or "")
            person = str(component.get("person") or "")
            allowed = VERB_FORM_PERSON_CONSTRAINTS.get(form)
            if allowed and person and person not in allowed:
                violations.append((code, form, person))
            if form in PERSONLESS_VERB_FORMS and person:
                violations.append((code, form, person))
    assert not violations, violations[:10]


@requires_corpus
def test_corpus_has_imperatives_and_cohortatives() -> None:
    """Before Phase 2A the corpus decoded to zero of both, which is impossible."""
    totals: dict[str, int] = {}
    for code, count in _corpus_codes().items():
        form = decode_hebrew_morphology(code).verb_conjugation
        if form:
            totals[form] = totals.get(form, 0) + count

    assert totals.get("Imperative", 0) == 4305
    assert totals.get("Cohortative", 0) == 534
    assert totals.get("Consecutive Perfect", 0) == 6344


@requires_corpus
def test_no_mapped_code_is_dead_and_no_corpus_code_is_unmapped() -> None:
    """Both directions — a table entry nobody uses is unverifiable.

    Phase 2B: stem codes are language-tagged (STEMS_BY_LANGUAGE), since the
    same letter can name a different binyan per language. "Polal" (Hebrew
    "O") is TEHMC-defined but unattested in this TAHOT edition — allow-listed
    rather than flagged as a dead mapping, since it is verified, not guessed.
    """
    from bible_engine.hebrew_morphology import _split_morphology_components

    tehmc_unattested = {("H", "O")}
    stem_codes: set[tuple[str, str]] = set()
    form_codes: set[str] = set()
    for code in _corpus_codes():
        for _raw, normalized in _split_morphology_components(code):
            if normalized[1:2] == "V":
                stem_codes.add((normalized[:1], normalized[2:3]))
                form_codes.add(normalized[3:4])

    all_stem_keys = {
        (language, letter) for language, table in STEMS_BY_LANGUAGE.items() for letter in table
    }
    dead_stems = all_stem_keys - stem_codes - tehmc_unattested
    assert not dead_stems, f"dead stem mappings: {dead_stems}"
    assert set(VERB_FORMS) <= form_codes, f"dead form mappings: {set(VERB_FORMS) - form_codes}"

    unmapped_stems = {
        (language, letter)
        for language, letter in stem_codes
        if letter not in STEMS_BY_LANGUAGE.get(language, {}) and letter not in UNVERIFIED_STEM_CODES
    }
    assert not unmapped_stems, f"unmapped stem codes: {unmapped_stems}"
    assert not form_codes - set(VERB_FORMS)


@requires_corpus
def test_corpus_decoding_confidence_is_stable() -> None:
    """Phase 2B: TEHMC resolved all 181 previously-unverified-stem tokens.

    Only the 14 pre-existing empty morphology codes remain short of full
    confidence.
    """
    by_status: dict[str, int] = {}
    for code, count in _corpus_codes().items():
        status = decode_hebrew_morphology(code).status
        by_status[status] = by_status.get(status, 0) + count

    assert by_status.get("partially_decoded", 0) == 0
    assert by_status.get("malformed", 0) == 14
    assert by_status.get("unresolved", 0) == 0
    assert by_status["fully_decoded"] == 305621
