# ruff: noqa: E402
"""Stabilizáció 1. fázis: a sikertelen Gemini-hívás eredménye nem lehet tartalom.

Viselkedési szerződés: HIBAÁLLAPOT != TARTALOM.

Ha a `generate_text()` bármilyen okból NEM tud érdemi választ adni (hálózati
hiba, időtúllépés, HTTP-hiba, kvóta, üres válasz, globális várakozás), akkor
a `generate_section()` útján

  * a szekció tartalmi mezője (`exegesis`) nem változhat meg — sem üres
    mezőbe, sem egy meglévő, jó tartalom helyére nem kerülhet a hibaszöveg;
  * a hibaszöveg nem juthat el a homiletikai munkafolyamat kontextusába
    (hétpontos vázlat, tervrajz, a vázlatmotor kanonikus forrásgyűjtője).

A teszt a VALÓDI `generate_text()` hibaágait hajtja végre: csak a
`requests.post` (hálózat) és a várakozás (`time.sleep`) van kiváltva.
Gemini API-t, Supabase-t, tudástárat nem érint. A teszt nem a hibaüzenet
szövegére épít: azt a tényleges visszatérési értéket figyeli, amelyet a
`generate_text()` az adott hibaágon ténylegesen visszaadott.
"""

from __future__ import annotations

import sys
import time
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

REFERENCE = "Júd 17–20"
PASSAGE_TEXT = "Ti pedig, szeretteim, emlékezzetek arra, amit előre megmondtak az apostolok."
PRIOR_GOOD = "## Korábbi, jó exegézis\n\nA perikópa központi hangsúlya a kitartás."
GOOD_ANSWER = "A perikópa központi hangsúlya az emlékezés és a kitartás Isten szeretetében."


def _collapse(text: str) -> str:
    return " ".join(str(text).split())


class _FakeResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text
        self.headers: dict[str, str] = {}

    def json(self) -> dict:
        return self._payload


def _ok_payload(text: str) -> dict:
    return {
        "candidates": [
            {"content": {"parts": [{"text": text}]}, "finishReason": "STOP"}
        ]
    }


def _post_returning(response: _FakeResponse):
    def _post(*_a, **_k):
        return response

    return _post


def _post_raising(exc: BaseException):
    def _post(*_a, **_k):
        raise exc

    return _post


def _post_forbidden(*_a, **_k):
    raise AssertionError("a teszt nem hívhat hálózatot ezen az úton")


# mód -> (requests.post helyettesítő | None, session_state előkészítő | None)
_FAILURE_MODES = {
    "kapcsolati_hiba": (_post_raising(requests.exceptions.ConnectionError("down")), None),
    "idotullepes": (_post_raising(requests.exceptions.Timeout("slow")), None),
    "http_500": (_post_returning(_FakeResponse(500, text="boom")), None),
    "http_429_kvota": (_post_returning(_FakeResponse(429, text="quota")), None),
    "http_404_modell": (_post_returning(_FakeResponse(404, text="no model")), None),
    "ures_valasz": (_post_returning(_FakeResponse(200, {"candidates": [{"content": {"parts": []}}]})), None),
    # Globális várakozás: nincs HTTP-hívás, a generate_text "várj" szöveget ad.
    "globalis_varakozas": (_post_forbidden, lambda s: s.__setitem__("_last_api_call_ts", time.time())),
}


class _Harness:
    """A valódi `generate_section` -> `generate_text` láncot futtatja, a
    hálózat nélkül. Rögzíti, mit adott vissza ténylegesen a `generate_text`."""

    def __init__(self, monkeypatch: pytest.MonkeyPatch, state: dict) -> None:
        import app as app_mod

        self.app = app_mod
        self.state = state
        self.returned: list[str] = []
        st_mock = MagicMock()
        st_mock.session_state = state
        monkeypatch.setattr(app_mod, "st", st_mock)
        monkeypatch.setattr(app_mod, "_resolve_api_key", lambda: "fake-key")
        monkeypatch.setattr(app_mod, "_sync_inputs_to_last", lambda: None)
        monkeypatch.setattr(app_mod, "build_alap_from_state", lambda **_k: f"ALAP: {REFERENCE}")
        # Tudástár / Supabase-ág kikapcsolva: a teszt nem érhet el semmilyen forrást.
        monkeypatch.setattr(app_mod, "_is_kb_grounded_injection_allowed", lambda: False)
        monkeypatch.setattr(app_mod, "_is_kb_shadow_enabled", lambda: False)
        monkeypatch.setattr(time, "sleep", lambda _s: None)
        monkeypatch.setattr(requests, "post", _post_forbidden)

        real_generate_text = app_mod.generate_text

        def _recording_generate_text(*a, **k):
            out = real_generate_text(*a, **k)
            self.returned.append(out)
            return out

        monkeypatch.setattr(app_mod, "generate_text", _recording_generate_text)

    def set_post(self, monkeypatch: pytest.MonkeyPatch, post) -> None:
        monkeypatch.setattr(requests, "post", post)

    def generate_exegesis(self) -> bool:
        return self.generate("exegesis")

    def generate(self, key: str) -> bool:
        return self.app.generate_section(key)

    @property
    def gemini_output(self) -> str:
        assert self.returned, "a generate_text nem futott le"
        return self.returned[-1]


def _base_state(prior_exegesis: str = "", *, section: str = "exegesis") -> dict:
    return {
        "last_igehely": REFERENCE,
        "igehely_input": REFERENCE,
        "passage_text": PASSAGE_TEXT,
        "bible_translation": "RÚF 2014",
        "exegesis": "",
        "theology": "",
        "history": "",
        section: prior_exegesis,
        "text_workshop": {},
        "sermon_workshop": {},
    }


def _harness(monkeypatch, prior: str, mode: str | None, section: str = "exegesis") -> _Harness:
    state = _base_state(prior, section=section)
    h = _Harness(monkeypatch, state)
    if mode is None:
        h.set_post(monkeypatch, _post_returning(_FakeResponse(200, _ok_payload(GOOD_ANSWER))))
    else:
        post, prepare = _FAILURE_MODES[mode]
        if prepare is not None:
            prepare(state)
        h.set_post(monkeypatch, post)
    return h


# --------------------------------------------------------------------------
# A. Sikeres MI-válasz: normál tartalomként továbbjut (kontroll, ma is zöld)
# --------------------------------------------------------------------------


def test_a_successful_answer_becomes_content_and_reaches_arc_context(monkeypatch):
    from sermon_workshop_arc_ai import build_arc_generation_context, build_arc_generation_prompt

    h = _harness(monkeypatch, prior="", mode=None)

    assert h.generate_exegesis() is True
    assert GOOD_ANSWER in h.state["exegesis"]

    context = build_arc_generation_context(h.state)
    assert GOOD_ANSWER in context.exegesis
    assert GOOD_ANSWER in build_arc_generation_prompt(context)


# --------------------------------------------------------------------------
# B/C. Hiba és várakozó állapot: nem lehet tartalom
# --------------------------------------------------------------------------


SECTIONS = ("exegesis", "theology", "history")


@pytest.mark.parametrize("section", SECTIONS)
@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_b_failure_never_becomes_content_of_an_empty_section(monkeypatch, mode, section):
    h = _harness(monkeypatch, prior="", mode=mode, section=section)

    h.generate(section)

    failure_text = h.gemini_output
    assert failure_text.strip(), "a hibaágnak is adnia kell valamilyen visszajelzést"
    assert h.state[section].strip() == "", (
        "a sikertelen Gemini-hívás eredménye tartalmi mezőbe került: "
        f"{h.state[section][:80]!r}"
    )


@pytest.mark.parametrize("section", SECTIONS)
@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_b_failure_never_overwrites_existing_good_content(monkeypatch, mode, section):
    h = _harness(monkeypatch, prior=PRIOR_GOOD, mode=mode, section=section)

    h.generate(section)

    assert h.state[section] == PRIOR_GOOD, (
        "a sikertelen Gemini-hívás felülírta a meglévő, jó tartalmat: "
        f"{h.state[section][:80]!r}"
    )


@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_c_failed_call_is_reported_to_the_caller_as_not_generated(monkeypatch, mode):
    """A hívó (`render_section_tab`) ebből dönt a frissességi bélyeg
    ráhelyezéséről: sikertelen hívásra nem szabad `True`-t kapnia."""
    h = _harness(monkeypatch, prior="", mode=mode)

    assert h.generate_exegesis() is False


# --------------------------------------------------------------------------
# Továbbjutás a homiletikai munkafolyamatba
# --------------------------------------------------------------------------


@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_failure_text_does_not_reach_the_seven_point_arc_context(monkeypatch, mode):
    from sermon_workshop_arc_ai import build_arc_generation_context, build_arc_generation_prompt

    h = _harness(monkeypatch, prior="", mode=mode)
    h.generate_exegesis()
    failure_text = h.gemini_output.strip()

    context = build_arc_generation_context(h.state)

    assert failure_text not in context.exegesis
    assert failure_text not in build_arc_generation_prompt(context)


@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_failure_text_does_not_reach_the_blueprint_context(monkeypatch, mode):
    from sermon_workshop_blueprint_ai import build_blueprint_generation_context

    h = _harness(monkeypatch, prior="", mode=mode)
    h.generate_exegesis()
    failure_text = h.gemini_output.strip()

    context = build_blueprint_generation_context(h.state)

    carried = [value for _field, value in context.raw_fallback]
    assert failure_text not in carried


@pytest.mark.parametrize("mode", sorted(_FAILURE_MODES))
def test_failed_call_is_not_marked_as_fresh_usable_source_for_the_outline_engine(
    monkeypatch, mode
):
    """A `render_section_tab` (app.py) a `generate_section` után MINDIG
    rábélyegzi az igehely-ujjlenyomatot (`<key>_approved_context_hash`).
    Ezt itt azonos módon, a production függvénnyel állítjuk elő, majd a
    vázlatmotor kanonikus forrásgyűjtője nem minősítheti a hibaszöveget
    "az aktuális igehelyhez tartozó, felhasználható" forrásnak."""
    from sermon_outline_engine import (
        collect_canonical_source_material,
        compute_current_passage_context_hash,
    )
    from sermon_workshop_outline_ai import collect_available_sermon_material

    h = _harness(monkeypatch, prior="", mode=mode)
    h.generate_exegesis()
    failure_text = h.gemini_output.strip()
    h.state["exegesis_approved_context_hash"] = compute_current_passage_context_hash(h.state)

    bundle = collect_available_sermon_material(h.state)
    sources = collect_canonical_source_material(bundle)["sources"]

    entry = sources.get("exegesis")
    # A gyűjtő a szóközöket normalizálhatja, ezért térköz-független összevetés.
    probe = _collapse(failure_text)[:60]
    usable_failure = (
        entry is not None
        and probe in _collapse(str(entry["content"]))
        and entry["current_passage"]
    )
    assert not usable_failure, "a hibaszöveg friss, felhasználható exegézis-forrásként szerepel"


# --------------------------------------------------------------------------
# A felismerő segédfüggvény: érvényes tartalmat nem minősít hibának
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        GOOD_ANSWER,
        "## Műfaj és szerkezet\n\nA szakasz narratív.",
        # MAX_TOKENS miatt csonkolt, de érdemi válasz: a jegyzet a VÉGÉN áll.
        "## Exegézis\n\nÉrdemi szöveg.\n\n---\n\n> ⚠️ **A válasz a modell kimeneti korlátjánál megszakadt.**",
    ],
)
def test_helper_does_not_flag_valid_content(text):
    import app as app_mod

    assert app_mod.is_generation_error_text(text) is False


@pytest.mark.parametrize("text", [None, "", "   \n", 42])
def test_helper_flags_empty_or_non_text(text):
    import app as app_mod

    assert app_mod.is_generation_error_text(text) is True


def test_failed_generation_keeps_error_out_of_content_but_available_for_display(monkeypatch):
    h = _harness(monkeypatch, prior=PRIOR_GOOD, mode="http_500")

    assert h.generate_exegesis() is False

    assert h.state["exegesis"] == PRIOR_GOOD
    assert h.state["exegesis_last_error"].strip()
    assert "exegesis_approved_context_hash" not in h.state


def test_successful_generation_clears_previous_error(monkeypatch):
    h = _harness(monkeypatch, prior="", mode=None)
    h.state["exegesis_last_error"] = "régi hiba"

    assert h.generate_exegesis() is True

    assert "exegesis_last_error" not in h.state
    assert GOOD_ANSWER in h.state["exegesis"]
