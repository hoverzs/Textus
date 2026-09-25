"""2026-09 audit fix — regression coverage for the project-save reliability
state machine in app.py (``_apply_update_result`` / ``_project_save_status``
/ ``_cloud_save_project`` / ``_maybe_autosave_project``).

Before this fix: a brand-new, never-saved project had zero autosave
protection with no visible signal beyond a generic "Ideiglenes" label; an
autosave failure (exception OR the project having been deleted/moved out
from under it) was swallowed by a bare ``return`` — no flash, no log, no
persistent indicator, while the settings panel kept claiming autosave runs
every ~3 minutes; and there was no conflict handling at all (see
``tests/test_project_storage_concurrency.py`` for the storage-layer half
of that fix). This file proves the app.py-level state machine built on top
of that storage fix behaves correctly for the specified scenarios:

A) successful autosave;
B) autosave transient failure -> recovery;
C) an exception during save produces a visible state/flash (manual AND
   autosave);
D) a brand-new (never-saved) project's autosave is a safe, side-effect-free
   no-op — not a silent data-eating trap.

Pattern: ``patch.object(app_mod, "st")`` swaps the module's ``st``
reference for a MagicMock whose ``session_state`` is a plain dict — the
same technique already used by
``tests/test_p0_generate_text_tls_temperature.py`` — so these tests
exercise the REAL app.py code without a live Streamlit script run or any
network access. ``project_storage.update_project``/``create_project`` are
monkeypatched directly (app.py imports them locally, by name, inside the
function body, so patching the ``project_storage`` module's attribute is
what the local import actually picks up).
"""

from __future__ import annotations

from unittest.mock import patch

import project_storage as ps


def _session_state(**overrides) -> dict:
    state = {
        "current_project_id": "proj-1",
        "current_project_revision": 3,
        "current_project_title": "Régi cím",
        "project_title_input": "Régi cím",
        "last_igehely": "Jn 3,16",
        "project_saved_fingerprint": "",
        "_project_last_save_ts": 0.0,
        "_project_save_state": None,
        "_project_save_error_streak": 0,
        "_project_conflict_streak": 0,
        "_project_conflict_current_revision": None,
        "_flash_message": None,
        "_pending_project_title_input": None,
    }
    state.update(overrides)
    return state


def _call_cloud_save(state: dict, *, as_new: bool = False, autosave: bool = False):
    import app as app_mod

    with patch.object(app_mod, "st") as st_mock, \
         patch.object(app_mod, "track_event"), \
         patch.object(app_mod, "_owner_sub", return_value="user-1"), \
         patch.object(app_mod, "_sync_inputs_to_last"), \
         patch.object(ps, "build_project_data_from_state", return_value={}):
        st_mock.session_state = state
        app_mod._cloud_save_project(as_new=as_new, autosave=autosave)
    return st_mock


# --- A: successful autosave -------------------------------------------------

def test_a_successful_autosave_updates_revision_silently():
    """Checkpoint 2: a successful background autosave is SILENT — no info
    flash and (see the rerun tests below) no app-scope rerun."""
    state = _session_state(current_project_revision=3)
    fake_result = ps.UpdateProjectResult(outcome=ps.SaveOutcome.OK, row={"id": "proj-1", "revision": 4})
    with patch.object(ps, "update_project", return_value=fake_result) as update_mock:
        _call_cloud_save(state, autosave=True)
    assert update_mock.call_args.kwargs["expected_revision"] == 3
    assert state["current_project_revision"] == 4
    assert state["_project_save_state"] == "saved"
    assert state["_project_save_error_streak"] == 0
    assert state["_flash_message"] is None


# --- A2: successful autosave never requests a rerun (ghosting fix) ---------

_OK4 = lambda: ps.UpdateProjectResult(outcome=ps.SaveOutcome.OK, row={"id": "proj-1", "revision": 4})  # noqa: E731


def test_a2_successful_autosave_does_not_request_any_rerun():
    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", return_value=_OK4()):
        st_mock = _call_cloud_save(state, autosave=True)
    st_mock.rerun.assert_not_called()


def test_a2_manual_save_success_still_reruns():
    """Deliberately preserved: only the AUTOSAVE success path lost its rerun."""
    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", return_value=_OK4()):
        st_mock = _call_cloud_save(state, autosave=False)
    st_mock.rerun.assert_called_once_with()
    assert state["_flash_message"] is not None  # manual save still flashes "Mentve"


def test_a2_autosave_updates_fingerprint_and_clears_dirty():
    import app as app_mod
    from workspace_data import project_content_fingerprint

    state = _session_state(current_project_revision=3, last_igehely="Jn 3,16")
    with patch.object(app_mod, "st") as st_mock, patch.object(app_mod, "_sync_inputs_to_last"):
        st_mock.session_state = state
        assert app_mod._is_project_dirty() is True  # nothing saved yet
    with patch.object(ps, "update_project", return_value=_OK4()):
        _call_cloud_save(state, autosave=True)
    assert state["project_saved_fingerprint"] == project_content_fingerprint(state)
    assert state["_project_last_save_ts"] > 0
    with patch.object(app_mod, "st") as st_mock, patch.object(app_mod, "_sync_inputs_to_last"):
        st_mock.session_state = state
        assert app_mod._is_project_dirty() is False


def test_a2_autosave_does_not_leave_a_stale_pending_title():
    """The old immediate rerun consumed _pending_project_title_input; without
    it the pending value must not linger and clobber a title typed later."""
    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", return_value=_OK4()):
        _call_cloud_save(state, autosave=True)
    assert state["_pending_project_title_input"] is None
    assert state["current_project_title"] == "Régi cím"


def test_a2_maybe_autosave_full_cycle_is_silent_and_not_repeated():
    """_maybe_autosave_project (the fragment's body): dirty + interval elapsed
    -> exactly one update, no rerun; immediately after, nothing is dirty so
    the next tick is a no-op."""
    import app as app_mod

    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", return_value=_OK4()) as update_mock,          patch.object(app_mod, "st") as st_mock,          patch.object(app_mod, "track_event"),          patch.object(app_mod, "_owner_sub", return_value="user-1"),          patch.object(app_mod, "_sync_inputs_to_last"),          patch.object(ps, "build_project_data_from_state", return_value={}):
        st_mock.session_state = state
        app_mod._maybe_autosave_project()
        assert update_mock.call_count == 1
        state["_project_last_save_ts"] = 0.0  # interval elapsed again
        app_mod._maybe_autosave_project()
        assert update_mock.call_count == 1  # clean -> nothing to save
        st_mock.rerun.assert_not_called()
    assert state["current_project_revision"] == 4


def test_a2_autosave_conflict_and_failure_paths_do_not_rerun():
    """Conflict / failure behaviour is unchanged (state + flash, no rerun)."""
    conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, row=None, current_revision=9)
    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", return_value=conflict):
        st_mock = _call_cloud_save(state, autosave=True)
    st_mock.rerun.assert_not_called()
    assert state["_project_save_state"] == "conflict"
    assert state["current_project_revision"] == 3

    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", side_effect=RuntimeError("boom")):
        st_mock = _call_cloud_save(state, autosave=True)
    st_mock.rerun.assert_not_called()
    assert state["_project_save_state"] == "save_failed"
    assert state["_project_save_error_streak"] == 1


# --- B: autosave transient failure -> recovery ------------------------------

def test_b_autosave_transient_exception_then_recovery():
    state = _session_state(current_project_revision=3)

    # First attempt: the network call raises (transient outage).
    with patch.object(ps, "update_project", side_effect=RuntimeError("network blip")):
        _call_cloud_save(state, autosave=True)
    assert state["_project_save_state"] == "save_failed"
    assert state["_project_save_error_streak"] == 1
    first_flash = state["_flash_message"]
    assert first_flash is not None and first_flash["type"] == "warning"
    # Revision must NOT have advanced on a failed attempt.
    assert state["current_project_revision"] == 3

    # Second attempt (backend recovered): must reach update_project again
    # with the SAME expected_revision (nothing was silently consumed) and
    # succeed, clearing the failure streak.
    state["_flash_message"] = None
    fake_result = ps.UpdateProjectResult(outcome=ps.SaveOutcome.OK, row={"id": "proj-1", "revision": 4})
    with patch.object(ps, "update_project", return_value=fake_result) as update_mock:
        _call_cloud_save(state, autosave=True)
    assert update_mock.call_args.kwargs["expected_revision"] == 3
    assert state["current_project_revision"] == 4
    assert state["_project_save_state"] == "saved"
    assert state["_project_save_error_streak"] == 0


def test_b_persistent_autosave_failure_does_not_spam_every_attempt():
    """A single blip flashes once; a run of consecutive failures reminds
    periodically (every _AUTOSAVE_FAILURE_REMINDER_EVERY-th attempt), not
    on every single ~3-minute tick."""
    import app as app_mod

    state = _session_state(current_project_revision=3)
    flashes = []
    for _ in range(app_mod._AUTOSAVE_FAILURE_REMINDER_EVERY - 1):
        state["_flash_message"] = None
        with patch.object(ps, "update_project", side_effect=RuntimeError("still down")):
            _call_cloud_save(state, autosave=True)
        flashes.append(state["_flash_message"])
    # Only the very first attempt (streak == 1) should have flashed.
    assert flashes[0] is not None
    assert all(f is None for f in flashes[1:])
    assert state["_project_save_error_streak"] == app_mod._AUTOSAVE_FAILURE_REMINDER_EVERY - 1
    # The chip status must stay visibly "failed" throughout the streak,
    # even on the ticks that didn't re-flash.
    assert state["_project_save_state"] == "save_failed"


# --- C: exception -> visible state/flash (manual save) ----------------------

def test_c_manual_save_exception_flashes_error_immediately():
    state = _session_state(current_project_revision=3)
    with patch.object(ps, "update_project", side_effect=RuntimeError("boom")):
        _call_cloud_save(state, autosave=False)
    assert state["_project_save_state"] == "save_failed"
    assert state["_project_save_error_streak"] == 1
    assert state["_flash_message"]["type"] == "error"
    assert "Mentési hiba" in state["_flash_message"]["text"]


def test_c_manual_save_conflict_never_overwrites_and_flashes_warning():
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=7)
    with patch.object(ps, "update_project", return_value=fake_conflict):
        _call_cloud_save(state, autosave=False)
    assert state["_project_save_state"] == "conflict"
    # The client's local revision must be left untouched — no assumption
    # that its stale copy is now somehow valid.
    assert state["current_project_revision"] == 3
    assert state["_flash_message"]["type"] == "warning"
    assert "Ütközés" in state["_flash_message"]["text"]


# --- D: brand-new (never-saved) project's autosave is a safe no-op ---------

def test_d_new_project_autosave_never_calls_storage_or_corrupts_state():
    state = _session_state(current_project_id="", current_project_revision=0)
    with patch.object(ps, "update_project") as update_mock, patch.object(ps, "create_project") as create_mock:
        _call_cloud_save(state, autosave=True)
    update_mock.assert_not_called()
    create_mock.assert_not_called()
    # No spurious failure/conflict state must appear for a project that was
    # never supposed to autosave in the first place.
    assert state["_project_save_state"] is None
    assert state["_project_save_error_streak"] == 0


def test_d_maybe_autosave_project_skips_when_no_current_project():
    import app as app_mod

    state = _session_state(current_project_id="")
    with patch.object(app_mod, "st") as st_mock, \
         patch.object(app_mod, "_owner_sub", return_value="user-1"), \
         patch.object(app_mod, "_cloud_save_project") as save_mock:
        st_mock.session_state = state
        app_mod._maybe_autosave_project()
    save_mock.assert_not_called()


# --- E: conflict notification dedup (2026-09 post-fix-verification regression) ---
#
# Root cause of the regression this section guards against: the autosave
# path (_cloud_save_project) unconditionally writes
# _project_save_state = "saving" immediately before calling update_project.
# The CONFLICT branch of _apply_update_result used to decide whether to
# re-flash by reading THAT SAME key ("was _project_save_state already
# 'conflict'?") — but by the time it ran, the key had just been overwritten
# to "saving", so the check could never see "conflict" there and re-flashed
# on every single autosave tick while the conflict persisted. The fix
# replaces that state-read with an explicit, independent streak counter
# (_project_conflict_streak), mirroring the NOT_FOUND branch's existing
# _project_save_error_streak pattern, which was never affected by this bug.

def test_e1_first_conflict_flashes_a_notification():
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=9)
    with patch.object(ps, "update_project", return_value=fake_conflict):
        _call_cloud_save(state, autosave=True)
    assert state["_project_conflict_streak"] == 1
    assert state["_flash_message"] is not None
    assert state["_flash_message"]["type"] == "warning"
    assert "Ütközés" in state["_flash_message"]["text"]


def test_e2_same_conflict_on_next_autosave_does_not_reflash():
    """The exact regression: a SECOND (and third) consecutive autosave
    attempt against the same unresolved conflict must NOT re-flash, even
    though _cloud_save_project always writes _project_save_state="saving"
    right before each attempt."""
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=9)

    with patch.object(ps, "update_project", return_value=fake_conflict):
        _call_cloud_save(state, autosave=True)  # 1st attempt: flashes
        state["_flash_message"] = None
        _call_cloud_save(state, autosave=True)  # 2nd attempt: must stay quiet
        second_flash = state["_flash_message"]
        state["_flash_message"] = None
        _call_cloud_save(state, autosave=True)  # 3rd attempt: still quiet
        third_flash = state["_flash_message"]

    assert second_flash is None
    assert third_flash is None
    assert state["_project_conflict_streak"] == 3


def test_e3_conflict_state_and_local_revision_are_preserved_across_repeats():
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=9)
    with patch.object(ps, "update_project", return_value=fake_conflict) as update_mock:
        _call_cloud_save(state, autosave=True)
        _call_cloud_save(state, autosave=True)
    assert state["_project_save_state"] == "conflict"
    # The local revision must never silently advance to the server's —
    # every attempt keeps retrying from the SAME stale revision (no
    # auto-merge, no silent overwrite of local state).
    assert state["current_project_revision"] == 3
    assert [c.kwargs["expected_revision"] for c in update_mock.call_args_list] == [3, 3]


def test_e4_successful_recovery_resets_the_conflict_dedup_state():
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=9)
    with patch.object(ps, "update_project", return_value=fake_conflict):
        _call_cloud_save(state, autosave=True)
    assert state["_project_conflict_streak"] == 1

    # User reloads (picks up revision 9) and the next save succeeds.
    state["current_project_revision"] = 9
    fake_ok = ps.UpdateProjectResult(outcome=ps.SaveOutcome.OK, row={"id": "proj-1", "revision": 10})
    with patch.object(ps, "update_project", return_value=fake_ok):
        _call_cloud_save(state, autosave=True)

    assert state["_project_save_state"] == "saved"
    assert state["_project_conflict_streak"] == 0


def test_e5_a_new_later_conflict_flashes_again_after_recovery():
    """After a recovered conflict resets the streak, a genuinely NEW,
    later conflict must be treated as fresh — flashing once again, not
    permanently suppressed by the earlier episode."""
    state = _session_state(current_project_revision=3)
    fake_conflict = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=9)
    with patch.object(ps, "update_project", return_value=fake_conflict):
        _call_cloud_save(state, autosave=True)  # first conflict episode

    state["current_project_revision"] = 9
    fake_ok = ps.UpdateProjectResult(outcome=ps.SaveOutcome.OK, row={"id": "proj-1", "revision": 10})
    with patch.object(ps, "update_project", return_value=fake_ok):
        _call_cloud_save(state, autosave=True)  # recovery in between
    assert state["_project_conflict_streak"] == 0

    state["_flash_message"] = None
    fake_conflict_2 = ps.UpdateProjectResult(outcome=ps.SaveOutcome.CONFLICT, current_revision=15)
    with patch.object(ps, "update_project", return_value=fake_conflict_2):
        _call_cloud_save(state, autosave=True)  # second, independent conflict episode

    assert state["_project_conflict_streak"] == 1
    assert state["_flash_message"] is not None
    assert "Ütközés" in state["_flash_message"]["text"]
