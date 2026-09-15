"""Targeted tests for scripts/publish_claude_enrichment_batch.py -- the
small, self-scoping publish helper for the Claude-manual-enrichment
batch (a distinct policy from apply_automated_corpus_approval_v1,
since that RPC hard-requires qa_status='passed', which this batch
deliberately never has). Fake Supabase client, no network access, no
LLM call anywhere."""

from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

import publish_claude_enrichment_batch as publisher  # noqa: E402


# ---------------------------------------------------------------------------
# Fake Supabase client -- adds .update().eq().execute() on top of the same
# select/insert shape used in test_import_claude_enrichment_batch.py.
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, data: list[dict]) -> None:
        self.data = data


class _FakeTable:
    def __init__(self, client: "_FakeSupabaseClient", name: str) -> None:
        self._client = client
        self._name = name
        self._filters: dict[str, object] = {}
        self._limit: int | None = None
        self._range: tuple[int, int] | None = None
        self._pending_update: dict | None = None

    def select(self, _cols: str) -> "_FakeTable":
        return self

    def eq(self, col: str, val: object) -> "_FakeTable":
        self._filters[col] = val
        return self

    def limit(self, n: int) -> "_FakeTable":
        self._limit = n
        return self

    def range(self, start: int, end: int) -> "_FakeTable":
        self._range = (start, end)
        return self

    def update(self, fields: dict) -> "_FakeTable":
        self._client.mutations.append(("update", self._name, fields))
        self._pending_update = fields
        return self

    def execute(self) -> _FakeResponse:
        rows = self._client.data.get(self._name, [])
        matched = [r for r in rows if all(r.get(k) == v for k, v in self._filters.items())]

        if self._pending_update is not None:
            for row in matched:
                row.update(self._pending_update)
            return _FakeResponse(matched)

        if self._limit is not None:
            matched = matched[: self._limit]
        if self._range is not None:
            start, end = self._range
            matched = matched[start : end + 1]
        return _FakeResponse(matched)


class _FakeSupabaseClient:
    def __init__(self, initial_data: dict[str, list[dict]] | None = None) -> None:
        self.data: dict[str, list[dict]] = {k: list(v) for k, v in (initial_data or {}).items()}
        self.mutations: list[tuple] = []

    def table(self, name: str) -> _FakeTable:
        return _FakeTable(self, name)


BATCH_MODEL = "claude-manual-enrichment-2026-09-13"


def _unit(
    id_: int, *, story_id: int = 1, status: str = "needs_review", approval_method: object = None,
    human_reviewed_at: object = None, enrichment_model: str = BATCH_MODEL,
    title_hu: str = "Cím", modern_hu_text: str = "Szöveg", summary_hu: str = "Összegzés",
) -> dict:
    return {
        "id": id_, "story_id": story_id, "status": status, "approval_method": approval_method,
        "human_reviewed_at": human_reviewed_at, "title_hu": title_hu, "modern_hu_text": modern_hu_text,
        "summary_hu": summary_hu, "enrichment_model": enrichment_model,
    }


def _client_with(units: list[dict], *, publishable_license: bool = True, has_tags: bool = True) -> _FakeSupabaseClient:
    data = {
        "illustration_units": units,
        "illustration_stories": [{"id": 1, "source_id": 1}],
        "illustration_sources": [{"id": 1, "license_status": "public_domain_confirmed" if publishable_license else "restricted"}],
        "illustration_unit_tags": [{"unit_id": u["id"], "tag_id": 1} for u in units] if has_tags else [],
    }
    return _FakeSupabaseClient(data)


# ---------------------------------------------------------------------------
# Core eligibility + publish behavior
# ---------------------------------------------------------------------------


def test_eligible_batch_unit_is_published_with_correct_provenance() -> None:
    client = _client_with([_unit(1)])

    counts = publisher.run_publish(client, apply=True)

    assert counts == {"candidates": 1, "eligible": 1, "skipped": 0, "published": 1}
    row = client.data["illustration_units"][0]
    assert row["status"] == "published"
    assert row["approval_method"] == "automated_corpus_approval"
    assert row["auto_approval_rule_version"] == "claude_enrichment_batch_v1"
    assert row["auto_approved_at"] is not None
    assert row["human_reviewed_at"] is None  # never touched


def test_custom_rule_version_is_recorded_and_scoping_unaffected() -> None:
    """--rule-version (round 2, batch v2) must only change what gets
    recorded, never which rows are eligible -- still scoped by
    enrichment_model prefix regardless of which string is passed."""
    client = _client_with([_unit(1)])

    counts = publisher.run_publish(client, apply=True, rule_version="claude_enrichment_batch_v2")

    assert counts == {"candidates": 1, "eligible": 1, "skipped": 0, "published": 1}
    row = client.data["illustration_units"][0]
    assert row["auto_approval_rule_version"] == "claude_enrichment_batch_v2"
    assert row["status"] == "published"


def test_two_batches_with_different_rule_versions_coexist_idempotently() -> None:
    """A round-2 run must never re-touch round-1's already-approved
    units, even though both share the same enrichment_model prefix."""
    round1_unit = _unit(1, approval_method="automated_corpus_approval")
    round2_unit = _unit(2)
    client = _client_with([round1_unit, round2_unit])

    counts = publisher.run_publish(client, apply=True, rule_version="claude_enrichment_batch_v2")

    assert counts == {"candidates": 2, "eligible": 1, "skipped": 1, "published": 1}
    rows = {r["id"]: r for r in client.data["illustration_units"]}
    assert rows[1].get("auto_approval_rule_version") is None  # untouched -- was already approved
    assert rows[2]["auto_approval_rule_version"] == "claude_enrichment_batch_v2"


def test_dry_run_reports_would_publish_and_never_writes() -> None:
    client = _client_with([_unit(1)])

    counts = publisher.run_publish(client, apply=False)

    assert counts == {"candidates": 1, "eligible": 1, "skipped": 0, "published": 0}
    assert client.mutations == []
    assert client.data["illustration_units"][0]["status"] == "needs_review"


def test_unit_not_from_claude_batch_is_never_a_candidate() -> None:
    """The whole point of the enrichment_model prefix scoping: a unit
    from some other pipeline (or none) must never be touched by this
    policy, even if it happens to be needs_review and otherwise
    eligible-looking."""
    client = _client_with([_unit(1, enrichment_model="gemini-2.5-flash-lite")])

    counts = publisher.run_publish(client, apply=True)

    assert counts["candidates"] == 0
    assert client.data["illustration_units"][0]["status"] == "needs_review"


def test_unit_missing_tags_is_skipped() -> None:
    client = _client_with([_unit(1)], has_tags=False)

    counts = publisher.run_publish(client, apply=True)

    assert counts == {"candidates": 1, "eligible": 0, "skipped": 1, "published": 0}
    assert client.data["illustration_units"][0]["status"] == "needs_review"


def test_unit_with_non_publishable_license_is_skipped() -> None:
    client = _client_with([_unit(1)], publishable_license=False)

    counts = publisher.run_publish(client, apply=True)

    assert counts == {"candidates": 1, "eligible": 0, "skipped": 1, "published": 0}


def test_unit_already_approved_is_skipped_not_reapproved() -> None:
    client = _client_with([_unit(1, approval_method="human_review")])

    counts = publisher.run_publish(client, apply=True)

    assert counts == {"candidates": 1, "eligible": 0, "skipped": 1, "published": 0}
    assert client.mutations == []


def test_unit_with_human_reviewed_at_set_is_never_touched() -> None:
    client = _client_with([_unit(1, human_reviewed_at="2026-01-01T00:00:00+00:00")])

    counts = publisher.run_publish(client, apply=True)

    assert counts["skipped"] == 1
    row = client.data["illustration_units"][0]
    assert row["human_reviewed_at"] == "2026-01-01T00:00:00+00:00"  # unchanged
    assert row["status"] == "needs_review"


def test_incomplete_content_is_skipped() -> None:
    client = _client_with([_unit(1, modern_hu_text="")])

    counts = publisher.run_publish(client, apply=True)

    assert counts == {"candidates": 1, "eligible": 0, "skipped": 1, "published": 0}


def test_running_publish_twice_is_idempotent() -> None:
    client = _client_with([_unit(1)])

    first = publisher.run_publish(client, apply=True)
    second = publisher.run_publish(client, apply=True)

    assert first["published"] == 1
    assert second["published"] == 0
    assert second["skipped"] == 1  # already approved this time
    assert len([m for m in client.mutations if m[0] == "update"]) == 1


def test_mixed_batch_only_publishes_eligible_units() -> None:
    units = [
        _unit(1, story_id=1),
        _unit(2, story_id=1, human_reviewed_at="2026-01-01T00:00:00+00:00"),
        _unit(3, story_id=1, enrichment_model="something-else"),
    ]
    client = _client_with(units)

    counts = publisher.run_publish(client, apply=True)

    assert counts["candidates"] == 2  # unit 3 never counted (wrong enrichment_model)
    assert counts["published"] == 1
    assert counts["skipped"] == 1
    published_ids = [u["id"] for u in client.data["illustration_units"] if u["status"] == "published"]
    assert published_ids == [1]


# ---------------------------------------------------------------------------
# Gemini/API guard
# ---------------------------------------------------------------------------


def test_publisher_source_never_references_gemini_or_other_llm_apis() -> None:
    source = (REPO_ROOT / "scripts" / "publish_claude_enrichment_batch.py").read_text(encoding="utf-8")
    forbidden = (
        "generativelanguage.googleapis", "GEMINI_API_KEY", "genai",
        "anthropic.Anthropic", "llm_generate", "openai",
    )
    for token in forbidden:
        assert token not in source, f"publish helper must never reference {token!r}"
