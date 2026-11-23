"""RESET 2D-B1 — célzott, elfogadásos MI-pontosítás a lapos Igehirdetési
műhely kilenc célmezőjéhez (a textus fő gondolata, az igehirdetés fő
gondolata / fókuszmondat, és mind a hét arc-pont).

Ennek a modulnak KIZÁRÓLAG egy feladata van: egy MEGADOTT, EGYETLEN
célmező jelenlegi (akár üres) tartalmából és egy opcionális rövid
felhasználói utasításból egyetlen AI-hívással egy pontosított szöveg-
javaslatot előállítani, majd az eredményt a `sermon_workshop_data.py`
párhuzamos, függőben lévő javaslat-tárolóján keresztül eltárolni.

Szándékosan TELJESEN FÜGGETLEN a hétpontos candidate-motortól
(`sermon_workshop_arc_ai.py`) és a régi section-szintű MI-segédektől:
  - nem importál `sermon_workshop_arc_ai`-ból semmit — külön, saját
    kontextus-összeállítást és promptot használ;
  - nem hívja a régi `sermon_workshop_*_ai.py` modulok `suggest_*`
    függvényeit, és nem nyúl a régi `refinement_chat` (app.py) kódhoz;
  - a kilenc célmező egymástól TELJESEN FÜGGETLEN: egy adott mezőhöz
    kért javaslat kizárólag annak a mezőnek a saját, aktuális tartalmát
    és a bibliai kontextust látja — sem a másik nyolc célmezőt, sem a
    teljes `arc`-ot, sem a Textusműhely háttéranyagait (áttekintés,
    exegézis, kortörténet, teológia) nem olvassa.

CANDIDATE-IDENTITÁS: a `context_hash` — a RESET 2C szűk korrekciójának
elvét követve — a ténylegesen felhasznált bemenet determinisztikus
azonosítója: igehely, bibliai szöveg, fordítás, a célmező saját aktuális
tartalma. Ha a generálás óta bármelyik megváltozik, az elfogadás
elutasításra kerül (`sermon_workshop_data.validate_field_refinement_
acceptance`). A felhasználói UTASÍTÁS szándékosan NEM része a hash-nek —
az a promptot alakító bemenet, nem egy élő, session-state-ben tovább
szerkeszthető mező, aminek a driftjét figyelni kellene.

Az AI-hívó függvényt (`generate_fn`) a hívó (UI) adja át — ez a modul
maga sosem importálja `app.generate_text`-et, és sosem hív valódi
hálózatot a saját tesztjeiben.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, replace
from typing import Any, Callable, Mapping, MutableMapping

from sermon_workshop_data import _REFINEMENT_FIELD_KEYS, set_field_refinement_suggestion
from llm_text_utils import starts_with_provider_warning

GenerateFn = Callable[..., str]

REFINEMENT_CONTEXT_VERSION = "field_refine_ctx_v1"

_FIELD_LABELS: dict[str, str] = {
    "text_main_idea": "A textus fő gondolata",
    "sermon_main_idea": "Az igehirdetés fő gondolata – fókuszmondat",
    "entry": "Belépés",
    "starting_point": "Alaphelyzet",
    "first_shift": "Első fordulópont",
    "deepening": "Mélyítés és fokozás",
    "reinterpretation": "Átértelmezés",
    "second_shift": "Második fordulópont",
    "arrival": "Megérkezés",
}

_FIELD_PURPOSE: dict[str, str] = {
    "text_main_idea": (
        "Mit mond ez a bibliai szakasz saját összefüggésében — EXEGETIKAI "
        "megállapítás, nem alkalmazás vagy felszólítás."
    ),
    "sermon_main_idea": (
        "Milyen felismerés vagy válasz felé vezesse az igehirdetés a "
        "hallgatót — HOMILETIKAI fókuszmondat, nem a szöveg tartalmi "
        "összefoglalása."
    ),
    "entry": "Természetes belépés a textus kérdésébe és a hallgató tapasztalatába.",
    "starting_point": "A textus és a hallgatói helyzet kiinduló feszültsége.",
    "first_shift": "Az első felismerés, amely elmozdítja a megszokott értelmezést.",
    "deepening": "A kérdés teológiai, emberi és egzisztenciális kibontása.",
    "reinterpretation": "A textus központi felismerése új fénybe helyezi a kiinduló kérdést.",
    "second_shift": "Az evangéliumi felismerés személyes és közösségi következménye.",
    "arrival": "A gondolatmenet természetes lezárása, amely eljuttat valahová.",
}


# =============================================================================
# Kontextus — kizárólag a MEGADOTT egyetlen célmezőre szűkítve
# =============================================================================


@dataclass(frozen=True)
class RefinementContext:
    field_key: str
    reference: str
    passage_text: str
    bible_translation: str
    current_text: str
    instruction: str
    context_hash: str

    def missing_required_fields(self) -> list[str]:
        missing: list[str] = []
        if not self.reference.strip():
            missing.append("igehely")
        if not self.passage_text.strip():
            missing.append("bibliai szöveg")
        if not self.context_hash.strip():
            missing.append("kontextusazonosító")
        return missing

    def is_valid(self) -> bool:
        return not self.missing_required_fields()


def compute_refinement_context_hash(context: RefinementContext) -> str:
    """A ténylegesen felhasznált bemenet determinisztikus azonosítója —
    igehely, bibliai szöveg, fordítás, a célmező kulcsa és SAJÁT aktuális
    tartalma. Szándékosan NEM tartalmazza a felhasználói utasítást (ld.
    modul docstring), a `generated_at`-ot, session-specifikus/véletlen
    adatot, vagy bármelyik MÁSIK célmező tartalmát."""
    payload = {
        "version": REFINEMENT_CONTEXT_VERSION,
        "field_key": context.field_key,
        "reference": context.reference,
        "passage_text": context.passage_text,
        "bible_translation": context.bible_translation,
        "current_text": context.current_text,
    }
    raw = json.dumps(payload, ensure_ascii=False, sort_keys=True)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _first_nonempty_str(session_state: Mapping[str, Any], *keys: str) -> str:
    for key in keys:
        val = session_state.get(key)
        if isinstance(val, str) and val.strip():
            return val.strip()
    return ""


def build_refinement_context(
    session_state: Mapping[str, Any],
    *,
    field_key: str,
    current_text: str,
    instruction: str = "",
) -> RefinementContext:
    """A kanonikus, EGYETLEN célmezőre szűkített pontosítási bemenet.

    Kizárólag a már meglévő, éles adatfolyamban is használt flat session-
    kulcsokból dolgozik (`last_igehely`/`igehely_input`, `passage_text`,
    `bible_translation`) — ugyanaz a forrás, mint a hétpontos candidate-
    motoré, de itt a célmező saját tartalmán kívül SEMMILYEN más mezőt
    (sem másik arc-pontot, sem Textusműhely-háttéranyagot) nem olvas."""
    reference = _first_nonempty_str(session_state, "last_igehely", "igehely_input")
    passage_text = _first_nonempty_str(session_state, "passage_text", "passage_text_input")
    bible_translation = _first_nonempty_str(session_state, "bible_translation") or "RÚF 2014"

    context = RefinementContext(
        field_key=field_key,
        reference=reference,
        passage_text=passage_text,
        bible_translation=bible_translation,
        current_text=str(current_text or "").strip(),
        instruction=str(instruction or "").strip(),
        context_hash="",
    )
    if context.reference and context.passage_text:
        context = replace(context, context_hash=compute_refinement_context_hash(context))
    return context


# =============================================================================
# Rendszerprompt + feladatprompt
# =============================================================================

REFINEMENT_SYSTEM_PROMPT = """SZEREP: Református homiletikai szerkesztő vagy, aki egyetlen, már meglévő (vagy még üres) szövegrészletet pontosít a felhasználó rövid utasítása szerint.

ALAPELVEK:
- KIZÁRÓLAG azt az egy mezőt pontosítsd, amelyikről szó van — ne generálj más pontokat, ne foglald össze a teljes igehirdetést vagy vázlatot;
- ha a felhasználó nem ad külön utasítást, végezz egy általános, minőségi pontosítást (tömörebb, konkrétabb, kevésbé közhelyes megfogalmazás);
- ha van felhasználói utasítás, azt kövesd elsődlegesen (pl. „legyen rövidebb”, „kapcsolódjon jobban a mai hallgatóhoz”, „fejtsd ki jobban”);
- ha a mező jelenleg üres, készíts új, a bibliai szöveghez illeszkedő javaslatot;
- ne találj ki bibliai, történeti vagy teológiai adatot;
- a válasz KIZÁRÓLAG a pontosított szöveg legyen — ne írj bevezetőt, magyarázatot, címkét, és ne idézd vissza az utasítást;
- a válasz magyar nyelvű, rövid, közvetlenül felhasználható szöveg legyen — nem teljes prédikáció és nem bekezdések sorozata."""

# A két főgondolat-mező funkcionálisan élesen elkülönül (RESET 2D-F1): a
# `text_main_idea` EXEGETIKAI állítás, a `sermon_main_idea` HOMILETIKAI
# fókuszmondat — a kilenc célmező egymástól független marad (ld. modul
# docstring), ezért ez a megkülönböztetés kizárólag a SAJÁT promptjukba
# épül be, nem a másik mező tartalmának ismeretéből fakad.
_MAIN_IDEA_CONTRAST_GUIDANCE: dict[str, str] = {
    "text_main_idea": (
        "Ez EXEGETIKAI állítás: fogalmazd meg tömören, mit állít, mit "
        "jelent ki vagy mit tesz Isten (illetve mi történik) EBBEN a "
        "szövegben, a maga összefüggésében — ne az igehirdetés "
        "alkalmazása, felszólítás vagy a hallgató felé mutass, és ne "
        "ismételd meg a szöveget. Legfeljebb 1–2 mondat."
    ),
    "sermon_main_idea": (
        "Ez HOMILETIKAI FÓKUSZMONDAT: fogalmazd meg tömören, milyen "
        "felismerés vagy válasz felé vezeti az igehirdetés a hallgatót — "
        "ez NE a szöveg tartalmi összefoglalása legyen (az a „textus fő "
        "gondolata” mező szerepe), hanem egy jól megjegyezhető, a "
        "hallgató felé forduló irány. Legfeljebb 1–2 mondat."
    ),
}


def build_refinement_prompt(context: RefinementContext) -> str:
    label = _FIELD_LABELS.get(context.field_key, context.field_key)
    purpose = _FIELD_PURPOSE.get(context.field_key, "")
    parts: list[str] = [
        f"IGEHELY: {context.reference}",
        f"FORDÍTÁS: {context.bible_translation}",
        "",
        "BIBLIAI SZÖVEG (textus):",
        context.passage_text,
        "",
        f"A PONTOSÍTANDÓ MEZŐ: {label}",
    ]
    if purpose:
        parts.append(f"A mező szerepe: {purpose}")
    contrast = _MAIN_IDEA_CONTRAST_GUIDANCE.get(context.field_key)
    if contrast:
        parts.append(contrast)
    parts += [
        "",
        "JELENLEGI TARTALOM:",
        context.current_text if context.current_text else "(még üres — készíts új javaslatot)",
    ]
    if context.instruction:
        parts += [
            "",
            "FELHASZNÁLÓI UTASÍTÁS (ezt kövesd elsődlegesen):",
            context.instruction,
        ]
    else:
        parts += [
            "",
            "Nincs külön felhasználói utasítás — végezz általános minőségi "
            "pontosítást (tömörebb, konkrétabb, kevésbé közhelyes).",
        ]
    parts += [
        "",
        "Add meg KIZÁRÓLAG a pontosított szöveget, bevezető vagy magyarázat nélkül.",
    ]
    return "\n".join(parts)


# =============================================================================
# Válasz-validálás
# =============================================================================


def validate_and_normalize_refinement_response(raw: Any) -> str | None:
    """Szigorú, de egyszerű validálás: a válasz nem üres, nem hibaüzenet-
    szerű szöveg. Bármilyen eltérés esetén `None` — a hívó ekkor SEM a
    kanonikus mezőbe, SEM a függőben lévő javaslatba nem írhat semmit."""
    if raw is None:
        return None
    text = str(raw).strip()
    if not text:
        return None
    if text.startswith("```"):
        text = text.strip("`").strip()
        if text.lower().startswith(("json", "text", "markdown")):
            text = text.split("\n", 1)[1] if "\n" in text else ""
        text = text.strip()
    return text or None


# 2026-11-23: a korábbi helyi másolat helyett a közös, viselkedésében
# azonos starts_with_provider_warning (llm_text_utils.py; azonosság: tests/test_llm_text_utils.py).
_looks_like_api_error = starts_with_provider_warning


# =============================================================================
# Orchestráció — egyetlen belépési pont a UI számára
# =============================================================================


@dataclass(frozen=True)
class RefinementOutcome:
    ok: bool
    status: str  # "suggested" | "error"
    error_message: str = ""
    text: str | None = None


def generate_field_refinement(
    session_state: MutableMapping[str, Any],
    *,
    field_key: str,
    current_text: str,
    instruction: str = "",
    generate_fn: GenerateFn,
) -> RefinementOutcome:
    """Egyetlen belépési pont: kontextus-ellenőrzés → legfeljebb EGY
    AI-hívás → válaszvalidálás → `set_field_refinement_suggestion()`
    (csak a MEGADOTT célmezőhöz — a másik nyolc érintetlen).

    Ha a kontextus hiányos, vagy a válasz üres/hibaüzenet-szerű, NEM
    indul (vagy nem hasznosul) AI-hívás, és semmilyen kanonikus mező,
    sem a függőben lévő javaslat-tároló nem módosul."""
    if field_key not in _REFINEMENT_FIELD_KEYS:
        raise ValueError(f"Ismeretlen pontosítási célmező: {field_key!r}")

    context = build_refinement_context(
        session_state,
        field_key=field_key,
        current_text=current_text,
        instruction=instruction,
    )
    missing = context.missing_required_fields()
    if missing:
        return RefinementOutcome(
            ok=False,
            status="error",
            error_message=(
                "Hiányzik a javaslatkéréshez: " + ", ".join(missing) + ". "
                "Ezek nélkül nem kérhető MI-javaslat."
            ),
        )

    prompt = build_refinement_prompt(context)
    label = _FIELD_LABELS.get(field_key, field_key)
    try:
        raw = generate_fn(
            prompt,
            tab_label=f"Pontosítás – {label}",
            use_cache=False,
            system_bundle=REFINEMENT_SYSTEM_PROMPT,
            include_brevity_directive=False,
        )
    except Exception as exc:  # noqa: BLE001 — a UI-nak mindenképp választ kell adnunk
        return RefinementOutcome(
            ok=False,
            status="error",
            error_message=f"A javaslatkérés sikertelen volt: {exc}",
        )

    if _looks_like_api_error(raw):
        return RefinementOutcome(ok=False, status="error", error_message=str(raw))

    text = validate_and_normalize_refinement_response(raw)
    if text is None:
        return RefinementOutcome(
            ok=False,
            status="error",
            error_message=(
                "A modell válasza nem használható javaslat — nem került "
                "mentésre. Próbáld újra."
            ),
        )

    set_field_refinement_suggestion(
        session_state,
        field_key,
        text=text,
        instruction=context.instruction,
        reference=context.reference,
        context_hash=context.context_hash,
    )
    return RefinementOutcome(ok=True, status="suggested", text=text)


__all__ = [
    "GenerateFn",
    "RefinementContext",
    "RefinementOutcome",
    "REFINEMENT_SYSTEM_PROMPT",
    "REFINEMENT_CONTEXT_VERSION",
    "compute_refinement_context_hash",
    "build_refinement_context",
    "build_refinement_prompt",
    "validate_and_normalize_refinement_response",
    "generate_field_refinement",
]
