from app.assistant.messages import MessageHistory


def test_window_keeps_most_recent_messages_by_count():
    history = MessageHistory(
        max_messages=4,
        max_chars=10**9,
        summarize=None,
        summarize_batch_size=100,
    )
    for i in range(6):
        history.add_user_message(f"u{i}")
        history.add_assistant_message(f"a{i}")

    assert history.get_message_count() == 4
    assert [m["content"] for m in history.get_context_messages()] == [
        "u4",
        "a4",
        "u5",
        "a5",
    ]


def test_window_evicts_by_char_budget():
    history = MessageHistory(
        max_messages=100,
        max_chars=20,
        summarize=None,
        summarize_batch_size=100,
    )
    history.add_user_message("a" * 10)
    history.add_assistant_message("b" * 10)
    history.add_user_message("c" * 10)
    history.add_assistant_message("d" * 10)

    # Only the last two messages fit the 20-char budget.
    assert [m["content"] for m in history.get_context_messages()] == [
        "c" * 10,
        "d" * 10,
    ]


def test_rolling_summary_folds_evicted_messages():
    calls = []

    def fake_summarize(existing, new_messages):
        calls.append((existing, [m["content"] for m in new_messages]))
        return "SUMMARY"

    history = MessageHistory(
        max_messages=2,
        max_chars=10**9,
        summarize=fake_summarize,
        summarize_batch_size=2,
    )
    history.add_user_message("u0")
    history.add_assistant_message("a0")
    history.add_user_message("u1")
    history.add_assistant_message("a1")

    assert len(calls) == 1
    assert calls[0][0] == ""
    assert calls[0][1] == ["u0", "a0"]

    context = history.get_context_messages()
    assert context[0]["content"].endswith("SUMMARY")
    assert [m["content"] for m in context[1:]] == ["u1", "a1"]


def test_no_summary_when_summarizer_is_none():
    history = MessageHistory(
        max_messages=2,
        max_chars=10**9,
        summarize=None,
        summarize_batch_size=1,
    )
    history.add_user_message("u0")
    history.add_assistant_message("a0")
    history.add_user_message("u1")

    context = history.get_context_messages()
    assert len(context) == 2
    assert context[0]["content"] == "a0"


def test_clear_resets_summary_and_pending():
    def fake_summarize(existing, new_messages):
        return "SUMMARY"

    history = MessageHistory(
        max_messages=2,
        max_chars=10**9,
        summarize=fake_summarize,
        summarize_batch_size=2,
    )
    history.add_user_message("u0")
    history.add_assistant_message("a0")
    history.add_user_message("u1")
    history.add_assistant_message("a1")
    history.clear()

    assert history.get_message_count() == 0
    assert history.get_context_messages() == []
