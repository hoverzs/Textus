"""Phase 2C — restore per-component surface/gloss fidelity onto
``HebrewToken`` objects read from the pruned production TAHOT database.

The production database (``tahot_ot_runtime.sqlite3``) was deliberately
pruned (see ``scripts/prune_tahot_runtime_db.py``) to drop each component's
own surface text and gloss — a prefix or suffix component's ``surface`` field
comes back empty from ``bible_engine.hebrew_sqlite._token_from_normalized_row``
today, even though the component genuinely exists (its role and Strong id
are preserved via ``token_strong_ids``). This module restores the missing
text from the compact ``data/generated/hebrew_component_fidelity.sqlite3``
store (see ``scripts/build_hebrew_component_fidelity_store.py``), without
touching the production database itself.

Per-component morphology is NOT restored here — it is already correctly
derivable from the token's composite ``morphology_code`` via
``bible_engine.hebrew_morphology.decode_hebrew_morphology`` (see that
module's docstring), so this repository leaves ``HebrewComponent.
morphology_code`` as the composite code the production row already carries
and lets callers decode per-component fields themselves when needed.
"""

from __future__ import annotations

import sqlite3
from dataclasses import replace
from pathlib import Path

from bible_engine.hebrew_parser import HebrewComponent, HebrewToken
from bible_engine.hebrew_sqlite import resolve_tahot_database_path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_COMPONENT_FIDELITY_PATH = ROOT / "data" / "generated" / "hebrew_component_fidelity.sqlite3"


class ComponentFidelityUnavailable(RuntimeError):
    """Raised when the compact fidelity store is missing. Callers should
    treat this as a coverage gap (see ``CoverageReport.has_component_fidelity``
    on ``HebrewAnalysisBundle``), never fall back to guessing component text."""


def resolve_component_fidelity_path(path: str | Path | None = None) -> Path:
    return Path(path) if path is not None else DEFAULT_COMPONENT_FIDELITY_PATH


def restore_component_fidelity(
    tokens: list[HebrewToken],
    *,
    production_db_path: str | Path | None = None,
    fidelity_db_path: str | Path | None = None,
) -> tuple[dict[str, HebrewToken], dict[str, str]]:
    """Given ``HebrewToken`` objects (as returned by ``HebrewTokenRepository``),
    return (1) the same tokens keyed by ``stable_key`` with prefix/core/suffix
    component ``surface``/``gloss`` filled in from the fidelity store, and
    (2) a ``stable_key -> source_token_id`` map (e.g. ``"Rut.1.1#01=L"``),
    the Phase 2D MACULA alignment anchor — see
    ``bible_engine.hebrew_token_identity``.

    Tokens with no fidelity-store match (e.g. the store predates a token, or
    a caller points ``fidelity_db_path`` at a partial rebuild) are returned
    unmodified, with no entry in the source-id map — callers must not treat
    a missing entry as an error; it degrades to the production database's
    existing (empty-surface) component fallback.
    """
    by_key = {token.stable_key: token for token in tokens}
    if not by_key:
        return {}, {}

    production_path = resolve_tahot_database_path(production_db_path)
    fidelity_path = resolve_component_fidelity_path(fidelity_db_path)
    if not fidelity_path.exists():
        raise ComponentFidelityUnavailable(f"Component-fidelity store not found: {fidelity_path}")

    with sqlite3.connect(production_path) as prod:
        placeholders = ",".join("?" for _ in by_key)
        token_ids: dict[str, int] = dict(
            prod.execute(
                f"SELECT stable_token_key, token_id FROM tokens WHERE stable_token_key IN ({placeholders})",
                list(by_key),
            ).fetchall()
        )
    if not token_ids:
        return dict(by_key), {}

    id_to_key = {token_id: key for key, token_id in token_ids.items()}
    with sqlite3.connect(fidelity_path) as fidelity:
        fidelity.row_factory = sqlite3.Row
        placeholders = ",".join("?" for _ in token_ids)
        component_rows = fidelity.execute(
            f"""
            SELECT token_id, component_index, surface, gloss
            FROM token_components
            WHERE token_id IN ({placeholders})
            ORDER BY token_id, component_index
            """,
            list(token_ids.values()),
        ).fetchall()
        source_id_rows = fidelity.execute(
            f"SELECT token_id, source_token_id FROM token_source_ids WHERE token_id IN ({placeholders})",
            list(token_ids.values()),
        ).fetchall()

    components_by_token_id: dict[int, list[sqlite3.Row]] = {}
    for row in component_rows:
        components_by_token_id.setdefault(row["token_id"], []).append(row)

    source_ids: dict[str, str] = {
        id_to_key[row["token_id"]]: row["source_token_id"] for row in source_id_rows if row["token_id"] in id_to_key
    }

    restored: dict[str, HebrewToken] = {}
    for key, token in by_key.items():
        token_id = token_ids.get(key)
        fidelity_rows = components_by_token_id.get(token_id) if token_id is not None else None
        if not fidelity_rows:
            restored[key] = token
            continue
        restored[key] = _apply_component_fidelity(token, fidelity_rows)
    return restored, source_ids


def _apply_component_fidelity(token: HebrewToken, fidelity_rows: list[sqlite3.Row]) -> HebrewToken:
    # Canonical left-to-right component order — verified at build time
    # (see scripts/build_hebrew_component_fidelity_store.py's
    # _verify_component_alignment) to match component_index order exactly.
    ordered: list[HebrewComponent] = list(token.prefix_components)
    if token.core_component is not None:
        ordered.append(token.core_component)
    ordered.extend(token.suffix_components)

    if len(ordered) != len(fidelity_rows):
        # Coverage gap for this token (e.g. store built from a different
        # source snapshot) — leave the token's components untouched rather
        # than risk zipping mismatched positions.
        return token

    updated = [
        replace(component, surface=row["surface"], gloss=row["gloss"])
        for component, row in zip(ordered, fidelity_rows)
    ]
    prefix_count = len(token.prefix_components)
    core_offset = prefix_count + (1 if token.core_component is not None else 0)
    new_prefixes = tuple(updated[:prefix_count])
    new_core = updated[prefix_count] if token.core_component is not None else None
    new_suffixes = tuple(updated[core_offset:])

    return replace(
        token,
        prefix_components=new_prefixes,
        core_component=new_core,
        suffix_components=new_suffixes,
    )


__all__ = [
    "DEFAULT_COMPONENT_FIDELITY_PATH",
    "ComponentFidelityUnavailable",
    "resolve_component_fidelity_path",
    "restore_component_fidelity",
]
