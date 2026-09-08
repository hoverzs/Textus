"""Phase 2D — deterministic parser for one MACULA-Hebrew "lowfat" XML
chapter file (``WLC/lowfat/NN-Book-CCC-lowfat.xml``).

Chosen representation: **lowfat**, not **nodes** or **tsv** — see
``docs/hebrew_analysis_v2_phase2d.md`` §2 for the full comparison. In
short: ``tsv`` carries no tree structure at all (explicitly ruled out by
the Phase 2D brief); ``nodes`` wraps every leaf in several purely-syntactic
intermediate layers (``cjp`` -> ``cj`` -> the leaf, ``V`` -> ``vp`` -> the
leaf) that add depth without adding information a relational import needs;
``lowfat`` gives the same tree with a flatter ``<wg>`` (word group) /
``<w>`` (word) structure, and — critically for alignment — every leaf's
``ref`` attribute (e.g. ``"RUT 1:1!1"``) directly carries a per-verse
orthographic-word ordinal that empirically equals TAHOT's own
``word_index`` (verified against the production database for Ruth 1 before
this parser was written: TAHOT word_index 1 is the single orthographic
token ``וַ/יְהִ֗י``, which lowfat splits into two ``<w>`` leaves, BOTH
carrying ``ref="RUT 1:1!1"``).

This module only parses one file's XML tree into plain dataclasses — no
alignment, no database access, no I/O beyond reading the given path. See
``bible_engine.hebrew_macula_alignment`` for the alignment algorithm built
on top of this.
"""

from __future__ import annotations

import re
import unicodedata
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from pathlib import Path

_REF_RE = re.compile(r"^(?P<book>[A-Z0-9]+)\s+(?P<chapter>\d+):(?P<verse>\d+)!(?P<word>\d+)$")


@dataclass(frozen=True)
class MaculaLeaf:
    """One ``<w>`` element — a single morpheme."""

    macula_node_id: str  # xml:id, e.g. "o080010010011"
    ref: str  # verbatim "RUT 1:1!1"
    ref_book: str
    ref_chapter: int
    ref_verse: int
    ref_word_number: int
    doc_order: int
    parent_group_id: str | None
    child_order: int  # position among the parent's children
    surface: str  # "unicode" attribute
    lemma: str
    transliteration: str
    gloss_en: str
    strong_number: str  # "strongnumberx"
    oshb_strongs: str  # not present on lowfat <w>, kept for forward-compat (usually empty)
    morph_code: str
    part_of_speech: str
    stem: str
    verb_type: str
    person: str
    gender: str
    number: str
    state: str
    role: str  # this leaf's own syntactic role within its parent group, e.g. "v", "s", "o"
    frame: str
    subjref: str
    participantref: str
    raw_attributes: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class MaculaGroup:
    """One ``<wg>`` element — a phrase or clause node. Groups have no
    ``xml:id`` in the source data (verified: 0/340 in a sample chapter), so
    ``macula_node_id`` is synthesized deterministically as
    ``f"{sentence_id}:wg{n}"`` (n = 0-based pre-order index of this group
    within its sentence) — reproducible from the same source file every
    time, never randomly generated."""

    macula_node_id: str
    sentence_id: str  # e.g. "RUT 1:1"
    doc_order: int
    parent_group_id: str | None
    child_order: int
    macula_class: str  # "class" attribute, e.g. "cl", "pp", "np"
    macula_role: str  # "role" attribute (this group's role within ITS parent), may be ""
    macula_rule: str
    clause_type: str  # "clausetype" attribute, only meaningful when macula_class == "cl"
    is_head: bool
    frame: str
    subjref: str
    participantref: str
    child_leaf_ids: tuple[str, ...] = ()
    child_group_ids: tuple[str, ...] = ()


@dataclass(frozen=True)
class MaculaSentence:
    """One ``<sentence>`` element — normally one verse, occasionally MACULA
    groups adjacent verses into one sentence for a single tree (rare; when
    it happens ``verse_ref`` is the sentence's own nominal id and
    individual leaves still carry their own accurate per-word ``ref``)."""

    sentence_id: str
    root_group_id: str | None
    leaves: tuple[MaculaLeaf, ...]
    groups: tuple[MaculaGroup, ...]

    def leaves_by_ref_word(self) -> dict[int, list[MaculaLeaf]]:
        buckets: dict[int, list[MaculaLeaf]] = {}
        for leaf in self.leaves:
            buckets.setdefault(leaf.ref_word_number, []).append(leaf)
        for word_number in buckets:
            buckets[word_number].sort(key=lambda leaf: leaf.doc_order)
        return buckets


@dataclass(frozen=True)
class MaculaChapter:
    source_path: str
    sentences: tuple[MaculaSentence, ...]


def strip_hebrew_points(text: str) -> str:
    """Cantillation + niqqud stripped, consonants only — used for
    surface-normalized comparison during alignment (never as the primary
    identity signal, only as one piece of corroborating evidence)."""
    decomposed = unicodedata.normalize("NFD", text or "")
    return "".join(ch for ch in decomposed if unicodedata.category(ch) != "Mn" and ch not in "־׀׃׆")


def parse_ref(ref: str) -> tuple[str, int, int, int] | None:
    match = _REF_RE.match((ref or "").strip())
    if not match:
        return None
    return (
        match.group("book"),
        int(match.group("chapter")),
        int(match.group("verse")),
        int(match.group("word")),
    )


_LEAF_ATTR_MAP = {
    "morph": "morph_code",
    "pos": "part_of_speech",
    "stem": "stem",
    "type": "verb_type",
    "person": "person",
    "gender": "gender",
    "number": "number",
    "state": "state",
    "role": "role",
    "frame": "frame",
    "subjref": "subjref",
    "participantref": "participantref",
    "english": "gloss_en",
    "transliteration": "transliteration",
    "lemma": "lemma",
    "unicode": "surface",
    "strongnumberx": "strong_number",
    "oshb-strongs": "oshb_strongs",
}


def parse_macula_lowfat_chapter(path: str | Path) -> MaculaChapter:
    source_path = str(path)
    tree = ET.parse(source_path)
    root = tree.getroot()

    sentences: list[MaculaSentence] = []
    for sentence_el in root.iter("sentence"):
        sentence_id = sentence_el.get("id", "")
        leaves: list[MaculaLeaf] = []
        groups: list[MaculaGroup] = []
        doc_order_counter = [0]
        group_counter = [0]

        # Group-like container tags: <wg> (word group — the normal phrase/
        # clause node) and <c> (a rarer "compound" wrapper MACULA uses for
        # a single lexical item spread across multiple TAHOT-side tokens,
        # e.g. the proper name "בֵּית לֶחֶם" / Bethlehem, word_index 10-11
        # in Ruth 1:1 — verified against the raw source: two <w> leaves,
        # each carrying the FULL two-word gloss, wrapped in <c role="">
        # inside a <wg class="np">). Both are walked identically; only the
        # tag name distinguishes them in the resulting MaculaGroup rows.
        _GROUP_TAGS = ("wg", "c")
        top_level_elements = [el for el in sentence_el if el.tag in ("w",) + _GROUP_TAGS]

        root_group_id: str | None = None

        def walk(element: ET.Element, parent_group_id: str | None, child_order: int) -> None:
            nonlocal root_group_id
            if element.tag == "w":
                _append_leaf(element, sentence_id, parent_group_id, child_order, doc_order_counter, leaves)
                return
            if element.tag not in _GROUP_TAGS:
                return
            this_group_id = f"{sentence_id}:wg{group_counter[0]}"
            group_counter[0] += 1
            doc_order = doc_order_counter[0]
            doc_order_counter[0] += 1
            if parent_group_id is None and root_group_id is None:
                root_group_id = this_group_id

            children = [child for child in element if child.tag in ("w",) + _GROUP_TAGS]
            child_leaf_ids: list[str] = []
            child_group_ids: list[str] = []
            for index, child in enumerate(children):
                if child.tag == "w":
                    xml_id = child.get("xml:id") or child.get("{http://www.w3.org/XML/1998/namespace}id") or ""
                    child_leaf_ids.append(xml_id)
                else:
                    child_group_ids.append(f"{sentence_id}:wg{group_counter[0]}")
                walk(child, this_group_id, index)

            groups.append(
                MaculaGroup(
                    macula_node_id=this_group_id,
                    sentence_id=sentence_id,
                    doc_order=doc_order,
                    parent_group_id=parent_group_id,
                    child_order=child_order,
                    macula_class=element.get("class") or element.tag,
                    macula_role=element.get("role", ""),
                    macula_rule=element.get("rule", ""),
                    clause_type=element.get("clausetype", ""),
                    is_head=(element.get("head", "").lower() == "true"),
                    frame=element.get("frame", ""),
                    subjref=element.get("subjref", ""),
                    participantref=element.get("participantref", ""),
                    child_leaf_ids=tuple(child_leaf_ids),
                    child_group_ids=tuple(child_group_ids),
                )
            )

        for index, element in enumerate(top_level_elements):
            walk(element, None, index)

        sentences.append(
            MaculaSentence(
                sentence_id=sentence_id,
                root_group_id=root_group_id,
                leaves=tuple(leaves),
                groups=tuple(groups),
            )
        )

    return MaculaChapter(source_path=source_path, sentences=tuple(sentences))


def _append_leaf(
    element: ET.Element,
    sentence_id: str,
    parent_group_id: str | None,
    child_order: int,
    doc_order_counter: list[int],
    leaves: list[MaculaLeaf],
) -> None:
    xml_id = element.get("xml:id") or element.get("{http://www.w3.org/XML/1998/namespace}id") or ""
    ref = element.get("ref", "")
    parsed_ref = parse_ref(ref)
    doc_order = doc_order_counter[0]
    doc_order_counter[0] += 1

    kwargs: dict[str, object] = {
        "macula_node_id": xml_id,
        "ref": ref,
        "ref_book": parsed_ref[0] if parsed_ref else "",
        "ref_chapter": parsed_ref[1] if parsed_ref else 0,
        "ref_verse": parsed_ref[2] if parsed_ref else 0,
        "ref_word_number": parsed_ref[3] if parsed_ref else 0,
        "doc_order": doc_order,
        "parent_group_id": parent_group_id,
        "child_order": child_order,
        "surface": "",
        "lemma": "",
        "transliteration": "",
        "gloss_en": "",
        "strong_number": "",
        "oshb_strongs": "",
        "morph_code": "",
        "part_of_speech": "",
        "stem": "",
        "verb_type": "",
        "person": "",
        "gender": "",
        "number": "",
        "state": "",
        "role": "",
        "frame": "",
        "subjref": "",
        "participantref": "",
    }
    raw_attributes: dict[str, str] = {}
    for attr_name, value in element.attrib.items():
        clean_name = attr_name.split("}")[-1] if "}" in attr_name else attr_name
        raw_attributes[clean_name] = value
        field_name = _LEAF_ATTR_MAP.get(clean_name)
        if field_name:
            kwargs[field_name] = value
    # The element's own TEXT content is this leaf's actual surface form.
    # The "unicode" attribute usually matches it, but for a multi-word
    # lexical compound (e.g. the "בֵּית לֶחֶם" / Bethlehem case — two <w>
    # leaves, ref!10 and ref!11, BOTH carrying the full two-word compound
    # as their "unicode" attribute) only the text content gives the true
    # per-leaf surface ("בֵּ֧ית" vs "לֶ֣חֶם" respectively).
    text_content = (element.text or "").strip()
    if text_content:
        kwargs["surface"] = text_content
    kwargs["raw_attributes"] = raw_attributes
    leaves.append(MaculaLeaf(**kwargs))


__all__ = [
    "MaculaChapter",
    "MaculaGroup",
    "MaculaLeaf",
    "MaculaSentence",
    "parse_macula_lowfat_chapter",
    "parse_ref",
    "strip_hebrew_points",
]
