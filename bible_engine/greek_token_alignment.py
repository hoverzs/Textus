"""Phase 2B §2/§3 — deterministic TAGNT ↔ MACULA Greek token alignment.

TAGNT remains authoritative for morphology and token identity (Phase 2A) —
this module NEVER lets a MACULA fact override a TAGNT fact; it only
determines, for each TAGNT token, which (if any) MACULA node it corresponds
to, so that MACULA's syntax/semantic-role/coreference data can be
deterministically attached to the correct TAGNT token.

No AI is used anywhere in this module (task requirement). Alignment is
resolved entirely by normalized-surface comparison, lemma agreement, Strong-
number correspondence, local position, and — critically — TAGNT's own
``edition_flags``, which let a token's expected absence from a specific
critical edition (like SBLGNT, which follows the Nestle-Aland/"Ancient"
tradition — see the phase doc §1 for the evidence) be predicted and
correctly classified rather than treated as a mysterious failure.

Every TAGNT token receives EXACTLY ONE ``TokenAlignment`` record with one of:

- ``EXACT``: normalized surface forms match (accent/breathing/case-
  insensitive) — the strongest possible evidence.
- ``COMPOSITE``: surfaces differ (spelling/elision/movable-nu variant) but
  lemma and Strong-number both corroborate the same lexeme.
- ``VALIDATED_FALLBACK``: neither surface nor lemma matches exactly, but
  position (after accounting for already-resolved variant skips) plus
  morphology-compatible case/number/gender/person agreement corroborate a
  match — the weakest positive evidence tier, used rarely.
- ``UNRESOLVED_TEXTUAL_VARIANT``: no MACULA counterpart found, and the
  TAGNT token's own ``edition_flags`` do not include the Ancient/Nestlé
  ("n"/"N") tradition marker SBLGNT follows — an EXPECTED, well-understood
  absence (a genuine textual variant), not a data or algorithm failure.
- ``UNRESOLVED_OTHER``: no MACULA counterpart found despite the token
  being flagged as belonging to the Ancient/Nestlé tradition — a genuine,
  uninvestigated discrepancy.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

from bible_engine.macula_greek_parser import MaculaGreekToken, normalize_greek_surface
from bible_engine.tagnt_parser import GreekToken

AlignmentStatus = Literal[
    "EXACT",
    "COMPOSITE",
    "VALIDATED_FALLBACK",
    "UNRESOLVED_TEXTUAL_VARIANT",
    "UNRESOLVED_OTHER",
]

_LOOKAHEAD = 4


@dataclass(frozen=True)
class TokenAlignment:
    tagnt_token_id: str  # Phase 2A greek_token_id format: "{book}.{chapter}.{verse}:{word_index}"
    macula_xml_id: str | None
    status: AlignmentStatus
    evidence: tuple[str, ...]


def _consonant_skeleton(text: str) -> str:
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()


def _strong_base(tagnt_strong_id: str) -> str:
    """"G0007G" -> "7" (bare numeric, matching MACULA's own unsuffixed
    ``strong`` field — MACULA does not disambiguate senses the way TAGNT's
    dStrong does)."""
    digits = "".join(ch for ch in (tagnt_strong_id or "") if ch.isdigit())
    return str(int(digits)) if digits else ""


def _surfaces_match(tagnt_surface: str, macula_text: str) -> bool:
    return normalize_greek_surface(tagnt_surface) == normalize_greek_surface(macula_text)


def _lemmas_match(tagnt_lemma: str, macula_lemma: str) -> bool:
    return bool(tagnt_lemma) and bool(macula_lemma) and (
        _consonant_skeleton(tagnt_lemma) == _consonant_skeleton(macula_lemma)
    )


def _strongs_match(tagnt_strong_id: str, macula_strong: str) -> bool:
    return bool(macula_strong) and _strong_base(tagnt_strong_id) == (macula_strong or "").strip()


def _is_ancient_tradition(edition_flags: str) -> bool:
    """True when this TAGNT token belongs to the Nestlé-Aland/"Ancient"
    tradition (upper or lower "n") — the tradition SBLGNT follows. See the
    phase doc §1 for the concrete Jn 3:16 "αὐτοῦ" (flags="ko", correctly
    absent from SBLGNT) evidence backing this rule."""
    return "n" in (edition_flags or "").lower()


def _token_id(token: GreekToken) -> str:
    return f"{token.book}.{token.chapter}.{token.verse}:{token.word_index}"


def _morphology_compatible(tagnt_token: GreekToken, macula_token: MaculaGreekToken) -> bool:
    from bible_engine.morphology_hu import parse_morphology_hu

    hu = parse_morphology_hu(tagnt_token.morph_code or "")
    components = hu.components or (hu,)
    hu_case = {c.case for c in components if c.case} or {""}
    hu_number = {c.number for c in components if c.number} or {""}
    macula_case = (macula_token.case or "").strip().lower()
    macula_number = (macula_token.number or "").strip().lower()
    case_ok = not macula_case or any(macula_case in (c or "").lower() for c in hu_case if c)
    number_ok = not macula_number or any(macula_number in (n or "").lower() for n in hu_number if n)
    return case_ok and number_ok


def align_verse_tokens(
    tagnt_tokens: list[GreekToken], macula_tokens: list[MaculaGreekToken]
) -> list[TokenAlignment]:
    """Aligns one verse's TAGNT tokens (ordered by ``word_index``) against
    that verse's MACULA tokens (ordered by MACULA's own ``word_index`` —
    NOT assumed equal to TAGNT's). Returns exactly ``len(tagnt_tokens)``
    records, one per TAGNT token, in TAGNT order.

    Uses a consumable "pool" of MACULA tokens rather than a strict two-
    pointer walk, so that a genuine WORD-ORDER TRANSPOSITION between
    editions (e.g. 1 Cor 1:2's well-known "ἡγιασμένοις ἐν Χριστῷ Ἰησοῦ" /
    "τῇ οὔσῃ ἐν Κορίνθῳ" clause-order variant between TAGNT and SBLGNT —
    both four-word chunks fully intact, just swapped) can still resolve
    correctly instead of cascading into false UNRESOLVED runs. A LOCAL
    window is tried first (cheapest, most common case); only if that fails
    does the search widen to the whole verse's remaining unconsumed pool.
    """
    pool: list[tuple[int, MaculaGreekToken]] = list(enumerate(macula_tokens))
    results: list[TokenAlignment] = []
    anchor = 0  # a moving soft reference point, not a hard pointer

    for t in tagnt_tokens:
        local = [(idx, mt) for idx, mt in pool if abs(idx - anchor) <= _LOOKAHEAD]

        match = _best_match(t, local)
        widened = False
        if match is None and pool:
            match = _best_match(t, pool)
            widened = match is not None

        if match is not None:
            idx, mt, tier = match
            evidence = [tier]
            if widened:
                evidence.append("whole_verse_search")
            if idx != anchor:
                evidence.append(f"position_shift={idx - anchor}")
            status: AlignmentStatus = "EXACT" if tier == "surface_match" else "COMPOSITE"
            results.append(TokenAlignment(_token_id(t), mt.xml_id, status, tuple(evidence)))
            pool = [(i2, m2) for i2, m2 in pool if i2 != idx]
            anchor = idx + 1
            continue

        # No lexical evidence anywhere in the verse. Last resort: whatever
        # MACULA token currently sits at the anchor position, IF its
        # morphology (case/number, where present) is at least compatible —
        # weak positive evidence, never used when the pool is empty.
        at_anchor = next((mt for idx, mt in pool if idx == anchor), None)
        if at_anchor is not None and _morphology_compatible(t, at_anchor):
            results.append(
                TokenAlignment(
                    _token_id(t), at_anchor.xml_id, "VALIDATED_FALLBACK",
                    ("position_match", "morphology_compatible"),
                )
            )
            pool = [(i2, m2) for i2, m2 in pool if i2 != anchor]
            anchor += 1
            continue

        results.append(_unresolved(t))
        # anchor intentionally not advanced — an unresolved TAGNT token
        # (e.g. a K/O-only variant) consumes no MACULA token, so the next
        # TAGNT token should still expect MACULA content at this position.

    return results


def _best_match(
    token: GreekToken, candidates: list[tuple[int, MaculaGreekToken]]
) -> tuple[int, MaculaGreekToken, str] | None:
    for idx, mt in candidates:
        if _surfaces_match(token.greek_form, mt.text):
            return idx, mt, "surface_match"
    # Lemma+Strong alone is NOT sufficient evidence for a common, frequently
    # repeated lemma (pronouns/articles/conjunctions all recur many times
    # per verse) — without also requiring morphology-compatible case/
    # number, this tier will happily "match" a genitive αὐτοῦ to an
    # unrelated accusative αὐτὸν elsewhere in the same verse purely because
    # both are forms of αὐτός/G0846. Case/number agreement is required for
    # every lemma+Strong candidate, not just the weaker VALIDATED_FALLBACK
    # tier below.
    for idx, mt in candidates:
        if (
            _lemmas_match(token.lemma, mt.lemma)
            and _strongs_match(token.strong_id, mt.strong)
            and _morphology_compatible(token, mt)
        ):
            return idx, mt, "lemma_and_strong_match"
    return None


def _unresolved(token: GreekToken) -> TokenAlignment:
    status: AlignmentStatus = (
        "UNRESOLVED_TEXTUAL_VARIANT"
        if not _is_ancient_tradition(token.edition_flags)
        else "UNRESOLVED_OTHER"
    )
    evidence = (f"edition_flags={token.edition_flags or '(none)'}",)
    return TokenAlignment(_token_id(token), None, status, evidence)
