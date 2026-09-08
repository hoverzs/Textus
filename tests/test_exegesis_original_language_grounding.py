"""RESET 3B-3 — az egzegézis modul eredeti nyelvi (görög/héber)
groundingja.

Cél: az egzegézis promptja a MEGLÉVŐ, helyi görög/héber token-adatbázisból
származó, determinisztikus token-blokkot kapja meg (`app.py::
build_original_language_token_block` — UGYANAZ, amiből az "Eredeti szöveg"
modul is dolgozik), ne a modell saját tréningemlékezetéből generáljon
görög/héber állítást.

FONTOS TESZTINFRASTRUKTÚRA-MEGJEGYZÉS — ugyanaz a korlátozás, mint a
`tests/test_original_language_token_block.py`-ban dokumentálva: `app.py`
egy tiszta Streamlit-szkript, aminek puszta importálása (`from app import
...`) a FŐ pytest-folyamatban korrumpálja a Streamlit globális
DeltaGenerator-állapotát, és később futó AppTest-alapú teszteket
hamisan buktat. Ezért minden, `app.py`-t importáló művelet egy KÜLÖN
ALFOLYAMATBAN fut. Mivel itt (a token-blokk-teszttel ellentétben)
`st.session_state`-re is szükség van (`build_alap_from_state` ezt
olvassa), az alfolyamat-szkript `streamlit.testing.v1.AppTest`-et használ
— ehhez a szkriptnek VALÓDI fájlként kell léteznie (`inspect.
getsourcelines` nem tud forrást olvasni egy `python -c` inline szkript
függvényéből), ezért egy ideiglenes `.py` fájlba írjuk, és úgy futtatjuk.
"""

from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

_WORKER_TEMPLATE = '''
import json
import sys

sys.path.insert(0, {root!r})

from streamlit.testing.v1 import AppTest


def _render():
    import streamlit as st
    from app import (
        SECTION_PROMPTS,
        build_alap_from_state,
        build_original_language_token_block,
    )

    st.session_state["last_igehely"] = {igehely!r}
    st.session_state["bible_translation"] = {translation!r}
    st.session_state["passage_text"] = {passage_text!r}

    alap_exegesis = build_alap_from_state(include_original_language_tokens=True)
    alap_history = build_alap_from_state(include_original_language_tokens=False)
    exegesis_prompt = SECTION_PROMPTS["exegesis"].format(alap=alap_exegesis)
    history_prompt = SECTION_PROMPTS["history"].format(alap=alap_history)
    direct_token_block = build_original_language_token_block({igehely!r})

    st.session_state["_worker_result"] = {{
        "alap_exegesis": alap_exegesis,
        "alap_history": alap_history,
        "exegesis_prompt": exegesis_prompt,
        "history_prompt": history_prompt,
        "direct_token_block": direct_token_block,
    }}


app = AppTest.from_function(_render).run(timeout=60)
result = app.session_state["_worker_result"]

with open({out_path!r}, "w", encoding="utf-8") as f:
    json.dump(result, f)
'''


def _run_worker(*, igehely: str, translation: str = "", passage_text: str = "") -> dict:
    """`build_alap_from_state`/`SECTION_PROMPTS["exegesis"]` hívása egy
    elkülönített alfolyamatban, VALÓDI ideiglenes .py fájlon keresztül
    (ld. modul docstring)."""
    with tempfile.TemporaryDirectory() as tmp_dir:
        out_path = Path(tmp_dir) / "out.json"
        worker_path = Path(tmp_dir) / "worker.py"
        script = _WORKER_TEMPLATE.format(
            root=str(ROOT),
            igehely=igehely,
            translation=translation,
            passage_text=passage_text,
            out_path=str(out_path),
        )
        worker_path.write_text(script, encoding="utf-8")
        proc = subprocess.run(
            [sys.executable, str(worker_path)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            cwd=str(ROOT),
            timeout=120,
        )
        assert proc.returncode == 0, (
            f"worker alfolyamat-hiba ({igehely!r}):\n"
            f"stdout={proc.stdout}\nstderr={proc.stderr}"
        )
        return json.loads(out_path.read_text(encoding="utf-8"))


# =============================================================================
# 1-2. ÚSZ/ÓSZ exegesis prompt tényleges token-blokkot kap
# =============================================================================


def test_1_nt_exegesis_prompt_contains_real_greek_token_block():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    prompt = result["exegesis_prompt"]
    assert "EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):" in prompt
    assert "[1]" in prompt
    assert "lemma:" in prompt
    assert "morf:" in prompt
    assert "Strong:" in prompt
    # Ugyanaz a konkrét, ismert token, mint a meglévő
    # test_original_language_token_block.py-ban (ἠγάπησεν / G0025).
    assert "G0025" in prompt


def test_2_ot_exegesis_prompt_contains_real_hebrew_token_block():
    result = _run_worker(igehely="1Móz 1:1", passage_text="Kezdetben teremté Isten...")
    prompt = result["exegesis_prompt"]
    assert "EREDETI NYELVI TOKENEK (helyi adatbázisból, kizárólagos forrás):" in prompt
    assert "lemma:" in prompt
    assert "Strong:" in prompt
    assert "H7225" in prompt
    # Phase 2A: the exegesis prompt reuses the same Hebrew token block, so it
    # must also carry the already-decoded morphology rather than a raw code.
    assert "morf-kód: HVqp3ms" in prompt
    assert "igetörzs: qal" in prompt
    assert "igealak: perfectum" in prompt


# =============================================================================
# 3. Ugyanabból a helyi source-of-truthból származik, mint az
#    original_text modulnál
# =============================================================================


def test_3_exegesis_token_block_is_byte_identical_to_original_text_source():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    # Az `alap_exegesis`-ben szereplő token-blokknak SZÓ SZERINT
    # tartalmaznia kell a `build_original_language_token_block` közvetlen
    # eredményét -- nem egy párhuzamos, újraimplementált változatot.
    assert result["direct_token_block"] in result["alap_exegesis"]
    assert result["direct_token_block"] in result["exegesis_prompt"]


# =============================================================================
# 4. Hiányzó tokenadat esetén az exegesis továbbra is működik
# =============================================================================


def test_4_missing_token_data_does_not_break_exegesis_prompt_and_forbids_invention():
    # Fejezetközi hivatkozás -- a token-block ilyenkor explicit
    # "nincs adat" üzenetet ad (ld. test_original_language_token_block.py).
    result = _run_worker(igehely="Jn 3,16-4,2", passage_text="")
    prompt = result["exegesis_prompt"]
    assert "Nincs lekérhető token-adat" in prompt or "nincs" in prompt.lower()
    # A prompt EZ ESETBEN IS tartalmazza a tiltó/óvatossági utasítást --
    # a modell akkor sem generálhat új nyelvi állítást, ha nincs adat.
    assert "GÖRÖG/HÉBER HIVATKOZÁS SZIGORÚ HATÁRA" in prompt


# =============================================================================
# 5-6. Explicit tilalom / nem kötelező jelleg a promptban
# =============================================================================


def test_5_prompt_explicitly_forbids_inventing_new_linguistic_data():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    prompt = result["exegesis_prompt"]
    assert (
        "Új szóalakot, lemmát, morfológiai adatot vagy Strong-számot NEM "
        "találhatsz" in prompt
    )
    assert "a KIZÁRÓLAGOS forrásod" in prompt


def test_6_prompt_states_original_language_insight_is_not_mandatory():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    prompt = result["exegesis_prompt"]
    assert "NEM KÖTELEZŐ minden alcímhez" in prompt


# =============================================================================
# 7. A meglévő exegesis szerkezet/output-elvárás változatlan
# =============================================================================


def test_7_existing_exegesis_headings_are_unchanged():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    prompt = result["exegesis_prompt"]
    for heading in (
        "## Műfaj és szerkezet",
        "## Kontextus",
        "## Kulcsszavak és kulcskifejezések",
        "## Nyelvtani és szerkezeti megfigyelések",
        "## Párhuzamos bibliai helyek",
        "## Értelmezési kérdések",
        "## Prédikációs haszon",
    ):
        assert heading in prompt, heading


# =============================================================================
# 8. A token-blokk NEM szivárog más szekciók promptjába (opt-in scope)
# =============================================================================


def test_8_token_block_does_not_leak_into_other_sections():
    result = _run_worker(igehely="Jn 3:16", passage_text="Mert úgy szerette Isten a világot.")
    assert "EREDETI NYELVI TOKENEK" not in result["alap_history"]
    assert "EREDETI NYELVI TOKENEK" not in result["history_prompt"]
