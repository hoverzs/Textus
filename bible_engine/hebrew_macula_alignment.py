"""Phase 2D — deterministic Textus/TAHOT <-> MACULA token alignment.

Evidence priority, per the Phase 2D brief (§7), implemented in this order:

1. **Canonical verse reference** — alignment is only ever attempted between
   a TAHOT token and MACULA leaves already known to belong to the SAME
   verse (the caller passes one verse's tokens against that verse's
   ``MaculaSentence`` only; this module never searches across verses).
2. **Source/token ordering** — MACULA's ``ref`` attribute carries a
   per-verse orthographic-word ordinal (``"RUT 1:1!7"`` -> word 7) that was
   empirically verified (see ``bible_engine.macula_lowfat_parser``'s
   module docstring) to equal TAHOT's own ``word_index`` in the COMMON
   case. It is the PRIMARY key, tried first — but see §Phase 2D.1 below
   for the bounded local-recovery search used only when the direct lookup
   fails.
3. **Normalized surface** and 4. **component surface sequence** — once a
   candidate MACULA leaf bucket is found (primary position or a recovered
   nearby one), components are paired against leaves by left-to-right
   position, and every pair's surface is compared after cantillation/
   niqqud stripping as corroborating evidence.
5. **Lemma** (folded into the token-level surface/Strong-id comparison —
   see §3-4; no separate per-component lemma field exists on
   ``HebrewComponent``) and 6. **Strong identifier** — compared where both
   sides carry one, numeric-prefix-only (STEPBible's lettered-homograph
   convention differs from MACULA's own id scheme).
7. **Morphology** is used only as validation evidence in ``evidence``
   text, never to decide alignment on its own, and NEVER to overwrite a
   TAHOT/TEHMC-decoded value (see ``docs/hebrew_analysis_v2_phase2d.md``
   §4 for the full authority-rule writeup).

No fuzzy matching is silent: every alignment carries an explicit
``alignment_type`` (``EXACT`` / ``COMPOSITE`` / ``VALIDATED_FALLBACK`` /
``UNRESOLVED``) and an ``evidence`` string stating exactly why.

Phase 2D.1 — bounded local reference-number recovery
=====================================================

Phase 2D's corpus-wide audit found that MACULA's ``ref`` word-number is
NOT always identical to TAHOT's ``word_index`` even for a word MACULA DOES
contain: verified on Ruth 1:8, TAHOT word_index 10 (``יַ֣עַשׂ``, the
Qere of a Ketiv/Qere pair) has NO MACULA leaf at ``ref=...!10`` — but
``ref=...!11`` carries that EXACT word (``יַ֣עַשׂ``), one position later
than expected, with every subsequent word in the verse shifted the same
way. This is a genuine MACULA ref-numbering quirk around a Ketiv/Qere
boundary, not a missing word — and it turned out NOT to be a one-way,
verse-wide constant shift in general (Genesis 13:3 was found to have
MACULA assign one MORE ref number than TAHOT has word_index values for
that verse, i.e. the opposite direction).

Given the shift is neither always the same size nor always the same
direction, this module does NOT apply a cumulative, verse-wide offset
(that would risk exactly the "one gap shifts everything after it"
cascade failure mode the Phase 2D.1 brief explicitly warns against).
Instead, when the primary ``word_index``-keyed lookup fails or does not
fully corroborate, ``align_token`` makes a bounded, PER-TOKEN,
evidence-gated search of nearby ref numbers
(``_NEARBY_OFFSET_SEARCH_ORDER``, closest first) — each candidate is
scored with the exact same component-pairing + surface/Strong-id
corroboration logic as the primary position, and is only accepted if
EVERY paired component fully corroborates (the same bar as a primary
``EXACT``/``COMPOSITE`` match). A recovered match is still reported as
``VALIDATED_FALLBACK`` (never ``EXACT``/``COMPOSITE``) — the ref-number
position itself was not the one TAHOT's own ordering predicted, so full
certainty is never claimed even when every other signal agrees. If more
than one nearby offset would independently fully corroborate, the
recovery is refused (stays ``UNRESOLVED``, evidence records the
ambiguity) rather than silently guessing between them.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bible_engine.hebrew_parser import HebrewComponent, HebrewToken
from bible_engine.macula_lowfat_parser import MaculaLeaf, MaculaSentence, strip_hebrew_points

ALIGNMENT_TYPES = ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK", "UNRESOLVED")

_PUNCTUATION_ONLY_RE = re.compile(r"^[־׀׃׆﬩:\\/-]*$")

# Closest candidates first; a bound of 5 comfortably covers every corpus
# case found during the Phase 2D.1 audit (the largest observed cluster of
# consecutive genuine MACULA ref-numbering gaps in one verse was 3).
_NEARBY_OFFSET_SEARCH_ORDER = (1, -1, 2, -2, 3, -3, 4, -4, 5, -5)

# Aramaic's determinative/emphatic-state suffix (a bare, unpointed א/ה/ן
# after niqqud-stripping) is realized in TAHOT as its own trailing
# "suffix"-role component, but MACULA's lowfat leaves do not split it out
# as a separate morpheme — verified corpus-wide (Phase 2D.1 §4): excluding
# it from the alignable-component count the same way empty/implicit
# leaves already are (see ordered_alignable_components) resolves this
# specific, language-general pattern without any Hebrew/Aramaic branching
# in the matching logic itself.
_ARAMAIC_STATE_SUFFIXES = frozenset({"א", "ה", "ן"})

# Minimum consonant length for whole-token substring-containment evidence
# to be trusted on its own — see _validated_fallback_or_unresolved.
_MIN_CONTAINMENT_CONSONANTS = 3


@dataclass(frozen=True)
class ComponentAlignment:
    component_index: int | None  # None = whole-token alignment (single-component token)
    macula_leaf_id: str | None


@dataclass(frozen=True)
class TokenAlignment:
    token_id: str
    word_index: int
    alignment_type: str
    confidence: str
    evidence: str
    components: tuple[ComponentAlignment, ...]


def _strong_numeric_prefix(value: str) -> str:
    match = re.match(r"H?0*(\d+)", (value or "").upper())
    return match.group(1) if match else ""


def is_punctuation_only(surface: str) -> bool:
    consonants = strip_hebrew_points(surface)
    return not consonants or bool(_PUNCTUATION_ONLY_RE.match(consonants))


def is_aramaic_state_suffix(component: HebrewComponent) -> bool:
    return component.role == "suffix" and strip_hebrew_points(component.surface) in _ARAMAIC_STATE_SUFFIXES


def ordered_alignable_components(token: HebrewToken) -> list[HebrewComponent]:
    """TAHOT's own prefix->core->suffix order, with two component classes
    excluded because MACULA's tree genuinely has no corresponding leaf for
    either — not a matching failure, a real representational difference:

    - pure-punctuation structural suffix components (sentence-final
      punctuation, maqaf marks — see Phase 2C's ``not_applicable``
      per-component confidence handling);
    - the Aramaic determinative/emphatic-state suffix (Phase 2D.1, see
      module docstring and ``is_aramaic_state_suffix``) — language-general
      because the check is purely structural (role + stripped surface),
      never an ``if language == "aramaic"`` branch.
    """
    ordered = list(token.prefix_components)
    if token.core_component is not None:
        ordered.append(token.core_component)
    ordered.extend(token.suffix_components)
    return [
        component
        for component in ordered
        if not is_punctuation_only(component.surface) and not is_aramaic_state_suffix(component)
    ]


def align_token(token: HebrewToken, token_id: str, sentence: MaculaSentence | None) -> TokenAlignment:
    components = ordered_alignable_components(token)
    if sentence is None:
        return _unresolved(token, token_id, components, "no MACULA sentence available for this verse")

    buckets = sentence.leaves_by_ref_word()
    primary = _match_at_ref_word(token, token_id, components, buckets, token.word_index)
    if primary.alignment_type != "UNRESOLVED":
        return primary

    recovered = _search_nearby_ref_offsets(token, token_id, components, buckets)
    return recovered if recovered is not None else primary


def _match_at_ref_word(
    token: HebrewToken,
    token_id: str,
    components: list[HebrewComponent],
    buckets: dict[int, list[MaculaLeaf]],
    ref_word_number: int,
) -> TokenAlignment:
    """Core reconciliation logic for ONE candidate ref-word-number — the
    same routine serves both the primary (``ref_word_number ==
    token.word_index``) and the bounded-recovery (§module docstring)
    lookups; only the caller decides which ``ref_word_number`` to try and
    how to interpret an off-primary-position success."""
    leaves = buckets.get(ref_word_number, [])
    if not leaves:
        return _unresolved(token, token_id, components, "no MACULA leaves found for this word position")

    non_empty = [leaf for leaf in leaves if leaf.surface]

    if len(components) == len(leaves):
        paired = list(zip(components, leaves))
        note = ""
    elif len(components) == len(non_empty):
        paired = list(zip(components, non_empty))
        note = f"; {len(leaves) - len(non_empty)} empty/implicit MACULA leaf(ves) excluded"
    else:
        return _validated_fallback_or_unresolved(token, token_id, components, leaves, non_empty)

    corroborated = sum(1 for component, leaf in paired if _pair_corroborated(component, leaf))

    if corroborated == 0:
        # Phase 2D.1 VALIDATED_FALLBACK audit (§10): a component/leaf COUNT
        # match with zero corroborating surface/lemma/Strong-id agreement
        # is not real evidence of alignment — it is indistinguishable from
        # a coincidental count match at the wrong ref position (see the
        # module docstring's Ruth 1:8 case, word 11, where ref=11
        # coincidentally has exactly 1 leaf but it is a DIFFERENT word).
        # Phase 2D reported this as a weak "low confidence" fallback;
        # Phase 2D.1 treats it honestly as unresolved instead of a guess.
        return _unresolved(
            token,
            token_id,
            components,
            f"component count matched MACULA ref word number {ref_word_number} by position "
            f"({len(paired)} component(s)/leaf(ves)) but zero corroborating surface/lemma/strong "
            f"evidence — treated as unresolved rather than a position-only guess{note}",
        )

    alignment_type = "EXACT" if len(paired) == 1 else "COMPOSITE"
    if corroborated < len(paired):
        alignment_type = "VALIDATED_FALLBACK"
        confidence = "probable"
    else:
        confidence = "certain"

    evidence = (
        f"word_index={token.word_index} matched MACULA ref word number {ref_word_number}; "
        f"{len(paired)} component(s)/leaf(ves) paired by position; "
        f"{corroborated}/{len(paired)} corroborated by surface/lemma/strong{note}"
    )

    component_alignments = tuple(
        ComponentAlignment(
            component_index=(index if len(paired) > 1 else None),
            macula_leaf_id=leaf.macula_node_id,
        )
        for index, (_, leaf) in enumerate(paired)
    )
    return TokenAlignment(
        token_id=token_id,
        word_index=token.word_index,
        alignment_type=alignment_type,
        confidence=confidence,
        evidence=evidence,
        components=component_alignments,
    )


def _pair_corroborated(component: HebrewComponent, leaf: MaculaLeaf) -> bool:
    return _surfaces_agree(component.surface, leaf.surface) or _lemmas_agree(component, leaf) or _strong_ids_agree(
        component, leaf
    )


def _pair_components_with_leaves(
    components: list[HebrewComponent], leaves: list[MaculaLeaf]
) -> list[tuple[HebrewComponent, MaculaLeaf]] | None:
    """Same count-reconciliation ``_match_at_ref_word`` uses (exact count,
    or count after excluding empty/implicit MACULA leaves) — factored out
    so the bounded-recovery search (below) can independently re-check
    surface agreement on the exact same pairing, without re-deriving its
    own pairing logic that could silently drift out of sync."""
    if not leaves:
        return None
    non_empty = [leaf for leaf in leaves if leaf.surface]
    if len(components) == len(leaves):
        return list(zip(components, leaves))
    if len(components) == len(non_empty):
        return list(zip(components, non_empty))
    return None


def _search_nearby_ref_offsets(
    token: HebrewToken,
    token_id: str,
    components: list[HebrewComponent],
    buckets: dict[int, list[MaculaLeaf]],
) -> TokenAlignment | None:
    """Bounded, per-token, evidence-gated recovery — see the module
    docstring's "Phase 2D.1" section. Returns ``None`` (never a fabricated
    result) when no nearby candidate fully corroborates, or when more than
    one does (ambiguous — refuse rather than guess).

    Requires actual SURFACE agreement on every paired component, not just
    Strong-id agreement (``_match_at_ref_word``'s own "certain" bar accepts
    either) — corpus-verified (Phase 2D.1, Ruth 1:8 word 15) that
    Strong-id-only corroboration is too weak once the ref-number position
    itself is already an assumption: a recurring verb root (e.g. עשה,
    Strong 6213) can share its Strong number across two DIFFERENT
    inflected forms sitting at two different nearby ref positions in the
    same short passage, which the primary lookup's own Strong-id-OR-surface
    rule does not distinguish but a recovery search — searching several
    nearby positions at once — genuinely can produce false, ambiguous-
    looking corroboration from. Surface agreement (after cantillation/
    niqqud stripping) does not have this weakness.
    """
    fully_corroborated: list[tuple[int, TokenAlignment]] = []
    for offset in _NEARBY_OFFSET_SEARCH_ORDER:
        candidate_ref = token.word_index + offset
        if candidate_ref < 1 or candidate_ref not in buckets:
            continue
        candidate = _match_at_ref_word(token, token_id, components, buckets, candidate_ref)
        if candidate.alignment_type not in {"EXACT", "COMPOSITE"} or candidate.confidence != "certain":
            continue
        paired = _pair_components_with_leaves(components, buckets[candidate_ref])
        if paired is None:
            continue  # defensive; _match_at_ref_word already reconciled this count
        if not all(_surfaces_agree(component.surface, leaf.surface) for component, leaf in paired):
            continue
        fully_corroborated.append((candidate_ref, candidate))

    if not fully_corroborated:
        return None
    if len(fully_corroborated) > 1:
        candidates_text = ", ".join(f"ref={ref}" for ref, _ in fully_corroborated)
        return _unresolved(
            token,
            token_id,
            components,
            f"ambiguous ref-number recovery: {len(fully_corroborated)} nearby candidates "
            f"({candidates_text}) all fully corroborated — refusing to guess",
        )

    ref_used, candidate = fully_corroborated[0]
    offset_used = ref_used - token.word_index
    # A recovered match is capped at VALIDATED_FALLBACK — see the module
    # docstring: the ref-number position itself was not the one TAHOT's
    # own word ordering predicted, so full certainty is never claimed even
    # when every paired component's surface/Strong id agrees.
    return TokenAlignment(
        token_id=token_id,
        word_index=token.word_index,
        alignment_type="VALIDATED_FALLBACK",
        confidence="probable",
        evidence=(
            f"recovered via bounded local ref-number search (offset={offset_used:+d}, tried ref={ref_used} "
            f"instead of the primary word_index={token.word_index}); originally unresolved at the primary "
            f"position; {candidate.evidence}"
        ),
        components=candidate.components,
    )


def _validated_fallback_or_unresolved(
    token: HebrewToken,
    token_id: str,
    components: list[HebrewComponent],
    leaves: list[MaculaLeaf],
    non_empty: list[MaculaLeaf],
) -> TokenAlignment:
    """Component/leaf counts disagree even after empty-leaf and Aramaic-
    state-suffix filtering (e.g. a MACULA lexical-compound leaf spanning
    what TAHOT treats as more than one component's surface — see the
    module docstring's Bethlehem case, which this module resolves earlier
    via ref-number grouping, not here; this path is for genuine remaining
    mismatches). Attempt one whole-token corroboration via concatenated
    surface containment before giving up.

    Phase 2D.1 VALIDATED_FALLBACK audit (§10): plain substring containment
    is only meaningful evidence once the compared string is long enough
    that a coincidental match is implausible — a bare 2-consonant word
    (e.g. את, לא) is a substring of many unrelated longer strings by pure
    chance. Below ``_MIN_CONTAINMENT_CONSONANTS`` this path requires exact
    equality instead of containment (corpus-verified: only 4/3,490 corpus
    cases were this short, so tightening here costs almost nothing while
    removing a real, if small, false-positive risk)."""
    token_surface_norm = strip_hebrew_points(token.surface.replace("/", ""))
    leaf_surface_norm = strip_hebrew_points("".join(leaf.surface for leaf in non_empty))
    short_string = len(token_surface_norm) < _MIN_CONTAINMENT_CONSONANTS or len(leaf_surface_norm) < _MIN_CONTAINMENT_CONSONANTS
    corroborated = token_surface_norm and leaf_surface_norm and (
        token_surface_norm == leaf_surface_norm
        if short_string
        else (token_surface_norm in leaf_surface_norm or leaf_surface_norm in token_surface_norm)
    )
    if corroborated:
        return TokenAlignment(
            token_id=token_id,
            word_index=token.word_index,
            alignment_type="VALIDATED_FALLBACK",
            confidence="probable",
            evidence=(
                f"component count mismatch (TAHOT {len(components)} vs MACULA {len(leaves)} leaves); "
                f"whole-token surface containment corroborated the word-number match"
            ),
            components=(ComponentAlignment(None, leaves[0].macula_node_id if leaves else None),),
        )
    return _unresolved(
        token,
        token_id,
        components,
        f"component count mismatch (TAHOT {len(components)} vs MACULA {len(leaves)} leaves) and no surface corroboration",
    )


def _unresolved(token: HebrewToken, token_id: str, components: list[HebrewComponent], reason: str) -> TokenAlignment:
    count = max(len(components), 1)
    return TokenAlignment(
        token_id=token_id,
        word_index=token.word_index,
        alignment_type="UNRESOLVED",
        confidence="none",
        evidence=reason,
        components=tuple(ComponentAlignment(None if count <= 1 else i, None) for i in range(count)),
    )


def _surfaces_agree(a: str, b: str) -> bool:
    return bool(a) and bool(b) and strip_hebrew_points(a) == strip_hebrew_points(b)


def _lemmas_agree(component: HebrewComponent, leaf: MaculaLeaf) -> bool:
    # HebrewComponent has no direct lemma field; comparison happens at the
    # token level by the caller when useful. Component-level lemma
    # corroboration is intentionally skipped here (component surface and
    # Strong id are the two signals actually available on HebrewComponent).
    return False


def _strong_ids_agree(component: HebrewComponent, leaf: MaculaLeaf) -> bool:
    left = _strong_numeric_prefix(component.strong_id)
    right = _strong_numeric_prefix(leaf.strong_number or leaf.oshb_strongs)
    return bool(left) and bool(right) and left == right


__all__ = [
    "ALIGNMENT_TYPES",
    "ComponentAlignment",
    "TokenAlignment",
    "align_token",
    "is_aramaic_state_suffix",
    "is_punctuation_only",
    "ordered_alignable_components",
]
