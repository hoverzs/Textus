# Textus – tesztelési alapvonal (2026-11-22)

A `main` ág (74c3c64) tesztcsomagja a tesztinfrastruktúra három javítása után **31 sikertelen, 4237 sikeres, 641 kihagyott és 1 várt hibás (xfail)** tesztet ad. A 31 hibából egyik sem bizonyítottan programhiba: 27 hiányzó helyi adatra vezethető vissza, 3 elavult teszt, 1 pedig adatváltozat-eltérés, amely további vizsgálatot igényel. Ez a jelentés rögzíti azt az állapotot, amelyhez a későbbi backend-módosítások eredményeit viszonyítjuk.

**Frissítve 2026-11-23:** az elavult tesztek javítása, az adatfüggő tesztek futtatási feltételei és a három helyi adatbázis másolata után a csomag eredménye **6 sikertelen, 4263 sikeres, 640 kihagyott, 1 xfail**. A hat hiba mind dokumentált, adat- vagy forrásfüggő; programhiba továbbra sem igazolódott. Részletek a jelentés végén, a „Kiegészítés (2026-11-23)” fejezetben; az érvényes elvárt hibalista is ott található.

## Környezet

| Tétel | Érték |
| --- | --- |
| Commit | `74c3c64fe6947825475f5d5889608cf60c7ea92e` (`main` = `origin/main`) |
| Python | 3.14.6 (a `Textus-dev` virtuális környezete 3.14.5) |
| Streamlit / pytest | 1.58.0 / 9.2.0 |
| Futtatás helye | Linuxos ellenőrző környezet, a `Textus-dev`-vel azonos klónon; API-kulcs, hálózat és gitignore-olt helyi adatbázisok nélkül |
| Tesztek | 281 tesztfájl, 4910 teszteset |

A Windows-gépen futtatott eredmény a platformtól függő kihagyások miatt kis mértékben eltérhet. Az ellenőrzéshez a `tests/` alatti, alább felsorolt elvárt hibalistát érdemes összevetni.

## Futtatott parancsok

```text
# 1. A gyűjtési hiba reprodukálása (javítás előtt)
python -m pytest -q -p no:cacheprovider --co

# 2. Teljes futás a javítás előtt (az összehasonlításhoz)
python -m pytest -q -p no:cacheprovider --import-mode=importlib --junitxml=run_before.xml tests

# 3. Az érintett fájlok egyenkénti futtatása (sorrendfüggés kiszűrése)
python -m pytest -q -p no:cacheprovider --import-mode=importlib <egyetlen tesztfájl>

# 4. Teljes futás a javítás után – csupasz pytest, a pytest.ini beállításaival
pytest -q -p no:cacheprovider -rfE --junitxml=run_after.xml

# 5. A maradék hibák újrafuttatása a régi Textus mappa három helyi adatbázisával
#    (aquifer_study_notes, aquifer_bible_dictionary, ruf_bible – csak egy külön
#    ellenőrző másolatban, a Textus-dev-be nem kerültek)
pytest -q -p no:cacheprovider <a 12 érintett tesztfájl>
```

## Eredmények

| Futás | Sikertelen | Sikeres | Kihagyott | xfail |
| --- | --- | --- | --- | --- |
| Javítás előtt (`--import-mode=importlib`, nyomkövetés kikapcsolva) | 42 | 4226 | 641 | 1 |
| Javítás után (csupasz `pytest`) | **31** | **4237** | 641 | 1 |
| Javítás után, a három helyi adatbázissal | 9 | – | – | – |

A javítás nem hozott új hibát: a két futás hibalistájának különbsége 11 megszűnt és 0 új hiba.

## A gyűjtési probléma

Az alapértelmezett `pytest` hívás a gyűjtésnél leállt (`2 errors during collection`), mert a `tests/test_retrieval.py` – `tests/test_textus_kb/test_retrieval.py` és a `tests/test_quality_gate.py` – `tests/test_textus_kb/test_quality_gate.py` pár azonos alapnevű, `__init__.py` nélküli modul. A javítás után a csupasz `pytest` parancs mind a 4910 tesztet összegyűjti.

## Módosított fájlok

Az alkalmazás kódjához és üzleti logikájához nem nyúltam, és egyetlen tesztet sem töröltem, kihagyásra sem jelöltem.

| Fájl | Változás |
| --- | --- |
| `pytest.ini` (új) | `testpaths = tests`, `addopts = --import-mode=importlib`, `pythonpath = .` – megszünteti a gyűjtési hibát, és biztosítja, hogy a `from tests.… import` hivatkozások csupasz `pytest` hívással is működjenek. |
| `tests/conftest.py` | **(1)** `pytest_configure`: a Streamlit `secrets.files` beállítását a gyűjtés előtt a `tests/fixtures/secrets.test.toml` fájlra rögzíti, és eltávolítja a `SUPABASE*` környezeti változókat. Így a tesztek sem a projekt, sem a felhasználói szintű `secrets.toml`-t nem látják, éles Supabase-hez és valódi kulcsokhoz nem férnek hozzá. **(2)** `_restore_commentary_ui_seams`: minden teszt után visszaállítja a `commentary_ui` három felülírható függvényét. |
| `.gitignore` | Új sor: `tests/fixtures/kb/tmp_manifest_*.json`. A `tests/test_textus_kb/conftest.py` `phase2a_manifest` fixture-je minden futáskor ide írja ideiglenes manifestjét, így a tesztek után a Git-állapot nem volt tiszta (a régi Textus mappában is ezért szerepelt nem követett fájlként). A fixture-t nem módosítottam, mert az áthelyezés a manifest relatív útvonalainak feloldását érinthetné. |
| `tests/fixtures/secrets.test.toml` (új) | Egyetlen álkulcs: `SZENTIRAS_EU_API_KEY`. Valódi kulcsot nem tartalmaz. |
| `docs/audits/test_baseline_2026-11-22.md` (új) | Ez a jelentés. |

## A 42 korábbi hiba besorolása

| Kategória | Db | Tesztek | Ok | Állapot |
| --- | --- | --- | --- | --- |
| Rejtett kulcsfüggés | 8 | `test_jude_e2e_workflow` (2), `test_outline_ai_gate_integration` (3), `test_outline_synthesis_quality` (1), `test_partial_outline_workflow` (1), `test_sermon_outline` (1) | A HTTP-válasz mockolt, de a `ruf_bible_service.SzentirasEuApiProvider.fetch` a kérés előtt kulcsot követel. A tesztek így csak valódi kulccsal rendelkező gépen futottak le. Ráadásul a Streamlit a `secrets.toml` legfelső szintű értékeit környezeti változóként exportálja, így egy üres `SZENTIRAS_EU_API_KEY = ""` sor a környezeti változót is felülírja. | Javítva (álkulcs a rögzített tesztes titokfájlban) |
| Sorrendfüggés | 2 | `test_textus_kb/test_commentary_runtime_consumer_wiring` (2) | A `tests/test_commentary_ui.py` segédfüggvényei visszaállítás nélkül írják felül a `commentary_ui._get_status` / `_get_repository` / `_translation_database_path` függvényt. Külön futtatva zöld, a két fájl együtt reprodukálja a hibát. | Javítva (visszaállító fixture) |
| A korábbi futás beállítása | 1 | `test_quick_tools_lazy_render::test_greek_analysis_renders_once_per_run_never_twice` | A teszt a `passage_trace` naplóüzeneteit számolja; az audit futása `TEXTUS_PASSAGE_TRACE=0` beállítással ment. Alapbeállítással zöld. | Nem hiba. **Megjegyzés:** a teszt az ideiglenes nyomkövetésre épül, ezért annak eltávolításakor (audit A3) át kell írni. |
| Hiányzó helyi adatbázis | 22 | `test_concept_concordance` (4), `test_textus_kb/test_phase4d_aquifer_sqlite` (11), `test_aquifer_bible_dictionary` (2), `test_context_selection` (2), `test_acai_entities` (1), `test_phase5h_dictionary_relevance` (1), `test_quality_gate` (1) | A gitignore-olt `data/generated/ruf_bible.sqlite3`, `aquifer_bible_dictionary.sqlite3` és `aquifer_study_notes.sqlite3` hiányzik. A régi Textus mappa példányaival mind a 22 zöld. | Fennmarad – környezeti |
| Hiányzó forrásadat-dump | 5 | `test_biblical_places_audit::test_full_catalog_builder_is_idempotent_in_memory`, `test_aquifer_bible_dictionary::test_chunk_ids_stable`, `test_aquifer_study_notes::test_invalid_mapping_skipped_during_import`, `test_phase4d_aquifer_sqlite::test_import_idempotent_dictionary` / `_study_notes` | A `_upstream_audit/` és a `data/biblical_places/raw/` nyers forrásai sem itt, sem a régi Textus mappában nincsenek meg. | Fennmarad – környezeti |
| Elavult teszt | 3 | `test_biblical_map_ui::test_bible_text_editor_has_no_map_callback_or_renderer`; `test_writing_desk_ui::test_writing_desk_compact_reaches_real_greek_analysis_panel` és `…token_selection_reaches_compact_analysis_panel` | (a) A teszt azt állítja, hogy a `bible_text_ui.py`-ban nincs `Callable`. A bb6400d commit óta a modul típusannotációként használja (`hebrew_contextual_analysis_generate_fn: Callable[..., str]`), térképes visszahívás nélkül. (b) A két Writing Desk-teszt kémfüggvénye (`spy_panel`) a `greek_analysis_ui._render_analysis_panel` régi szignatúráját követi; a `reference` kulcsszavas argumentum hiányzik belőle. A `TypeError`-t a `bible_text_ui.render_bible_text_reading_block` elnyeli, a teszt ezért `KeyError`-ral bukik. | Fennmarad – javítási javaslat lent |
| További vizsgálatot igényel | 1 | `test_textus_kb/test_context_builder::test_exegesis_matches_golden_fixture` | Az evidence-azonosítók egyeznek, a becsült tokenszám 750 a mintában rögzített 736 helyett. A mintafájl eredeti commitján (05cbe85) és a 2026-09-03-i kommentár-commit előtti kóddal is elbukik ugyanezekkel az adatokkal, tehát valószínűleg a helyi Aquifer-adatbázis változata tér el a minta készítésekor használttól. **Javítva 2026-11-23:** ez a feltételezés téves; a valódi ok a TBESG-lexikon változata, lásd a kiegészítést. | Fennmarad – adatváltozat |

**Valódi programhiba** a 42 teszt között nem igazolódott. Az auditban talált Bibliai szöveg CSS-hiba (P1) nincs tesztekkel lefedve, ezért itt nem jelenik meg.

## Fennmaradó problémák és javasolt döntések

1. **Elavult tesztek (3).** Javaslat, döntésre vár:
    - `tests/test_biblical_map_ui.py:612`: az `assert "Callable" not in …` sort a teszt valódi szándékára kell szűkíteni (nincs `after_bible_text` és `render_biblical_map_prototype`; ez a két másik állítás már ellenőrzi).
    - `tests/test_writing_desk_ui.py` `spy_panel`: a szignatúra kiegészítése `reference=None` paraméterrel és továbbadással (vagy `**kwargs`), az állítások változatlanok.
2. **Helyi adatbázisok (22 teszt).** Döntés kell: átmásoljuk-e a `Textus-dev`-be a három, név szerint ismert adatbázist (`ruf_bible.sqlite3` 9,7 MB, `aquifer_bible_dictionary.sqlite3` 50,1 MB, `aquifer_study_notes.sqlite3` 29,5 MB), vagy egységes `requires_local_data` jelölést kapnak ezek a tesztek. A csomag más adatfüggő tesztjei (például a 190 `greek_syntax_dev.sqlite3`-függő) már most kihagyással jelzik a hiányt, ez a 22 viszont hibával – ez következetlenség.
3. **Forrásadat-dumpok (5 teszt).** Csak a nyers források letöltésével futtathatók; ennek módja és helye dokumentálandó.
4. **Aranymintás eltérés (1 teszt).** Tisztázni kell, melyik Aquifer-adatváltozat a hiteles, és ahhoz kell igazítani a mintát vagy az adatbázist.
5. **Repóba író fixture.** A `phase2a_manifest` fixture hosszabb távon `tmp_path`-ba írjon, ha a manifest útvonalfeloldása ezt megengedi; addig a `.gitignore` sor kezeli.
6. **Nyomkövetés-függés.** A `test_quick_tools_lazy_render` a `passage_trace` modulra épül; a nyomkövetés kivezetésekor új számlálási pont kell.

## A 31 elvárt hiba listája (javítás után, helyi adatbázisok nélkül)

```text
test_biblical_map_ui::test_bible_text_editor_has_no_map_callback_or_renderer
test_biblical_places_audit::test_full_catalog_builder_is_idempotent_in_memory
test_concept_concordance::test_search_concept_keyword_hits_exclude_already_shown_verses
test_concept_concordance::test_search_concept_unknown_relation_defaults_to_megerosit
test_concept_concordance::test_search_concept_validates_and_dedupes_references
test_concept_concordance::test_validate_reference_valid
test_textus_kb/test_acai_entities::test_disabled_acai_graceful
test_textus_kb/test_aquifer_bible_dictionary::test_chunk_ids_stable
test_textus_kb/test_aquifer_bible_dictionary::test_phase3c_golden_fixtures
test_textus_kb/test_aquifer_bible_dictionary::test_retrieval_includes_dictionary_evidence_deterministically
test_textus_kb/test_aquifer_study_notes::test_invalid_mapping_skipped_during_import
test_textus_kb/test_context_builder::test_exegesis_matches_golden_fixture
test_textus_kb/test_context_selection::test_per_source_type_budget_respected
test_textus_kb/test_context_selection::test_selection_diagnostics_present
test_textus_kb/test_phase4d_aquifer_sqlite::test_adapters_use_sqlite_backend
test_textus_kb/test_phase4d_aquifer_sqlite::test_dictionary_sqlite_store_exists
test_textus_kb/test_phase4d_aquifer_sqlite::test_health_includes_aquifer_stores
test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_dictionary
test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_study_notes
test_textus_kb/test_phase4d_aquifer_sqlite::test_john4_parity_dictionary_article_ids
test_textus_kb/test_phase4d_aquifer_sqlite::test_john4_parity_study_notes_article_ids
test_textus_kb/test_phase4d_aquifer_sqlite::test_luke10_parity_dictionary_article_ids
test_textus_kb/test_phase4d_aquifer_sqlite::test_luke10_parity_study_notes_article_ids
test_textus_kb/test_phase4d_aquifer_sqlite::test_passage_query_performance_smoke
test_textus_kb/test_phase4d_aquifer_sqlite::test_stable_dictionary_evidence_ids
test_textus_kb/test_phase4d_aquifer_sqlite::test_study_notes_sqlite_store_exists
test_textus_kb/test_phase4d_aquifer_sqlite::test_third_passage_without_pilot_registry
test_textus_kb/test_phase5h_dictionary_relevance::test_source_trace_scope_is_not_rewritten_to_request
test_textus_kb/test_quality_gate::test_disabled_ruf_missing_does_not_degrade_health
test_writing_desk_ui::test_writing_desk_compact_reaches_real_greek_analysis_panel
test_writing_desk_ui::test_writing_desk_token_selection_reaches_compact_analysis_panel
```


## Kiegészítés (2026-11-23)

### Mi változott

| Fájl | Változás |
| --- | --- |
| `tests/test_biblical_map_ui.py` | Az `assert "Callable" not in bible_text_source` helyett AST-alapú ellenőrzés: `Callable` típusú paraméter csak a `hebrew_contextual_analysis_generate_fn` és a `greek_contextual_analysis_generate_fn` lehet. Ezeket a bb6400d (2026-09-11) és a 002d8a0 (2026-09-12) commit szándékosan vezette be. A teszt célja (nincs térképes vagy egyéb, a Bibliai szöveg után futó visszahívás) és a másik két állítása változatlan. |
| `tests/test_writing_desk_ui.py` | A `spy_panel` kémfüggvény `**kwargs` paramétert kapott, és minden további argumentumot továbbad a valódi `_render_analysis_panel`-nek. A 002d8a0 óta a függvény `reference=` és `contextual_analysis_*` argumentumot is kap; a régi spy erre `TypeError`-t dobott, amelyet a `bible_text_ui` elnyelt, így a panel le sem futott. Az állítások változatlanok. |
| `tests/local_data.py` (új) | Négy futtatási feltétel (`requires_ruf_bible_db`, `requires_aquifer_dictionary_db`, `requires_aquifer_study_notes_db`, `requires_any_aquifer_db`). A projekt meglévő mintáját követik (`pytest.mark.skipif(not PATH.exists(), reason=…)`), az útvonalakat pedig az alkalmazás saját `DEFAULT_DATABASE_PATH` konstansaiból veszik. |
| 7 tesztfájl | 26 jelölés 22 teszten (három teszt mindkét Aquifer-adatbázist igényli): `test_concept_concordance.py` (4), `test_textus_kb/test_phase4d_aquifer_sqlite.py` (11), `test_aquifer_bible_dictionary.py` (2), `test_context_selection.py` (2), `test_acai_entities.py` (1), `test_phase5h_dictionary_relevance.py` (1), `test_quality_gate.py` (1). Állítást nem módosítottam. |
| `data/generated/` (gitignore-olt, nem verziókezelt) | `ruf_bible.sqlite3`, `aquifer_bible_dictionary.sqlite3`, `aquifer_study_notes.sqlite3`: másolat a régi `C:\Users\Hover\Textus` mappából. Az eredetiek érintetlenek, a SHA-256 ellenőrzőösszegek egyeznek. |

**A feltételek bizonyítéka.** A 22 teszt adatigényét a három adatbázis egyenkénti elvételével állapítottam meg. `ruf_bible.sqlite3` nélkül a 4 konkordanciateszt bukik el; az Aquifer-szótár nélkül 13, a jegyzetek nélkül 8 teszt (a kettő közös része 3). A `test_disabled_acai_graceful` bármelyik Aquifer-adatbázissal lefut, de ha mindkettő hiányzik, a `build_id` a Phase 3c-s pilotra esik vissza. Adatbázisok nélkül mind a 22 teszt megnevezett okkal hagyódik ki („local generated database not present: …”), adatbázisokkal változatlanul lefut.

### Eredmények (Linux, Python 3.14.6, a Textus-dev mostani állapotával azonos klón)

| Futás | Sikertelen | Sikeres | Kihagyott | xfail |
| --- | --- | --- | --- | --- |
| 2026-11-22, infrastruktúra-javítás után | 31 | 4237 | 641 | 1 |
| 2026-11-23, adatbázisokkal és a tesztjavításokkal | **6** | **4263** | **640** | 1 |
| A hét érintett fájl, adatbázisok nélkül | 3 | 82 | 22 (mind megnevezett okkal) | – |

A Windows-futtatás még hátravan: a számítógép-vezérlés a terminálokban szándékosan nem engedi a gépelést, közvetlen parancssori hozzáférésem pedig nincs.

**Időszakos hiba.** A `tests/test_writing_desk_ui.py::test_writing_desk_hebrew_compact_path_keeps_isolated_key` egyszer elbukott, amikor a `test_writing_desk_ui.py` és a `test_biblical_map_ui.py` együtt futott. Utána kilenc egymást követő futásban sikeres volt, a hibaüzenetet nem sikerült rögzíteni. Megfigyelés alatt tartandó.

### Az öt hiányzó forrásadat

Mind az öt teszt nyers, upstream forrásállományt olvas, amely sem a Gitben, sem a régi Textus mappában nincs meg. Ezeket nem töltöttem le, és az elvárásokat sem módosítottam.

| Teszt | Hiányzó állomány | Beszerzés |
| --- | --- | --- |
| `test_biblical_places_audit::test_full_catalog_builder_is_idempotent_in_memory` | `data/biblical_places/raw/openbible/ancient.jsonl` | `biblical_map_import/download.py` (`download_openbible`), forrás: `openbibleinfo/Bible-Geocoding-Data` |
| `test_textus_kb/test_aquifer_bible_dictionary::test_chunk_ids_stable` | `_upstream_audit/AquiferOpenBibleDictionary/eng/metadata.json` | Aquifer Open Bible Dictionary upstream; útvonal: `textus_kb/importers/aquifer_bible_dictionary.py:31` |
| `test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_dictionary` | ugyanaz | ugyanaz |
| `test_textus_kb/test_aquifer_study_notes::test_invalid_mapping_skipped_during_import` | `_upstream_audit/AquiferOpenStudyNotes/eng/metadata.json` | Aquifer Open Study Notes upstream; útvonal: `textus_kb/importers/aquifer_study_notes.py:34` |
| `test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_study_notes` | ugyanaz | ugyanaz |

Javaslat, döntésre vár: vagy a beszerzési lépések dokumentálása (egy `scripts/` alatti letöltőszkript, illetve a meglévő `download_openbible` használata), vagy a már bevezetett mintához hasonló feltétel.

### Az aranymintás eltérés valódi oka

A `test_textus_kb/test_context_builder::test_exegesis_matches_golden_fixture` a `phase2a` manifestet használja, amelyben az Aquifer és az ACAI ki van kapcsolva, ezért a tegnapi „Aquifer-adatváltozat” magyarázat téves. A szakaszonkénti összevetés szerint az evidence-azonosítók egyeznek, és csak a nyelvi (`linguistic`) evidenciák szövege tér el:

- **Minta (2026-08-24):** `Jn 4,7 — λέγει (G3004G), verb, "mond; szól"`, forrás: `lexicon_hu_overlay`
- **Most:** `Jn 4,7 — λέγει (G3004G), verb, "to say" / "mond; szól"`, forrás: `stepbible_tbesg`

A becsült tokenszám TBESG-lexikon nélkül 714, a mostani, verziókezelt `data/generated/tbesg_lexicon.sqlite3`-mal 750, a mintában 736. A minta tehát egy harmadik, korábbi lexikonváltozattal készült: a `G3588`-hoz hasonló szavaknál már TBESG-glosszát tartalmaz, a kiterjesztett Strong-azonosítójú szavaknál (`G3004G`, `G3754G`, `G1135G`, `G2424G` …) még nem. A lexikon a 7d30899 commitban (2026-09-11, Greek Analysis v2 Phase 2A) került a repóba, illetve ott bővült ezekre a szavakra; a minta azóta elavult.

Javaslat, döntésre vár: ha a gazdagabb, angol + magyar glossza a kívánt viselkedés (a Greek Analysis v2 ezt célozta), a mintát a jelenlegi kimenetből újra kell generálni, és ezt a commitüzenetben a 7d30899-re hivatkozva kell rögzíteni. Bizonyított döntés nélkül a mintát nem módosítottam.

### Érvényes elvárt hibalista (a Textus-dev-ben, a három helyi adatbázissal)

```text
test_biblical_places_audit::test_full_catalog_builder_is_idempotent_in_memory
test_textus_kb/test_aquifer_bible_dictionary::test_chunk_ids_stable
test_textus_kb/test_aquifer_study_notes::test_invalid_mapping_skipped_during_import
test_textus_kb/test_context_builder::test_exegesis_matches_golden_fixture
test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_dictionary
test_textus_kb/test_phase4d_aquifer_sqlite::test_import_idempotent_study_notes
```
