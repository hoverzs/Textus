"""Supabase projekt CRUD — minden lekérdezés `owner_sub` szerint szűr.

A secret key megkerülheti az RLS-t, ezért az `owner_sub` szűrés soha
nem opcionális. Vendég-ellenőrzés az app.py felületén történik később;
ezek a függvények feltételezik, hogy érvényes `owner_sub`-ot kapnak.

2026-09 audit fix — optimistic concurrency: minden sor egy monoton növekvő
`revision` oszlopot hordoz (lásd
``supabase/migrations/20260912150000_projects_revision_optimistic_lock.sql``).
``update_project`` csak akkor sikerül, ha a kliens által ismert
``expected_revision`` még mindig egyezik az adatbázisban tárolt értékkel —
ez zárja ki a blind "utolsó mentés nyer" felülírást két lap/eszköz között.
Nincs automatikus merge: ütközés esetén a hívó felelőssége eldönteni, mit
tegyen (újratöltés, mentés másolatként) — lásd ``UpdateProjectResult``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from supabase_client import get_supabase_client
from workspace_data import build_project_data as _build_project_data
from workspace_data import sanitize_project_data

PROJECTS_TABLE = "projects"


class SaveOutcome:
    """``UpdateProjectResult.outcome`` values."""

    OK = "ok"
    CONFLICT = "conflict"
    NOT_FOUND = "not_found"


@dataclass(frozen=True)
class UpdateProjectResult:
    outcome: str
    row: dict[str, Any] | None = None
    # Populated only on CONFLICT — the revision actually stored in the
    # database right now, so the caller can decide whether to reload.
    current_revision: int | None = None


def build_project_data_from_state(state: Mapping[str, Any], *, version: str | None = None) -> dict[str, Any]:
    """Aktuális projektadat a közös workspace-serializáció alapján."""
    return _build_project_data(state, version=version)


def _require_owner_sub(owner_sub: str) -> str:
    value = (owner_sub or "").strip()
    if not value:
        raise ValueError("owner_sub kötelező — vendég módban ne hívd a storage függvényeket.")
    return value


def _require_project_id(project_id: str) -> str:
    value = (project_id or "").strip()
    if not value:
        raise ValueError("project_id kötelező.")
    return value


def create_project(
    owner_sub: str,
    title: str,
    passage: str,
    project_data: Mapping[str, Any],
) -> dict[str, Any]:
    """Új projekt beszúrása. Az `owner_sub` a sor része (kötelező)."""
    owner = _require_owner_sub(owner_sub)
    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "owner_sub": owner,
        "title": (title or "").strip() or "Névtelen projekt",
        "passage": (passage or "").strip(),
        "project_data": sanitize_project_data(project_data),
        "updated_at": now_iso,
    }
    response = get_supabase_client().table(PROJECTS_TABLE).insert(row).execute()
    rows = response.data or []
    if not rows:
        raise RuntimeError("A create_project nem adott vissza sort.")
    return rows[0]


def update_project(
    project_id: str,
    owner_sub: str,
    title: str,
    passage: str,
    project_data: Mapping[str, Any],
    *,
    expected_revision: int,
) -> UpdateProjectResult:
    """Projekt frissítése — csak `id` + `owner_sub` + `revision` egyezés esetén.

    ``expected_revision`` a kliens által utoljára ismert revízió (betöltéskor
    vagy az előző sikeres mentéskor kapott érték). Az UPDATE csak akkor
    talál sort, ha az adatbázisban még mindig ez a revízió van — így egy
    időközben (másik lapon/eszközön) történt mentés nem íródik felül
    csendben, hanem ``SaveOutcome.CONFLICT``-ot ad vissza.
    """
    pid = _require_project_id(project_id)
    owner = _require_owner_sub(owner_sub)
    now_iso = datetime.now(timezone.utc).isoformat()
    row = {
        "title": (title or "").strip() or "Névtelen projekt",
        "passage": (passage or "").strip(),
        "project_data": sanitize_project_data(project_data),
        "updated_at": now_iso,
        "revision": int(expected_revision) + 1,
    }
    response = (
        get_supabase_client()
        .table(PROJECTS_TABLE)
        .update(row)
        .eq("id", pid)
        .eq("owner_sub", owner)
        .eq("revision", int(expected_revision))
        .execute()
    )
    rows = response.data or []
    if rows:
        return UpdateProjectResult(outcome=SaveOutcome.OK, row=rows[0])

    # 0 rows: either the id/owner doesn't match at all, or the revision has
    # already moved on (another writer saved first). One extra read only on
    # this rare path — the happy path above stays a single UPDATE call.
    current = get_project(pid, owner)
    if current is None:
        return UpdateProjectResult(outcome=SaveOutcome.NOT_FOUND)
    return UpdateProjectResult(outcome=SaveOutcome.CONFLICT, current_revision=current.get("revision"))


def get_user_projects(owner_sub: str) -> list[dict[str, Any]]:
    """A felhasználó összes projektje — kizárólag `owner_sub` szerint."""
    owner = _require_owner_sub(owner_sub)
    response = (
        get_supabase_client()
        .table(PROJECTS_TABLE)
        .select("id,owner_sub,title,passage,created_at,updated_at")
        .eq("owner_sub", owner)
        .order("updated_at", desc=True)
        .execute()
    )
    return list(response.data or [])


def get_project(project_id: str, owner_sub: str) -> dict[str, Any] | None:
    """Egy projekt lekérése — `id` és `owner_sub` együttes szűréssel."""
    pid = _require_project_id(project_id)
    owner = _require_owner_sub(owner_sub)
    response = (
        get_supabase_client()
        .table(PROJECTS_TABLE)
        .select("id,owner_sub,title,passage,project_data,revision,created_at,updated_at")
        .eq("id", pid)
        .eq("owner_sub", owner)
        .limit(1)
        .execute()
    )
    rows = response.data or []
    if not rows:
        return None
    row = dict(rows[0])
    row["project_data"] = sanitize_project_data(row.get("project_data"))
    return row


def delete_project(project_id: str, owner_sub: str) -> bool:
    """Projekt törlése — csak `id` + `owner_sub` egyezés esetén."""
    pid = _require_project_id(project_id)
    owner = _require_owner_sub(owner_sub)
    response = (
        get_supabase_client()
        .table(PROJECTS_TABLE)
        .delete()
        .eq("id", pid)
        .eq("owner_sub", owner)
        .execute()
    )
    rows = response.data or []
    return bool(rows)
