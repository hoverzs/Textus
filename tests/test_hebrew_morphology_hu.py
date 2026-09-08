from __future__ import annotations

from bible_engine.hebrew_morphology import HebrewMorphology, decode_hebrew_morphology
from bible_engine.hebrew_morphology_hu import (
    classify_hebrew_morphology_hu,
    format_hebrew_component_hu,
    format_hebrew_morphology_hu,
    format_pronominal_suffix_hu,
    untranslated_terms,
)


def _hu(code: str) -> str:
    return format_hebrew_morphology_hu(decode_hebrew_morphology(code), include_language=True)


def assert_no_technical_english(text: str) -> None:
    assert untranslated_terms(text) == ()


def test_formats_prefix_plus_wayyiqtol_in_hungarian() -> None:
    text = _hu("Hc/Vqw3ms")

    assert text == "héber; kötőszó + ige; qal törzs, wayyiqtol, harmadik személy, hímnem, egyes szám"
    assert_no_technical_english(text)


def test_formats_multiple_prefixes_and_core() -> None:
    text = _hu("HC/R/Vpcc")

    assert text == "héber; kötőszó + elöljárószó + ige; piel törzs, infinitivus constructus, constructus"
    assert_no_technical_english(text)


def test_formats_core_with_pronominal_suffix() -> None:
    text = _hu("HNcmpc/Sp3ms")

    assert "főnév + suffixum" in text
    assert "hímnem, többes szám, constructus" in text
    assert "egyes szám harmadik személy hímnem birtokos suffixummal" in text
    assert_no_technical_english(text)


def test_formats_construct_noun() -> None:
    text = _hu("HNcmsc")

    assert text == "héber; főnév, köznév, hímnem, egyes szám, constructus"
    assert_no_technical_english(text)


def test_formats_personal_pronoun_person_gender_number() -> None:
    text = _hu("HPp1bs")

    assert text == "héber; névmás, személyes névmás, első személy, mindkét nem, egyes szám"
    assert_no_technical_english(text)


def test_formats_participle_and_passive_participle() -> None:
    active = _hu("HVqrmsc/Sp1bs")
    passive = _hu("HVqsmsa")

    assert "qal törzs, participium, hímnem, egyes szám, constructus" in active
    assert "egyes szám első személy birtokos suffixummal" in active
    assert passive == "héber; ige, qal törzs, passzív participium, hímnem, egyes szám, absolutus"
    assert_no_technical_english(active)
    assert_no_technical_english(passive)


def test_formats_common_verbal_stems_and_forms() -> None:
    expectations = {
        "HVqp3ms": "qal törzs, perfectum",
        "HVqi3ms": "qal törzs, imperfectum",
        # Phase 2A: "HVqv3ms" -> "weqatal" and "HVqm2ms" -> "imperativus" used
        # to be asserted here. Neither code can occur: "v" is the imperative and
        # is ALWAYS second person (4305/4305 tokens), while "m" appears zero
        # times in the corpus. The codes below are real TAHOT codes.
        "HVqq3ms": "qal törzs, weqatal",
        "HVqv2ms": "qal törzs, imperativus",
        "HVqc1cs": "qal törzs, cohortativus",
        "HVqcc": "qal törzs, infinitivus constructus, constructus",
        "HVqaa": "qal törzs, infinitivus absolutus, absolutus",
        "HVNp3ms": "nifal törzs, perfectum",
        "HVpp3ms": "piel törzs, perfectum",
        "HVPp3ms": "pual törzs, perfectum",
        "HVhp3ms": "hifil törzs, perfectum",
        "HVHp3ms": "hofal törzs, perfectum",
        "HVtp3ms": "hitpael törzs, perfectum",
    }

    for code, expected in expectations.items():
        text = _hu(code)
        assert expected in text
        assert_no_technical_english(text)


def test_formats_cohortative_and_jussive_if_decoder_supplies_them() -> None:
    cohortative = HebrewMorphology(
        code="synthetic",
        part_of_speech="Verb",
        verb_conjugation="Cohortative",
        status="fully_decoded",
    )
    jussive = HebrewMorphology(
        code="synthetic",
        part_of_speech="Verb",
        verb_conjugation="Jussive",
        status="fully_decoded",
    )

    assert format_hebrew_morphology_hu(cohortative) == "ige, cohortativus"
    assert format_hebrew_morphology_hu(jussive) == "ige, jussivus"


def test_formats_aramaic_slash_component() -> None:
    text = _hu("ANcbsd/Ta")

    assert text == "arámi; főnév + névelő; mindkét nem, egyes szám, határozott"
    assert_no_technical_english(text)


def test_partial_code_keeps_hungarian_fields_without_raw_unresolved_value() -> None:
    text = _hu("HVqz3ms")

    assert "qal törzs" in text
    assert "harmadik személy" in text
    assert "részben feloldott morfológia" in text
    assert "; z" not in text
    assert classify_hebrew_morphology_hu(decode_hebrew_morphology("HVqz3ms")) == "partial"
    assert_no_technical_english(text)


def test_component_formatter_and_suffix_formatter_are_hungarian() -> None:
    decoded = decode_hebrew_morphology("HVhi3ms/Sp1bs")
    component_texts = [format_hebrew_component_hu(component) for component in decoded.components]

    assert component_texts[0] == "ige, hifil törzs, imperfectum, harmadik személy, hímnem, egyes szám"
    assert component_texts[1] == "suffixum; egyes szám első személy birtokos suffixummal"
    assert format_pronominal_suffix_hu(decoded) == "egyes szám első személy birtokos suffixummal"
    for text in component_texts:
        assert_no_technical_english(text)


def test_common_former_partial_patterns_are_fully_hungarian() -> None:
    codes = [
        "HNpl",
        "HNpt",
        "HR/Npl",
        "Hc/Vqq3ms",
        "HTj",
        "HPp1bs",
        "HPp3ms",
        "Hc/Vqq3cp",
        "HR/Npt",
        "HTd/Ngmsa",
        "Hc/Vqq2ms",
        "HTd/Npl",
        "HTd/Aamsa",
        "HPp2ms",
        "HC/Npl",
        "Hc/Vqq1cs",
        "HTd/Aomsa",
        "HC/Tj",
        "HPp3mp",
        "Hc/Vqq2mp",
        "AVui2mp",
        "AC/Vhu2ms",
        "ANgmpa",
        "AAabsd/Ta",
        "AC/Tj",
        "Hc/VDq3cp",
        "ATi/Tn",
        "HTi/Pp1bs",
        "HNpl/Sd",
        "AVMi3fs",
        "AVQp3ms",
        "HVci2ms",
    ]

    # Phase 2B: the authoritative STEPBible TEHMC source is now vendored and
    # resolves every stem code Phase 2A left unnamed (D/u/M/Q included — see
    # STEMS_BY_LANGUAGE in bible_engine/hebrew_morphology.py). All codes below
    # must therefore now be fully_decoded, with leak-free Hungarian rendering.
    for code in codes:
        decoded = decode_hebrew_morphology(code)
        text = format_hebrew_morphology_hu(decoded, include_language=True)
        assert decoded.status == "fully_decoded", code
        assert classify_hebrew_morphology_hu(decoded) == "complete", code
        assert "részben feloldott" not in text
        assert_no_technical_english(text)
