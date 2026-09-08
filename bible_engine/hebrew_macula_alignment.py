"""Phase 2D — deterministic Textus/TAHOT <-> MACULA token alignment.

Evidence priority, per the Phase 2D brief (§7), implemented in this order:

1. **Canonical verse reference** — alignment is only ever attempted between
   a TAHOT token and MACULA leaves already known to belong to the SAME
   verse (the caller passes one verse's tokens against that verse's
   ``MaculaSentence`` only; this module never searches across verses).
2. **Source/token ordering** — MACULA's ``ref`` attribute carries a
   per-verse orthographic-word ordinal (``"RUT 1:1!7"`` -> word 7) that was
   empirically verified (see ``bible_engine.macula_lowfat_parser``'s
   module docstring) to equal TAHOT's own ``word_index``. This is the
   PRIMARY key: a TAHOT token's ``word_index`` is looked up directly
   against ``MaculaSentence.leaves_by_ref_word()``.
3. **Normalized surface** and 4. **component surface sequence** — once the
   right MACULA leaf bucket is found, components are paired against
   leaves by left-to-right position, and every pair's surface is compared
   after cantillation/niqqud stripping as corroborating evidence.
5. **Lemma** and 6. **Strong identifier** — compared where both sides
   carry one (MACULA's ``strongnumberx``/``oshb-strongs`` against TAHOT's
   own Strong id, numeric-prefix-only since the lettered-homograph
   convention differs between the two sources — see the module's
   ``_strong_numeric_prefix``).
7. **Morphology** is used only as validation evidence in ``evidence``
   text, never to decide alignment on its own, and NEVER to overwrite a
   TAHOT/TEHMC-decoded value (see ``docs/hebrew_analysis_v2_phase2d.md``
   §4 for the full authority-rule writeup).

No fuzzy matching is silent: every alignment carries an explicit
``alignment_type`` (``EXACT`` / ``COMPOSITE`` / ``VALIDATED_FALLBACK`` /
``UNRESOLVED``) and an ``evidence`` string stating exactly why.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from bible_engine.hebrew_parser import HebrewComponent, HebrewToken
from bible_engine.macula_lowfat_parser import MaculaLeaf, MaculaSentence, strip_hebrew_points

ALIGNMENT_TYPES = ("EXACT", "COMPOSITE", "VALIDATED_FALLBACK", "UNRESOLVED")

_PUNCTUATION_ONLY_RE = re.compile(r"^[־׀׃׆﬩:\\/-]*$")


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


def _is_punctuation_only(surface: str) -> bool:
    consonants = strip_hebrew_points(surface)
    return not consonants or bool(_PUNCTUATION_ONLY_RE.match(consonants))


def _ordered_alignable_components(token: HebrewToken) -> list[HebrewComponent]:
    """TAHOT's own prefix->core->suffix order, with pure-punctuation
    structural suffix components (sentence-final punctuation, maqaf marks
    — never their own MACULA morpheme, see Phase 2C's ``not_applicable``
    per-component confidence handling) excluded, since MACULA's tree
    genuinely has no corresponding leaf for them."""
    ordered = list(token.prefix_components)
    if token.core_component is not None:
        ordered.append(token.core_component)
    ordered.extend(token.suffix_components)
    return [component for component in ordered if not _is_punctuation_only(component.surface)]


def align_token(token: HebrewToken, token_id: str, sentence: MaculaSentence | None) -> TokenAlignment:
    components = _ordered_alignable_components(token)
    if sentence is None:
        return _unresolved(token, token_id, components, "no MACULA sentence available for this verse")

    buckets = sentence.leaves_by_ref_word()
    leaves = buckets.get(token.word_index, [])

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

    corroborated = 0
    for component, leaf in paired:
        if _surfaces_agree(component.surface, leaf.surface) or _lemmas_agree(component, leaf) or _strong_ids_agree(
            component, leaf
        ):
            corroborated += 1

    alignment_type = "EXACT" if len(paired) == 1 else "COMPOSITE"
    if corroborated < len(paired):
        alignment_type = "VALIDATED_FALLBACK"
        confidence = "probable" if corroborated > 0 else "low"
    else:
        confidence = "certain"

    evidence = (
        f"word_index={token.word_index} matched MACULA ref word number; "
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


def _validated_fallback_or_unresolved(
    token: HebrewToken,
    token_id: str,
    components: list[HebrewComponent],
    leaves: list[MaculaLeaf],
    non_empty: list[MaculaLeaf],
) -> TokenAlignment:
    """Component/leaf counts disagree even after empty-leaf filtering (e.g.
    a MACULA lexical-compound leaf spanning what TAHOT treats as more than
    one component's surface — see the module docstring's Bethlehem case,
    which this module resolves earlier via ref-number grouping, not here;
    this path is for genuine remaining mismatches). Attempt one whole-token
    corroboration via concatenated surface containment before giving up."""
    token_surface_norm = strip_hebrew_points(token.surface.replace("/", ""))
    leaf_surface_norm = strip_hebrew_points("".join(leaf.surface for leaf in non_empty))
    if token_surface_norm and leaf_surface_norm and (
        token_surface_norm in leaf_surface_norm or leaf_surface_norm in token_surface_norm
    ):
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
]
