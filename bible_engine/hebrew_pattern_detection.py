"""Phase 2C — Detected Features v1: purely structural, deterministic
Hebrew pattern detection over an already-built ``VerseAnalysis``.

CRITICAL, per the Phase 2C spec this module implements: every detector
reports a STRUCTURAL FACT about the text, never an interpretation of what
that fact means.

    GOOD: "Two negation particles occur in this clause/window."
    BAD:  "This creates emphatic negation."

If a feature cannot be identified confidently without syntax (a real parse
tree, clause boundaries, discourse structure), it is NOT implemented here —
see ``bible_engine.hebrew_analysis_bundle``'s ``PhraseAnalysis``/
``ClauseAnalysis``, both reserved-but-empty until Phase 2D's MACULA
integration. Every detector below only needs data already on
``TokenAnalysis``/``ComponentAnalysis`` (morphology, lemma, Strong id,
Ketiv/Qere) plus adjacency within one verse — no cross-verse or syntactic
reasoning.

Each function takes one ``VerseAnalysis`` and returns
``tuple[DetectedPattern, ...]``; ``detect_patterns`` runs all of them.
"""

from __future__ import annotations

from bible_engine.hebrew_analysis_bundle import DetectedPattern, TokenAnalysis, VerseAnalysis

DETECTOR_VERSION = "2c.0.0"

_FINITE_VERB_FORMS = {
    "Perfect",
    "Imperfect",
    "Consecutive Perfect",
    "Consecutive Imperfect",
    "Imperative",
    "Jussive",
    "Cohortative",
}
_ADJACENCY_WINDOW = 3


def detect_patterns(verse: VerseAnalysis) -> tuple[DetectedPattern, ...]:
    patterns: list[DetectedPattern] = []
    patterns.extend(_detect_multiple_negation(verse))
    patterns.extend(_detect_construct_chains(verse))
    patterns.extend(_detect_infinitive_absolute_with_finite_verb(verse))
    patterns.extend(_detect_independent_pronoun_verb_agreement(verse))
    patterns.extend(_detect_repeated_lemma(verse))
    patterns.extend(_detect_ketiv_qere_presence(verse))
    patterns.extend(_detect_multicomponent_prefix_structures(verse))
    return tuple(patterns)


def _detect_multiple_negation(verse: VerseAnalysis) -> list[DetectedPattern]:
    negations = [t for t in verse.tokens if t.morphology.part_of_speech == "Negative"]
    if len(negations) < 2:
        return []
    return [
        DetectedPattern(
            pattern_id=f"{verse.verse_id}.negation",
            pattern_type="multiple_negation_particles",
            token_ids=tuple(t.token_id for t in negations),
            evidence_token_ids=tuple(t.token_id for t in negations),
            detector_version=DETECTOR_VERSION,
            confidence="certain",
            explanation_hu=f"Ebben a versben {len(negations)} tagadószó fordul elő.",
        )
    ]


def _detect_construct_chains(verse: VerseAnalysis) -> list[DetectedPattern]:
    patterns: list[DetectedPattern] = []
    tokens = sorted(verse.tokens, key=lambda t: t.word_index)
    for index in range(len(tokens) - 1):
        current, following = tokens[index], tokens[index + 1]
        if current.morphology.state != "Construct":
            continue
        if current.morphology.part_of_speech not in {"Noun", "Adjective"}:
            continue
        if following.word_index != current.word_index + 1:
            continue
        if following.morphology.part_of_speech not in {"Noun", "Adjective", "Pronoun", "Proper name"}:
            continue
        patterns.append(
            DetectedPattern(
                pattern_id=f"{verse.verse_id}.construct.{current.token_id}",
                pattern_type="construct_state_chain",
                token_ids=(current.token_id, following.token_id),
                evidence_token_ids=(current.token_id, following.token_id),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=(
                    f"'{current.surface_plain or current.surface}' szerkezetes (status constructus) "
                    f"állapotban áll, közvetlenül '{following.surface_plain or following.surface}' előtt."
                ),
            )
        )
    return patterns


def _detect_infinitive_absolute_with_finite_verb(verse: VerseAnalysis) -> list[DetectedPattern]:
    patterns: list[DetectedPattern] = []
    tokens = sorted(verse.tokens, key=lambda t: t.word_index)
    infinitives = [t for t in tokens if t.morphology.verb_form == "Infinitive Absolute"]
    for infinitive in infinitives:
        for other in tokens:
            if other.token_id == infinitive.token_id:
                continue
            if other.morphology.verb_form not in _FINITE_VERB_FORMS:
                continue
            if other.lemma != infinitive.lemma:
                continue
            if abs(other.word_index - infinitive.word_index) > _ADJACENCY_WINDOW:
                continue
            patterns.append(
                DetectedPattern(
                    pattern_id=f"{verse.verse_id}.infabs.{infinitive.token_id}.{other.token_id}",
                    pattern_type="infinitive_absolute_with_finite_verb",
                    token_ids=(infinitive.token_id, other.token_id),
                    evidence_token_ids=(infinitive.token_id, other.token_id),
                    detector_version=DETECTOR_VERSION,
                    confidence="certain",
                    explanation_hu=(
                        f"Az abszolút infinitivus '{infinitive.surface_plain or infinitive.surface}' "
                        f"ugyanabból a szótőből képzett véges igealak ('{other.surface_plain or other.surface}') "
                        f"közelében fordul elő."
                    ),
                )
            )
    return patterns


def _detect_independent_pronoun_verb_agreement(verse: VerseAnalysis) -> list[DetectedPattern]:
    patterns: list[DetectedPattern] = []
    tokens = sorted(verse.tokens, key=lambda t: t.word_index)
    pronouns = [t for t in tokens if t.morphology.pronoun_type == "Personal"]
    for pronoun in pronouns:
        for other in tokens:
            if other.token_id == pronoun.token_id:
                continue
            if other.morphology.verb_form not in _FINITE_VERB_FORMS:
                continue
            if abs(other.word_index - pronoun.word_index) > _ADJACENCY_WINDOW:
                continue
            if not other.morphology.person or not other.morphology.number:
                continue
            if other.morphology.person != pronoun.morphology.person:
                continue
            if other.morphology.number != pronoun.morphology.number:
                continue
            patterns.append(
                DetectedPattern(
                    pattern_id=f"{verse.verse_id}.pronoun_agreement.{pronoun.token_id}.{other.token_id}",
                    pattern_type="explicit_pronoun_finite_verb_agreement",
                    token_ids=(pronoun.token_id, other.token_id),
                    evidence_token_ids=(pronoun.token_id, other.token_id),
                    detector_version=DETECTOR_VERSION,
                    confidence="certain",
                    explanation_hu=(
                        f"A kifejezett önálló névmás '{pronoun.surface_plain or pronoun.surface}' és a közeli "
                        f"véges igealak '{other.surface_plain or other.surface}' személy- és számjelölése megegyezik "
                        f"({pronoun.morphology.person}, {pronoun.morphology.number})."
                    ),
                )
            )
    return patterns


def _detect_repeated_lemma(verse: VerseAnalysis) -> list[DetectedPattern]:
    by_lemma: dict[str, list[TokenAnalysis]] = {}
    for token in verse.tokens:
        if not token.lemma:
            continue
        by_lemma.setdefault(token.lemma, []).append(token)
    patterns = []
    for lemma, occurrences in by_lemma.items():
        if len(occurrences) < 2:
            continue
        patterns.append(
            DetectedPattern(
                pattern_id=f"{verse.verse_id}.repeated_lemma.{lemma}",
                pattern_type="repeated_lemma_in_verse",
                token_ids=tuple(t.token_id for t in occurrences),
                evidence_token_ids=tuple(t.token_id for t in occurrences),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=f"A(z) '{lemma}' szótő {len(occurrences)}-szer fordul elő ebben a versben.",
            )
        )
    return patterns


def _detect_ketiv_qere_presence(verse: VerseAnalysis) -> list[DetectedPattern]:
    tokens_with_variant = [t for t in verse.tokens if t.ketiv or t.qere]
    if not tokens_with_variant:
        return []
    return [
        DetectedPattern(
            pattern_id=f"{verse.verse_id}.ketiv_qere",
            pattern_type="ketiv_qere_present",
            token_ids=tuple(t.token_id for t in tokens_with_variant),
            evidence_token_ids=tuple(t.token_id for t in tokens_with_variant),
            detector_version=DETECTOR_VERSION,
            confidence="certain",
            explanation_hu=(
                f"Ebben a versben {len(tokens_with_variant)} szónál van dokumentált ketiv/kere "
                "(írott/olvasott alak) eltérés."
            ),
        )
    ]


def _detect_multicomponent_prefix_structures(verse: VerseAnalysis) -> list[DetectedPattern]:
    patterns = []
    for token in verse.tokens:
        prefix_components = [c for c in token.components if c.role == "prefix"]
        if len(prefix_components) < 2:
            continue
        labels = [c.morphology.part_of_speech or c.role_label_hu for c in prefix_components]
        patterns.append(
            DetectedPattern(
                pattern_id=f"{verse.verse_id}.multi_prefix.{token.token_id}",
                pattern_type="multicomponent_prefix_structure",
                token_ids=(token.token_id,),
                evidence_token_ids=tuple(c.component_id for c in prefix_components),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=(
                    f"'{token.surface}' {len(prefix_components)} elöljáró/kötőszói/névelői komponensből "
                    f"épül fel ({' + '.join(labels)})."
                ),
            )
        )
    return patterns


__all__ = ["DETECTOR_VERSION", "detect_patterns"]
