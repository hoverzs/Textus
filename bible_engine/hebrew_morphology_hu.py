from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from typing import Iterable, Mapping

from bible_engine.hebrew_morphology import HebrewMorphology


LANGUAGE_HU = {"Hebrew": "héber", "Aramaic": "arámi"}

PART_OF_SPEECH_HU = {
    "Noun": "főnév",
    "Adjective": "melléknév",
    "Pronoun": "névmás",
    "Preposition": "elöljárószó",
    "Conjunction": "kötőszó",
    "Particle": "partikula",
    "Adverb": "határozószó",
    "Verb": "ige",
    "Suffix": "suffixum",
    "Object marker": "tárgyjelölő",
    "Article": "névelő",
    "Negative": "tagadószó",
    "Interrogative": "kérdő partikula",
    "Relative": "vonatkozó partikula",
    "Interjection": "indulatszó",
    # Phase 2B — decode_hebrew_morphology sets part_of_speech to the same
    # PARTICLE_FORMS value as particle_type (see hebrew_morphology.py, the
    # function_code == "T" branch), so every particle subtype needs an entry
    # here too, or it leaks through _shape_details()'s include_pos path.
    "Conditional": "feltételes/okhatározó partikula",
    "Demonstrative": "mutató partikula",
}

NOUN_TYPE_HU = {"Common": "köznév", "Proper": "tulajdonnév", "Gentilic": "népnév", "Title": "titulus"}
ADJECTIVE_TYPE_HU = {
    "Adjective": "melléknév",
    "Cardinal": "tőszámnév",
    "Numerical": "számnévi melléknév",
    "Ordinal": "sorszámnév",
    "Numerical position": "sorszámnévi melléknév",
}
PRONOUN_TYPE_HU = {"Personal": "személyes névmás", "Demonstrative": "mutató névmás", "Interrogative": "kérdő névmás"}
PROPER_NAME_TYPE_HU = {"Location": "helynév", "Title": "titulus"}
PARTICLE_TYPE_HU = {
    "Article": "névelő",
    "Object marker": "tárgyjelölő partikula",
    "Negative": "tagadószó",
    "Interrogative": "kérdő partikula",
    "Relative": "vonatkozó partikula",
    "Conjunction": "kötőszói partikula",
    "Interjection": "indulatszó",
    # Phase 2B — TEHMC-confirmed corrections (see hebrew_morphology.PARTICLE_FORMS):
    "Conditional": "feltételes/okhatározó partikula",  # was mislabelled "Conjunction" (HTc/ATc, 6047 tokens: כִּי "hogy/mert", דִּי "hogy/aki")
    "Demonstrative": "mutató partikula",  # was mislabelled "Interrogative" (HTm/ATm, 2664 tokens: זֶה/זֹאת/אֵלֶּה "ez/az/ezek")
}

STEM_HU = {
    "Qal": "qal",
    "Niphal": "nifal",
    "Piel": "piel",
    "Pual": "pual",
    "Hiphil": "hifil",
    "Hophal": "hofal",
    "Hithpael": "hitpael",
    "Hishtaphel": "hishtafel",
    "Aphel": "afel",
    "Haphel": "hafel",
    "Peal": "peal",
    "Peil": "peil",
    "Ithpeel": "itpeel",
    "Hithpaal": "hitpaal",
    "Shaphel": "shafel",
    "Tiphil": "tifil",
    "Hitpael": "hitpael",
    "Nithpael": "nitpael",
    # Phase 2B — TEHMC-authoritative stems added once STEMS_BY_LANGUAGE made
    # them reachable (previously unnamed/unreached, see hebrew_morphology.py):
    "Hitpeel": "hitpeel",  # Aramaic passive/reflexive t-stem — distinct from "Ithpeel"
    "Hothpaal": "hotpaal",  # Hebrew rare passive/reflexive — TEHMC classifies it Reflexive, not Passive
    "Ishtaphel": "istafel",  # Aramaic causative-reflexive — distinct spelling from Hebrew "Hishtaphel"
    "Polal": "polal",  # TEHMC-defined; unattested in this TAHOT edition
    "Pael": "pael",  # Aramaic — distinct from Hebrew "Piel" (both simple-intensive, different names)
    "Hitpaal": "hitpaal",  # TEHMC's exact spelling (previously only "Hithpaal" was mapped, with an extra 'h')
}

VERB_FORM_HU = {
    "Perfect": "perfectum",
    "Imperfect": "imperfectum",
    "Consecutive Imperfect": "wayyiqtol",
    "Consecutive Perfect": "weqatal",
    "Imperative": "imperativus",
    "Infinitive Construct": "infinitivus constructus",
    "Infinitive Absolute": "infinitivus absolutus",
    "Participle": "participium",
    "Passive Participle": "passzív participium",
    "Cohortative": "cohortativus",
    "Jussive": "jussivus",
    "Conjunction Imperfect": "kötőszós imperfectum",
}

PERSON_HU = {"First": "első személy", "Second": "második személy", "Third": "harmadik személy"}
GENDER_HU = {
    "Masculine": "hímnem",
    "Feminine": "nőnem",
    "Common": "közös nem",
    "Either gender": "mindkét nem",
}
NUMBER_HU = {"Singular": "egyes szám", "Plural": "többes szám", "Dual": "kettős szám"}
STATE_HU = {"Absolute": "absolutus", "Construct": "constructus", "Definite": "határozott", "Emphatic": "emphaticus"}
SUFFIX_TYPE_HU = {
    "Pronominal": "birtokos",
    "Object": "tárgyi",
    "Directional": "irányjelölő",
    # Phase 2B — TEHMC-confirmed corrections (see hebrew_morphology.SUFFIX_TYPES):
    "Paragogic Nun": "paragogikus nun",  # was mislabelled "Emphatic" (Sn, 309 tokens)
    "Paragogic Hé": "paragogikus hé",  # previously unmapped entirely (Sh, 407 tokens)
}
PREPOSITION_TYPE_HU = {"Definite": "határozott névelővel"}

# A "core" komponens az a szóelem, amelynek a TAHOT dStrong-mezőjében kapcsos
# zárójeles {Hxxxx} Strong-száma van (ld. hebrew_parser._core_index): vagyis a
# szóalak LEXÉMÁT HORDOZÓ tagja, a rátapadó prefixumok (waw, elöljárószó,
# névelő) és suffixumok (birtokos/tárgyi rag) nélkül.
#
# Ez NEM a héber gyök. A gyök (pl. ב־ר־א) külön, önálló normalizált mező lesz,
# és külön adatforrást igényel — a jelenlegi TAHOT/TBESH adat nem tartalmazza
# (ld. docs/hebrew_analysis_v2_phase2a.md). Ezért a korábbi "lexikai mag"
# címkét NEM "gyök"-re cseréltük — az új nyelvi hibát okozna —, hanem a
# ténylegesen leírt dologra: "alapszó".
COMPONENT_ROLE_HU = {"prefix": "prefixum", "core": "alapszó", "suffix": "suffixum", "composite": "összetett alak"}

STATUS_HU = {
    "fully_decoded": "teljesen feloldott morfológia",
    "partially_decoded": "részben feloldott morfológia",
    "unresolved": "nem feloldott morfológia",
    "malformed": "hibás morfológiai kód",
}

TECHNICAL_LEAK_TERMS = frozenset(
    {
        "Hebrew",
        "Aramaic",
        "Noun",
        "Adjective",
        "Pronoun",
        "Preposition",
        "Conjunction",
        "Particle",
        "Adverb",
        "Verb",
        "Suffix",
        "Object marker",
        "Article",
        "Negative",
        "Interrogative",
        "Relative",
        "Interjection",
        "Qal",
        "Niphal",
        "Piel",
        "Pual",
        "Hiphil",
        "Hophal",
        "Hithpael",
        "Tiphil",
        "Hitpael",
        "Nithpael",
        # Phase 2B — the remaining STEM_HU terms were reachable even before
        # this phase but were missing from leak detection; closing that gap
        # here since it directly touches the same table.
        "Hishtaphel",
        "Aphel",
        "Haphel",
        "Peal",
        "Peil",
        "Ithpeel",
        "Hithpaal",
        "Shaphel",
        # Phase 2B — newly reachable via STEMS_BY_LANGUAGE:
        "Hitpeel",
        "Hothpaal",
        "Ishtaphel",
        "Polal",
        "Perfect",
        "Imperfect",
        "Consecutive Imperfect",
        "Consecutive Perfect",
        "Imperative",
        "Infinitive Construct",
        "Infinitive Absolute",
        "Participle",
        "Passive Participle",
        "Conjunction Imperfect",
        "First",
        "Second",
        "Third",
        "Masculine",
        "Feminine",
        "Common",
        "Either gender",
        "Singular",
        "Plural",
        "Dual",
        "Absolute",
        "Construct",
        "Definite",
        "Emphatic",
        "Pronominal",
        "Object",
        "Directional",
        "Emphatic",
        "Location",
        "Title",
        "Gentilic",
        "Numerical position",
        "Numerical",
        # Phase 2B — TEHMC-confirmed additions:
        "Conditional",
        "Demonstrative",
        "Paragogic Nun",
        "Paragogic Hé",
        "fully_decoded",
        "partially_decoded",
        "unresolved",
        "malformed",
    }
)


def format_hebrew_morphology_hu(
    morphology: HebrewMorphology | Mapping[str, object],
    *,
    include_language: bool = False,
    include_status: bool = True,
) -> str:
    data = _as_mapping(morphology)
    components = [_as_mapping(component) for component in data.get("components", ()) or ()]
    if components:
        parts = [" + ".join(_component_head(component) for component in components if _component_head(component))]
        detail = _shape_details(data, include_pos=False)
        if detail:
            parts.append(detail)
        parts.extend(_suffix_phrases(data))
    else:
        parts = [_shape_details(data, include_pos=True), *_suffix_phrases(data)]

    if include_language and _translate_joined(data.get("language"), LANGUAGE_HU):
        parts.insert(0, _translate_joined(data.get("language"), LANGUAGE_HU))
    if include_status and data.get("status") in {"partially_decoded", "unresolved", "malformed"}:
        parts.append(STATUS_HU.get(str(data.get("status")), "nem feloldott morfológia"))
    return "; ".join(_dedupe(part for part in parts if part))


def format_hebrew_component_hu(
    component: HebrewMorphology | Mapping[str, object],
    *,
    include_language: bool = False,
) -> str:
    data = _as_mapping(component)
    parts = [_shape_details(data, include_pos=True), *_suffix_phrases(data)]
    if include_language and _translate_joined(data.get("language"), LANGUAGE_HU):
        parts.insert(0, _translate_joined(data.get("language"), LANGUAGE_HU))
    if data.get("status") in {"partially_decoded", "unresolved", "malformed"}:
        parts.append(STATUS_HU.get(str(data.get("status")), "nem feloldott morfológia"))
    return "; ".join(_dedupe(part for part in parts if part))


def format_hebrew_morphology_rows_hu(morphology: HebrewMorphology | Mapping[str, object]) -> list[tuple[str, str]]:
    data = _as_mapping(morphology)
    rows = [
        ("Nyelv", _translate_joined(data.get("language"), LANGUAGE_HU)),
        ("Szófaj", _translate_composite(data.get("part_of_speech"), PART_OF_SPEECH_HU)),
        ("Főnévi típus", _hu(data, "noun_type", NOUN_TYPE_HU)),
        ("Melléknévi típus", _hu(data, "adjective_type", ADJECTIVE_TYPE_HU)),
        ("Névmási típus", _hu(data, "pronoun_type", PRONOUN_TYPE_HU)),
        ("Tulajdonnévi típus", _hu(data, "proper_name_type", PROPER_NAME_TYPE_HU)),
        ("Partikulatípus", _hu(data, "particle_type", PARTICLE_TYPE_HU)),
        ("Elöljárótípus", _hu(data, "preposition_type", PREPOSITION_TYPE_HU)),
        ("Igetörzs", _hu(data, "verb_stem", STEM_HU)),
        ("Igealak", _hu(data, "verb_conjugation", VERB_FORM_HU)),
        ("Személy", _hu(data, "person", PERSON_HU)),
        ("Nem", _hu(data, "gender", GENDER_HU)),
        ("Szám", _hu(data, "number", NUMBER_HU)),
        ("Állapot", _hu(data, "state", STATE_HU)),
        ("Suffixum", "; ".join(_suffix_phrases(data))),
        ("Státusz", STATUS_HU.get(str(data.get("status")), "")),
    ]
    return [(label, value) for label, value in rows if value]


def format_pronominal_suffix_hu(morphology: HebrewMorphology | Mapping[str, object]) -> str:
    return "; ".join(_suffix_phrases(_as_mapping(morphology)))


def untranslated_terms(text: str) -> tuple[str, ...]:
    hits = [term for term in TECHNICAL_LEAK_TERMS if term in text]
    return tuple(sorted(hits, key=lambda item: (text.index(item), item)))


def classify_hebrew_morphology_hu(morphology: HebrewMorphology | Mapping[str, object]) -> str:
    data = _as_mapping(morphology)
    summary = format_hebrew_morphology_hu(data, include_language=True)
    if untranslated_terms(summary):
        return "technical_leak"
    if data.get("status") == "fully_decoded" and summary:
        return "complete"
    if data.get("status") == "partially_decoded" and summary:
        return "partial"
    return "unresolved"


def audit_hebrew_morphology_hu(
    decoded_by_code: Mapping[str, HebrewMorphology],
    counts_by_code: Mapping[str, int],
) -> dict[str, object]:
    categories: dict[str, list[str]] = {"complete": [], "partial": [], "technical_leak": [], "unresolved": []}
    leaks: Counter[str] = Counter()
    for code, morphology in decoded_by_code.items():
        category = classify_hebrew_morphology_hu(morphology)
        categories[category].append(code)
        leaks.update(untranslated_terms(format_hebrew_morphology_hu(morphology, include_language=True)))

    total_tokens = sum(counts_by_code.values())
    complete_tokens = sum(counts_by_code[code] for code in categories["complete"])
    partial_tokens = sum(counts_by_code[code] for code in categories["partial"])
    leak_tokens = sum(counts_by_code[code] for code in categories["technical_leak"])
    unresolved_tokens = sum(counts_by_code[code] for code in categories["unresolved"])
    return {
        "unique_morphology_codes": len(counts_by_code),
        "fully_hungarian_codes": len(categories["complete"]),
        "partially_hungarian_codes": len(categories["partial"]),
        "technical_leak_codes": len(categories["technical_leak"]),
        "unresolved_codes": len(categories["unresolved"]),
        "fully_hungarian_token_count": complete_tokens,
        "partially_hungarian_token_count": partial_tokens,
        "technical_leak_token_count": leak_tokens,
        "unresolved_token_count": unresolved_tokens,
        "affected_tokens": partial_tokens + leak_tokens + unresolved_tokens,
        "token_coverage_percent": 100.0 * complete_tokens / total_tokens if total_tokens else 0.0,
        "unique_code_coverage_percent": 100.0 * len(categories["complete"]) / len(counts_by_code) if counts_by_code else 0.0,
        "most_common_missing_terms": [{"term": term, "code_count": count} for term, count in leaks.most_common(50)],
        "examples": {
            category: [
                {
                    "code": code,
                    "token_count": counts_by_code[code],
                    "status": decoded_by_code[code].status,
                    "summary_hu": format_hebrew_morphology_hu(decoded_by_code[code], include_language=True),
                    "unresolved_parts": decoded_by_code[code].unresolved_parts,
                }
                for code in sorted(codes, key=lambda item: (-counts_by_code[item], item))[:25]
            ]
            for category, codes in categories.items()
        },
    }


def _shape_details(data: Mapping[str, object], *, include_pos: bool) -> str:
    parts: list[str] = []
    if include_pos:
        parts.append(_translate_composite(data.get("part_of_speech"), PART_OF_SPEECH_HU))
    for field, mapping in (
        ("noun_type", NOUN_TYPE_HU),
        ("adjective_type", ADJECTIVE_TYPE_HU),
        ("pronoun_type", PRONOUN_TYPE_HU),
        ("proper_name_type", PROPER_NAME_TYPE_HU),
        ("particle_type", PARTICLE_TYPE_HU),
        ("preposition_type", PREPOSITION_TYPE_HU),
    ):
        if data.get(field):
            value = _hu(data, field, mapping)
            if value not in parts:
                parts.append(value)
    if data.get("verb_stem"):
        parts.append(f"{_hu(data, 'verb_stem', STEM_HU)} törzs")
    if data.get("verb_conjugation"):
        parts.append(_hu(data, "verb_conjugation", VERB_FORM_HU))
    for field, mapping in (
        ("person", PERSON_HU),
        ("gender", GENDER_HU),
        ("number", NUMBER_HU),
        ("state", STATE_HU),
    ):
        if data.get(field):
            parts.append(_hu(data, field, mapping))
    return ", ".join(_dedupe(parts))


def _suffix_phrases(data: Mapping[str, object]) -> list[str]:
    components = [_as_mapping(component) for component in data.get("components", ()) or ()]
    suffixes = [component for component in components if component.get("component_type") == "suffix"]
    if not suffixes and data.get("part_of_speech") == "Suffix":
        suffixes = [data]
    phrases: list[str] = []
    for suffix in suffixes:
        suffix_type = _hu(suffix, "suffix_type", SUFFIX_TYPE_HU) or "névmási"
        person = _hu(suffix, "suffix_person", PERSON_HU)
        number = _hu(suffix, "suffix_number", NUMBER_HU)
        gender = _hu(suffix, "suffix_gender", GENDER_HU)
        agreement_parts = [number, person]
        if gender and gender not in {"közös nem", "mindkét nem"}:
            agreement_parts.append(gender)
        agreement = " ".join(part for part in agreement_parts if part)
        phrases.append(f"{agreement} {suffix_type} suffixummal".strip())
    return phrases


def _component_head(component: Mapping[str, object]) -> str:
    return _translate_composite(component.get("part_of_speech"), PART_OF_SPEECH_HU)


def _translate_composite(value: object, mapping: Mapping[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if " + " in text:
        return " + ".join(_translate_composite(part, mapping) for part in text.split(" + "))
    return mapping.get(text, text)


def _translate_joined(value: object, mapping: Mapping[str, str]) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if ", " in text:
        return ", ".join(_translate_joined(part, mapping) for part in text.split(", "))
    return _translate_composite(text, mapping)


def _hu(data: Mapping[str, object], field: str, mapping: Mapping[str, str]) -> str:
    value = str(data.get(field) or "").strip()
    return mapping.get(value, value)


def _as_mapping(value: HebrewMorphology | Mapping[str, object]) -> Mapping[str, object]:
    if isinstance(value, HebrewMorphology):
        return asdict(value)
    return value


def _dedupe(parts: Iterable[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return out
