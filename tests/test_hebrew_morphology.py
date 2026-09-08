from __future__ import annotations

from bible_engine.hebrew_morphology import decode_hebrew_morphology


def test_decodes_qal_perfect_and_wayyiqtol() -> None:
    perfect = decode_hebrew_morphology("HVqp3ms", {"HVqp3ms": "Function=Verb ; Stem=Qal"})
    wayyiqtol = decode_hebrew_morphology("HVqw3ms", {"HVqw3ms": "Function=Verb ; Stem=Qal"})

    assert perfect.language == "Hebrew"
    assert perfect.part_of_speech == "Verb"
    assert perfect.verb_stem == "Qal"
    assert perfect.verb_conjugation == "Perfect"
    assert perfect.person == "Third"
    assert perfect.gender == "Masculine"
    assert perfect.number == "Singular"
    assert perfect.status == "fully_decoded"
    assert wayyiqtol.verb_conjugation == "Consecutive Imperfect"


def test_decodes_common_stems_and_nonverbs() -> None:
    assert decode_hebrew_morphology("HVNp3ms").verb_stem == "Niphal"
    assert decode_hebrew_morphology("HVpp3ms").verb_stem == "Piel"
    assert decode_hebrew_morphology("HVPp3ms").verb_stem == "Pual"
    assert decode_hebrew_morphology("HVhp3ms").verb_stem == "Hiphil"
    assert decode_hebrew_morphology("HVHp3ms").verb_stem == "Hophal"
    assert decode_hebrew_morphology("HVtp3ms").verb_stem == "Hithpael"
    assert decode_hebrew_morphology("HVcp1cs").verb_stem == "Tiphil"
    # Phase 2B: the authoritative STEPBible TEHMC source is now vendored
    # (data/stepbible_sources/TEHMC.txt) and resolves every stem code Phase 2A
    # left unnamed. Stem letters are LANGUAGE-DEPENDENT — TEHMC assigns a
    # different binyan name to the same letter in Hebrew vs. Aramaic (e.g.
    # Hebrew "u" = Hothpaal, Aramaic "u" = Hitpael) — so "HVDq3cp" (Hebrew "D")
    # and "AVMi3fs" (Aramaic "M") resolve to different-language stem tables.
    # See STEMS_BY_LANGUAGE and docs/hebrew_analysis_v2_phase2b.md.
    assert decode_hebrew_morphology("HVDq3cp").verb_stem == "Nithpael"
    assert decode_hebrew_morphology("AVMi3fs").verb_stem == "Hitpaal"
    aramaic_u = decode_hebrew_morphology("AVui2mp")
    assert aramaic_u.verb_stem == "Hitpael"
    hebrew_u = decode_hebrew_morphology("HVucc")
    assert hebrew_u.verb_stem == "Hothpaal"
    noun = decode_hebrew_morphology("HNcmsc")
    assert noun.part_of_speech == "Noun"
    assert noun.noun_type == "Common"
    assert noun.state == "Construct"
    assert noun.status == "fully_decoded"


def test_decodes_suffix_and_aramaic_without_inventing_unknowns() -> None:
    suffix = decode_hebrew_morphology("Sp3ms")
    directional = decode_hebrew_morphology("Sd")
    emphatic = decode_hebrew_morphology("Sn")
    aramaic = decode_hebrew_morphology("AVqp3ms")
    unknown = decode_hebrew_morphology("HZzzz")
    pronoun = decode_hebrew_morphology("HPp1bs")

    assert suffix.part_of_speech == "Suffix"
    assert suffix.suffix_person == "Third"
    assert suffix.suffix_gender == "Masculine"
    assert suffix.suffix_number == "Singular"
    assert directional.suffix_type == "Directional"
    # Phase 2B: TEHMC (Sn) names this "Paragogic Nun", a specific energic
    # suffix — not a generic "Emphatic" marker as Phase 1/2A guessed.
    assert emphatic.suffix_type == "Paragogic Nun"
    assert pronoun.pronoun_type == "Personal"
    assert pronoun.person == "First"
    assert pronoun.gender == "Either gender"
    assert pronoun.number == "Singular"
    assert pronoun.status == "fully_decoded"
    assert aramaic.language == "Aramaic"
    assert aramaic.status == "fully_decoded"
    assert unknown.unresolved_parts
    assert unknown.status in {"partially_decoded", "unresolved"}


def test_decodes_documented_proper_gentilic_and_particle_types() -> None:
    location = decode_hebrew_morphology("HNpl")
    title = decode_hebrew_morphology("HNtmsa")
    gentilic = decode_hebrew_morphology("HNgmsa")
    interrogative = decode_hebrew_morphology("HTi")
    interjection = decode_hebrew_morphology("ATj")

    assert location.noun_type == "Proper"
    assert location.proper_name_type == "Location"
    assert title.noun_type == "Title"
    assert title.gender == "Masculine"
    assert gentilic.noun_type == "Gentilic"
    assert gentilic.state == "Absolute"
    assert interrogative.part_of_speech == "Interrogative"
    assert interrogative.particle_type == "Interrogative"
    assert interjection.part_of_speech == "Interjection"
    assert interjection.particle_type == "Interjection"
    assert all(item.status == "fully_decoded" for item in (location, title, gentilic, interrogative, interjection))


def test_decodes_slash_components_with_inherited_language() -> None:
    decoded = decode_hebrew_morphology(
        "Hc/Vqw3ms",
        {
            "Hc": "Function=Conjunction; Form=Consecutive",
            "HVqw3ms": "Function=Verb ; Stem=Qal ; Form=Consecutive Imperfect",
        },
    )

    assert decoded.language == "Hebrew"
    assert decoded.part_of_speech == "Conjunction + Verb"
    assert decoded.verb_stem == "Qal"
    assert decoded.verb_conjugation == "Consecutive Imperfect"
    assert decoded.person == "Third"
    assert decoded.gender == "Masculine"
    assert decoded.number == "Singular"
    assert len(decoded.components) == 2
    assert decoded.components[0]["original_code"] == "Hc"
    assert decoded.components[0]["component_type"] == "prefix"
    assert decoded.components[1]["original_code"] == "Vqw3ms"
    assert decoded.components[1]["code"] == "HVqw3ms"
    assert decoded.components[1]["component_type"] == "core"
    assert decoded.components[1]["verb_stem"] == "Qal"
    assert decoded.status == "fully_decoded"
    assert not decoded.unresolved_parts


def test_decodes_multiple_prefixes_and_core_component() -> None:
    decoded = decode_hebrew_morphology("HC/R/Vpcc")

    assert decoded.part_of_speech == "Conjunction + Preposition + Verb"
    assert decoded.components[0]["component_type"] == "prefix"
    assert decoded.components[1]["component_type"] == "prefix"
    assert decoded.components[2]["component_type"] == "core"
    assert decoded.verb_stem == "Piel"
    assert decoded.verb_conjugation == "Infinitive Construct"


def test_decodes_core_with_pronominal_suffix() -> None:
    decoded = decode_hebrew_morphology("HNcmpc/Sp3ms")

    assert decoded.part_of_speech == "Noun + Suffix"
    assert decoded.state == "Construct"
    assert decoded.components[0]["component_type"] == "core"
    assert decoded.components[1]["component_type"] == "suffix"
    assert decoded.components[1]["suffix_person"] == "Third"
    assert decoded.components[1]["suffix_gender"] == "Masculine"
    assert decoded.components[1]["suffix_number"] == "Singular"


def test_decodes_aramaic_slash_components() -> None:
    decoded = decode_hebrew_morphology("AC/Vqp3ms")

    assert decoded.language == "Aramaic"
    assert decoded.part_of_speech == "Conjunction + Verb"
    # Phase 2B: Aramaic "q" is Peal, not Qal — TEHMC-confirmed. The Phase 2A
    # decoder wrongly applied the Hebrew stem name to Aramaic tokens (a
    # language-independent STEMS dict); this was a real defect affecting 939
    # Aramaic tokens across six stem letters (see STEMS_BY_LANGUAGE).
    assert decoded.verb_stem == "Peal"
    assert decoded.person == "Third"
    assert decoded.gender == "Masculine"
    assert decoded.number == "Singular"


def test_aramaic_partial_slash_component_is_partially_decoded() -> None:
    decoded = decode_hebrew_morphology("ANcbsd/Ta")

    assert decoded.language == "Aramaic"
    assert decoded.part_of_speech == "Noun + Article"
    assert decoded.gender == "Either gender"
    assert decoded.number == "Singular"
    assert decoded.state == "Definite"
    assert decoded.status == "fully_decoded"
    assert not decoded.unresolved_parts


def test_partial_code_keeps_decoded_fields() -> None:
    decoded = decode_hebrew_morphology("HVqz3ms", {"HVqz3ms": "Function=Verb ; Stem=Qal"})

    assert decoded.status == "partially_decoded"
    assert decoded.verb_stem == "Qal"
    assert decoded.person == "Third"
    assert decoded.gender == "Masculine"
    assert decoded.number == "Singular"
    assert decoded.unresolved_parts


def test_common_previously_unresolved_patterns_are_consumed() -> None:
    expansions = {
        "HR": "Function=Preposition",
        "HTd": "Function=Particle ; Form=Definite article (Hebrew)",
        "HNcmsa": "Function=Noun ; Form=Common ; Gender=Masculine; Number=Singular; State=Absolute",
        "HNcmsc": "Function=Noun ; Form=Common ; Gender=Masculine; Number=Singular; State=Construct",
        "HVqcc": "Function=Verb ; Stem=Qal ; Form=Infinitive ; State=Construct",
        "HTo": "Function=Particle ; Form=Object marker",
        "HSp3ms": "Function=Suffix ; Person=Third; Gender=Masculine; Number=Singular",
    }

    for code in ["HR/Ncmsc", "HTd/Ncmsa", "HR/Vqcc", "HC/To", "HR/Sp3ms"]:
        decoded = decode_hebrew_morphology(code, expansions)
        assert decoded.status == "fully_decoded"
        assert not decoded.unresolved_parts


def test_empty_morphology_is_malformed() -> None:
    decoded = decode_hebrew_morphology("")

    assert decoded.status == "malformed"
