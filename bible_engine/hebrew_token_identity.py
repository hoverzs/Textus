"""Phase 2C — stable Hebrew/Aramaic token identity.

This is the one identity scheme every future consumer of
``HebrewAnalysisBundle`` (the current UI, the deterministic feature
detectors, and eventually Phase 2D's MACULA alignment) must agree on. It is
deliberately NOT the production database's integer ``token_id`` primary key,
because that key is an autoincrement artifact of one particular import run's
row-insertion order — correct as a database key, but not something a caller
should treat as meaningful, reconstructible, or stable if the database were
ever rebuilt with e.g. a different SQLite version's insertion order.

Two identities are exposed, deliberately kept distinct:

* ``token_id`` — the Phase 2C **canonical-reference-based** stable id, of the
  form ``{OSIS_book}.{chapter}.{verse}:{word_index}`` (e.g. ``"Ruth.1.1:1"``).
  Built from data already on every token (canonical book/chapter/verse via
  ``bible_engine.hebrew_books.ruf_code_from_tahot_code`` +
  ``textus_kb.books.RUF_TO_OSIS``, and the token's 1-based position within
  its verse). Deterministically rebuildable from the same source data on any
  machine, independent of database insertion order, and stable across app
  restarts because it depends only on canonical reference + position, never
  on a database rowid.

  This does NOT depend solely on array index in the sense the user's spec
  warns against: `word_index` is TAHOT's own per-verse word position (from
  the source record id's ``#NN`` suffix), not a position recomputed from
  whatever tokens happen to be loaded — so it stays stable even if a future
  loader skips or filters tokens for some other purpose, as long as it
  preserves the original per-verse ordinal.

* ``source_token_id`` — the STEPBible TAHOT source record id verbatim (e.g.
  ``"Rut.1.1#01=L"``), carried through unmodified as a SEPARATE field on
  ``TokenAnalysis`` (see ``bible_engine.hebrew_analysis_bundle``). This is
  kept only as a passthrough provenance anchor for Phase 2D's MACULA/OSHB
  alignment — Phase 2B/2C measured that it cannot be reliably *reconstructed*
  from parsed (book, chapter, verse, word_index, edition) components (~22,000
  mismatches out of 305,635 tokens, from variable word-index zero-padding and
  lost Masoretic/English versification parentheticals), so it is stored
  verbatim in the component-fidelity store rather than derived.

Multi-component tokens (a single Hebrew orthographic word with prefix/core/
suffix components, e.g. a token with a prepositional prefix) get ONE
``token_id`` for the whole surface token; each component is addressed as
``f"{token_id}.{component_index}"`` (``ComponentAnalysis.component_id``),
0-based in surface (left-to-right) order — see
``bible_engine.hebrew_component_repository``.
"""

from __future__ import annotations

from dataclasses import dataclass

from bible_engine.hebrew_books import ruf_code_from_tahot_code
from textus_kb.books import RUF_TO_OSIS


class TokenIdentityError(ValueError):
    pass


def canonical_book_id_from_tahot_code(tahot_book_code: str) -> str:
    """Bridge a TAHOT book code (e.g. ``"1Sa"``) to the canonical OSIS-like
    book id used throughout ``textus_kb`` (e.g. ``"1Sam"``), via the RUF
    code both ``bible_engine.hebrew_books`` and ``textus_kb.books`` already
    share. Raises rather than guessing if either module has no entry for the
    supplied code — a silent identity fallback here would defeat the whole
    point of a *stable* id.
    """
    ruf_code = ruf_code_from_tahot_code(tahot_book_code)
    if ruf_code is None:
        raise TokenIdentityError(f"Unknown TAHOT book code: {tahot_book_code!r}")
    osis_id = RUF_TO_OSIS.get(ruf_code)
    if osis_id is None:
        raise TokenIdentityError(f"No canonical OSIS id registered for RUF code: {ruf_code!r}")
    return osis_id


def build_token_id(tahot_book_code: str, chapter: int, verse: int, word_index: int) -> str:
    """The Phase 2C stable token id: ``{OSIS_book}.{chapter}.{verse}:{word_index}``."""
    book_id = canonical_book_id_from_tahot_code(tahot_book_code)
    return f"{book_id}.{chapter}.{verse}:{word_index}"


def build_legacy_stable_key(tahot_book_code: str, chapter: int, verse: int, word_index: int) -> str:
    """The pre-Phase-2C ``book:chapter:verse:word_index`` form (TAHOT book
    code, not OSIS), kept for compatibility with existing UI/cache callers
    that already key off ``tokens.stable_token_key`` in the production
    database — see ``bible_engine/hebrew_sqlite.py``.
    """
    return f"{tahot_book_code}:{chapter}:{verse}:{word_index}"


def build_component_id(token_id: str, component_index: int) -> str:
    return f"{token_id}.{component_index}"


@dataclass(frozen=True)
class ParsedTokenId:
    book_id: str
    chapter: int
    verse: int
    word_index: int


def parse_token_id(token_id: str) -> ParsedTokenId:
    try:
        book_and_chapter_verse, word_index_text = token_id.rsplit(":", 1)
        book_id, chapter_text, verse_text = book_and_chapter_verse.rsplit(".", 2)
        return ParsedTokenId(book_id, int(chapter_text), int(verse_text), int(word_index_text))
    except ValueError as exc:
        raise TokenIdentityError(f"Malformed Phase 2C token id: {token_id!r}") from exc


__all__ = [
    "ParsedTokenId",
    "TokenIdentityError",
    "build_component_id",
    "build_legacy_stable_key",
    "build_token_id",
    "canonical_book_id_from_tahot_code",
    "parse_token_id",
]
