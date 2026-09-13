"""Phase 1 skeleton — Supabase-backed illustration review WRITE
repository.

NOT wired into `illustration_review_ui.py` yet (deliberate — the current
SQLite-backed review UI keeps working unchanged until this repository
has been exercised against a real Supabase project and the DDL migration
has actually been applied; see the Phase 1 report). Same public method
shape as `illustration_engine.illustration_unit_repository`'s
`approve_unit`/`publish_unit`/`send_back_for_rework`/`replace_review_
tags`, so swapping the review UI's import later is a drop-in change, not
a rewrite.

Every write here goes through a client obtained from
`illustration_engine.supabase_review_client.get_illustration_review_
client` — SERVER-TRUST model, not RLS user-auth; see that module's
docstring and the DDL migration's header note for the full rationale.
This repository itself performs NO authorization check of its own — by
the time it is constructed, `get_illustration_review_client()` has
already refused to hand out a client unless `is_authorized_reviewer()`
passed. Constructing this repository with an unauthorized/absent client
is a programming error, not a security boundary this class re-enforces.

`reviewer_email` is accepted as an explicit parameter on `approve_unit`
because it MUST come from the caller's already-authenticated Streamlit
Google session (`st.user`/`st.experimental_user`), never from a request
or form field this repository could be tricked into trusting — this
repository has no session of its own to read from, by design (it must
stay independently testable with a fake client, with no Streamlit
dependency)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from illustration_engine.illustration_sqlite import (
    PILOT_HOMILETIC_FUNCTIONS,
    PILOT_TONES,
    PILOT_TOPICS,
)

_UNITS_TABLE = "illustration_units"
_UNIT_TAGS_TABLE = "illustration_unit_tags"
_TAGS_TABLE = "illustration_tags"


class IllustrationUnitReviewProtectionError(ValueError):
    """Mirrors `illustration_engine.illustration_sqlite.
    IllustrationUnitReviewProtectionError` — raised when this repository's
    own pre-check refuses to overwrite already-reviewed content/tags. The
    Postgres trigger (`illustration_unit_tags_protect_reviewed` /
    `illustration_units_protect_reviewed_content`, see the DDL migration)
    is the actual fail-closed guarantee; this exception exists for the
    same reason the SQLite-side Python check does -- a clearer message,
    raised before a network round trip, not the sole guarantee."""


class IllustrationUnitNotFoundError(ValueError):
    pass


class IllustrationUnitNotEligibleError(ValueError):
    """Raised when a lifecycle transition's precondition (e.g. `status
    must be 'needs_review'` for approve) is not met -- mirrors the
    `validate_approve_ready`/`validate_publish_ready` pre-check pattern
    from the SQLite repository, just surfaced as a specific exception
    instead of a `(bool, list[str])` tuple, since this repository has no
    Streamlit form to render a reasons list into yet."""


@dataclass(frozen=True)
class SupabaseIllustrationReviewRepository:
    """`client`: a `service_role`-keyed `supabase.Client`, ALWAYS obtained
    from `supabase_review_client.get_illustration_review_client()` in
    real usage -- a fake/mock client is injected directly in tests."""

    client: object

    def _fetch_unit(self, unit_id: int) -> dict | None:
        result = self.client.table(_UNITS_TABLE).select("*").eq("id", unit_id).execute()
        rows = result.data or []
        return rows[0] if rows else None

    def approve_unit(self, unit_id: int, *, reviewer_email: str) -> None:
        if not (reviewer_email or "").strip():
            raise ValueError(
                "reviewer_email must be a non-empty string from the authenticated Streamlit "
                "session -- never omitted, never sourced from a request/form parameter."
            )
        unit = self._fetch_unit(unit_id)
        if unit is None:
            raise IllustrationUnitNotFoundError(f"illustration unit not found: id={unit_id}")

        missing = [
            name
            for name in ("title_hu", "modern_hu_text", "summary_hu")
            if not unit.get(name)
        ]
        if missing:
            raise IllustrationUnitNotEligibleError(
                f"cannot approve illustration unit id={unit_id}: missing {missing}"
            )

        result = (
            self.client.table(_UNITS_TABLE)
            .update(
                {
                    "status": "approved",
                    "human_reviewed_at": datetime.now(UTC).isoformat(),
                    "reviewed_by_email": reviewer_email.strip(),
                }
            )
            .eq("id", unit_id)
            .eq("status", "needs_review")
            .execute()
        )
        if not result.data:
            raise IllustrationUnitNotEligibleError(
                f"illustration unit id={unit_id} was not approved -- not found, or not "
                "currently needs_review (approve is only valid from needs_review)."
            )

    def publish_unit(self, unit_id: int) -> None:
        result = (
            self.client.table(_UNITS_TABLE)
            .update({"status": "published"})
            .eq("id", unit_id)
            .eq("status", "approved")
            .execute()
        )
        if not result.data:
            raise IllustrationUnitNotEligibleError(
                f"illustration unit id={unit_id} was not published -- not found, or not "
                "currently approved (publish is only valid from approved)."
            )

    def send_back_for_rework(self, unit_id: int) -> None:
        result = (
            self.client.table(_UNITS_TABLE)
            .update(
                {
                    "status": "needs_review",
                    "human_reviewed_at": None,
                    "reviewed_by": None,
                    "reviewed_by_email": None,
                }
            )
            .eq("id", unit_id)
            .execute()
        )
        if not result.data:
            raise IllustrationUnitNotFoundError(f"illustration unit not found: id={unit_id}")

    def _get_or_create_tag(self, *, category: str, slug: str) -> int:
        existing = (
            self.client.table(_TAGS_TABLE)
            .select("id")
            .eq("category", category)
            .eq("slug", slug)
            .execute()
        )
        rows = existing.data or []
        if rows:
            return rows[0]["id"]
        created = self.client.table(_TAGS_TABLE).insert(
            {"category": category, "slug": slug, "label_hu": slug}
        ).execute()
        return created.data[0]["id"]

    def replace_review_tags(
        self, unit_id: int, *, topics: list[str], tone: str, homiletic_functions: list[str]
    ) -> None:
        """Same ALL-OR-NOTHING controlled-vocabulary validation as
        `illustration_unit_repository.replace_review_tags` (checked
        BEFORE any write), and -- audit fix ported alongside this
        skeleton, see that function's own "REVIEW PROTECTION" docstring
        section -- the SAME human_reviewed_at REJECT gate: an already
        reviewed (approved/published) unit's tags cannot be changed
        through this method at all; `send_back_for_rework()` must be
        called first. The `illustration_unit_tags_protect_reviewed`
        Postgres trigger enforces the identical rule even if this
        Python-side check were ever bypassed."""
        invalid: list[str] = []
        if not topics or not (1 <= len(topics) <= 3):
            invalid.append("topics must be a list of 1-3 items")
        else:
            invalid.extend(f"invalid topic slug: {t!r}" for t in topics if t not in PILOT_TOPICS)
        if tone not in PILOT_TONES:
            invalid.append(f"invalid tone slug: {tone!r}")
        if not homiletic_functions or not (1 <= len(homiletic_functions) <= 2):
            invalid.append("homiletic_functions must be a list of 1-2 items")
        else:
            invalid.extend(
                f"invalid homiletic_function slug: {f!r}"
                for f in homiletic_functions
                if f not in PILOT_HOMILETIC_FUNCTIONS
            )
        if invalid:
            raise ValueError(f"cannot replace tags for unit id={unit_id}: {'; '.join(invalid)}")

        unit = self._fetch_unit(unit_id)
        if unit is None:
            raise IllustrationUnitNotFoundError(f"illustration unit not found: id={unit_id}")
        if unit.get("human_reviewed_at") is not None:
            raise IllustrationUnitReviewProtectionError(
                f"illustration unit id={unit_id} was human-reviewed at "
                f"{unit['human_reviewed_at']!r} -- refusing to silently change its taxonomy "
                "tags. Call send_back_for_rework() first."
            )

        desired = (
            {("topic", slug) for slug in topics}
            | {("tone", tone)}
            | {("function", slug) for slug in homiletic_functions}
        )
        tag_ids = [self._get_or_create_tag(category=c, slug=s) for c, s in desired]

        self.client.table(_UNIT_TAGS_TABLE).delete().eq("unit_id", unit_id).execute()
        self.client.table(_UNIT_TAGS_TABLE).insert(
            [{"unit_id": unit_id, "tag_id": tag_id} for tag_id in tag_ids]
        ).execute()


__all__ = [
    "IllustrationUnitNotEligibleError",
    "IllustrationUnitNotFoundError",
    "IllustrationUnitReviewProtectionError",
    "SupabaseIllustrationReviewRepository",
]
