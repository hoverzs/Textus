# TEXTUS · Homiletikai műhely

**A szövegtől a szószékig** — református lelkipásztori környezetre szabott, MI-asszisztált homiletikai műhely Streamlit-alapon, Google Gemini modellekkel. Ingyenes és nyílt forráskódú ([MIT licenc](LICENSE)). Verzió: `APP_VERSION` az `app.py` elején.

**Web:** [textus.ro](https://textus.ro) · [textus.streamlit.app](https://textus.streamlit.app)

## Mit tud

- **Igehely:** igeszakasz megadása, a RÚF 2014 szöveg betöltése (szentiras.eu), igehely-keresés, konkordancia, eredeti nyelvi (görög/héber) elemzés, kommentárok, bibliai térkép.
- **Textusműhely** és **Igehirdetési műhely:** lépésenként vezetett exegetikai és homiletikai munkafolyamat, vázlatkészítéssel és diagnosztikával.
- **Íróasztal:** a vázlat kidolgozása, Word-export.
- **Projektek:** bejelentkezés után felhőbe mentett munkamenetek (Supabase).

## Projektstruktúra

| Hely | Tartalom |
| --- | --- |
| `app.py` | A Streamlit-belépési pont: oldalbeállítás, globális CSS, fülek, Gemini-hívás (`generate_text`) |
| `sermon_workshop_*.py`, `textus_*_ai.py`, `sermon_outline_engine.py` | Műhelyek: adatmodell, MI-lépések, vázlatmotor |
| `*_ui.py` | Felületi modulok (pl. `bible_text_ui.py`, `concordance_ui.py`, `sermon_workshop_ui.py`, `ui_theme.py`) |
| `bible_engine/` | Eredeti nyelvi elemzés (TAGNT, TAHOT, MACULA, lexikonok, himnuszok) |
| `textus_kb/` | Tudásbázis: Aquifer, ACAI, kommentárok, teológia, kontextusépítés |
| `illustration_engine/` | Illusztrációk importja, minősítése, visszakeresése |
| `components/` | Egyedi Streamlit-komponensek (token-kiválasztók, szerkesztő) |
| `data/` | Adatok; a `data/generated/` nagy része helyben generált és gitignore-olt |
| `scripts/` | Adatépítő, importáló és auditszkriptek |
| `supabase/migrations/` | Adatbázis-migrációk |
| `tests/` | pytest-tesztek (AppTest-alapú UI-tesztekkel) |
| `docs/` | Tervek, auditok (`docs/audits/`), adatdokumentáció |

## Fejlesztői környezet

Előfeltétel: Git és Python 3.14 (a helyi fejlesztés ezzel fut; a függőségeket a `requirements.txt` rögzíti, köztük a `streamlit==1.58.0`-t).

```powershell
git clone https://github.com/hoverzs/Textus.git Textus-dev
cd Textus-dev
py -3.14 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt -r requirements-dev.txt
```

### Titkos kulcsok

Másold a `.streamlit/secrets.toml.example` fájlt `.streamlit/secrets.toml` néven (gitignore-olt), és töltsd ki:

- `GEMINI_API_KEY` — Gemini-hívásokhoz. Sorrend: környezeti változó → a projekt `.streamlit/secrets.toml` fájlja → `st.secrets`; ha egyik sincs, a Beállítások fülön adható meg.
- `SZENTIRAS_EU_API_KEY` — a RÚF-szöveg automatikus betöltéséhez.
- `[supabase]`, `[auth]` — csak akkor, ha a felhőmentés és a bejelentkezés is kell. **Fejlesztéshez ne add meg az éles értékeket.**

A Streamlit alapból a felhasználói szintű `%USERPROFILE%\.streamlit\secrets.toml` fájlt is betölti. Ha abban éles adatok vannak, indítsd az alkalmazást `--secrets.files` kapcsolóval, és ellenőrizd, hogy egyetlen `SUPABASE*` környezeti változó sincs beállítva.

### Indítás

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.port 8502 --secrets.files .streamlit\secrets.toml
```

### Helyi adatbázisok

Néhány funkció és teszt gitignore-olt, helyben generált SQLite-adatbázist használ a `data/generated/` alatt (pl. `ruf_bible.sqlite3`, `aquifer_bible_dictionary.sqlite3`, `aquifer_study_notes.sqlite3`). Hiányukban a felület visszafogottan működik, az ezekre épülő tesztek pedig megnevezett okkal kimaradnak. Az előállításuk módja a `scripts/` alatti `build_*` és `import_*` szkriptekben található.

### Diagnosztikai nyomkövetés

A `passage_trace.py` `[PASSAGE_TRACE]` naplója alapértelmezésben ki van kapcsolva. Bekapcsolás: `TEXTUS_PASSAGE_TRACE=1` környezeti változó (PowerShellben: `$env:TEXTUS_PASSAGE_TRACE = "1"`).

## Tesztelés

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

A `pytest.ini` beállítja az importálási módot és a tesztkönyvtárat, a `tests/conftest.py` pedig a teszteket egy álkulcsos titokfájlra (`tests/fixtures/secrets.test.toml`) rögzíti, így éles kulcs vagy Supabase egyetlen tesztből sem érhető el. A teljes csomag nagyjából 8–10 percig fut. Az érvényes tesztalapvonal és az ismert hibák a `docs/audits/test_baseline_2026-11-22.md` jelentésben vannak.

Egyetlen fájl vagy teszt futtatása:

```powershell
.\.venv\Scripts\python.exe -m pytest -q tests/test_bible_text_reading_view.py
.\.venv\Scripts\python.exe -m pytest -q "tests/test_phase3_stabilization.py::test_bible_text_styles_survive_reruns"
```

## Licenc

**MIT** — lásd a [LICENSE](LICENSE) fájlt. Copyright (c) 2026 Hover.

## Közreműködés

Pull request és issue üdvözölt, különösen hibajavítások, hozzáférhetőség és dokumentáció terén.

---

*„A teljes Írás Istentől ihletett és hasznos a tanításra, a feddésre, a megjobbításra és az igazságban való nevelésre.” — 2Timóteus 3,16*
