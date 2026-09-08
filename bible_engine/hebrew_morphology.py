from __future__ import annotations

import re
from collections import Counter
from dataclasses import asdict, dataclass
from pathlib import Path


@dataclass(frozen=True)
class HebrewMorphology:
    code: str
    original_code: str = ""
    language: str = ""
    part_of_speech: str = ""
    component_type: str = ""
    components: tuple[dict[str, object], ...] = ()
    noun_type: str = ""
    adjective_type: str = ""
    pronoun_type: str = ""
    proper_name_type: str = ""
    particle_type: str = ""
    preposition_type: str = ""
    conjunction_type: str = ""
    verb_stem: str = ""
    verb_conjugation: str = ""
    person: str = ""
    gender: str = ""
    number: str = ""
    state: str = ""
    suffix_type: str = ""
    suffix_person: str = ""
    suffix_gender: str = ""
    suffix_number: str = ""
    english_expansion: str = ""
    unresolved_parts: tuple[str, ...] = ()
    status: str = "unresolved"

    @property
    def fully_decoded(self) -> bool:
        return self.status == "fully_decoded"


LANGUAGE = {"H": "Hebrew", "A": "Aramaic"}
FUNCTION = {
    "N": "Noun",
    "A": "Adjective",
    "P": "Pronoun",
    "R": "Preposition",
    "C": "Conjunction",
    "c": "Conjunction",
    "T": "Particle",
    "D": "Adverb",
    "V": "Verb",
    "S": "Suffix",
    "o": "Object marker",
    "d": "Article",
    "n": "Negative",
    "m": "Interrogative",
    "r": "Relative",
}
# Phase 2B — the STEPBible TEHMC particle-form letters (verified against the
# authoritative source; see docs/hebrew_analysis_v2_phase2b.md). Corrects two
# Phase 2A errors inherited from the original hand-maintained table:
#   "m" was "Interrogative" — TEHMC (HTm/ATm) says "Demonstrative", confirmed
#     by corpus glosses (אֵלֶּה "these", זֹאת/זֶה "this", never "where?"/"when?").
#     2,664 tokens.
#   "c" was "Conjunction" — TEHMC (HTc/ATc) says "Conditional", confirmed by
#     corpus glosses (כִּי "that"/"for", דִּי "that"/"who" — a causal/relative
#     conjunction, not a plain "and"-type conjunction). 6,047 tokens.
# "i" (Interrogative) and "j" (Interjection) were already correct.
PARTICLE_FORMS = {
    "a": "Article",
    "d": "Article",
    "o": "Object marker",
    "n": "Negative",
    "m": "Demonstrative",
    "r": "Relative",
    "c": "Conditional",
    "i": "Interrogative",
    "j": "Interjection",
}

# Phase 2B — TEHMC suffix-form letters (HSp*/ASp*, HSd/HSh/HSn — identical in
# both languages). Corrects one Phase 2A error and closes one Phase 2A gap:
#   "n" was "Emphatic" — TEHMC (Sn) says "Paragogic Nun", a specific energic
#     suffix, not a generic emphasis marker. 309 tokens.
#   "h" had NO mapping at all — TEHMC (Sh) says "Paragogic Hé". Every Sh token
#     previously decoded with an empty suffix_type while still being marked
#     `fully_decoded` (part_of_speech="Suffix" alone satisfied that check).
#     407 tokens.
SUFFIX_TYPES = {
    "p": "Pronominal",
    "o": "Object",
    "d": "Directional",
    "n": "Paragogic Nun",
    "h": "Paragogic Hé",
}
# ---------------------------------------------------------------------------
# TEHMC verb stem (binyan) codes — Phase 2B, authoritative.
#
# Provenance: STEPBible/STEPBible-Data, "Morphology codes/TEHMC - Translators
# Expansion of Hebrew Morphology Codes - STEPBible.org CC BY.txt", vendored at
# data/stepbible_sources/TEHMC.txt (exact commit/checksum/licence recorded in
# docs/hebrew_analysis_v2_phase2b.md). Phase 2A had to infer this table from
# corpus evidence alone because TEHMC was unavailable; every stem letter below
# is now the literal ``Stem=`` value TEHMC assigns to the corresponding full
# code (e.g. ``HVqp3ms`` -> Qal, ``AVqp3ms`` -> Peal).
#
# CRITICAL, Phase-2A-missed finding: stem letters are LANGUAGE-DEPENDENT — the
# same letter names a different binyan in Hebrew than in Aramaic. Phase 2A's
# flat, language-independent STEMS dict therefore mislabelled 939 Aramaic
# tokens with a Hebrew stem name (e.g. an Aramaic Peal verb shown as "Qal").
# All seven codes Phase 2A left unresolved (Q, u, M, e, a, D, i) are now
# resolved, several of them precisely BECAUSE they are Aramaic-specific
# letters that never had a Hebrew reading to begin with.
STEMS_BY_LANGUAGE: dict[str, dict[str, str]] = {
    "H": {  # Hebrew (code[:1] == "H")
        "q": "Qal",  # 50,202 tokens
        "N": "Niphal",  # 4,148
        "p": "Piel",  # 6,818
        "P": "Pual",  # 511
        "h": "Hiphil",  # 9,415
        "H": "Hophal",  # 417
        "t": "Hithpael",  # 1,001
        "v": "Hishtaphel",  # 131 — lemma שָׁחָה "bow down"
        "c": "Tiphil",  # 3 — lemmas תִּרְגַּל / תַּחָרָה
        "D": "Nithpael",  # 3 — Deu.21.8, Prov.27.15, Eze.23.48 (TEHMC's own note)
        "u": "Hothpaal",  # 8 — Lev.13.55f, Num.1.47 etc (TEHMC's own note)
        "O": "Polal",  # 0 — TEHMC-defined, unattested in this TAHOT edition
    },
    "A": {  # Aramaic (code[:1] == "A")
        "q": "Peal",  # 629 — was wrongly shown as "Qal"
        "h": "Haphel",  # 161 — was wrongly shown as "Hiphil"
        "p": "Pael",  # 88 — was wrongly shown as "Piel"
        "P": "Hitpeel",  # 6 — was wrongly shown as "Pual" (a different voice entirely)
        "H": "Hophal",  # 14 — same name in both languages
        "v": "Ishtaphel",  # 2 — was wrongly shown as "Hishtaphel"
        "e": "Shaphel",  # 15 — was Phase-1 "Peal", contradicted by lemma evidence
        "a": "Aphel",  # 4
        "i": "Hitpeel",  # 3
        "M": "Hitpaal",  # 30
        "Q": "Peil",  # 65
        "u": "Hitpael",  # 53 — the Aramaic reading of "u" (Hebrew "u" = Hothpaal)
    },
}

# Retained for backward compatibility (a handful of call sites still expect a
# flat mapping); language-aware lookup happens via STEMS_BY_LANGUAGE. Kept in
# sync at import time — see the assertion below.
STEMS: dict[str, str] = dict(STEMS_BY_LANGUAGE["H"])

# Empty as of Phase 2B: TEHMC resolved every stem letter Phase 2A left
# unnamed. Kept (rather than removed) so existing imports do not break, and so
# a FUTURE unnameable code has somewhere to go without inventing a new symbol.
UNVERIFIED_STEM_CODES: frozenset[str] = frozenset()


def _stem_for_code(language_letter: str, stem_code: str) -> str:
    """Resolve a verb stem letter using the correct language's table."""
    return STEMS_BY_LANGUAGE.get(language_letter, {}).get(stem_code, "")

# ---------------------------------------------------------------------------
# TEHMC verb form/conjugation codes — VERIFIED against the shipped corpus.
#
#   w  14978  person tail, "he said"            -> narrative past   Consecutive Imperfect
#   p  14791  person tail, "he created"         -> past             Perfect
#   i  13471  person tail, "you will eat"       -> modal/future     Imperfect
#   r   8419  gender+number+state, "separating" -> active           Participle
#   c   7292  OVERLOADED, see _verb_form_for_code()
#   q   6344  person tail, "they will become", follows consecutive waw
#                                               -> weqatal          Consecutive Perfect
#   v   4305  tail is 2ms/2mp/2fs/2fp ONLY — 100% second person, glosses
#             "be fruitful" (Gen 1:22), "take" (Gen 22:2), "listen to"
#             (Gen 4:23)                        -> Imperative
#   s   1280  gender+number+state, "[be] blessed" -> passive        Passive Participle
#   j   1099  person tail, "let it be"          -> volitional       Jussive
#   u    999  person tail, occurs ONLY after an ordinary (uppercase C)
#             conjunction, never bare; "so that I may bless"
#                                               -> Conjunction Imperfect
#   a    749  tail is always "a"                -> Infinitive Absolute
#
# The previous table additionally mapped "m" -> Imperative and "n" -> Imperfect.
# Neither code occurs even once in the corpus, while the real imperative code
# "v" was mapped to "Consecutive Perfect". Those dead entries are removed so an
# unknown form code now surfaces as unresolved instead of silently decoding.
VERB_FORMS = {
    "p": "Perfect",
    "q": "Consecutive Perfect",
    "i": "Imperfect",
    "w": "Consecutive Imperfect",
    "u": "Conjunction Imperfect",
    "j": "Jussive",
    "v": "Imperative",
    "c": "Infinitive Construct",
    "a": "Infinitive Absolute",
    "r": "Participle",
    "s": "Passive Participle",
}

# Verb forms whose tail carries gender/number/state rather than person.
NON_FINITE_VERB_FORMS = frozenset({"Participle", "Passive Participle"})

# Verb forms that may never be inflected for person. Used by the corpus
# validator to turn a future table mistake into a test failure.
PERSONLESS_VERB_FORMS = NON_FINITE_VERB_FORMS | {
    "Infinitive Construct",
    "Infinitive Absolute",
}

# Structural person constraints verified across the whole corpus. A form listed
# here must only ever appear with these persons.
VERB_FORM_PERSON_CONSTRAINTS: dict[str, frozenset[str]] = {
    "Imperative": frozenset({"Second"}),
    "Cohortative": frozenset({"First"}),
}


def _verb_form_for_code(form_code: str, tail: str) -> str:
    """Resolve a TEHMC verb form code, disambiguating the overloaded ``c``.

    TEHMC reuses ``c`` for two different forms, distinguished by what follows:

    * ``Vqcc``    — tail is a state letter  -> Infinitive Construct (6758 tokens)
    * ``Vqc1cs``  — tail begins with a person digit -> Cohortative (534 tokens)

    The cohortative reading is not a guess: in the whole corpus ``c`` followed
    by a person is **exclusively first person** (1cs 358, 1cp 176), which is the
    cohortative's defining constraint, and STEPBible glosses the forms
    accordingly — "let us go down" (Gen 11:7), "let me bless" (Gen 12:3).
    Before this disambiguation those 534 tokens were reported as infinitive
    constructs carrying a person, which is self-contradictory.
    """
    if form_code == "c" and tail[:1] in PERSON:
        return "Cohortative"
    return VERB_FORMS.get(form_code, "")
PERSON = {"1": "First", "2": "Second", "3": "Third"}
GENDER = {"m": "Masculine", "f": "Feminine", "b": "Either gender", "c": "Common"}
NUMBER = {"s": "Singular", "p": "Plural", "d": "Dual"}
STATE = {"a": "Absolute", "c": "Construct", "d": "Definite", "e": "Emphatic"}


def load_tehmc_expansions(source_path: str | Path) -> dict[str, str]:
    expansions: dict[str, str] = {}
    for raw_line in Path(source_path).read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()
        if not line or "\t" not in line:
            continue
        code, expansion = line.split("\t", 1)
        code = code.strip()
        if re.match(r"^(?:[AH][A-Za-z0-9]+|S[po]?[123]?[cfmb]?[spd]?)$", code):
            expansions[code] = expansion.strip()
    return expansions


def decode_hebrew_morphology(code: str, expansions: dict[str, str] | None = None) -> HebrewMorphology:
    clean = (code or "").strip()
    if not clean:
        return HebrewMorphology(code=clean, unresolved_parts=("empty",), status="malformed")
    parts = _split_morphology_components(clean)
    decoded = [
        _decode_single(
            part,
            expansions or {},
            original_code=raw_part,
            component_type=_component_type(part, index, len(parts)),
        )
        for index, (raw_part, part) in enumerate(parts)
    ]
    if len(decoded) == 1:
        return decoded[0]
    unresolved = tuple(item for morph in decoded for item in morph.unresolved_parts)
    primary = _primary_component(decoded)
    return HebrewMorphology(
        code=clean,
        original_code=clean,
        language=", ".join(dict.fromkeys(m.language for m in decoded if m.language)),
        part_of_speech=" + ".join(m.part_of_speech for m in decoded if m.part_of_speech),
        component_type="composite",
        components=tuple(_component_payload(morph) for morph in decoded),
        proper_name_type=primary.proper_name_type,
        particle_type=primary.particle_type,
        verb_stem=primary.verb_stem,
        verb_conjugation=primary.verb_conjugation,
        person=primary.person,
        gender=primary.gender,
        number=primary.number,
        state=primary.state,
        suffix_type=primary.suffix_type,
        suffix_person=primary.suffix_person,
        suffix_gender=primary.suffix_gender,
        suffix_number=primary.suffix_number,
        english_expansion=" / ".join(m.english_expansion for m in decoded if m.english_expansion),
        unresolved_parts=unresolved,
        status=_combined_status(decoded, unresolved),
    )


def audit_morphology_codes(codes: list[str], expansions: dict[str, str]) -> dict[str, object]:
    counts = Counter(codes)
    decoded = {code: decode_hebrew_morphology(code, expansions) for code in counts}
    fully = [code for code, morph in decoded.items() if morph.status == "fully_decoded"]
    partial = [code for code, morph in decoded.items() if morph.status == "partially_decoded"]
    unresolved = [code for code, morph in decoded.items() if morph.status == "unresolved"]
    malformed = [code for code, morph in decoded.items() if morph.status == "malformed"]
    total_tokens = sum(counts.values())
    return {
        "unique_morphology_codes": len(counts),
        "fully_decoded_codes": len(fully),
        "partially_decoded_codes": len(partial),
        "unresolved_codes": len(unresolved),
        "malformed_codes": len(malformed),
        "decoded_token_count": sum(counts[code] for code in fully),
        "partially_decoded_token_count": sum(counts[code] for code in partial),
        "unresolved_token_count": sum(counts[code] for code in unresolved),
        "malformed_token_count": sum(counts[code] for code in malformed),
        "token_coverage_percent": (
            100.0 * sum(counts[code] for code in fully) / total_tokens if total_tokens else 0.0
        ),
        "unique_code_coverage_percent": 100.0 * len(fully) / len(counts) if counts else 0.0,
        "unresolved_pattern_groups": _group_unresolved_patterns(counts, decoded),
        "most_common_unresolved": [
            {"code": code, "token_count": counts[code], "decoded": asdict(decoded[code])}
            for code in sorted(unresolved, key=lambda item: (-counts[item], item))[:100]
        ],
    }


def _decode_single(
    code: str,
    expansions: dict[str, str],
    *,
    original_code: str | None = None,
    component_type: str = "",
) -> HebrewMorphology:
    expansion = expansions.get(code, "")
    unresolved: list[str] = []
    if code.startswith("S"):
        values: dict[str, str | tuple[str, ...]] = {
            "code": code,
            "original_code": original_code or code,
            "component_type": component_type or "suffix",
            "part_of_speech": "Suffix",
            "english_expansion": expansion,
            "suffix_type": SUFFIX_TYPES.get(code[1:2], ""),
        }
        _decode_person_gender_number(code[2:], values, unresolved, prefix="suffix_")
        values["unresolved_parts"] = tuple(unresolved)
        values["status"] = _status(code, expansion, unresolved, values)
        return HebrewMorphology(**values)  # type: ignore[arg-type]
    language = LANGUAGE.get(code[:1], "")
    if not language:
        unresolved.append(code[:1] or "missing-language")
    function_code = code[1:2]
    pos = FUNCTION.get(function_code, "")
    if not pos:
        unresolved.append(function_code or "missing-function")
    values: dict[str, str | tuple[str, ...]] = {
        "code": code,
        "original_code": original_code or code,
        "language": language,
        "part_of_speech": pos,
        "component_type": component_type,
        "english_expansion": expansion,
    }
    tail = code[2:]
    if function_code == "V":
        stem_code = tail[:1]
        # Phase 2B: stem letters are language-dependent (STEMS_BY_LANGUAGE) —
        # the same letter names a different binyan in Hebrew than in Aramaic.
        stem_name = _stem_for_code(code[:1], stem_code)
        if stem_name:
            values["verb_stem"] = stem_name
        else:
            unresolved.append(stem_code or "missing-verb-stem")
        form_code = tail[1:2]
        conjugation = _verb_form_for_code(form_code, tail[2:])
        if conjugation:
            values["verb_conjugation"] = conjugation
        else:
            unresolved.append(form_code or "missing-verb-form")
        _decode_verb_ending(tail[2:], values, unresolved)
    elif function_code in {"N", "A", "P"}:
        if tail[:1]:
            if function_code == "N":
                values["noun_type"] = {
                    "c": "Common",
                    "p": "Proper",
                    "g": "Gentilic",
                    "t": "Title",
                }.get(tail[:1], "")
            elif function_code == "A":
                values["adjective_type"] = {
                    "a": "Adjective",
                    "c": "Numerical",
                    "o": "Numerical position",
                }.get(tail[:1], "")
            else:
                values["pronoun_type"] = {"p": "Personal", "d": "Demonstrative", "i": "Interrogative"}.get(tail[:1], "")
            if function_code == "N" and values.get("noun_type") == "Proper":
                values["proper_name_type"] = {"l": "Location", "t": "Title"}.get(tail[1:2], "")
            if not values.get("noun_type") and not values.get("adjective_type") and not values.get("pronoun_type"):
                unresolved.append(tail[:1])
        tail = tail[1:]
        if function_code == "N" and values.get("proper_name_type"):
            tail = tail[1:]
        if function_code == "P" and tail[:1] in PERSON:
            _decode_person_gender_number(tail, values, unresolved)
        else:
            _decode_gender_number_state(tail, values, unresolved)
    elif function_code == "S":
        values["suffix_type"] = SUFFIX_TYPES.get(tail[:1], "")
        _decode_person_gender_number(tail[1:], values, unresolved, prefix="suffix_")
    elif function_code == "T":
        if tail[:1] in PARTICLE_FORMS:
            values["part_of_speech"] = PARTICLE_FORMS[tail[:1]]
            values["particle_type"] = PARTICLE_FORMS[tail[:1]]
            tail = tail[1:]
        if tail:
            unresolved.append(tail)
    elif function_code == "R":
        # TEHMC-confirmed (HRd/ARd -> Form=Definite): the only preposition
        # tail is "d" (12,176 tokens), the same definite-article marker used
        # by the particle code "Td" (23,947 tokens) — i.e. a fused
        # preposition + article such as לַ / בַּ. Anything else is not
        # silently accepted. Phase 2A used the ad hoc label "With article";
        # renamed to TEHMC's own term "Definite" in Phase 2B.
        if not tail:
            values["preposition_type"] = ""
        elif tail == "d":
            values["preposition_type"] = "Definite"
        else:
            unresolved.append(tail)
    elif function_code in {"C", "c"}:
        # Conjunction codes carry no tail anywhere in the corpus (C 30518,
        # c 21324, both always bare). Do not swallow an unknown remainder.
        if tail:
            unresolved.append(tail)
        values["conjunction_type"] = ""
    elif tail and expansion:
        pass
    elif tail:
        unresolved.append(tail)
    values["unresolved_parts"] = tuple(unresolved)
    values["status"] = _status(code, expansion, unresolved, values)
    return HebrewMorphology(**values)  # type: ignore[arg-type]


def _split_morphology_components(code: str) -> list[tuple[str, str]]:
    raw_parts = [part for part in code.split("/") if part]
    parts: list[tuple[str, str]] = []
    current_language = ""
    for part in raw_parts:
        if current_language and part[:1] == "A" and part[1:2] in {"a", "c", "o"} and part[2:3] in GENDER:
            normalized = current_language + part
        elif part[:1] in LANGUAGE or part.startswith("S"):
            normalized = part
        elif current_language:
            normalized = current_language + part
        else:
            normalized = part
        if normalized[:1] == "A" and normalized[1:2] in {"a", "c", "o"} and normalized[2:3] in GENDER:
            normalized = "A" + normalized
        elif normalized[:1] == "A" and normalized[1:2] not in FUNCTION:
            normalized = "A" + normalized
        if normalized[:1] in LANGUAGE:
            current_language = normalized[:1]
        parts.append((part, normalized))
    return parts


def _component_type(code: str, index: int, total: int) -> str:
    function_code = code[1:2] if code[:1] in LANGUAGE else code[:1]
    if function_code in {"C", "c", "R", "T", "D", "d", "o", "n", "m", "r"} and index < total - 1:
        return "prefix"
    if function_code == "S" or code.startswith("S"):
        return "suffix"
    return "core"


def _primary_component(decoded: list[HebrewMorphology]) -> HebrewMorphology:
    for morph in decoded:
        if morph.part_of_speech == "Verb":
            return morph
    for morph in decoded:
        if morph.component_type == "core":
            return morph
    return decoded[0]


def _component_payload(morph: HebrewMorphology) -> dict[str, object]:
    return {
        "code": morph.code,
        "original_code": morph.original_code or morph.code,
        "language": morph.language,
        "component_type": morph.component_type,
        "part_of_speech": morph.part_of_speech,
        "noun_type": morph.noun_type,
        "adjective_type": morph.adjective_type,
        "pronoun_type": morph.pronoun_type,
        "proper_name_type": morph.proper_name_type,
        "particle_type": morph.particle_type,
        "preposition_type": morph.preposition_type,
        "conjunction_type": morph.conjunction_type,
        "verb_stem": morph.verb_stem,
        "verb_conjugation": morph.verb_conjugation,
        "person": morph.person,
        "gender": morph.gender,
        "number": morph.number,
        "state": morph.state,
        "suffix_type": morph.suffix_type,
        "suffix_person": morph.suffix_person,
        "suffix_gender": morph.suffix_gender,
        "suffix_number": morph.suffix_number,
        "english_expansion": morph.english_expansion,
        "unresolved_parts": morph.unresolved_parts,
        "status": morph.status,
    }


def _status(
    code: str,
    expansion: str,
    unresolved: list[str],
    values: dict[str, str | tuple[str, ...]],
) -> str:
    if not code or any(item.startswith("missing-") for item in unresolved):
        return "malformed"
    if unresolved:
        return "partially_decoded" if _has_decoded_morphology(values) else "unresolved"
    # Full confidence requires that the VERIFIED deterministic tables actually
    # produced grammatical content. It is deliberately NOT granted merely
    # because the code starts with a known language letter or because a TEHMC
    # expansion string happens to exist: a code the decoder does not really
    # understand must never present itself as fully resolved (Phase 2A).
    return "fully_decoded" if _has_decoded_morphology(values) else "unresolved"


def _has_decoded_morphology(values: dict[str, str | tuple[str, ...]]) -> bool:
    for field in (
        "part_of_speech",
        "noun_type",
        "adjective_type",
        "pronoun_type",
        "proper_name_type",
        "particle_type",
        "preposition_type",
        "conjunction_type",
        "verb_stem",
        "verb_conjugation",
        "person",
        "gender",
        "number",
        "state",
        "suffix_type",
        "suffix_person",
        "suffix_gender",
        "suffix_number",
    ):
        if values.get(field):
            return True
    return False


def _combined_status(decoded: list[HebrewMorphology], unresolved: tuple[str, ...]) -> str:
    if any(item.status == "malformed" for item in decoded):
        return "malformed"
    if unresolved:
        return (
            "partially_decoded"
            if any(item.status in {"fully_decoded", "partially_decoded"} for item in decoded)
            else "unresolved"
        )
    if all(item.status == "fully_decoded" for item in decoded):
        return "fully_decoded"
    return "partially_decoded"


def _group_unresolved_patterns(
    counts: Counter[str],
    decoded: dict[str, HebrewMorphology],
) -> list[dict[str, object]]:
    grouped: dict[str, dict[str, object]] = {}
    for code, morph in decoded.items():
        if morph.status not in {"unresolved", "malformed"}:
            continue
        pattern = _pattern_for_code(code)
        group = grouped.setdefault(
            pattern,
            {
                "pattern": pattern,
                "unique_code_count": 0,
                "affected_tokens": 0,
                "examples": [],
                "needed_parser_fix": _parser_fix_for_pattern(pattern),
                "documentation_reference": "TEHMC full morphology code table",
            },
        )
        group["unique_code_count"] = int(group["unique_code_count"]) + 1
        group["affected_tokens"] = int(group["affected_tokens"]) + counts[code]
        examples = group["examples"]
        if isinstance(examples, list) and len(examples) < 10:
            examples.append({"code": code, "token_count": counts[code], "unresolved_parts": morph.unresolved_parts})
    return sorted(grouped.values(), key=lambda item: (-int(item["affected_tokens"]), str(item["pattern"])))


def _pattern_for_code(code: str) -> str:
    return re.sub(r"\d", "0", re.sub(r"[a-z]", "x", re.sub(r"[A-Z]", "X", code)))


def _parser_fix_for_pattern(pattern: str) -> str:
    if "/" in pattern:
        return "Decode slash-separated component analyses with inherited language code."
    if pattern.startswith("S"):
        return "Decode standalone suffix morphology."
    return "Check TEHMC expansion and structural code consumption."


def _decode_person_gender_number(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
    *,
    prefix: str = "",
) -> None:
    if not tail:
        return
    if tail[:1] in PERSON:
        values[f"{prefix}person"] = PERSON[tail[:1]]
        tail = tail[1:]
    if tail[:1] in GENDER:
        values[f"{prefix}gender"] = GENDER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in NUMBER:
        values[f"{prefix}number"] = NUMBER[tail[:1]]
        tail = tail[1:]
    if tail:
        unresolved.append(tail)


def _decode_verb_ending(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
) -> None:
    conjugation = values.get("verb_conjugation")
    # Infinitives never inflect for person; their tail is a state letter (or
    # empty). A Cohortative reaches this function with a person tail and is
    # therefore handled by the finite path below — see _verb_form_for_code().
    if conjugation in {"Infinitive Construct", "Infinitive Absolute"}:
        if not tail:
            return
        if tail in STATE:
            values["state"] = STATE[tail]
        else:
            unresolved.append(tail)
        return
    if conjugation in NON_FINITE_VERB_FORMS:
        _decode_gender_number_state(tail, values, unresolved)
        return
    _decode_person_gender_number(tail, values, unresolved)


def _decode_gender_number_state(
    tail: str,
    values: dict[str, str | tuple[str, ...]],
    unresolved: list[str],
) -> None:
    if tail[:1] in GENDER:
        values["gender"] = GENDER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in NUMBER:
        values["number"] = NUMBER[tail[:1]]
        tail = tail[1:]
    if tail[:1] in STATE:
        values["state"] = STATE[tail[:1]]
        tail = tail[1:]
    if tail:
        unresolved.append(tail)
