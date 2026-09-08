"""Phase 2D — deterministic offline importer: one parsed MACULA chapter +
its corresponding TAHOT tokens -> rows in the normalized linguistic store
(``bible_engine.hebrew_linguistic_sqlite`` locally; the same shape targets
``supabase/migrations/20260908190000_hebrew_linguistic_layer.sql`` in
production).

Nothing here calls a network or an LLM. ``import_chapter`` is pure aside
from the two database connections it is handed (production TAHOT +
destination linguistic store) — no global state, safely re-runnable.

Authority rule (see docs/hebrew_analysis_v2_phase2d.md §4): this importer
NEVER writes a MACULA-sourced value into ``hebrew_tokens`` or
``hebrew_token_components`` — those two tables are populated once, up
front, straight from the already-authoritative TAHOT/TEHMC/component-
fidelity data, before any MACULA file is even read. MACULA's own
morphology opinions land only in ``hebrew_source_nodes.macula_*`` columns,
kept strictly for comparison/provenance.
"""

from __future__ import annotations

import json
import sqlite3
from dataclasses import dataclass

from bible_engine.hebrew_analysis_bundle import MorphologyFacts
from bible_engine.hebrew_component_repository import ComponentFidelityUnavailable, restore_component_fidelity
from bible_engine.hebrew_macula_alignment import TokenAlignment, align_token
from bible_engine.hebrew_morphology import decode_hebrew_morphology
from bible_engine.hebrew_parser import HebrewToken
from bible_engine.hebrew_token_identity import build_token_id
from bible_engine.hebrew_token_repository import HebrewTokenRepository
from bible_engine.macula_lowfat_parser import MaculaChapter, MaculaGroup, MaculaLeaf, MaculaSentence

_KNOWN_RELATION_TYPES = {"v": "predicate", "s": "subject", "o": "object", "adv": "modifier"}
_KNOWN_ROLE_LABELS = {"A0": "agent", "A1": "patient"}


def _normalize_macula_ref_id(raw_id: str) -> str:
    """``frame``/``subjref``/``participantref`` attribute values reference
    other nodes by id WITHOUT the leading ``"o"`` that real ``xml:id``
    values carry (verified: ``subjref="080010010091"`` refers to
    ``xml:id="o080010010091"``) — normalize before any
    ``macula_node_id`` lookup."""
    raw_id = raw_id.strip()
    return raw_id if not raw_id or raw_id.startswith("o") else f"o{raw_id}"


@dataclass
class ImportStats:
    verses_processed: int = 0
    tokens_processed: int = 0
    macula_leaf_count: int = 0
    macula_group_count: int = 0
    exact: int = 0
    composite: int = 0
    validated_fallback: int = 0
    unresolved: int = 0
    phrases: int = 0
    clauses: int = 0
    syntax_edges: int = 0
    semantic_roles: int = 0
    participants: int = 0
    coreference: int = 0
    unresolved_examples: list[dict] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.unresolved_examples is None:
            self.unresolved_examples = []

    def as_dict(self) -> dict:
        return {
            "verses_processed": self.verses_processed,
            "tokens_processed": self.tokens_processed,
            "macula_leaf_count": self.macula_leaf_count,
            "macula_group_count": self.macula_group_count,
            "alignment": {
                "exact": self.exact,
                "composite": self.composite,
                "validated_fallback": self.validated_fallback,
                "unresolved": self.unresolved,
            },
            "phrases": self.phrases,
            "clauses": self.clauses,
            "syntax_edges": self.syntax_edges,
            "semantic_roles": self.semantic_roles,
            "participants": self.participants,
            "coreference": self.coreference,
            "unresolved_examples": self.unresolved_examples[:50],
        }


def ensure_dataset_version(
    store: sqlite3.Connection,
    *,
    dataset_id: str,
    display_name: str,
    revision: str,
    source_repository: str = "",
    source_commit: str = "",
    license: str = "",
    attribution: str = "",
) -> int:
    row = store.execute(
        "SELECT id FROM original_language_dataset_versions WHERE dataset_id = ? AND revision = ?",
        (dataset_id, revision),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = store.execute(
        """
        INSERT INTO original_language_dataset_versions
            (dataset_id, display_name, revision, source_repository, source_commit, license, attribution)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (dataset_id, display_name, revision, source_repository, source_commit, license, attribution),
    )
    store.commit()
    return int(cursor.lastrowid)


def import_chapter(
    chapter: MaculaChapter,
    *,
    tahot_book_code: str,
    chapter_number: int,
    store: sqlite3.Connection,
    token_repository: HebrewTokenRepository,
    textus_dataset_version_id: int,
    macula_dataset_version_id: int,
    component_fidelity_db_path: str | None = None,
) -> ImportStats:
    stats = ImportStats()
    sentences_by_verse: dict[int, list[MaculaSentence]] = {}
    for sentence in chapter.sentences:
        verses = {leaf.ref_verse for leaf in sentence.leaves if leaf.ref_verse}
        for verse_number in verses or {0}:
            sentences_by_verse.setdefault(verse_number, []).append(sentence)

    for verse_number, sentences in sorted(sentences_by_verse.items()):
        if verse_number == 0:
            continue
        _import_verse(
            tahot_book_code=tahot_book_code,
            chapter_number=chapter_number,
            verse_number=verse_number,
            sentences=sentences,
            store=store,
            token_repository=token_repository,
            textus_dataset_version_id=textus_dataset_version_id,
            macula_dataset_version_id=macula_dataset_version_id,
            component_fidelity_db_path=component_fidelity_db_path,
            stats=stats,
        )
    store.commit()
    return stats


def _import_verse(
    *,
    tahot_book_code: str,
    chapter_number: int,
    verse_number: int,
    sentences: list[MaculaSentence],
    store: sqlite3.Connection,
    token_repository: HebrewTokenRepository,
    textus_dataset_version_id: int,
    macula_dataset_version_id: int,
    component_fidelity_db_path: str | None,
    stats: ImportStats,
) -> None:
    result = token_repository.passage(tahot_book_code, chapter_number, verse_number, verse_number)
    if result.status != "ok" or not result.tokens:
        return
    tokens = list(result.tokens)
    try:
        restored, source_ids = restore_component_fidelity(
            tokens,
            production_db_path=token_repository.database_path,
            fidelity_db_path=component_fidelity_db_path,
        )
    except ComponentFidelityUnavailable:
        restored, source_ids = {t.stable_key: t for t in tokens}, {}

    token_id_from_book = _canonical_book_id_or_none(tahot_book_code)
    if token_id_from_book is None:
        return
    verse_ref = f"{token_id_from_book}.{chapter_number}.{verse_number}"
    language = "aramaic" if any(t.language.lower() == "aramaic" for t in tokens) else "hebrew"

    verse_row_id = _upsert_verse(store, token_id_from_book, chapter_number, verse_number, verse_ref, language, textus_dataset_version_id)

    macula_leaves_by_id: dict[str, MaculaLeaf] = {}
    macula_group_by_id: dict[str, MaculaGroup] = {}
    source_node_id_by_macula_id: dict[str, int] = {}
    for sentence in sentences:
        for leaf in sentence.leaves:
            macula_leaves_by_id[leaf.macula_node_id] = leaf
        for group in sentence.groups:
            macula_group_by_id[group.macula_node_id] = group

    combined_sentence = _merged_sentence(sentences)

    for token in tokens:
        enriched = restored.get(token.stable_key, token)
        _upsert_token(store, enriched, token_id_from_book, verse_row_id, source_ids.get(token.stable_key, enriched.source_token_id), textus_dataset_version_id)
        stats.tokens_processed += 1

    stats.verses_processed += 1
    stats.macula_leaf_count += len(macula_leaves_by_id)
    stats.macula_group_count += len(macula_group_by_id)

    _import_source_nodes(
        store,
        macula_group_by_id,
        macula_leaves_by_id,
        verse_ref,
        macula_dataset_version_id,
        source_node_id_by_macula_id,
    )

    confirmed_alignments: list[TokenAlignment] = []
    for token in tokens:
        enriched = restored.get(token.stable_key, token)
        token_id = build_token_id(tahot_book_code, chapter_number, verse_number, token.word_index)
        alignment = align_token(enriched, token_id, combined_sentence)
        _record_alignment(store, alignment, source_node_id_by_macula_id, textus_dataset_version_id, macula_dataset_version_id)
        if alignment.alignment_type == "EXACT":
            stats.exact += 1
            confirmed_alignments.append(alignment)
        elif alignment.alignment_type == "COMPOSITE":
            stats.composite += 1
            confirmed_alignments.append(alignment)
        elif alignment.alignment_type == "VALIDATED_FALLBACK":
            stats.validated_fallback += 1
            confirmed_alignments.append(alignment)
        else:
            stats.unresolved += 1
            if len(stats.unresolved_examples) < 200:
                stats.unresolved_examples.append(
                    {"verse_ref": verse_ref, "word_index": token.word_index, "surface": enriched.surface, "reason": alignment.evidence}
                )

    # Phase 2D.1 §12: a MACULA leaf is only mapped to a Textus token id here
    # when that token's OWN alignment was actually confirmed (EXACT/
    # COMPOSITE/VALIDATED_FALLBACK) — never from the raw coincidence that a
    # leaf's ref_word_number equals some token's word_index. An UNRESOLVED
    # token contributes NOTHING to this map, so no phrase/clause/syntax-edge/
    # semantic-role/coreference fact below can ever silently attach to a
    # token whose correspondence to that leaf was never actually verified.
    macula_leaf_id_to_token_id = _resolve_leaf_to_token_map(confirmed_alignments)

    phrase_id_by_group: dict[str, int] = {}
    clause_id_by_group: dict[str, int] = {}
    for group in combined_sentence.groups:
        source_node_id = source_node_id_by_macula_id.get(group.macula_node_id)
        if source_node_id is None:
            continue
        if group.macula_class == "cl":
            clause_row_id = _upsert_clause(store, source_node_id, macula_dataset_version_id, verse_ref, group)
            clause_id_by_group[group.macula_node_id] = clause_row_id
            stats.clauses += 1
        else:
            phrase_row_id = _upsert_phrase(store, source_node_id, macula_dataset_version_id, verse_ref, group)
            phrase_id_by_group[group.macula_node_id] = phrase_row_id
            stats.phrases += 1

    for group in combined_sentence.groups:
        if group.parent_group_id is None:
            continue
        _link_parent(store, group, phrase_id_by_group, clause_id_by_group)

    for group in combined_sentence.groups:
        for leaf_id in group.child_leaf_ids:
            token_id = macula_leaf_id_to_token_id.get(leaf_id)
            _insert_membership(store, token_id, phrase_id_by_group.get(group.macula_node_id), clause_id_by_group.get(group.macula_node_id))

    for group in combined_sentence.groups:
        parent_source_node_id = source_node_id_by_macula_id.get(group.macula_node_id)
        if parent_source_node_id is None:
            continue
        for leaf_id in group.child_leaf_ids:
            leaf = macula_leaves_by_id.get(leaf_id)
            child_source_node_id = source_node_id_by_macula_id.get(leaf_id)
            if leaf is None or child_source_node_id is None:
                continue
            _insert_syntax_edge(
                store, macula_dataset_version_id, verse_ref, parent_source_node_id, child_source_node_id,
                leaf.role, macula_leaf_id_to_token_id.get(group.macula_node_id), macula_leaf_id_to_token_id.get(leaf_id),
            )
            stats.syntax_edges += 1
        for child_group_id in group.child_group_ids:
            child_group = macula_group_by_id.get(child_group_id)
            child_source_node_id = source_node_id_by_macula_id.get(child_group_id)
            if child_group is None or child_source_node_id is None:
                continue
            _insert_syntax_edge(
                store, macula_dataset_version_id, verse_ref, parent_source_node_id, child_source_node_id,
                child_group.macula_role, None, None,
            )
            stats.syntax_edges += 1

    participant_row_id_by_leaf: dict[str, int] = {}
    for leaf in combined_sentence.leaves:
        for ref_kind, ref_value in (("subjref", leaf.subjref), ("participantref", leaf.participantref)):
            for target_id in ref_value.split():
                target_id = _normalize_macula_ref_id(target_id)
                target_source_node_id = source_node_id_by_macula_id.get(target_id)
                if target_source_node_id is None:
                    continue
                participant_row_id = participant_row_id_by_leaf.get(target_id)
                if participant_row_id is None:
                    participant_row_id = _upsert_participant(
                        store, target_source_node_id, macula_dataset_version_id, verse_ref, macula_leaf_id_to_token_id.get(target_id)
                    )
                    participant_row_id_by_leaf[target_id] = participant_row_id
                    stats.participants += 1
                referring_source_node_id = source_node_id_by_macula_id.get(leaf.macula_node_id)
                if referring_source_node_id is None:
                    continue
                store.execute(
                    """
                    INSERT INTO hebrew_coreference
                        (dataset_version_id, verse_ref, referring_source_node_id, referring_token_id, participant_id, relation_type)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (
                        macula_dataset_version_id, verse_ref, referring_source_node_id,
                        macula_leaf_id_to_token_id.get(leaf.macula_node_id), participant_row_id, ref_kind,
                    ),
                )
                stats.coreference += 1

    for node_id_str, node in list(macula_leaves_by_id.items()) + [(g.macula_node_id, g) for g in combined_sentence.groups]:
        frame = getattr(node, "frame", "")
        if not frame:
            continue
        predicate_source_node_id = source_node_id_by_macula_id.get(node_id_str)
        if predicate_source_node_id is None:
            continue
        for segment in frame.split():
            if ":" not in segment:
                continue
            role_code, _, ids_part = segment.partition(":")
            role_code = role_code.strip()
            if not role_code:
                continue
            participant_ids = [_normalize_macula_ref_id(pid) for pid in ids_part.split(";") if pid]
            targets = participant_ids or [None]
            for participant_leaf_id in targets:
                participant_source_node_id = (
                    source_node_id_by_macula_id.get(participant_leaf_id) if participant_leaf_id else None
                )
                store.execute(
                    """
                    INSERT INTO hebrew_semantic_roles
                        (dataset_version_id, verse_ref, predicate_source_node_id, predicate_token_id,
                         role_code, role_label, participant_source_node_id, participant_token_id, confidence)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?, '')
                    """,
                    (
                        macula_dataset_version_id, verse_ref, predicate_source_node_id,
                        macula_leaf_id_to_token_id.get(node_id_str), role_code, _KNOWN_ROLE_LABELS.get(role_code, ""),
                        participant_source_node_id,
                        macula_leaf_id_to_token_id.get(participant_leaf_id) if participant_leaf_id else None,
                    ),
                )
                stats.semantic_roles += 1

    store.commit()


def _canonical_book_id_or_none(tahot_book_code: str) -> str | None:
    from bible_engine.hebrew_token_identity import TokenIdentityError, canonical_book_id_from_tahot_code

    try:
        return canonical_book_id_from_tahot_code(tahot_book_code)
    except TokenIdentityError:
        return None


def _merged_sentence(sentences: list[MaculaSentence]) -> MaculaSentence:
    if len(sentences) == 1:
        return sentences[0]
    leaves: list[MaculaLeaf] = []
    groups: list[MaculaGroup] = []
    for sentence in sentences:
        leaves.extend(sentence.leaves)
        groups.extend(sentence.groups)
    return MaculaSentence(sentence_id=sentences[0].sentence_id, root_group_id=sentences[0].root_group_id, leaves=tuple(leaves), groups=tuple(groups))


def _resolve_leaf_to_token_map(confirmed_alignments: list[TokenAlignment]) -> dict[str, str]:
    """Only leaves that a CONFIRMED alignment (§Phase 2D.1 §12 in the
    calling function's comment) actually paired with a token contribute a
    mapping here — never derived from raw ref_word_number/word_index
    coincidence, which can silently be wrong exactly when alignment
    recovery (a nonzero offset) or an outright UNRESOLVED result means
    that coincidence does not hold."""
    mapping: dict[str, str] = {}
    for alignment in confirmed_alignments:
        for component in alignment.components:
            if component.macula_leaf_id:
                mapping[component.macula_leaf_id] = alignment.token_id
    return mapping


def _upsert_verse(store, book_id: str, chapter: int, verse: int, verse_ref: str, language: str, dataset_version_id: int) -> int:
    row = store.execute("SELECT id FROM hebrew_verses WHERE verse_ref = ?", (verse_ref,)).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = store.execute(
        "INSERT INTO hebrew_verses (book_id, chapter, verse, verse_ref, language, dataset_version_id) VALUES (?, ?, ?, ?, ?, ?)",
        (book_id, chapter, verse, verse_ref, language, dataset_version_id),
    )
    return int(cursor.lastrowid)


def _upsert_token(store, token: HebrewToken, book_id: str, verse_row_id: int, source_token_id: str, dataset_version_id: int) -> None:
    token_id = build_token_id(token.book, token.chapter, token.verse, token.word_index)
    morphology: MorphologyFacts = _morphology_facts(token)
    store.execute(
        """
        INSERT OR REPLACE INTO hebrew_tokens (
            token_id, verse_id, legacy_stable_key, source_token_id, word_index,
            surface, surface_plain, lemma, transliteration, part_of_speech,
            morphology_raw_code, morphology_confidence, verb_stem, verb_form,
            person, gender, number, state, ketiv, qere, source_edition, maqaf, punctuation,
            dataset_version_id
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            token_id, verse_row_id, token.stable_key, source_token_id, token.word_index,
            token.surface, token.surface_without_accents, token.lemma, token.transliteration, morphology.part_of_speech,
            morphology.raw_code, morphology.confidence, morphology.verb_stem, morphology.verb_form,
            morphology.person, morphology.gender, morphology.number, morphology.state,
            token.ketiv, token.qere, token.source_edition, int(token.maqaf), token.punctuation,
            dataset_version_id,
        ),
    )
    for seq, strong_id in enumerate(token.strong_ids):
        store.execute(
            "INSERT OR REPLACE INTO hebrew_token_strong_ids (token_id, seq, strong_id) VALUES (?, ?, ?)",
            (token_id, seq, strong_id),
        )
    ordered = list(token.prefix_components) + ([token.core_component] if token.core_component else []) + list(token.suffix_components)
    for index, component in enumerate(ordered):
        store.execute(
            """
            INSERT OR REPLACE INTO hebrew_token_components
                (token_id, component_index, role, surface, gloss_en, strong_id, is_grammar_marker)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (token_id, index, component.role, component.surface, component.gloss, component.strong_id, int(component.strong_id.upper().startswith("H9"))),
        )


def _morphology_facts(token: HebrewToken) -> MorphologyFacts:
    morph = decode_hebrew_morphology(token.morphology_code)
    return MorphologyFacts(
        raw_code=morph.code,
        language=morph.language.lower() if morph.language else "",
        part_of_speech=morph.part_of_speech,
        verb_stem=morph.verb_stem,
        verb_form=morph.verb_conjugation,
        person=morph.person,
        gender=morph.gender,
        number=morph.number,
        state=morph.state,
        confidence=morph.status,
    )


def _import_source_nodes(store, groups: dict[str, MaculaGroup], leaves: dict[str, MaculaLeaf], verse_ref: str, dataset_version_id: int, out_id_map: dict[str, int]) -> None:
    ordered_groups = sorted(groups.values(), key=lambda g: g.doc_order)
    for group in ordered_groups:
        parent_id = out_id_map.get(group.parent_group_id) if group.parent_group_id else None
        row = store.execute(
            "SELECT id FROM hebrew_source_nodes WHERE dataset_version_id = ? AND macula_node_id = ?",
            (dataset_version_id, group.macula_node_id),
        ).fetchone()
        if row is not None:
            out_id_map[group.macula_node_id] = int(row["id"])
            continue
        cursor = store.execute(
            """
            INSERT INTO hebrew_source_nodes
                (dataset_version_id, macula_node_id, node_kind, macula_class, macula_role, macula_rule,
                 clause_type, parent_node_id, child_order, verse_ref, raw_attributes)
            VALUES (?, ?, 'group', ?, ?, ?, ?, ?, ?, ?, '{}')
            """,
            (dataset_version_id, group.macula_node_id, group.macula_class, group.macula_role, group.macula_rule,
             group.clause_type, parent_id, group.child_order, verse_ref),
        )
        out_id_map[group.macula_node_id] = int(cursor.lastrowid)

    ordered_leaves = sorted(leaves.values(), key=lambda leaf: leaf.doc_order)
    for leaf in ordered_leaves:
        parent_id = out_id_map.get(leaf.parent_group_id) if leaf.parent_group_id else None
        row = store.execute(
            "SELECT id FROM hebrew_source_nodes WHERE dataset_version_id = ? AND macula_node_id = ?",
            (dataset_version_id, leaf.macula_node_id),
        ).fetchone()
        if row is not None:
            out_id_map[leaf.macula_node_id] = int(row["id"])
            continue
        cursor = store.execute(
            """
            INSERT INTO hebrew_source_nodes
                (dataset_version_id, macula_node_id, node_kind, macula_class, macula_role, parent_node_id,
                 child_order, verse_ref, surface, lemma, transliteration, gloss_en,
                 macula_strong_number, macula_morph_code, macula_part_of_speech, macula_stem,
                 macula_person, macula_gender, macula_number, raw_attributes)
            VALUES (?, ?, 'word', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                dataset_version_id, leaf.macula_node_id, leaf.part_of_speech, leaf.role, parent_id, leaf.child_order,
                verse_ref, leaf.surface, leaf.lemma, leaf.transliteration, leaf.gloss_en,
                leaf.strong_number or leaf.oshb_strongs, leaf.morph_code, leaf.part_of_speech, leaf.stem,
                leaf.person, leaf.gender, leaf.number, json.dumps(leaf.raw_attributes, ensure_ascii=False),
            ),
        )
        out_id_map[leaf.macula_node_id] = int(cursor.lastrowid)


def _record_alignment(store, alignment, source_node_id_by_macula_id: dict[str, int], textus_dv: int, macula_dv: int) -> None:
    if alignment.alignment_type == "UNRESOLVED":
        store.execute(
            """
            INSERT INTO hebrew_token_alignments
                (token_id, component_index, source_node_id, alignment_type, confidence, evidence,
                 dataset_version_id_textus, dataset_version_id_macula)
            VALUES (?, NULL, NULL, ?, ?, ?, ?, ?)
            """,
            (alignment.token_id, alignment.alignment_type, alignment.confidence, alignment.evidence, textus_dv, macula_dv),
        )
        return
    for component in alignment.components:
        source_node_id = source_node_id_by_macula_id.get(component.macula_leaf_id) if component.macula_leaf_id else None
        store.execute(
            """
            INSERT INTO hebrew_token_alignments
                (token_id, component_index, source_node_id, alignment_type, confidence, evidence,
                 dataset_version_id_textus, dataset_version_id_macula)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                alignment.token_id, component.component_index, source_node_id, alignment.alignment_type,
                alignment.confidence, alignment.evidence, textus_dv, macula_dv,
            ),
        )


def _upsert_phrase(store, source_node_id: int, dataset_version_id: int, verse_ref: str, group: MaculaGroup) -> int:
    row = store.execute(
        "SELECT id FROM hebrew_phrases WHERE dataset_version_id = ? AND source_node_id = ?",
        (dataset_version_id, source_node_id),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = store.execute(
        "INSERT INTO hebrew_phrases (source_node_id, dataset_version_id, verse_ref, phrase_type, child_order) VALUES (?, ?, ?, ?, ?)",
        (source_node_id, dataset_version_id, verse_ref, group.macula_class, group.child_order),
    )
    return int(cursor.lastrowid)


def _upsert_clause(store, source_node_id: int, dataset_version_id: int, verse_ref: str, group: MaculaGroup) -> int:
    row = store.execute(
        "SELECT id FROM hebrew_clauses WHERE dataset_version_id = ? AND source_node_id = ?",
        (dataset_version_id, source_node_id),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = store.execute(
        "INSERT INTO hebrew_clauses (source_node_id, dataset_version_id, verse_ref, clause_type, child_order) VALUES (?, ?, ?, ?, ?)",
        (source_node_id, dataset_version_id, verse_ref, group.clause_type, group.child_order),
    )
    return int(cursor.lastrowid)


def _link_parent(store, group: MaculaGroup, phrase_id_by_group: dict[str, int], clause_id_by_group: dict[str, int]) -> None:
    own_phrase_id = phrase_id_by_group.get(group.macula_node_id)
    own_clause_id = clause_id_by_group.get(group.macula_node_id)
    parent_phrase_id = phrase_id_by_group.get(group.parent_group_id)
    parent_clause_id = clause_id_by_group.get(group.parent_group_id)
    if own_phrase_id is not None:
        store.execute(
            "UPDATE hebrew_phrases SET parent_phrase_id = ?, parent_clause_id = ? WHERE id = ?",
            (parent_phrase_id, parent_clause_id, own_phrase_id),
        )
    if own_clause_id is not None and parent_clause_id is not None:
        store.execute("UPDATE hebrew_clauses SET parent_clause_id = ? WHERE id = ?", (parent_clause_id, own_clause_id))


def _insert_membership(store, token_id: str | None, phrase_id: int | None, clause_id: int | None) -> None:
    if token_id is None or (phrase_id is None and clause_id is None):
        return
    store.execute(
        "INSERT INTO hebrew_syntax_membership (token_id, phrase_id, clause_id) VALUES (?, ?, ?)",
        (token_id, phrase_id, clause_id),
    )


def _insert_syntax_edge(store, dataset_version_id: int, verse_ref: str, parent_source_node_id: int, child_source_node_id: int, role_code: str, parent_token_id: str | None, child_token_id: str | None) -> None:
    relation_type = _KNOWN_RELATION_TYPES.get(role_code, "other")
    store.execute(
        """
        INSERT OR IGNORE INTO hebrew_syntax_edges
            (dataset_version_id, verse_ref, parent_source_node_id, child_source_node_id,
             relation_type, source_role_code, parent_token_id, child_token_id)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (dataset_version_id, verse_ref, parent_source_node_id, child_source_node_id, relation_type, role_code, parent_token_id, child_token_id),
    )


def _upsert_participant(store, source_node_id: int, dataset_version_id: int, verse_ref: str, token_id: str | None) -> int:
    row = store.execute(
        "SELECT id FROM hebrew_participants WHERE dataset_version_id = ? AND source_node_id = ?",
        (dataset_version_id, source_node_id),
    ).fetchone()
    if row is not None:
        return int(row["id"])
    cursor = store.execute(
        "INSERT INTO hebrew_participants (dataset_version_id, source_node_id, token_id, verse_ref) VALUES (?, ?, ?, ?)",
        (dataset_version_id, source_node_id, token_id, verse_ref),
    )
    return int(cursor.lastrowid)


__all__ = ["ImportStats", "ensure_dataset_version", "import_chapter"]
