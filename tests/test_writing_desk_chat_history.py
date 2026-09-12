"""2026-09 audit fix — regression coverage for the Segítő chat becoming a
REAL multi-turn conversation, per the system audit's finding that the UI
looked like a chat but every question went out to the model with zero
memory of earlier turns in the same session, and that the whole
conversation was silently discarded on project close/reopen.

Covers exactly the scenario named in the fix brief: the assistant gives
two suggestions, the user says "fejtsd ki a másodikat" ("expand on the
second one"), and the new prompt must actually carry the prior exchange —
plus the project save / reopen / switch lifecycle around it.
"""

from __future__ import annotations

from workspace_data import build_project_data, sanitize_project_data
from writing_desk_chat import (
    MAX_HISTORY_MESSAGES,
    WRITING_DESK_CHAT_KEY,
    build_writing_desk_chat_prompt,
    ensure_writing_desk_chat_state,
    normalize_writing_desk_chat,
    send_writing_desk_chat_message,
    writing_desk_chat_messages,
)


def _mock_generate(text: str, bucket: list | None = None):
    def _fn(prompt, **kwargs):
        if bucket is not None:
            bucket.append(prompt)
        return text

    return _fn


def test_second_question_prompt_carries_the_first_exchange():
    """The exact spec scenario: assistant gives two suggestions, user asks
    to expand on the second one — the new prompt must contain both the
    prior user question AND the prior assistant reply, not just the
    current question."""
    session: dict = {"last_igehely": "Jn 3,16"}
    prompts: list[str] = []

    first = send_writing_desk_chat_message(
        session,
        "Adj két javaslatot a bevezető megnyitására.",
        generate_fn=_mock_generate(
            "1) Kezdd egy kérdéssel. 2) Kezdd egy rövid történettel.", prompts,
        ),
    )
    assert first.ok

    second = send_writing_desk_chat_message(
        session,
        "A második javaslatodat fejtsd ki.",
        generate_fn=_mock_generate("Rendben, a történettel kezdést részletezem...", prompts),
    )
    assert second.ok
    assert len(prompts) == 2

    second_prompt = prompts[1]
    assert "A második javaslatodat fejtsd ki." in second_prompt
    # The history block must carry the FULL prior exchange, not just an
    # acknowledgement that history exists.
    assert "Adj két javaslatot a bevezető megnyitására." in second_prompt
    assert "Kezdd egy rövid történettel." in second_prompt

    # And the model's own most recent turn is not treated as history of
    # itself — sanity check that the first call had no history to send.
    first_prompt = prompts[0]
    assert "nincs korábbi üzenet" in first_prompt


def test_history_window_is_bounded_not_unlimited():
    """A long-running conversation must not grow the prompt without bound
    — only the last MAX_HISTORY_MESSAGES messages are included."""
    session: dict = {"last_igehely": "Jn 3,16"}
    for i in range(MAX_HISTORY_MESSAGES + 6):
        send_writing_desk_chat_message(
            session, f"kérdés-{i}", generate_fn=_mock_generate(f"válasz-{i}"),
        )

    all_messages = writing_desk_chat_messages(session)
    assert len(all_messages) >= MAX_HISTORY_MESSAGES + 2  # stored history isn't itself this narrow

    # Build the prompt for one more turn and confirm the history block
    # only ever carries the bounded window, not the entire conversation.
    prompt = build_writing_desk_chat_prompt(
        reference="Jn 3,16", draft_plain="", question="még egy kérdés",
        history=all_messages,
    )
    assert "kérdés-0" not in prompt  # earliest turns fell out of the window
    assert f"kérdés-{MAX_HISTORY_MESSAGES + 5}" in prompt  # most recent turn kept


def test_chat_survives_full_save_then_reopen_round_trip():
    """Project save -> reopen: the conversation must come back exactly,
    via the same normalize/sanitize path the real save/load pipeline uses
    (workspace_data.build_project_data / sanitize_project_data)."""
    session: dict = {"last_igehely": "Jn 3,16", "current_project_id": "proj-1"}
    send_writing_desk_chat_message(
        session, "Hogyan zárjam le a beszédet?", generate_fn=_mock_generate("Egy rövid imával."),
    )
    before = writing_desk_chat_messages(session)
    assert len(before) == 2

    # Simulate a save: build + sanitize the persisted project_data exactly
    # like project_storage.update_project/create_project do.
    saved = sanitize_project_data(build_project_data(session, version="test"))
    assert WRITING_DESK_CHAT_KEY in saved
    assert saved[WRITING_DESK_CHAT_KEY]["messages"] == before

    # Simulate reopening the SAME project in a fresh session — the
    # restoration line app.py._apply_project_data_to_session runs.
    reopened_session: dict = {
        "current_project_id": "proj-1",
        "last_igehely": "Jn 3,16",
    }
    reopened_session[WRITING_DESK_CHAT_KEY] = normalize_writing_desk_chat(
        saved.get(WRITING_DESK_CHAT_KEY)
    )
    # The lazy fingerprint check (as if rendering the chat panel again)
    # must recognize this as the SAME context and keep the history —
    # not wipe it, since current_project_id/last_igehely match what was
    # saved.
    restored_state = ensure_writing_desk_chat_state(reopened_session)
    assert restored_state["messages"] == before


def test_chat_does_not_survive_switching_to_a_different_project():
    """Opening a DIFFERENT project (or resetting to a new one) must not
    leak the previous project's conversation — this is the existing
    context-fingerprint guard, re-verified here alongside persistence."""
    session: dict = {"last_igehely": "Jn 3,16", "current_project_id": "proj-1"}
    send_writing_desk_chat_message(
        session, "Ez a proj-1 kérdése.", generate_fn=_mock_generate("proj-1 válasz"),
    )
    assert len(writing_desk_chat_messages(session)) == 2

    # Switch: a different project's data gets applied to the same session
    # (current_project_id changes, as app.py._cloud_open_project does).
    session["current_project_id"] = "proj-2"
    session[WRITING_DESK_CHAT_KEY] = normalize_writing_desk_chat(None)  # proj-2 has no saved chat
    restored = ensure_writing_desk_chat_state(session)
    assert restored["messages"] == []
