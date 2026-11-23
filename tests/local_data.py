"""Futtatási feltételek a gitignore-olt, helyben generált adatbázisokra épülő tesztekhez.

A ``data/generated/`` alatti SQLite-állományok nincsenek a Gitben (méret és
licenc miatt), ezért egy friss klónban hiányoznak. Az ezekre épülő tesztek
korábban hibával buktak el; mostantól a csomag többi adatfüggő tesztjéhez
(pl. ``greek_syntax_dev.sqlite3 not built locally``) hasonlóan, megnevezett
okkal kihagyódnak, ha az állomány nincs meg. Ha megvan, változatlanul lefutnak.

Az útvonalak az alkalmazás saját alapértelmezett konstansaiból jönnek, így a
feltétel pontosan azt az állományt vizsgálja, amelyet a kód is megnyitna.
Részletek: docs/audits/test_baseline_2026-11-22.md (2026-11-23-i kiegészítés).
"""

from __future__ import annotations

import pytest

from ruf_bible_local_db import DEFAULT_DATABASE_PATH as RUF_BIBLE_DB
from textus_kb.importers.aquifer_bible_dictionary_sqlite import (
    DEFAULT_DATABASE_PATH as AQUIFER_DICTIONARY_DB,
)
from textus_kb.importers.aquifer_study_notes_sqlite import (
    DEFAULT_DATABASE_PATH as AQUIFER_STUDY_NOTES_DB,
)


def _reason(*paths) -> str:
    names = ", ".join(f"data/generated/{path.name}" for path in paths)
    return f"local generated database not present: {names} (gitignored; see docs/audits/test_baseline_2026-11-22.md)"


requires_ruf_bible_db = pytest.mark.skipif(
    not RUF_BIBLE_DB.exists(), reason=_reason(RUF_BIBLE_DB)
)

requires_aquifer_dictionary_db = pytest.mark.skipif(
    not AQUIFER_DICTIONARY_DB.exists(), reason=_reason(AQUIFER_DICTIONARY_DB)
)

requires_aquifer_study_notes_db = pytest.mark.skipif(
    not AQUIFER_STUDY_NOTES_DB.exists(), reason=_reason(AQUIFER_STUDY_NOTES_DB)
)

# Bizonyítva (2026-11-23): a test_disabled_acai_graceful bármelyik Aquifer-
# adatbázissal lefut, de ha mindkettő hiányzik, a build_id a Phase 3c-s
# pilotra esik vissza.
requires_any_aquifer_db = pytest.mark.skipif(
    not (AQUIFER_DICTIONARY_DB.exists() or AQUIFER_STUDY_NOTES_DB.exists()),
    reason=_reason(AQUIFER_DICTIONARY_DB, AQUIFER_STUDY_NOTES_DB),
)
