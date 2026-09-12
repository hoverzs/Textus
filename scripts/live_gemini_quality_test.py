"""Production validation §10/§19 — live Gemini 2.5 Flash quality test.

Runs the REAL Supabase-backed GreekAnalysisService (SupabaseGreekAnalysisRepository
against the deployed production project) through the REAL contextual-analysis
prompt/validator, using the REAL configured GEMINI_API_KEY — not a mock, not
a simulated response. Prints each verse's validated GreekContextualAnalysis
plus any warnings the validator raised, for manual quality review.

Usage: python scripts/live_gemini_quality_test.py
"""

from __future__ import annotations

import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import requests  # noqa: E402

from bible_engine.greek_analysis_repository import (  # noqa: E402
    SupabaseGreekAnalysisRepository,
    attach_syntax_via_repository,
)
from bible_engine.greek_analysis_service import get_greek_analysis  # noqa: E402
from bible_engine.greek_construction_detection import attach_detected_patterns  # noqa: E402
from bible_engine.greek_contextual_analysis import (  # noqa: E402
    GREEK_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA,
    build_greek_contextual_analysis_prompt,
)
from bible_engine.greek_contextual_analysis_service import (  # noqa: E402
    request_greek_contextual_analysis,
)

MODEL = "gemini-2.5-flash"
TIMEOUT_S = 40.0

TEST_CASES = [
    ("Jn 3,16", "Jhn.3.16", "ἵνα clause + aorist; PARTIALLY_GROUNDED_SYNTAX"),
    ("Jn 1,1", "Jhn.1.1", "imperfect (ἦν) + anarthrous predicate nominative"),
    ("Jn 19,30", "Jhn.19.30", "perfect (τετέλεσται)"),
    ("1Tim 3,1", "1Ti.3.1", "middle voice, non-reflexive risk case"),
    ("Mt 28,19-20", "Mat.28.19", "chained participles + finite imperative"),
    ("Mt 9,18", "Mat.9.18", "genitive absolute"),
    ("Mk 9,44", "Mrk.9.44", "NO_GROUNDED_SYNTAX (SBLGNT omits this verse)"),
]


def _load_api_key() -> str:
    import app  # Streamlit-coupled but importable bare; only used for its key loader

    return app._load_builtin_api_key().strip()


def generate_via_rest(prompt: str, api_key: str) -> str:
    import app

    final_prompt = "\n\n".join([
        app.BASE_SYSTEM_PROMPT.strip(),
        "==================================================\nFELADAT\n==================================================\n\n" + prompt,
    ])
    payload = {
        "contents": [{"parts": [{"text": final_prompt}]}],
        "generationConfig": {
            "temperature": 0.3,
            "responseMimeType": "application/json",
            "responseSchema": GREEK_CONTEXTUAL_ANALYSIS_RESPONSE_SCHEMA,
        },
    }
    url = f"https://generativelanguage.googleapis.com/v1beta/models/{MODEL}:generateContent"
    headers = {"Content-Type": "application/json", "x-goog-api-key": api_key}
    response = requests.post(url, headers=headers, json=payload, timeout=TIMEOUT_S)
    response.raise_for_status()
    data = response.json()
    parts = data["candidates"][0]["content"]["parts"]
    return "".join(p.get("text", "") for p in parts)


def main() -> int:
    api_key = _load_api_key()
    if not api_key:
        print("No GEMINI_API_KEY available — cannot run the live quality test.")
        return 1

    repo = SupabaseGreekAnalysisRepository()

    for reference, verse_id, phenomenon in TEST_CASES:
        print("=" * 100)
        print(f"{reference}  ({verse_id})  —  {phenomenon}")
        print("=" * 100)

        bundle = get_greek_analysis(reference)
        bundle = attach_syntax_via_repository(bundle, repo)
        bundle = attach_detected_patterns(bundle)
        verse = next((v for v in bundle.verses if v.verse_id == verse_id), None)
        if verse is None:
            print("  VERSE NOT FOUND IN BUNDLE — skipping")
            continue

        print(f"  grounding_status: {verse.syntax_grounding}")
        print(f"  Greek: {verse.greek_text}")

        t0 = time.time()
        result = request_greek_contextual_analysis(
            verse, generate_fn=lambda p, **kw: generate_via_rest(p, api_key)
        )
        elapsed = time.time() - t0
        print(f"  status: {result.status}  ({elapsed:.1f}s)")

        if result.status != "ok":
            print(f"  UNAVAILABLE/INVALID — warnings: {result.warnings}")
            continue

        analysis = result.analysis
        print(f"  validator warnings ({len(result.warnings)}): {list(result.warnings)}")
        print(f"  word_notes ({len(analysis.word_notes)}):")
        for note in analysis.word_notes:
            print(f"    [{note.token_id}] lex={note.lexical_basic_meaning_hu!r} ({note.lexical_provenance})")
            print(f"        contextual={note.contextual_meaning_hu!r}")
            print(f"        morph_expl={note.morphological_explanation_hu!r}")
            print(f"        syntax_role={note.syntax_role_hu!r}  confidence={note.confidence}")
        print(f"  construction_notes ({len(analysis.construction_notes)}):")
        for c in analysis.construction_notes:
            print(f"    [{c.construction_type}] {c.title_hu!r} evidence={c.evidence_ids} tokens={c.token_ids}")
            print(f"        {c.explanation_hu!r}")
        print(f"  syntax_summary: {analysis.syntax_summary.summary_hu!r}")
        print(f"  translation_notes: {list(analysis.translation_notes)}")
        print(f"  exegetical_notes: {list(analysis.exegetical_notes)}")
        print(f"  model warnings: {list(analysis.warnings)}")
        print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
