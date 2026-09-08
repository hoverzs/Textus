"""Phase 2D.1 — deterministic diagnostic classification for UNRESOLVED
(and, on request, weak VALIDATED_FALLBACK) TAHOT<->MACULA alignments.

Purpose: turn "5,826 unresolved tokens" into an explained, categorized
population, per docs/hebrew_analysis_v2_phase2d1.md §3. Every case gets
exactly one category from a fixed taxonomy, assigned by fixed-priority
deterministic rules — never a guess, never an LLM call.

Categories (checked in this order; first match wins):

1. ``ketiv_qere`` — the token has a recorded Ketiv/Qere pair.
2. ``textual_reference_numbering_gap`` — TAHOT's own STEPBible-Data
   convention for a supplied/bracketed reading (word_index >= 500, see
   the Genesis 4:8 case in docs/hebrew_analysis_v2_phase2d.md §5.2).
3. ``punctuation_non_lexical_node_difference`` — the token has no
   alignable (non-punctuation, non-Aramaic-state-suffix) components at
   all after filtering — nothing genuinely lexical to align.
4. ``maqaf_related_segmentation`` — the token is maqaf-joined.
5. ``aramaic_specific_segmentation`` — the token's language is Aramaic and
   none of the categories above explain it (i.e. something Aramaic-
   specific beyond the already-handled determinative-state suffix).
6. ``macula_missing_node`` — MACULA has zero leaves at the token's ref
   position AND the bounded nearby-offset search (Phase 2D.1) also found
   nothing — a genuine content gap, not just a numbering shift.
7. ``component_segmentation_mismatch`` — MACULA has leaves at that
   position but the component/leaf count could not be reconciled; the
   ``direction`` sub-field records whether TAHOT or MACULA has more
   pieces.
8. ``lemma_difference`` — reserved: only assigned when a future consumer
   supplies independent lemma-comparison evidence not currently computed
   here (``HebrewComponent`` carries no lemma field — see
   ``hebrew_macula_alignment._lemmas_agree``). Never assigned by this
   module today; included in the taxonomy for forward compatibility.
9. ``true_source_text_difference`` — reserved similarly: would require
   confirming TAHOT and MACULA's underlying editions genuinely diverge at
   this word, which this module cannot determine from alignment evidence
   alone. Not assigned today.
10. ``unknown`` — nothing above applies; the diagnosis genuinely doesn't
    know why this case failed. Kept honest rather than mis-categorized.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from bible_engine.hebrew_macula_alignment import TokenAlignment, ordered_alignable_components
from bible_engine.hebrew_parser import HebrewToken
from bible_engine.macula_lowfat_parser import MaculaSentence

CATEGORIES = (
    "ketiv_qere",
    "textual_reference_numbering_gap",
    "punctuation_non_lexical_node_difference",
    "maqaf_related_segmentation",
    "aramaic_specific_segmentation",
    "macula_missing_node",
    "surface_normalization_difference",
    "component_segmentation_mismatch",
    "lemma_difference",
    "true_source_text_difference",
    "unknown",
)

_SUPPLIED_TEXT_WORD_INDEX_THRESHOLD = 500


@dataclass(frozen=True)
class UnresolvedDiagnosis:
    category: str
    verse_ref: str
    token_id: str
    surface: str
    word_index: int
    language: str
    direction: str = ""  # "tahot_more" | "macula_more" | "" — only for component_segmentation_mismatch
    candidate_macula_leaf_ids: tuple[str, ...] = field(default_factory=tuple)
    evidence: str = ""


def classify_unresolved(
    token: HebrewToken,
    token_id: str,
    verse_ref: str,
    alignment: TokenAlignment,
    sentence: MaculaSentence | None,
) -> UnresolvedDiagnosis:
    """Classify one UNRESOLVED ``TokenAlignment``. Calling this on a
    non-UNRESOLVED alignment is a caller error but harmless — the
    category rules below only inspect the token/sentence, not the
    alignment's own type, aside from reusing its ``evidence`` text."""
    base = dict(
        verse_ref=verse_ref,
        token_id=token_id,
        surface=token.surface,
        word_index=token.word_index,
        language=(token.language or "").lower(),
    )

    if token.ketiv or token.qere:
        return UnresolvedDiagnosis(
            category="ketiv_qere",
            evidence=f"ketiv={token.ketiv!r} qere={token.qere!r}; {alignment.evidence}",
            **base,
        )

    if token.word_index >= _SUPPLIED_TEXT_WORD_INDEX_THRESHOLD:
        return UnresolvedDiagnosis(
            category="textual_reference_numbering_gap",
            evidence=(
                f"word_index={token.word_index} >= {_SUPPLIED_TEXT_WORD_INDEX_THRESHOLD} "
                f"(STEPBible-Data supplied/bracketed-reading convention); {alignment.evidence}"
            ),
            **base,
        )

    alignable = ordered_alignable_components(token)
    if not alignable:
        return UnresolvedDiagnosis(
            category="punctuation_non_lexical_node_difference",
            evidence=f"no alignable (non-punctuation, non-state-suffix) components; {alignment.evidence}",
            **base,
        )

    if token.maqaf:
        return UnresolvedDiagnosis(
            category="maqaf_related_segmentation",
            evidence=f"token.maqaf=True; {alignment.evidence}",
            **base,
        )

    if base["language"] == "aramaic":
        return UnresolvedDiagnosis(
            category="aramaic_specific_segmentation",
            evidence=f"language=aramaic, not explained by ketiv/qere, maqaf, or the state-suffix rule; {alignment.evidence}",
            **base,
        )

    leaves_at_position: list = []
    if sentence is not None:
        leaves_at_position = sentence.leaves_by_ref_word().get(token.word_index, [])

    if not leaves_at_position:
        return UnresolvedDiagnosis(
            category="macula_missing_node",
            evidence=(
                f"zero MACULA leaves at ref word {token.word_index}, and the bounded nearby-offset "
                f"search also found no corroborated candidate; {alignment.evidence}"
            ),
            **base,
        )

    if len(alignable) == len(leaves_at_position) and "zero corroborating" in alignment.evidence:
        return UnresolvedDiagnosis(
            category="surface_normalization_difference",
            candidate_macula_leaf_ids=tuple(leaf.macula_node_id for leaf in leaves_at_position),
            evidence=(
                f"component/leaf counts match ({len(alignable)}) but zero surface/lemma/Strong-id "
                f"corroboration at this ref position; {alignment.evidence}"
            ),
            **base,
        )

    direction = "tahot_more" if len(alignable) > len(leaves_at_position) else (
        "macula_more" if len(leaves_at_position) > len(alignable) else ""
    )
    return UnresolvedDiagnosis(
        category="component_segmentation_mismatch",
        direction=direction,
        candidate_macula_leaf_ids=tuple(leaf.macula_node_id for leaf in leaves_at_position),
        evidence=(
            f"TAHOT {len(alignable)} alignable component(s) vs MACULA {len(leaves_at_position)} "
            f"leaf(ves) at this ref position, uncorroborated; {alignment.evidence}"
        ),
        **base,
    )


__all__ = ["CATEGORIES", "UnresolvedDiagnosis", "classify_unresolved"]
