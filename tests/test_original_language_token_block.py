"""`app.py::build_original_language_token_block` — helyi eredeti nyelvi
token-lista, kizárólagos forrás (nem generálható).

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS (2026-08-13, tesztalap-stabilizálás):
`app.py` egy tiszta Streamlit-szkript — nincs benne `if __name__ ==
"__main__":` őr, minden `st.*` hívása (pl. `st.form("textus_feedback_form",
...)`) a modul TETEJÉN, importáláskor fut le. A `build_original_language_
token_block` maga Streamlit-független, tiszta logika (csak helyi
lexikon-repository hívásokat végez), de mivel ugyanabban a fájlban él, a
puszta `from app import build_original_language_token_block` a TELJES
app.py-t végrehajtja — a valódi, nem AppTest-sandboxolt Streamlit
DeltaGenerator-singleton ellenében. Ez korrumpálja a Streamlit globális
form-/widget-nyomkövetési állapotát a pytest-folyamatban, és a KÉSŐBB (a
teljes `pytest tests/` futásban, ábécésorrendben utána) végrehajtódó,
AppTest-alapú tesztek (pl. tests/test_bible_text_reading_view.py) hamis,
"DeltaGeneratorSingleton instance already exists!" / "st.button() can't be
used in an st.form()" hibákkal buknak — bizonyítva minimális, determinisztikus
2 fájlos reprodukcióval (`pytest tests/test_bible_text_reading_view.py
tests/test_original_language_token_block.py`).

Ez KIZÁRÓLAG tesztinfrastruktúra-probléma — production alatt az app.py-t
mindig `streamlit run app.py` futtatja, valódi Streamlit-runtime kontextusban,
ahol ez nem jelentkezik. A termékkódot (app.py, build_original_language_
token_block) NEM módosítottuk. A javítás: a függvényt egy KÜLÖN
ALFOLYAMATBAN hívjuk, hogy az app.py importálásának mellékhatásai sose
szennyezzék a fő pytest-folyamat megosztott Streamlit-állapotát."""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_WORKER_TEMPLATE = """
import json
import sys

sys.path.insert(0, {root!r})

from app import build_original_language_token_block

with open({in_path!r}, encoding="utf-8") as f:
    payload = json.load(f)

result = build_original_language_token_block(payload["igehely"])

with open({out_path!r}, "w", encoding="utf-8") as f:
    json.dump({{"result": result}}, f)
"""


def _build_token_block_in_subprocess(igehely: str) -> str:
    """`build_original_language_token_block` hívása elkülönített Python-
    alfolyamatban (ld. modul docstring — az app.py importálásának
    Streamlit-mellékhatásai miatt szükséges elszigetelés)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        in_path = Path(tmp_dir) / "in.json"
        out_path = Path(tmp_dir) / "out.json"
        in_path.write_text(json.dumps({"igehely": igehely}), encoding="utf-8")

        script = _WORKER_TEMPLATE.format(
            root=str(ROOT), in_path=str(in_path), out_path=str(out_path)
        )
        proc = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"build_original_language_token_block({igehely!r}) alfolyamat-hiba:\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
        payload = json.loads(out_path.read_text(encoding="utf-8"))
        return payload["result"]


def test_greek_passage_returns_real_tokens_not_free_generation() -> None:
    block = _build_token_block_in_subprocess("Jn 3:16")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    assert "Nincs" not in block.splitlines()[0]
    lines = block.splitlines()[1:]
    assert len(lines) == 26  # Jn 3:16 TAGNT token count

    first = lines[0]
    assert first.startswith("[1] ")
    assert "lemma:" in first
    assert "morf:" in first
    assert "Strong:" in first
    # word_index 3 is ἠγάπησεν / ἀγαπάω, Strong G0025 (already "G"-prefixed
    # in the source data — must appear verbatim, not double-prefixed as "GG0025").
    assert "G0025" in block
    assert "GG0025" not in block


def test_hebrew_passage_returns_real_tokens_not_free_generation() -> None:
    block = _build_token_block_in_subprocess("1Móz 1:1")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    lines = block.splitlines()[1:]
    assert len(lines) == 7  # Gen 1:1 TAHOT token count

    first = lines[0]
    assert first.startswith("[1] ")
    assert "lemma:" in first
    assert "Strong:" in first
    assert "H7225" in block  # רֵאשִׁית -> Strong H7225, must appear verbatim from DB

    # Phase 2A: the Hebrew line no longer forwards a bare "morf: <TEHMC code>"
    # and an English part of speech. The morphology Textus has already decoded
    # is supplied explicitly so the AI never has to re-parse Hebrew grammar,
    # with the raw code retained only for traceability.
    assert "morf-kód: HR/Ncfsa" in first
    assert "szófaj: elöljárószó + főnév" in first
    verb = lines[1]  # בָּרָא — Qal perfect 3ms
    assert "igetörzs: qal" in verb
    assert "igealak: perfectum" in verb
    assert "személy: harmadik személy" in verb
    assert "morf-kód: HVqp3ms" in verb


def test_cross_chapter_reference_yields_explicit_no_data_message_not_generated_content() -> None:
    block = _build_token_block_in_subprocess("Jn 3,16-4,2")

    assert block.startswith("EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):\n")
    body = block.split("\n", 1)[1]
    # Explicit "no data" signal, not a fabricated token list.
    assert "Nincs lekérhető token-adat" in body
    assert "[1]" not in body
    assert "lemma:" not in body
