"""Phase 5A shadow integration tests."""

from __future__ import annotations

from pathlib import Path

import pytest

from textus_kb.shadow import build_shadow_benchmark_report, run_kb_shadow_for_module


def test_shadow_artifact_exegesis() -> None:
    artifact = run_kb_shadow_for_module("Jn 4,1-42", module="exegesis")
    assert artifact.success is True
    assert artifact.status in {"success", "degraded"}
    assert artifact.profile == "exegesis"
    assert artifact.passage_canonical == "John.4.1-42"
    assert artifact.token_estimate > 0
    assert artifact.evidence_item_count > 0
    assert artifact.context_packet.get("profile") == "exegesis"


def test_shadow_artifact_historical() -> None:
    artifact = run_kb_shadow_for_module("Lk 10,25-37", module="historical_context")
    assert artifact.success is True
    assert artifact.status in {"success", "degraded"}
    assert artifact.profile == "historical_context"
    assert artifact.passage_canonical == "Luke.10.25-37"
    assert artifact.context_packet.get("profile") == "historical_context"


def test_shadow_failure_isolated(monkeypatch: pytest.MonkeyPatch) -> None:
    import textus_kb.shadow as shadow

    def _boom(_: str):
        raise RuntimeError("boom")

    monkeypatch.setattr(shadow, "retrieve", _boom)
    artifact = run_kb_shadow_for_module("Jn 4,1-42", module="exegesis")
    assert artifact.success is False
    assert artifact.status == "error"
    assert "RuntimeError" in artifact.error


def test_shadow_benchmark_report_four_passages() -> None:
    report = build_shadow_benchmark_report(
        ["John.4.1-42", "Luke.10.25-37", "Acts.2.1-13", "Rom.8.28-30"],
        modules=["exegesis", "historical_context"],
    )
    assert len(report["artifacts"]) == 8
    assert all("retrieval_duration_ms" in item for item in report["artifacts"])


def test_app_shadow_flag_default_false_and_hooked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A shadow-jelző alapértéke hamis, és a `generate_section` a
    `run_production_with_optional_shadow` útvonalon át dolgozik.

    Viselkedési/strukturális ellenőrzés, nem egy konkrét forrássor
    szó szerinti alakja: az S-01 hibaszűrő (`is_generation_error_text`)
    óta a sikeres kimenet egy feltételes ágban kerül a mezőbe, ezért a
    korábbi `st.session_state[key] = run.production_output` literál
    nem elvárás. A szerződés:
      * a flag env nélkül hamis;
      * a `generate_section` ezt a flaget adja át a shadow-útvonalnak;
      * a `run.production_output` sikeres esetben a mezőbe kerül.
    """
    import ast
    from unittest.mock import MagicMock

    import app as app_mod
    import textus_kb.shadow_integration as shadow_integration
    from textus_kb.shadow_integration import SectionRunResult

    # --- a flag alapértéke és bekötése (forrás- és viselkedési szinten)
    app_src = Path("app.py").read_text(encoding="utf-8")
    assert 'KB_SHADOW_FLAG = "TEXTUS_KB_SHADOW_ENABLED"' in app_src
    assert 'os.getenv(KB_SHADOW_FLAG, "false")' in app_src
    assert "TEXTUS_KB_GROUNDED_STAGE_ALLOWED" not in app_src
    monkeypatch.delenv(app_mod.KB_SHADOW_FLAG, raising=False)
    assert app_mod._is_kb_shadow_enabled() is False

    # --- szerkezet: a generate_section tényleg a shadow-útvonalat hívja,
    # a flaget a `_is_kb_shadow_enabled()`-ből adja át, és olvassa a
    # `run.production_output`-ot.
    tree = ast.parse(app_src)
    func = next(
        n for n in tree.body if isinstance(n, ast.FunctionDef) and n.name == "generate_section"
    )
    shadow_calls = [
        n
        for n in ast.walk(func)
        if isinstance(n, ast.Call)
        and getattr(n.func, "id", None) == "run_production_with_optional_shadow"
    ]
    assert len(shadow_calls) == 1
    shadow_kw = {kw.arg: kw.value for kw in shadow_calls[0].keywords}
    assert isinstance(shadow_kw["shadow_enabled"], ast.Call)
    assert getattr(shadow_kw["shadow_enabled"].func, "id", None) == "_is_kb_shadow_enabled"
    assert any(
        isinstance(n, ast.Attribute)
        and n.attr == "production_output"
        and getattr(n.value, "id", None) == "run"
        for n in ast.walk(func)
    )

    # --- viselkedés: a sikeres `production_output` a mezőbe kerül, és a
    # shadow-útvonal a hamis flaggel fut (hálózat, tudástár nélkül).
    seen: dict = {}

    def fake_run(**kwargs):
        seen.update(kwargs)
        return SectionRunResult(
            production_output="A perikópa központi hangsúlya a kitartás.",
            generation_duration_ms=1,
            shadow_event=None,
        )

    monkeypatch.setattr(shadow_integration, "run_production_with_optional_shadow", fake_run)
    st_mock = MagicMock()
    st_mock.session_state = {"last_igehely": "Júd 17–20", "exegesis": ""}
    monkeypatch.setattr(app_mod, "st", st_mock)
    monkeypatch.setattr(app_mod, "_resolve_api_key", lambda: "fake-key")
    monkeypatch.setattr(app_mod, "_sync_inputs_to_last", lambda: None)
    monkeypatch.setattr(app_mod, "build_alap_from_state", lambda **_k: "ALAP")
    monkeypatch.setattr(app_mod, "_is_kb_grounded_injection_allowed", lambda: False)

    assert app_mod.generate_section("exegesis") is True

    assert seen["shadow_enabled"] is False
    assert seen["key"] == "exegesis"
    assert st_mock.session_state["exegesis"] == "A perikópa központi hangsúlya a kitartás."


def test_shadow_explicit_true_still_produces_artifact() -> None:
    from textus_kb.prompt_composer import DRY_RUN_PRODUCTION_STUB
    from textus_kb.shadow_integration import run_production_with_optional_shadow

    calls: list[dict] = []

    def fake_generate(prompt: str, *, enable_google_search: bool, tab_label: str) -> str:
        calls.append({"prompt": prompt})
        return "OUT"

    def counting_shadow(**kwargs):
        return {"status": "success", "success": True, "module": kwargs.get("module")}

    result = run_production_with_optional_shadow(
        key="exegesis",
        prompt=DRY_RUN_PRODUCTION_STUB,
        tab_label="Exegézis",
        use_search=False,
        passage="Jn 4,1-42",
        shadow_enabled=True,
        grounded_enabled=False,
        generate_text_fn=fake_generate,
        shadow_runner_fn=counting_shadow,
    )
    assert len(calls) == 1
    assert result.shadow_event is not None
    assert result.shadow_event.get("success") is True

