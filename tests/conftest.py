"""Session-szintű teszt-előkészítés (tesztinfrastruktúra, NEM termékkód).

Gyökérok (bizonyítva, 2026-08-13, tesztalap-stabilizálás): `app.py` egy
tiszta Streamlit-szkript — nincs benne `if __name__ == "__main__":` őr, a
teljes modul tetőtől talpig, importáláskor lefut, beleértve a valódi
`st.form("textus_feedback_form", ...)` hívást is. Éles üzemben ez helyes és
szükséges (mindig `streamlit run app.py` futtatja, valódi Streamlit-runtime
kontextusban).

A tesztkörnyezetben viszont számos tesztfájl importálja közvetlenül az
`app` modult (pl. csak egyetlen segédfüggvényért), AppTest-sandbox NÉLKÜL —
lásd pl. `tests/test_canonical_source_collector.py`,
`tests/test_concept_concordance.py`, `tests/test_occasion_context.py`,
`tests/test_outline_engine.py`, `tests/test_p0_generate_text_tls_
temperature.py`, `tests/test_security_hygiene.py`, `tests/test_word_
export.py`. A LEGELSŐ ilyen import a pytest-folyamat főszálán, közvetlenül
(sandbox nélkül) hajtja végre az `app.py` teljes tetejét — ez szennyezi a
Streamlit globális DeltaGenerator form-/widget-nyomkövetési állapotát, és a
később (a teljes `pytest tests/` futásban, ábécésorrendben utána) végrehajtódó,
`streamlit.testing.v1.AppTest`-alapú tesztek ettől hamis,
"DeltaGeneratorSingleton instance already exists!" / "st.button() can't be
used in an st.form()" / "Within a form, callbacks can only be defined on
st.form_submit_button" hibákkal buknak — miközben külön futtatva zöldek.

Ezt minimális, determinisztikus fájlpár-reprodukcióval bizonyítottuk (pl.
`pytest tests/test_bible_text_reading_view.py
tests/test_original_language_token_block.py` — a régi, közvetlen `import
app`-ot használó verzióval, javítás előtt).

A javítás: az `app` modult a session ELSŐ lépéseként, EGYETLEN alkalommal,
`AppTest`-sandboxban importáljuk be — a Streamlit saját tesztelési
infrastruktúrája megfelelően kezeli a script-futtatási kontextust, így az
`app.py` tetején lévő kód itt biztonságosan lefuthat, DeltaGenerator-
szennyezés nélkül. Miután a modul egyszer bekerült a `sys.modules`
gyorsítótárba, Python importrendszere a FENTI tesztfájlok mindegyikében
található, későbbi `import app` / `import app as app_mod` hívásokat már csak
a gyorsítótárazott modul visszaadásaként kezeli — NEM hajtja újra végre a
tetején lévő kódot —, tehát biztonságos.

Ez KIZÁRÓLAG tesztinfrastruktúra-intézkedés: sem az `app.py`, sem a fent
felsorolt tesztfájlok `import app` hívásai nem változtak."""

from __future__ import annotations

import os
from pathlib import Path

import pytest

_TEST_SECRETS_FILE = Path(__file__).resolve().parent / "fixtures" / "secrets.test.toml"


def pytest_configure(config: pytest.Config) -> None:
    """Hermetikus titokkezelés a teljes tesztfutásra (2026-11-22, tesztalapvonal).

    1. A Streamlit alapból a felhasználói szintű ``~/.streamlit/secrets.toml``-t
       ÉS a projekt ``.streamlit/secrets.toml``-ját is betölti — a fejlesztő
       gépén ezekben éles Supabase-, bejelentkezési és Gemini-kulcsok lehetnek.
       A ``secrets.files`` beállítást ezért, még a gyűjtés előtt, kizárólag a
       ``tests/fixtures/secrets.test.toml`` álkulcs-fájlra rögzítjük.
    2. A ``SUPABASE*`` környezeti változókat ebből a folyamatból eltávolítjuk,
       hogy egyetlen teszt se érhesse el az éles adatbázist.

    Csak a pytest-folyamatot érinti; a felhasználói/rendszer-beállításokhoz,
    az ``app.py``-hoz és az üzleti logikához nem nyúl.
    """
    for name in [key for key in os.environ if key.upper().startswith("SUPABASE")]:
        del os.environ[name]

    import streamlit.config as st_config

    st_config.set_option("secrets.files", [str(_TEST_SECRETS_FILE)])


@pytest.fixture(autouse=True)
def _restore_commentary_ui_seams():
    """Visszaállítja a ``commentary_ui`` modul felülírható varratfüggvényeit
    minden teszt után (2026-11-22, tesztalapvonal).

    Gyökérok (bizonyítva): a ``tests/test_commentary_ui.py`` AppTest-segédfüggvényei
    a ``commentary_ui._get_repository`` / ``_get_status`` /
    ``_translation_database_path`` függvényeket közvetlen értékadással, visszaállítás
    nélkül cserélik le. A felülírás a teszt után is a modulban marad, ezért a
    később futó ``tests/test_textus_kb/test_commentary_runtime_consumer_wiring.py``
    két tesztje a teljes futásban elbukik, külön futtatva viszont zöld
    (reprodukció: a két fájl együttes futtatása). A fixture a tesztek tartalmát
    nem változtatja, csak a modulállapotot állítja vissza."""
    try:
        import commentary_ui
    except Exception:  # noqa: BLE001 — import-hiba esetén a teszt maga jelez
        yield
        return
    names = ("_get_repository", "_get_status", "_translation_database_path")
    saved = {name: getattr(commentary_ui, name) for name in names if hasattr(commentary_ui, name)}
    try:
        yield
    finally:
        for name, value in saved.items():
            setattr(commentary_ui, name, value)


@pytest.fixture(autouse=True)
def _isolate_commentary_storage_config(monkeypatch: pytest.MonkeyPatch) -> None:
    """Guard against any test accidentally reaching real Supabase Storage
    through ``textus_kb.commentary_runtime.ensure_status`` (2026-09-04
    production-storage round): that function is now the SINGLE choke
    point called, with no explicit ``database_path``, by every real
    Commentary-evidence consumer (the reader UI, Exegézis, Eredeti
    szöveg, Kortörténet) -- meaning it is reachable from a much wider set
    of tests than just ``test_commentary_runtime.py``'s own dedicated
    suite (which already isolates itself further via its own autouse
    fixture). Any test whose mocked/real local status comes back
    unavailable would otherwise fall through to real storage-config
    resolution, and if THIS machine's env/secrets happen to have
    ``TEXTUS_COMMENTARY_DB_STORAGE_BUCKET`` (etc.) configured -- exactly
    as they legitimately would be post-deployment -- that fall-through
    would attempt a real network call during a unit test. Clearing these
    three env vars for every test (regardless of whether that test cares)
    keeps ``ensure_status`` degrading to the local, network-free
    ``storage_not_configured`` reason unless a test explicitly opts back
    in (ld. ``tests/test_textus_kb/test_commentary_runtime.py``'s own
    mocked-Supabase-client tests, which set these via monkeypatch/kwargs
    themselves)."""
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_STORAGE_BUCKET", raising=False)
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_STORAGE_OBJECT", raising=False)
    monkeypatch.delenv("TEXTUS_COMMENTARY_DB_SHA256", raising=False)


@pytest.fixture(scope="session", autouse=True)
def _preimport_app_module_inside_streamlit_sandbox() -> None:
    """Lásd a modul docstringjét — ez a session legelső, mindenki által
    (autouse) megkövetelt lépése, mielőtt bármely teszt teste lefutna.

    Szándékosan NEM nyel el semmilyen hibát: az `AppTest.run()` önmagában
    nem dob kivételt egy, a sandboxolt szkriptben történt hibára (csak az
    `.exception` listába gyűjti) — ezért itt explicit módon ellenőrizzük és
    újra felemeljük, hogy egy valódi `app.py`-import-hiba hangosan,
    azonnal buktassa a session legelső lépését, ne csendben sikkadjon el."""
    from streamlit.testing.v1 import AppTest

    def _do_import() -> None:
        import app  # noqa: F401

    result = AppTest.from_function(_do_import).run(timeout=60)
    if result.exception:
        raise RuntimeError(
            "Az 'app' modul előimportja a Streamlit-sandboxban hibázott: "
            f"{[exc.message for exc in result.exception]}"
        )
