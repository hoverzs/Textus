"""Phase 2B — deterministic parsers for MACULA Greek (Clear Bible, SBLGNT
variant) source files.

Two independent representations are parsed, matching what the source
actually ships (see docs/greek_analysis_v2_phase2b_syntax.md §1):

1. The flat, whole-NT TSV (``SBLGNT/tsv/macula-greek-SBLGNT.tsv``) — one row
   per token, carrying morphology (already split into person/number/gender/
   case/tense/voice/mood/degree — MACULA's own decoding, kept separate from
   TAGNT's), Strong number, a short dependency-ish ``role`` code, Louw-Nida
   domain/sense numbers, and — critically — semantic FRAME role assignments
   (``frame``, e.g. ``"A0:n... A1:n..."``) and coreference (``referent``,
   ``subjref``) already present at the flat level, with no tree needed.
   Used for full-corpus token alignment (§2/§3) and semantic-role/
   coreference extraction.

2. The per-book "lowfat" XML tree (``SBLGNT/lowfat/NN-bookname.xml``) — the
   ONLY representation that carries phrase/clause constituent structure
   (nested ``<wg class="cl|np|pp|vp|adjp|advp">`` word-group elements).
   This phase parses it for a bounded set of books only (the ones the 15
   Phase 2A regression verses live in) — see the phase doc for why full
   27-book phrase/clause coverage was not attempted this phase.

Both representations share the same ``xml:id`` token identity, letting a
caller cross-reference token-level data (representation 1) with the phrase/
clause group a token belongs to (representation 2).

Never vendored/committed — files are large (up to ~21 MB for the flat TSV,
up to ~17 MB per book for lowfat XML) and fetched to a local scratch path
by ``scripts/build_greek_syntax_store.py``; only the resulting normalized,
compact SQLite store is a build artifact under consideration for commit.
"""

from __future__ import annotations

import csv
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from pathlib import Path

_REF_RE = re.compile(r"^(?P<book>[A-Z1-3]+)\s+(?P<chapter>\d+):(?P<verse>\d+)!(?P<word_index>\d+)$")

# Group (<wg>) class values that are genuine phrase/clause constituents —
# distinct from leaf (<w>) class values (noun/verb/adj/adv/conj/det/pron/
# prep/ptcl), which describe a single token's part of speech, not a group.
CLAUSE_CLASS = "cl"
PHRASE_CLASSES = frozenset({"np", "pp", "vp", "adjp", "advp"})


@dataclass(frozen=True)
class MaculaGreekToken:
    """One row of the flat MACULA SBLGNT TSV."""

    xml_id: str
    book: str  # 3-letter MACULA code, e.g. "JHN" — upper() of TAGNT's own code
    chapter: int
    verse: int
    word_index: int  # MACULA's OWN per-verse word index — NOT assumed equal to TAGNT's
    role: str
    word_class: str
    word_type: str
    text: str
    after: str
    lemma: str
    normalized: str
    strong: str  # bare numeric, e.g. "976" — NOT TAGNT's disambiguated "G0976x" form
    morph: str
    person: str
    number: str
    gender: str
    case: str
    tense: str
    voice: str
    mood: str
    degree: str
    domain: str
    ln: str
    frame: str  # e.g. "A0:n40001002001 A1:n40001002004" — semantic role assignments
    subjref: str
    referent: str


def parse_macula_greek_tsv(path: str | Path) -> list[MaculaGreekToken]:
    tokens: list[MaculaGreekToken] = []
    with Path(path).open("r", encoding="utf-8") as handle:
        reader = csv.DictReader(handle, delimiter="\t")
        for row in reader:
            match = _REF_RE.match(row.get("ref", "") or "")
            if not match:
                continue
            tokens.append(
                MaculaGreekToken(
                    xml_id=row.get("xml:id", "") or "",
                    book=match.group("book"),
                    chapter=int(match.group("chapter")),
                    verse=int(match.group("verse")),
                    word_index=int(match.group("word_index")),
                    role=row.get("role", "") or "",
                    word_class=row.get("class", "") or "",
                    word_type=row.get("type", "") or "",
                    text=row.get("text", "") or "",
                    after=row.get("after", "") or "",
                    lemma=row.get("lemma", "") or "",
                    normalized=row.get("normalized", "") or "",
                    strong=row.get("strong", "") or "",
                    morph=row.get("morph", "") or "",
                    person=row.get("person", "") or "",
                    number=row.get("number", "") or "",
                    gender=row.get("gender", "") or "",
                    case=row.get("case", "") or "",
                    tense=row.get("tense", "") or "",
                    voice=row.get("voice", "") or "",
                    mood=row.get("mood", "") or "",
                    degree=row.get("degree", "") or "",
                    domain=row.get("domain", "") or "",
                    ln=row.get("ln", "") or "",
                    frame=row.get("frame", "") or "",
                    subjref=row.get("subjref", "") or "",
                    referent=row.get("referent", "") or "",
                )
            )
    return tokens


@dataclass(frozen=True)
class MaculaGreekGroup:
    """One phrase or clause constituent from the lowfat XML tree.

    ``group_id`` is SYNTHESIZED (the source does not assign ``<wg>`` its own
    id) as ``{first_leaf_xml_id}.g{depth}.{sibling_index}`` — deterministic
    and stable across re-parses of the identical source file, never
    arbitrary/counter-based across runs.
    """

    group_id: str
    group_class: str  # "cl" | "np" | "pp" | "vp" | "adjp" | "advp"
    rule: str  # MACULA's own constituent-rule label, e.g. "Np-Appos" — kept verbatim, never reinterpreted
    role: str  # e.g. "s" (subject) when the source itself provides one — kept verbatim
    predication: str  # e.g. "elided" when present
    token_ids: tuple[str, ...]  # every leaf <w> xml:id under this group, in document order
    parent_group_id: str | None
    depth: int


def parse_macula_greek_lowfat_book(path: str | Path) -> list[MaculaGreekGroup]:
    """Parses one whole-book lowfat XML file into a flat list of
    ``MaculaGreekGroup`` records (clauses and phrases only — leaf tokens are
    already fully covered by the flat TSV parser above, so this function
    does not re-extract per-token morphology)."""
    tree = ET.parse(str(path))
    root = tree.getroot()
    groups: list[MaculaGreekGroup] = []
    _walk(root, parent_id=None, depth=0, groups=groups)
    return groups


def _walk(
    element: ET.Element,
    *,
    parent_id: str | None,
    depth: int,
    groups: list[MaculaGreekGroup],
) -> None:
    sibling_counts: dict[str, int] = {}
    for child in element:
        tag = _local_tag(child)
        if tag == "wg":
            token_ids = tuple(_leaf_ids(child))
            first_id = token_ids[0] if token_ids else f"empty.{depth}.{len(groups)}"
            sibling_counts[first_id] = sibling_counts.get(first_id, 0) + 1
            group_id = f"{first_id}.g{depth}.{sibling_counts[first_id]}"
            group_class = child.get("class", "") or ""
            if group_class == CLAUSE_CLASS or group_class in PHRASE_CLASSES:
                groups.append(
                    MaculaGreekGroup(
                        group_id=group_id,
                        group_class=group_class,
                        rule=child.get("rule", "") or "",
                        role=child.get("role", "") or "",
                        predication=child.get("predication", "") or "",
                        token_ids=token_ids,
                        parent_group_id=parent_id,
                        depth=depth,
                    )
                )
                _walk(child, parent_id=group_id, depth=depth + 1, groups=groups)
            else:
                # An unrecognized/other <wg> class — still descend so nested
                # cl/np/pp/etc groups inside it are not silently dropped,
                # but do not emit a record for the unrecognized wrapper
                # itself (never invent a phrase/clause type the source
                # didn't label as one of the known constituent classes).
                _walk(child, parent_id=parent_id, depth=depth, groups=groups)
        elif tag in ("sentence", "p"):
            _walk(child, parent_id=parent_id, depth=depth, groups=groups)
        # <w> leaves and <milestone> markers carry no further group nesting.


def _leaf_ids(element: ET.Element) -> list[str]:
    ids: list[str] = []
    for descendant in element.iter():
        if _local_tag(descendant) == "w":
            xml_id = descendant.get("{http://www.w3.org/XML/1998/namespace}id") or descendant.get("xml:id") or ""
            if xml_id:
                ids.append(xml_id)
    return ids


def _local_tag(element: ET.Element) -> str:
    tag = element.tag
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


def normalize_greek_surface(text: str) -> str:
    """Accent/breathing/iota-subscript-insensitive comparison key — used
    ONLY for alignment matching (bible_engine.greek_token_alignment), never
    to alter any stored/displayed surface form."""
    import unicodedata

    decomposed = unicodedata.normalize("NFD", text or "")
    stripped = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    return stripped.lower().strip("().,;:·!?’‘·")
