"""Phase 2C §1 — one explicit Greek Analysis v2 dataset version/signature.

Combines every deterministic input this codebase currently pins, so the
signature changes if ANY of them would change a fact the AI layer might
explain — the cache (§16) and any future Supabase-backed repository
invalidate automatically the moment this string changes, with no separate
invalidation logic (identical principle to Hebrew's
``dataset_version_signature()``, see
bible_engine.hebrew_analysis_repository).
"""

from __future__ import annotations

# Pinned per docs/greek_analysis_v2_phase2a_foundation.md §1 and
# docs/greek_analysis_v2_phase2b1_full_corpus.md §5 — update these
# constants (and bump ALIGNMENT_ALGORITHM_VERSION / SCHEMA_VERSION as
# appropriate) whenever any of the underlying sources or code is re-pinned
# or changed in a way that could alter a deterministic fact.
STEPBIBLE_DATA_COMMIT = "ae39711d7843b2902d54993e432de9c12d6a4b9a"
MACULA_GREEK_COMMIT = "8423afe47b9e8f24b7772e808af45c7159a6fe7e"

TAGNT_VERSION = f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}"
TEGMC_VERSION = f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}"
TBESG_VERSION = f"stepbible-data@{STEPBIBLE_DATA_COMMIT[:12]}"
HUNGARIAN_LEXICON_VERSION = "greek-hu-lexicon@phase2a"
MACULA_GREEK_VERSION = f"clear-bible-macula-greek@{MACULA_GREEK_COMMIT[:12]}"

# Bump when bible_engine.greek_token_alignment's matching logic changes in
# any way that could change an EXACT/COMPOSITE/VALIDATED_FALLBACK/
# UNRESOLVED_* classification for any token.
ALIGNMENT_ALGORITHM_VERSION = "greek-align-v1"

# Bump when the normalized schema shape changes (new/removed/renamed field
# on GreekAnalysisBundle/GreekTokenAnalysis/GreekVerseAnalysis, or the
# Supabase greek_* table shapes) in a way that would change what a cached
# result or a repository read returns.
NORMALIZED_SCHEMA_VERSION = "greek-schema-2c-v1"


def greek_dataset_version_signature() -> str:
    """A short, stable, sorted string identifying every pinned input.
    Mirrors bible_engine.hebrew_analysis_repository's own
    dataset_version_signature() contract exactly: deterministic, order-
    independent of dict construction, safe to use directly as a cache key
    component (Phase 2C §16)."""
    parts = {
        "tagnt": TAGNT_VERSION,
        "tegmc": TEGMC_VERSION,
        "tbesg": TBESG_VERSION,
        "greek_hu_lexicon": HUNGARIAN_LEXICON_VERSION,
        "macula_greek": MACULA_GREEK_VERSION,
        "alignment_algorithm": ALIGNMENT_ALGORITHM_VERSION,
        "schema": NORMALIZED_SCHEMA_VERSION,
    }
    return ",".join(f"{key}:{value}" for key, value in sorted(parts.items()))


__all__ = [
    "STEPBIBLE_DATA_COMMIT",
    "MACULA_GREEK_COMMIT",
    "TAGNT_VERSION",
    "TEGMC_VERSION",
    "TBESG_VERSION",
    "HUNGARIAN_LEXICON_VERSION",
    "MACULA_GREEK_VERSION",
    "ALIGNMENT_ALGORITHM_VERSION",
    "NORMALIZED_SCHEMA_VERSION",
    "greek_dataset_version_signature",
]
