"""Phase 2B §8 — deterministic Greek construction detection.

Every detector reports a STRUCTURAL FACT only — never an interpretation
(task §7/§9: phrase co-membership is not modification, dependency proximity
is not emphasis, participle morphology is not automatically a temporal/
causal/concessive function, genitive case is not automatically possessive).
``explanation_hu`` strings below are deliberately flat and structural,
mirroring the Hebrew pattern-detector convention
(``bible_engine.hebrew_pattern_detection``).

Detectors are grouped by the evidence tier they require:

- Token-morphology-only (work on EVERY verse, any book, Phase 2A alone):
  repeated lemma, negation, article+participle, preposition+case,
  infinitive constructions, ἵνα/ὅτι/conditional-marker presence, relative
  pronoun presence.
- Syntax-grounded (require ``bible_engine.greek_syntax_service.attach_syntax``
  to have populated ``verse.clauses`` — only the 9 books this phase
  downloaded lowfat XML for, see the phase doc §1): genitive absolute
  (structurally requires clause-boundary evidence to distinguish it from an
  ordinary genitive noun+participle phrase — see the audit's §8 finding),
  coordinated structures (reported with syntax evidence when available,
  degraded to a lower-confidence token-only report otherwise).
"""

from __future__ import annotations

from bible_engine.greek_analysis_bundle import GreekDetectedPattern, GreekTokenAnalysis, GreekVerseAnalysis

DETECTOR_VERSION = "greek-2b-v1"

_NEGATION_LEMMAS = {"μή", "οὐ", "οὐκ", "οὐχ", "οὐχί"}
_RELATIVE_LEMMAS = {"ὅς", "ἥ", "ὅ", "ὅστις", "ἥτις", "ὅ τι"}
_CONDITIONAL_LEMMAS = {"εἰ", "ἐάν"}


def detect_patterns(verse: GreekVerseAnalysis) -> tuple[GreekDetectedPattern, ...]:
    patterns: list[GreekDetectedPattern] = []
    patterns.extend(_detect_repeated_lemma(verse))
    patterns.extend(_detect_negation(verse))
    patterns.extend(_detect_article_participle(verse))
    patterns.extend(_detect_preposition_case(verse))
    patterns.extend(_detect_infinitive_construction(verse))
    patterns.extend(_detect_lemma_marked_clause(verse, "ἵνα", "hina_clause_marker"))
    patterns.extend(_detect_lemma_marked_clause(verse, "ὅτι", "hoti_clause_marker"))
    patterns.extend(_detect_conditional_marker(verse))
    patterns.extend(_detect_relative_pronoun(verse))
    patterns.extend(_detect_genitive_absolute(verse))
    patterns.extend(_detect_coordinated_structures(verse))
    return tuple(patterns)


def _pattern_id(verse: GreekVerseAnalysis, pattern_type: str, suffix: str) -> str:
    return f"{verse.verse_id}.{pattern_type}.{suffix}"


def _detect_repeated_lemma(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    by_lemma: dict[str, list[GreekTokenAnalysis]] = {}
    for token in verse.tokens:
        if token.lemma:
            by_lemma.setdefault(token.lemma, []).append(token)
    patterns = []
    for lemma, tokens in by_lemma.items():
        if len(tokens) < 2:
            continue
        token_ids = tuple(t.token_id for t in tokens)
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "repeated_lemma", lemma),
                pattern_type="repeated_lemma_in_verse",
                token_ids=token_ids,
                evidence_token_ids=token_ids,
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=f"A(z) \"{lemma}\" lemma {len(tokens)}-szer fordul elő ebben a versben.",
            )
        )
    return patterns


def _detect_negation(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    negations = [t for t in verse.tokens if t.lemma in _NEGATION_LEMMAS]
    if len(negations) < 2:
        return []
    token_ids = tuple(t.token_id for t in negations)
    return [
        GreekDetectedPattern(
            pattern_id=_pattern_id(verse, "multiple_negation", "1"),
            pattern_type="multiple_negation",
            token_ids=token_ids,
            evidence_token_ids=token_ids,
            detector_version=DETECTOR_VERSION,
            confidence="certain",
            explanation_hu=f"{len(negations)} tagadószó szerepel ebben a mondatban.",
        )
    ]


def _agree(a: GreekTokenAnalysis, b: GreekTokenAnalysis) -> bool:
    m1, m2 = a.morphology, b.morphology
    return bool(m1.case and m1.case == m2.case) and bool(m1.number and m1.number == m2.number)


def _detect_article_participle(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    patterns = []
    tokens = verse.tokens
    for i in range(len(tokens) - 1):
        article, following = tokens[i], tokens[i + 1]
        if article.morphology.part_of_speech != "határozott névelő":
            continue
        if following.morphology.verb_form != "participle":
            continue
        if not _agree(article, following):
            continue
        token_ids = (article.token_id, following.token_id)
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "article_participle", str(i)),
                pattern_type="article_plus_participle",
                token_ids=token_ids,
                evidence_token_ids=token_ids,
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=(
                    "Határozott névelő közvetlenül egy vele egyeztetett (eset, szám) "
                    "igenevet előz meg."
                ),
            )
        )
    return patterns


def _detect_preposition_case(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    patterns = []
    tokens = verse.tokens
    for i in range(len(tokens) - 1):
        prep = tokens[i]
        if prep.morphology.part_of_speech != "elöljárószó":
            continue
        following = tokens[i + 1]
        governed = following
        # Article-mediated: prep + article + noun (article shares the case).
        if following.morphology.part_of_speech == "határozott névelő" and i + 2 < len(tokens):
            governed = tokens[i + 2]
        if not governed.morphology.case:
            continue
        token_ids = tuple(dict.fromkeys((prep.token_id, following.token_id, governed.token_id)))
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "preposition_case", str(i)),
                pattern_type="preposition_plus_case",
                token_ids=token_ids,
                evidence_token_ids=token_ids,
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=(
                    f"Elöljárószó ({prep.lemma}) {governed.morphology.case} esetű bővítménnyel."
                ),
            )
        )
    return patterns


def _detect_infinitive_construction(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    infinitives = [t for t in verse.tokens if t.morphology.verb_form == "infinitive"]
    patterns = []
    for token in infinitives:
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "infinitive_construction", token.token_id),
                pattern_type="infinitive_construction",
                token_ids=(token.token_id,),
                evidence_token_ids=(token.token_id,),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=f"\"{token.surface}\" főnévi igenévi alak.",
            )
        )
    return patterns


def _detect_lemma_marked_clause(
    verse: GreekVerseAnalysis, lemma: str, pattern_type: str
) -> list[GreekDetectedPattern]:
    patterns = []
    for token in verse.tokens:
        if token.lemma != lemma:
            continue
        containing = [c for c in verse.clauses if token.token_id in c.token_ids]
        # The MOST SPECIFIC (fewest-token) enclosing clause — clauses form a
        # nesting hierarchy in document order, so the first match is often
        # the outermost sentence-level clause rather than the actual ἵνα/
        # ὅτι sub-clause.
        clause = min(containing, key=lambda c: len(c.token_ids)) if containing else None
        token_ids = clause.token_ids if clause is not None else (token.token_id,)
        confidence = "certain" if clause is not None else "probable"
        note = (
            f"\"{lemma}\" kötőszóval bevezetett tagmondat (a tagmondat határa szintaktikailag adatolt)."
            if clause is not None
            else f"\"{lemma}\" kötőszó jelen van a mondatban (a tagmondat pontos határa itt nem adatolt)."
        )
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, pattern_type, token.token_id),
                pattern_type=pattern_type,
                token_ids=token_ids,
                evidence_token_ids=(token.token_id,),
                detector_version=DETECTOR_VERSION,
                confidence=confidence,
                explanation_hu=note,
            )
        )
    return patterns


def _detect_conditional_marker(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    patterns = []
    for token in verse.tokens:
        if token.lemma not in _CONDITIONAL_LEMMAS:
            continue
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "conditional_marker", token.token_id),
                pattern_type="conditional_clause_marker",
                token_ids=(token.token_id,),
                evidence_token_ids=(token.token_id,),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=f"\"{token.surface}\" feltételes kötőszó jelen van a mondatban.",
            )
        )
    return patterns


def _detect_relative_pronoun(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    patterns = []
    for token in verse.tokens:
        if token.morphology.pronoun_type != "vonatkozó névmás":
            continue
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "relative_pronoun", token.token_id),
                pattern_type="relative_clause_marker",
                token_ids=(token.token_id,),
                evidence_token_ids=(token.token_id,),
                detector_version=DETECTOR_VERSION,
                confidence="certain",
                explanation_hu=f"\"{token.surface}\" vonatkozó névmás jelen van a mondatban.",
            )
        )
    return patterns


def _detect_genitive_absolute(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    """Requires clause-boundary evidence (audit §8: pure morphology cannot
    distinguish a genitive absolute from an ordinary genitive noun+
    participle phrase) — only fires for syntax-grounded verses."""
    if not verse.clauses:
        return []
    tokens_by_id = {t.token_id: t for t in verse.tokens}
    patterns = []
    for clause in verse.clauses:
        if clause.parent_clause_id is None:
            continue  # the sentence's own root clause is never itself an absolute
        clause_tokens = [tokens_by_id[tid] for tid in clause.token_ids if tid in tokens_by_id]
        genitive_nominal = next(
            (
                t for t in clause_tokens
                if t.morphology.case == "birtokos eset"
                and t.morphology.part_of_speech in ("főnév", "személyes névmás", "mutató névmás")
            ),
            None,
        )
        genitive_participle = next(
            (
                t for t in clause_tokens
                if t.morphology.case == "birtokos eset" and t.morphology.verb_form == "participle"
            ),
            None,
        )
        if genitive_nominal is None or genitive_participle is None:
            continue
        token_ids = (genitive_nominal.token_id, genitive_participle.token_id)
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "genitive_absolute", clause.clause_id),
                pattern_type="genitive_absolute_candidate",
                token_ids=token_ids,
                evidence_token_ids=tuple(clause.token_ids),
                detector_version=DETECTOR_VERSION,
                confidence="probable",
                explanation_hu=(
                    "Birtokos esetű névszó és birtokos esetű igenév egy önálló, "
                    "a főmondattól elkülönülő tagmondatban — genitivus absolutus jelölt."
                ),
            )
        )
    return patterns


def _detect_coordinated_structures(verse: GreekVerseAnalysis) -> list[GreekDetectedPattern]:
    patterns = []
    phrases_by_id = {p.phrase_id: p for p in verse.phrases}
    siblings_by_parent: dict[str | None, list] = {}
    for phrase in verse.phrases:
        siblings_by_parent.setdefault(phrase.parent_phrase_id, []).append(phrase)

    coord_conjunctions = [t for t in verse.tokens if t.lemma in {"καί", "δέ"}]
    if not coord_conjunctions:
        return []

    if verse.phrases:
        for parent_id, siblings in siblings_by_parent.items():
            same_type = {}
            for s in siblings:
                same_type.setdefault(s.phrase_type, []).append(s)
            for phrase_type, group in same_type.items():
                if len(group) < 2:
                    continue
                token_ids = tuple(tid for p in group for tid in p.token_ids)
                patterns.append(
                    GreekDetectedPattern(
                        pattern_id=_pattern_id(verse, "coordinated_structure", f"{parent_id}.{phrase_type}"),
                        pattern_type="coordinated_structure",
                        token_ids=token_ids,
                        evidence_token_ids=tuple(p.phrase_id for p in group),
                        detector_version=DETECTOR_VERSION,
                        confidence="probable",
                        explanation_hu=(
                            f"{len(group)} azonos típusú ({phrase_type}) szerkezet szerepel "
                            "közös szülő alatt, kötőszóval a versben."
                        ),
                    )
                )
    else:
        token_ids = tuple(t.token_id for t in coord_conjunctions)
        patterns.append(
            GreekDetectedPattern(
                pattern_id=_pattern_id(verse, "coordinated_structure", "token_only"),
                pattern_type="coordinated_structure",
                token_ids=token_ids,
                evidence_token_ids=token_ids,
                detector_version=DETECTOR_VERSION,
                confidence="probable",
                explanation_hu=(
                    "Mellérendelő kötőszó jelen van a mondatban (a mellérendelt "
                    "szerkezetek pontos határa itt nem adatolt)."
                ),
            )
        )
    return patterns
