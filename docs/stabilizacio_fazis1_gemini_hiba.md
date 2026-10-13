# Stabilizáció 1. fázis: a Gemini-hiba tartalommá válása

**Alap:** `d7d9f0e` (`origin/main`, azonos az auditált állapottal) · **Ág:** `stabilization/gemini-error-boundary` · **Production kód:** változatlan.

## Bizonyított hibaút (a `d7d9f0e` kódján ellenőrizve)

```
generate_text (hiba) → szöveg-visszatérés → generate_section → tartalmi mező
  → frissességi bélyeg → kontextusgyűjtők → vázlatmotor
```

| Lépés | Hely | Mi történik |
|---|---|---|
| 1. Forrás | `app.py:7028` `generate_text` | Minden hibaág **sima szöveget** ad vissza, nincs szerkezetes állapot: hiányzó kulcs `:7079`, globális várakozás `:7146` (⏳), időtúllépés `:7208`, kapcsolati hiba `:7229`, üres válasz `:7304`, HTTP 404/429/5xx, biztonsági elutasítás. A szöveg csak a prefixéről (⚠️/⏳) ismerhető fel. |
| 2. Átvétel | `textus_kb/shadow_integration.py:95` `output = generate_text_fn(...)` | Átadja a szöveget, nem vizsgálja. |
| 3. Tárolás (**a határátlépés**) | `app.py:4841` `st.session_state[key] = run.production_output` | Feltétel nélküli értékadás. Ez írja felül a meglévő jó tartalmat is. A `generate_section` (`:4791`) a végén mindig `True`-t ad. Egyetlen védelem az API-kulcs és az igehely hiánya (`:4801-4806`), de ezek még a hívás előtt futnak. |
| 4. Frissességi jelölés | `app.py:4949` és `:4962` (`render_section_tab`) | A `generate_section` után **mindig** rábélyegzi a `{key}_approved_context_hash` ujjlenyomatot. Az ujjlenyomat csak az igehelyet hasonlítja, a tartalmat nem. |
| 5. Hétpontos vázlat | `sermon_workshop_arc_ai.py:179` `build_arc_generation_context` | `_first_nonempty_str(session_state, "exegesis")`: nyers mező, se hiba-, se frissességi ellenőrzés. |
| 6. Tervrajz | `sermon_workshop_blueprint_ai.py:395` `raw_fallback.append` | A bélyeg „friss” → bekerül. A hiányzó bélyeg is frissnek számít (`_is_narrow_context_fresh`). |
| 7. Vázlatmotor | `sermon_outline_engine.py:1843` `collect_canonical_source_material`, `:1874` `current_passage` | `_background_value_is_usable` (`:1760`) csak üres szöveget és néhány jelölőt (pl. „nincs adat”, „-”) szűr. A hibaszöveg `current_passage: True` forrásként szerepel. |

**Érintett session-kulcsok:** `exegesis` / `theology` / `history` (és minden más `generate_section` kulcs), `{key}_approved_context_hash`, `_last_api_call_ts` (a cooldown állapota), `_call_cache`.

**A rendszer nem különbözteti meg a sikert a hibától:** a `generate_text` szerződése „mindig `str`”. A hiba csak a szöveg tartalmából ismerhető fel, a lánc egyetlen pontja sem ellenőrzi. Az `_is_api_error_text` 8 másolata más modulokban létezik, de a `generate_section` útvonalon egyiket sem hívja senki.

## Reprodukció

`tests/test_gemini_error_boundary.py`: a **valódi** `generate_section` → `generate_text` láncot futtatja. Csak a `requests.post` (hálózat) és a `time.sleep` van kiváltva, a tudástár és a Supabase ág ki van kapcsolva (`_is_kb_grounded_injection_allowed` és `_is_kb_shadow_enabled` = hamis). Nincs Gemini-, Supabase- vagy hálózathívás, nincs fájlírás.

Hibamódok (mind a `generate_text` saját hibaága): kapcsolati hiba, időtúllépés, HTTP 500, HTTP 429 (kvóta), HTTP 404 (modell), üres válasz, globális várakozás (⏳). A teszt nem szövegre illeszt: azt figyeli, amit a `generate_text` az adott ágon ténylegesen visszaadott.

## Eredmény a `d7d9f0e` kódon

`70 failed, 1 passed`. Az egyetlen zöld a kontroll (A eset: sikeres válasz normál tartalomként jut tovább). A 70 bukás mindegyike azonos ok: a `generate_text` hibaszövege a tartalmi mezőbe kerül (üres mezőbe és meglévő jó tartalom helyére is), a `generate_section` `True`-t ad, és a szöveg bekerül a hétpontos és a tervrajz kontextusba, valamint `current_passage: True` forrásként a vázlatmotorba.

## Minimális javítási irány (nincs végrehajtva)

A `generate_section` (`app.py:4841` körül) a `run.production_output` értékét csak akkor írja a mezőbe, ha az nem hibaszöveg. Hibánál a mező marad, `False`-t ad vissza, a hibát egy külön kulcsba (pl. `{key}_last_error`) teszi és a felületen megjeleníti. A `render_section_tab` (`:4949-4964`) csak `True` esetén bélyegez. A hiba felismeréséhez egy közös `is_generation_error_text()` kell (a meglévő `_is_api_error_text` mintája: ⚠️/⏳/üres), a `generate_text` szerződését érintetlenül hagyva.
