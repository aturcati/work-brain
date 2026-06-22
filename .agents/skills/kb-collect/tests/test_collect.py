import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from collect import get_cursor, check_id, record, slugify, meeting_id


# --- slugify ---

def test_slugify_basic():
    assert slugify("Sprint Planning") == "sprint-planning"


def test_slugify_accents():
    assert slugify("Müller & Schmidt") == "muller-schmidt"


def test_slugify_trailing_hyphens():
    assert slugify("hello---world--") == "hello-world"


def test_slugify_truncate():
    long = "a" * 60
    result = slugify(long)
    assert len(result) <= 50
    assert not result.endswith("-")


# --- meeting_id ---

def test_meeting_id_basic():
    assert meeting_id("Widget Planning Sync", "2026-05-06T09:00:00.000Z") == "2026-05-06-widget-planning-sync"


def test_meeting_id_special_chars():
    assert meeting_id("[acme.cloud] Scrum Review", "2026-05-07T12:00:00.000Z") == "2026-05-07-acme-cloud-scrum-review"


# --- get_cursor ---

def test_get_cursor_empty_state():
    assert get_cursor({}, "teams") == "NONE"


def test_get_cursor_populated():
    state = {"teams": {"cursor": "2026-05-06T00:00:00Z"}}
    assert get_cursor(state, "teams") == "2026-05-06T00:00:00Z"


def test_get_cursor_other_provider():
    state = {"outlook": {"cursor": "2026-05-01T00:00:00Z"}}
    assert get_cursor(state, "teams") == "NONE"


# --- check_id ---

def test_check_id_new():
    assert check_id({}, "teams", "2026-05-06-widget-planning-sync") == "NEW"


def test_check_id_seen():
    state = {"teams": {"seen_ids": ["2026-05-06-widget-planning-sync"]}}
    assert check_id(state, "teams", "2026-05-06-widget-planning-sync") == "SEEN"


def test_check_id_different_provider():
    state = {"outlook": {"seen_ids": ["2026-05-06-widget-planning-sync"]}}
    assert check_id(state, "teams", "2026-05-06-widget-planning-sync") == "NEW"


# --- record ---

def test_record_adds_id_and_cursor():
    state = {}
    new_state = record(state, "teams", "2026-05-06-widget-planning-sync", "2026-05-06T09:00:00Z")
    assert "2026-05-06-widget-planning-sync" in new_state["teams"]["seen_ids"]
    assert new_state["teams"]["cursor"] == "2026-05-06T09:00:00Z"


def test_record_no_duplicate_ids():
    state = {"teams": {"seen_ids": ["2026-05-06-widget-planning-sync"]}}
    new_state = record(state, "teams", "2026-05-06-widget-planning-sync", None)
    assert new_state["teams"]["seen_ids"].count("2026-05-06-widget-planning-sync") == 1


def test_record_cursor_none_preserves_existing():
    state = {"teams": {"cursor": "2026-05-01T00:00:00Z", "seen_ids": []}}
    new_state = record(state, "teams", "some-id", None)
    assert new_state["teams"]["cursor"] == "2026-05-01T00:00:00Z"


def test_record_does_not_mutate_input():
    state = {"teams": {"seen_ids": []}}
    record(state, "teams", "some-id", "2026-05-06T00:00:00Z")
    assert state["teams"]["seen_ids"] == []


# --- url_key ---

def test_url_key_deterministic():
    from collect import url_key
    a = url_key("https://example.com/article")
    b = url_key("https://example.com/article")
    assert a == b
    assert len(a) == 16


def test_url_key_ignores_trailing_slash():
    from collect import url_key
    assert url_key("https://example.com/article") == url_key("https://example.com/article/")


def test_url_key_ignores_fragment():
    from collect import url_key
    assert url_key("https://example.com/article") == url_key("https://example.com/article#section-2")


def test_url_key_strips_utm_params():
    from collect import url_key
    a = url_key("https://example.com/article?utm_source=twitter&utm_medium=social")
    b = url_key("https://example.com/article")
    assert a == b


def test_url_key_keeps_non_tracking_params():
    from collect import url_key
    a = url_key("https://example.com/article?id=42")
    b = url_key("https://example.com/article")
    assert a != b


def test_url_key_case_insensitive_on_host():
    from collect import url_key
    assert url_key("https://Example.COM/article") == url_key("https://example.com/article")


def test_url_key_keeps_case_on_path():
    from collect import url_key
    # Path is case-sensitive by HTTP spec; treat distinct paths as distinct keys
    assert url_key("https://example.com/Article") != url_key("https://example.com/article")


def test_url_key_strips_default_ports():
    from collect import url_key
    assert url_key("https://example.com:443/article") == url_key("https://example.com/article")
    assert url_key("http://example.com:80/article") == url_key("http://example.com/article")


# --- url_slug ---

def test_url_slug_uses_title_when_provided():
    from collect import url_slug
    out = url_slug("https://example.com/x", title="The Quick Brown Fox", date="2026-05-24")
    assert out == "2026-05-24-the-quick-brown-fox"


def test_url_slug_falls_back_to_host_path():
    from collect import url_slug
    out = url_slug("https://example.com/blog/post-42", title="", date="2026-05-24")
    assert out.startswith("2026-05-24-")
    assert "example-com" in out
    assert "blog-post-42" in out


def test_url_slug_strips_www_prefix():
    from collect import url_slug
    out = url_slug("https://www.anthropic.com/news/foo", title="", date="2026-05-24")
    assert "www" not in out
    assert "anthropic-com" in out


def test_url_slug_truncates_long_title():
    from collect import url_slug
    long_title = "A " * 100  # 200 chars
    out = url_slug("https://example.com/", title=long_title, date="2026-05-24")
    assert len(out) <= 80


def test_url_slug_strips_accents():
    from collect import url_slug
    out = url_slug("https://example.com/x", title="Café Müller", date="2026-05-24")
    assert out == "2026-05-24-cafe-muller"


def test_url_slug_default_date_is_today_utc():
    import datetime
    from collect import url_slug
    out = url_slug("https://example.com/x", title="hello", date="")
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    assert out.startswith(today + "-")


def test_url_slug_does_not_chew_wallaby():
    from collect import url_slug
    # Regression test: lstrip("www.") would have chewed "w","a","l","l","y","." → "by-com"
    out = url_slug("https://wallaby.com/blog", title="", date="2026-05-24")
    assert "wallaby-com" in out, f"got: {out}"


# --- file_key ---

def test_file_key_deterministic(tmp_path):
    from collect import file_key
    f = tmp_path / "a.pdf"
    f.write_bytes(b"hello world" * 100)
    a = file_key(str(f))
    b = file_key(str(f))
    assert a == b
    assert len(a) == 16


def test_file_key_changes_with_content(tmp_path):
    from collect import file_key
    f1 = tmp_path / "a.pdf"
    f2 = tmp_path / "b.pdf"
    f1.write_bytes(b"content one")
    f2.write_bytes(b"content two")
    assert file_key(str(f1)) != file_key(str(f2))


def test_file_key_rename_invariant(tmp_path):
    from collect import file_key
    f1 = tmp_path / "original.pdf"
    f2 = tmp_path / "renamed.pdf"
    payload = b"identical bytes"
    f1.write_bytes(payload)
    f2.write_bytes(payload)
    # Same content, different filenames → same key
    assert file_key(str(f1)) == file_key(str(f2))


def test_file_key_large_file_streaming(tmp_path):
    """Confirm we don't OOM on a >1MB file (the stream-in-chunks path)."""
    from collect import file_key
    f = tmp_path / "big.pdf"
    f.write_bytes(b"x" * (2 * 1024 * 1024))  # 2 MB
    out = file_key(str(f))
    assert len(out) == 16


def test_file_key_missing_file_raises(tmp_path):
    from collect import file_key
    import pytest
    with pytest.raises(FileNotFoundError):
        file_key(str(tmp_path / "nope.pdf"))


# --- file_slug ---

def test_file_slug_uses_title_when_provided(tmp_path):
    from collect import file_slug
    f = tmp_path / "report.pdf"
    f.write_bytes(b"x")
    out = file_slug(str(f), title="Quarterly Report Q1", date="2026-05-25")
    assert out == "2026-05-25-quarterly-report-q1"


def test_file_slug_falls_back_to_filename_stem(tmp_path):
    from collect import file_slug
    f = tmp_path / "My Report Q1.pdf"
    f.write_bytes(b"x")
    out = file_slug(str(f), title="", date="2026-05-25")
    assert out == "2026-05-25-my-report-q1"


def test_file_slug_strips_accents(tmp_path):
    from collect import file_slug
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    out = file_slug(str(f), title="Café Müller", date="2026-05-25")
    assert out == "2026-05-25-cafe-muller"


def test_file_slug_truncates_long_title(tmp_path):
    from collect import file_slug
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    long_title = "A " * 100  # 200 chars
    out = file_slug(str(f), title=long_title, date="2026-05-25")
    assert len(out) <= 80


def test_file_slug_default_date_is_today_utc(tmp_path):
    import datetime
    from collect import file_slug
    f = tmp_path / "x.pdf"
    f.write_bytes(b"x")
    out = file_slug(str(f), title="hello", date="")
    today = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%d")
    assert out.startswith(today + "-")


def test_file_slug_handles_empty_body_gracefully(tmp_path):
    """File with no slugifiable stem (e.g. all punctuation) → no trailing hyphen."""
    from collect import file_slug
    f = tmp_path / "----.pdf"
    f.write_bytes(b"x")
    out = file_slug(str(f), title="", date="2026-05-25")
    assert out == "2026-05-25"
    assert not out.endswith("-")


# --- conversation_key ---

def test_conversation_key_deterministic():
    from collect import conversation_key
    a = conversation_key("AAQkAGUx...long-guid-string-from-outlook")
    b = conversation_key("AAQkAGUx...long-guid-string-from-outlook")
    assert a == b
    assert len(a) == 16


def test_conversation_key_distinct_inputs_distinct_keys():
    from collect import conversation_key
    a = conversation_key("AAQkAGUx-A")
    b = conversation_key("AAQkAGUx-B")
    assert a != b


def test_conversation_key_empty_string():
    from collect import conversation_key
    out = conversation_key("")
    assert len(out) == 16  # sha256("") prefix


# --- thread_slug ---

def test_thread_slug_basic():
    from collect import thread_slug
    out = thread_slug("2026-05-25T09:30:00Z", "Quarterly Review")
    assert out == "2026-05-25-quarterly-review"


def test_thread_slug_strips_re_prefix():
    from collect import thread_slug
    out = thread_slug("2026-05-25T09:30:00Z", "Re: Quarterly Review")
    assert out == "2026-05-25-quarterly-review"


def test_thread_slug_strips_fwd_prefix():
    from collect import thread_slug
    out = thread_slug("2026-05-25T09:30:00Z", "Fwd: Status Update")
    assert out == "2026-05-25-status-update"


def test_thread_slug_strips_external_tag():
    from collect import thread_slug
    out = thread_slug("2026-05-25T09:30:00Z", "[EXTERNAL] Vendor Quote")
    assert out == "2026-05-25-vendor-quote"


def test_thread_slug_strips_chained_prefixes():
    from collect import thread_slug
    # Real-world replies often chain: "Re: Fwd: Re: original"
    out = thread_slug("2026-05-25T09:30:00Z", "Re: Fwd: Re: Original Subject")
    assert out == "2026-05-25-original-subject"


def test_thread_slug_accent_stripping():
    from collect import thread_slug
    out = thread_slug("2026-05-25T09:30:00Z", "Café Müller meeting")
    assert out == "2026-05-25-cafe-muller-meeting"


def test_thread_slug_length_cap():
    from collect import thread_slug
    long_subject = "A " * 100
    out = thread_slug("2026-05-25T09:30:00Z", long_subject)
    assert len(out) <= 80


def test_thread_slug_empty_subject():
    from collect import thread_slug
    # Subject became empty after prefix stripping
    out = thread_slug("2026-05-25T09:30:00Z", "Re:")
    assert out == "2026-05-25"  # no trailing hyphen


# --- coalesce_messages ---

def _msg(conv_id, received, subject, from_addr, to_addrs=None, cc_addrs=None):
    """Build a minimal Outlook-shaped message dict for tests."""
    return {
        "conversationId": conv_id,
        "receivedDateTime": received,
        "subject": subject,
        "from": {"emailAddress": {"address": from_addr, "name": from_addr.split("@")[0]}},
        "toRecipients": [
            {"emailAddress": {"address": a, "name": a.split("@")[0]}}
            for a in (to_addrs or [])
        ],
        "ccRecipients": [
            {"emailAddress": {"address": a, "name": a.split("@")[0]}}
            for a in (cc_addrs or [])
        ],
    }


def test_coalesce_messages_single_message():
    from collect import coalesce_messages
    msgs = [_msg("conv-1", "2026-05-25T09:00:00Z", "Hello", "a@x.com", ["b@x.com"])]
    out = coalesce_messages(msgs)
    assert len(out) == 1
    assert out[0]["conversation_id"] == "conv-1"
    assert out[0]["message_count"] == 1
    assert out[0]["subject"] == "Hello"


def test_coalesce_messages_multi_message_sorted():
    from collect import coalesce_messages
    msgs = [
        _msg("conv-1", "2026-05-25T11:00:00Z", "Re: Hello", "b@x.com", ["a@x.com"]),
        _msg("conv-1", "2026-05-25T09:00:00Z", "Hello", "a@x.com", ["b@x.com"]),
        _msg("conv-1", "2026-05-25T10:00:00Z", "Re: Hello", "c@x.com", ["a@x.com", "b@x.com"]),
    ]
    out = coalesce_messages(msgs)
    assert len(out) == 1
    conv = out[0]
    assert conv["message_count"] == 3
    assert conv["first_received"] == "2026-05-25T09:00:00Z"
    assert conv["last_received"] == "2026-05-25T11:00:00Z"
    # subject from FIRST message (chronologically), not last
    assert conv["subject"] == "Hello"
    # messages_sorted in chronological order
    received = [m["receivedDateTime"] for m in conv["messages_sorted"]]
    assert received == ["2026-05-25T09:00:00Z", "2026-05-25T10:00:00Z", "2026-05-25T11:00:00Z"]


def test_coalesce_messages_participants_union_dedup():
    from collect import coalesce_messages
    msgs = [
        _msg("conv-1", "2026-05-25T09:00:00Z", "Hi", "a@x.com", ["b@x.com", "c@x.com"]),
        _msg("conv-1", "2026-05-25T10:00:00Z", "Re: Hi", "b@x.com", ["a@x.com"], cc_addrs=["d@x.com"]),
    ]
    out = coalesce_messages(msgs)
    parts = out[0]["participants"]
    assert set(parts) == {"a@x.com", "b@x.com", "c@x.com", "d@x.com"}
    # Order preserved (first-seen wins) — a appears before b which appears before c, d last
    assert parts.index("a@x.com") < parts.index("b@x.com")
    assert parts.index("c@x.com") < parts.index("d@x.com")


def test_coalesce_messages_multiple_conversations():
    from collect import coalesce_messages
    msgs = [
        _msg("conv-A", "2026-05-25T09:00:00Z", "Topic A", "a@x.com"),
        _msg("conv-B", "2026-05-24T15:00:00Z", "Topic B", "b@x.com"),
        _msg("conv-A", "2026-05-25T10:00:00Z", "Re: Topic A", "b@x.com"),
    ]
    out = coalesce_messages(msgs)
    assert len(out) == 2
    # Sorted by first_received ascending
    assert out[0]["conversation_id"] == "conv-B"
    assert out[1]["conversation_id"] == "conv-A"
    assert out[1]["message_count"] == 2


def test_coalesce_messages_skips_messages_with_no_conversation_id():
    from collect import coalesce_messages
    msgs = [
        _msg("conv-1", "2026-05-25T09:00:00Z", "Hi", "a@x.com"),
        {"receivedDateTime": "2026-05-25T10:00:00Z", "subject": "Orphan", "from": {}},
    ]
    out = coalesce_messages(msgs)
    assert len(out) == 1
    assert out[0]["conversation_id"] == "conv-1"


def test_coalesce_messages_accepts_connector_snake_case_conversation_id():
    from collect import coalesce_messages
    msg = _msg("ignored", "2026-05-25T09:00:00Z", "Hi", "a@x.com")
    msg.pop("conversationId")
    msg["conversation_id"] = "conv-snake"

    out = coalesce_messages([msg])

    assert len(out) == 1
    assert out[0]["conversation_id"] == "conv-snake"


# --- Outlook folder selection ---

def test_select_outlook_email_folders_includes_work_folders():
    from collect import select_outlook_email_folders
    folders = [
        {"id": "1", "displayName": "Inbox", "path": "Inbox"},
        {"id": "2", "displayName": "Archive", "path": "Archive"},
        {"id": "3", "displayName": "Sent Items", "path": "Sent Items"},
        {"id": "4", "displayName": "AI", "path": "Projects/AI"},
    ]

    selected = select_outlook_email_folders(folders)

    assert [folder["id"] for folder in selected] == ["1", "2", "3", "4"]


def test_select_outlook_email_folders_excludes_drafts_junk_deleted_and_hidden():
    from collect import select_outlook_email_folders
    folders = [
        {"id": "1", "displayName": "Drafts", "path": "Drafts"},
        {"id": "2", "displayName": "Junk Email", "path": "Junk Email"},
        {"id": "3", "displayName": "Deleted Items", "path": "Deleted Items"},
        {"id": "4", "displayName": "Recoverable Items", "path": "Recoverable Items", "isHidden": True},
        {"id": "5", "displayName": "Vendors", "path": "Vendors"},
    ]

    selected = select_outlook_email_folders(folders)

    assert [folder["id"] for folder in selected] == ["5"]


def test_select_outlook_email_folders_excludes_nested_under_blocked_folders():
    from collect import select_outlook_email_folders
    folders = [
        {"id": "1", "displayName": "AI", "path": "Deleted Items/AI"},
        {"id": "2", "displayName": "Maybe Later", "path": "Junk Email/Maybe Later"},
        {"id": "3", "displayName": "Acme", "path": "Archive/Acme"},
    ]

    selected = select_outlook_email_folders(folders)

    assert [folder["id"] for folder in selected] == ["3"]


# --- sender-domain filtering ---

def test_sender_matches_domain_accepts_acme_sender():
    from collect import sender_matches_domain

    assert sender_matches_domain(_msg("c", "2026-05-25T09:00:00Z", "Hi", "alice@acme.com"), "acme.com")


def test_sender_matches_domain_is_case_insensitive():
    from collect import sender_matches_domain

    assert sender_matches_domain(_msg("c", "2026-05-25T09:00:00Z", "Hi", "Alice@Acme.com"), "acme.com")


def test_sender_matches_domain_rejects_other_domains():
    from collect import sender_matches_domain

    assert not sender_matches_domain(_msg("c", "2026-05-25T09:00:00Z", "Hi", "alice@example.com"), "acme.com")


def test_sender_matches_domain_handles_missing_sender():
    from collect import sender_matches_domain

    assert not sender_matches_domain({"subject": "No sender"}, "acme.com")


# --- Outlook per-folder cursors ---

def test_get_folder_cursor_missing_returns_none():
    from collect import get_folder_cursor

    assert get_folder_cursor({}, "outlook", "Inbox") == "NONE"


def test_get_folder_cursor_reads_folder_specific_cursor():
    from collect import get_folder_cursor
    state = {"outlook": {"folder_cursors": {"Inbox": "2026-05-26T10:00:00Z"}}}

    assert get_folder_cursor(state, "outlook", "Inbox") == "2026-05-26T10:00:00Z"


def test_record_folder_cursor_updates_one_folder_only():
    from collect import record_folder_cursor
    state = {
        "outlook": {
            "seen_ids": ["conv-1"],
            "folder_cursors": {
                "Inbox": "2026-05-26T10:00:00Z",
                "Archive": "2026-05-25T09:00:00Z",
            },
        }
    }

    new_state = record_folder_cursor(state, "outlook", "Archive", "2026-05-26T12:00:00Z")

    assert new_state["outlook"]["folder_cursors"]["Inbox"] == "2026-05-26T10:00:00Z"
    assert new_state["outlook"]["folder_cursors"]["Archive"] == "2026-05-26T12:00:00Z"
    assert new_state["outlook"]["seen_ids"] == ["conv-1"]


def test_record_folder_cursor_does_not_mutate_input():
    from collect import record_folder_cursor
    state = {"outlook": {"folder_cursors": {"Inbox": "2026-05-26T10:00:00Z"}}}

    record_folder_cursor(state, "outlook", "Inbox", "2026-05-26T12:00:00Z")

    assert state["outlook"]["folder_cursors"]["Inbox"] == "2026-05-26T10:00:00Z"


# --- chat_key ---

def test_chat_key_hashes_file_contents(tmp_path):
    import collect
    path = tmp_path / "chat.md"
    path.write_bytes(b"hello")
    assert collect.chat_key(path) == "2cf24dba5fb0a30e"


def test_chat_key_streams_binary_file_contents(tmp_path):
    import collect
    path = tmp_path / "chat.md"
    path.write_bytes(b"hello\nworld\n")
    assert collect.chat_key(path) == "4a1e67f2fe1d1cc7"


def test_chat_key_changes_with_content(tmp_path):
    import collect
    a = tmp_path / "a.md"
    b = tmp_path / "b.md"
    a.write_bytes(b"content one")
    b.write_bytes(b"content two")
    assert collect.chat_key(a) != collect.chat_key(b)


def test_chat_key_returns_16_hex_chars(tmp_path):
    import collect
    path = tmp_path / "chat.md"
    path.write_bytes(b"any content")
    result = collect.chat_key(path)
    assert len(result) == 16
    assert all(c in "0123456789abcdef" for c in result)


def test_chat_key_missing_file_raises(tmp_path):
    import collect
    import pytest
    with pytest.raises(FileNotFoundError):
        collect.chat_key(tmp_path / "nope.md")


# --- chat_slug ---

def test_chat_slug_uses_date_and_title():
    import collect
    assert collect.chat_slug("2026-05-26", "Team Standup Chat") == "2026-05-26-team-standup-chat"


def test_chat_slug_uses_chat_fallback_for_blank_title():
    import collect
    assert collect.chat_slug("2026-05-26", "") == "2026-05-26-chat"


def test_chat_slug_caps_total_length_to_80():
    import collect
    slug = collect.chat_slug("2026-05-26", "A" * 120)
    assert slug.startswith("2026-05-26-")
    assert len(slug) <= 80


def test_chat_slug_strips_accents():
    import collect
    assert collect.chat_slug("2026-05-26", "Café Müller") == "2026-05-26-cafe-muller"


def test_chat_slug_no_trailing_hyphen():
    import collect
    slug = collect.chat_slug("2026-05-26", "---")
    assert not slug.endswith("-")


def test_coalesce_messages_falls_back_to_message_id_when_thread_id_missing():
    from collect import coalesce_messages
    msg = {
        "id": "message-1",
        "receivedDateTime": "2026-05-25T09:00:00Z",
        "subject": "Connector message",
        "sender": {"emailAddress": {"address": "sender@x.com", "name": "Sender"}},
        "toRecipients": [{"emailAddress": {"address": "to@x.com", "name": "To"}}],
    }

    out = coalesce_messages([msg])

    assert len(out) == 1
    assert out[0]["conversation_id"] == "message-1"
    assert out[0]["participants"] == ["sender@x.com", "to@x.com"]


# --- is_low_quality_meeting ---

def test_is_low_quality_meeting_all_bad_signals():
    from collect import is_low_quality_meeting
    assert is_low_quality_meeting(has_transcript=False, attendee_count=2, description_word_count=0) is True


def test_is_low_quality_meeting_has_transcript_saves_it():
    from collect import is_low_quality_meeting
    assert is_low_quality_meeting(has_transcript=True, attendee_count=1, description_word_count=0) is False


def test_is_low_quality_meeting_enough_attendees_saves_it():
    from collect import is_low_quality_meeting
    assert is_low_quality_meeting(has_transcript=False, attendee_count=3, description_word_count=0) is False


def test_is_low_quality_meeting_has_description_saves_it():
    from collect import is_low_quality_meeting
    assert is_low_quality_meeting(has_transcript=False, attendee_count=2, description_word_count=25) is False


# --- email quality helpers ---

def _make_email_thread(from_addr: str, subject: str, message_count: int, words_per_msg: int) -> dict:
    body = ("word " * max(words_per_msg, 1)).strip()
    msg = {
        "from": {"emailAddress": {"address": from_addr, "name": from_addr.split("@")[0]}},
        "body_text": body,
        "receivedDateTime": "2026-05-27T10:00:00Z",
    }
    return {
        "subject": subject,
        "message_count": message_count,
        "messages_sorted": [msg] * message_count,
        "first_received": "2026-05-27T10:00:00Z",
        "last_received": "2026-05-27T10:00:00Z",
        "participants": [from_addr],
    }


def test_email_quality_tier_noreply_sender_drops():
    from collect import email_quality_tier
    thread = _make_email_thread("noreply@example.com", "Hello", 3, 200)
    assert email_quality_tier(thread) == "drop"


def test_email_quality_tier_noise_subject_drops():
    from collect import email_quality_tier
    thread = _make_email_thread("alice@acme.com", "Has invited you to collaborate", 1, 200)
    assert email_quality_tier(thread) == "drop"


def test_email_quality_tier_single_short_drops():
    from collect import email_quality_tier
    thread = _make_email_thread("alice@acme.com", "Hello", 1, 40)
    assert email_quality_tier(thread) == "drop"


def test_email_quality_tier_single_long_triages():
    from collect import email_quality_tier
    thread = _make_email_thread("alice@acme.com", "Project update", 1, 150)
    assert email_quality_tier(thread) == "triage"


def test_email_quality_tier_multi_clean_keeps():
    from collect import email_quality_tier
    thread = _make_email_thread("alice@acme.com", "Project update", 3, 100)
    assert email_quality_tier(thread) == "keep"


def test_email_quality_tier_multi_noreply_drops():
    from collect import email_quality_tier
    thread = _make_email_thread("noreply@example.com", "Newsletter", 3, 200)
    assert email_quality_tier(thread) == "drop"


def test_email_quality_tier_meetgeek_allow_list_keeps():
    from collect import email_quality_tier
    thread = _make_email_thread("noreply@meetgeek.ai", "Meeting Summary", 1, 20)
    assert email_quality_tier(thread) == "keep"


def test_email_quality_tier_out_of_office_multi_drops():
    from collect import email_quality_tier
    thread = _make_email_thread("alice@acme.com", "Out of Office: away this week", 3, 200)
    assert email_quality_tier(thread) == "drop"


# --- meetgeek_key ---

def test_meetgeek_key_deterministic():
    from collect import meetgeek_key
    assert meetgeek_key("abc-123") == meetgeek_key("abc-123")
    assert len(meetgeek_key("abc-123")) == 16


def test_meetgeek_key_distinct_inputs():
    from collect import meetgeek_key
    assert meetgeek_key("meeting-A") != meetgeek_key("meeting-B")


def test_meetgeek_key_empty_string():
    from collect import meetgeek_key
    assert len(meetgeek_key("")) == 16


def test_meetgeek_key_matches_meeting_id_slug_format():
    from collect import meetgeek_key, meeting_id
    slug = meeting_id("AI Review", "2026-05-11T09:00:00Z")
    key = meetgeek_key(slug)
    assert len(key) == 16 and all(c in "0123456789abcdef" for c in key)


# --- is_meetgeek_summary ---

def test_is_meetgeek_summary_from_meetgeek_domain():
    from collect import is_meetgeek_summary
    thread = _make_email_thread("summaries@meetgeek.ai", "Meeting Summary: AI Review", 1, 300)
    assert is_meetgeek_summary(thread) is True


def test_is_meetgeek_summary_subject_prefix():
    from collect import is_meetgeek_summary
    thread = _make_email_thread("someone@example.com", "Meeting Summary: Quarterly Review", 1, 300)
    assert is_meetgeek_summary(thread) is True


def test_is_meetgeek_summary_false_for_normal_thread():
    from collect import is_meetgeek_summary
    thread = _make_email_thread("alice@acme.com", "RE: Project Update", 2, 300)
    assert is_meetgeek_summary(thread) is False


def test_is_meetgeek_summary_subdomain():
    from collect import is_meetgeek_summary
    thread = _make_email_thread("noreply@app.meetgeek.ai", "Meeting notes", 1, 100)
    assert is_meetgeek_summary(thread) is True


# --- meeting_description_word_count (A1: HTML-stripped quality gate input) ---

from collect import meeting_description_word_count, is_low_quality_meeting

TEAMS_INVITE_ONLY = """<html><body><br>
<div class="me-email-text" lang="en-US">
<div aria-hidden="true">________________________________________________________________________________</div>
<div><span style="font-weight:600">Microsoft Teams meeting</span></div>
<div><span>Join: </span><a href="https://teams.microsoft.com/meet/123?p=x">https://teams.microsoft.com/meet/123?p=x</a></div>
<div><span>Meeting ID: </span><span>313 880 197 148 82</span></div>
<div><span>Passcode: </span><span>6uK6H5v2</span></div>
<div><a href="https://aka.ms/JoinTeamsMeeting">Need help?</a> | <a href="https://teams.microsoft.com/l/meetup-join/x">System reference</a></div>
<div><span>For organizers: </span><a href="https://teams.microsoft.com/meetingOptions/?x=1">Meeting options</a></div>
<div aria-hidden="true">________________________________________________________________________________</div>
</div></body></html>"""

REAL_DESCRIPTION = """<html><body>
<div>Hi there,</div>
<div>This is simply a placeholder, we can shift the time to whatever suits you better and discuss the crawler design in detail.</div>
<div>Cheers,</div><div>Zoltan</div>
<div aria-hidden="true">________________________________________________________________________________</div>
<div><span>Microsoft Teams meeting</span></div>
<div><span>Join: </span><a href="https://teams.microsoft.com/meet/456?p=y">link</a></div>
<div aria-hidden="true">________________________________________________________________________________</div>
</body></html>"""


def test_invite_only_body_counts_under_20_words():
    # raw split() on this body gives hundreds of "words"; stripped must be ~0
    assert meeting_description_word_count(TEAMS_INVITE_ONLY) < 20


def test_real_description_counts_words():
    assert meeting_description_word_count(REAL_DESCRIPTION) >= 20


def test_empty_body():
    assert meeting_description_word_count("") == 0
    assert meeting_description_word_count(None) == 0


def test_quality_gate_with_stripped_count():
    # 1:1 no-transcript meeting with boilerplate-only body is low quality
    wc = meeting_description_word_count(TEAMS_INVITE_ONLY)
    assert is_low_quality_meeting(False, 2, wc) is True
    # same meeting with a real description passes the gate
    wc2 = meeting_description_word_count(REAL_DESCRIPTION)
    assert is_low_quality_meeting(False, 2, wc2) is False


# --- grown-thread detection (conv_key -> last_received) ---

def test_check_id_grown_when_newer_last_received():
    state = {"outlook": {"seen_ids": ["abc"], "thread_last": {"abc": "2026-06-03T10:00:00Z"}}}
    assert check_id(state, "outlook", "abc", last_received="2026-06-10T08:00:00Z") == "GROWN"


def test_check_id_seen_when_same_last_received():
    state = {"outlook": {"seen_ids": ["abc"], "thread_last": {"abc": "2026-06-03T10:00:00Z"}}}
    assert check_id(state, "outlook", "abc", last_received="2026-06-03T10:00:00Z") == "SEEN"


def test_check_id_seen_for_legacy_key_without_thread_last():
    # keys recorded before the thread_last map existed stay SEEN (conservative)
    state = {"outlook": {"seen_ids": ["abc"]}}
    assert check_id(state, "outlook", "abc", last_received="2026-06-10T08:00:00Z") == "SEEN"


def test_check_id_new_unaffected_by_last_received():
    state = {"outlook": {"seen_ids": []}}
    assert check_id(state, "outlook", "abc", last_received="2026-06-10T08:00:00Z") == "NEW"


def test_check_id_no_last_received_keeps_legacy_behavior():
    state = {"outlook": {"seen_ids": ["abc"], "thread_last": {"abc": "2026-06-03T10:00:00Z"}}}
    assert check_id(state, "outlook", "abc") == "SEEN"


def test_record_stores_last_received():
    state = record({}, "outlook", "abc", None, last_received="2026-06-03T10:00:00Z")
    assert state["outlook"]["thread_last"]["abc"] == "2026-06-03T10:00:00Z"


def test_record_updates_last_received_on_regrow():
    state = {"outlook": {"seen_ids": ["abc"], "thread_last": {"abc": "2026-06-03T10:00:00Z"}}}
    state = record(state, "outlook", "abc", None, last_received="2026-06-10T08:00:00Z")
    assert state["outlook"]["thread_last"]["abc"] == "2026-06-10T08:00:00Z"
    assert state["outlook"]["seen_ids"].count("abc") == 1


def test_record_without_last_received_leaves_thread_last_untouched():
    state = {"outlook": {"seen_ids": [], "thread_last": {"x": "2026-06-01T00:00:00Z"}}}
    state = record(state, "outlook", "abc", None)
    assert state["outlook"]["thread_last"] == {"x": "2026-06-01T00:00:00Z"}


def test_record_does_not_mutate_input_thread_last():
    orig = {"outlook": {"seen_ids": [], "thread_last": {}}}
    record(orig, "outlook", "abc", None, last_received="2026-06-03T10:00:00Z")
    assert orig["outlook"]["thread_last"] == {}
