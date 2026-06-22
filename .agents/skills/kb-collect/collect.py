#!/usr/bin/env python3
# /// script
# dependencies = []
# ///
"""
Collect state helper for kb-collect.

Usage:
  python collect.py --state-file raw/.collect-state.json \
                   --provider teams --action get-cursor
  → prints ISO datetime string or "NONE"

  python collect.py --state-file raw/.collect-state.json \
                   --provider teams --action check-id \
                   --meeting-id 2026-05-06-widget-planning-sync
  → prints "SEEN" or "NEW"

  python collect.py --state-file raw/.collect-state.json \
                   --provider teams --action record \
                   --meeting-id 2026-05-06-widget-planning-sync \
                   [--cursor 2026-05-06T09:00:00Z]
  → prints "RECORDED"

  python collect.py --action meeting-id \
                   --subject "Sprint Planning" \
                   --start "2026-05-08T08:00:00.000Z"
  → prints "2026-05-08-sprint-planning"
"""
import argparse
import hashlib
import html as _html
import json
import re
import sys
import unicodedata
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from quality import (  # noqa: F401  (re-exported for tests and callers)
    COLLECT_ALWAYS_DOMAINS, _EMAIL_PREFIX_RE, _strip_email_prefixes,
    _thread_from_address, _thread_word_count, _is_noreply_sender,
    _is_noise_subject, email_quality_tier, is_meetgeek_summary,
    _EXCLUDED_OUTLOOK_FOLDER_SEGMENTS, _folder_path, _normalise_folder_segment,
    select_outlook_email_folders, _sender_address, sender_matches_domain,
    meeting_description_word_count, is_low_quality_meeting,
)


def slugify(text: str, max_len: int = 50) -> str:
    """Lowercase, strip accents, replace non-alphanumeric runs with hyphens."""
    text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    text = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return text[:max_len].rstrip("-")


_TRACKING_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref",
}


def _normalise_url(url: str) -> str:
    """Return canonical URL form: lowercased scheme/host, no default ports,
    no fragment, no tracking params, no trailing slash on non-root path."""
    parts = urlsplit(url.strip())
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    # Strip default ports
    if (scheme == "https" and netloc.endswith(":443")) or (scheme == "http" and netloc.endswith(":80")):
        netloc = netloc.rsplit(":", 1)[0]
    # Path: strip trailing slash unless it's the root
    path = parts.path or "/"
    if len(path) > 1 and path.endswith("/"):
        path = path.rstrip("/")
    # Query: drop tracking params, preserve order of remaining
    query_pairs = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True)
                   if k not in _TRACKING_PARAMS]
    query = urlencode(query_pairs)
    # Fragment dropped entirely
    return urlunsplit((scheme, netloc, path, query, ""))


def url_key(url: str) -> str:
    """Return 16-hex-char sha256 prefix of normalised URL for idempotency."""
    canonical = _normalise_url(url)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:16]


def url_slug(url: str, title: str = "", date: str = "") -> str:
    """Return `<YYYY-MM-DD>-<slugified-body>` filename slug (≤ 80 chars).

    Body precedence: title (if non-empty) > host+path.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if title.strip():
        body = slugify(title, max_len=60)
    else:
        parts = urlsplit(url)
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        body_raw = f"{host} {parts.path.replace('/', ' ')}"
        body = slugify(body_raw, max_len=60)
    return f"{date}-{body}".rstrip("-")


def file_key(path: str) -> str:
    """Return 16-hex-char sha256 prefix of file contents for idempotency."""
    digest = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(64 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()[:16]


def file_slug(path: str, title: str = "", date: str = "") -> str:
    """Return `<YYYY-MM-DD>-<slugified-body>` filename slug (≤ 80 chars).

    Body precedence: title (if non-empty) > filename stem.
    """
    if not date:
        date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    if title.strip():
        body = slugify(title, max_len=60)
    else:
        body = slugify(Path(path).stem, max_len=60)
    return f"{date}-{body}".rstrip("-")


def chat_key(path: "Path | str") -> str:
    """Return 16-hex-char sha256 prefix of chat export file contents."""
    return file_key(str(path))


def chat_slug(captured_at: str, title: str = "") -> str:
    """Return `<YYYY-MM-DD>-<slugified-title-or-chat>` capped at 80 chars."""
    date = captured_at[:10] if captured_at else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    body = slugify(title or "chat", max_len=69)
    if not body:
        body = "chat"
    return f"{date}-{body}"[:80].rstrip("-")


def conversation_key(conversation_id: str) -> str:
    """Return 16-hex-char sha256 prefix of an Outlook conversation_id."""
    return hashlib.sha256(conversation_id.encode("utf-8")).hexdigest()[:16]


def meetgeek_key(meeting_id: str) -> str:
    return hashlib.sha256(meeting_id.encode("utf-8")).hexdigest()[:16]



def thread_slug(first_received_iso: str, subject: str) -> str:
    """Return `<YYYY-MM-DD>-<slugified-subject>` for an email thread."""
    date = first_received_iso[:10] if len(first_received_iso) >= 10 else "0000-00-00"
    body = slugify(_strip_email_prefixes(subject), max_len=60)
    return f"{date}-{body}".rstrip("-")


def _msg_recipients(msg: dict) -> list[str]:
    """Extract from + to + cc email addresses from an Outlook-shaped message."""
    recipients: list[str] = []
    from_email = ((msg.get("from") or msg.get("sender")) or {}).get("emailAddress") or {}
    if from_email.get("address"):
        recipients.append(from_email["address"])
    for recipient in msg.get("toRecipients") or []:
        address = (recipient.get("emailAddress") or {}).get("address")
        if address:
            recipients.append(address)
    for recipient in msg.get("ccRecipients") or []:
        address = (recipient.get("emailAddress") or {}).get("address")
        if address:
            recipients.append(address)
    return recipients


def _conversation_id(msg: dict) -> str | None:
    """Return best available thread key from raw Graph or connector-shaped payloads."""
    return msg.get("conversationId") or msg.get("conversation_id") or msg.get("id")


def coalesce_messages(messages: list[dict]) -> list[dict]:
    """Group Outlook messages into chronological conversation thread dicts."""
    grouped: dict[str, list[dict]] = {}
    for msg in messages:
        conversation_id = _conversation_id(msg)
        if not conversation_id:
            continue
        grouped.setdefault(conversation_id, []).append(msg)

    threads: list[dict] = []
    for conversation_id, group in grouped.items():
        messages_sorted = sorted(group, key=lambda msg: msg.get("receivedDateTime", ""))
        participants: list[str] = []
        seen_participants: set[str] = set()
        for msg in messages_sorted:
            for address in _msg_recipients(msg):
                if address not in seen_participants:
                    seen_participants.add(address)
                    participants.append(address)

        threads.append({
            "conversation_id": conversation_id,
            "subject": messages_sorted[0].get("subject", ""),
            "first_received": messages_sorted[0].get("receivedDateTime", ""),
            "last_received": messages_sorted[-1].get("receivedDateTime", ""),
            "message_count": len(messages_sorted),
            "participants": participants,
            "messages_sorted": messages_sorted,
        })

    return sorted(threads, key=lambda thread: thread["first_received"])


def meeting_id(subject: str, start: str) -> str:
    """Compute canonical meeting_id from calendar event subject and start datetime."""
    if len(start) < 10 or start[4] != '-' or start[7] != '-':
        raise ValueError(f"start must begin with YYYY-MM-DD, got: {start!r}")
    date = start[:10]
    return f"{date}-{slugify(subject)}"




def get_cursor(state: dict, provider: str) -> str:
    return state.get(provider, {}).get("cursor", "NONE")


def get_folder_cursor(state: dict, provider: str, folder_path: str) -> str:
    return state.get(provider, {}).get("folder_cursors", {}).get(folder_path, "NONE")


def check_id(state: dict, provider: str, mid: str, last_received: str | None = None) -> str:
    provider_state = state.get(provider, {})
    if mid not in provider_state.get("seen_ids", []):
        return "NEW"
    if last_received:
        stored = provider_state.get("thread_last", {}).get(mid)
        # Legacy keys without a thread_last entry stay SEEN (conservative):
        # growth detection only applies once a baseline last_received is recorded.
        if stored and last_received > stored:
            return "GROWN"
    return "SEEN"


def record(state: dict, provider: str, mid: str, cursor: str | None,
           last_received: str | None = None) -> dict:
    """Return new state dict (does not mutate input)."""
    provider_state = dict(state.get(provider, {}))
    seen = list(provider_state.get("seen_ids", []))
    if mid not in seen:
        seen.append(mid)
    provider_state["seen_ids"] = seen
    if cursor is not None:
        provider_state["cursor"] = cursor
    if last_received is not None:
        thread_last = dict(provider_state.get("thread_last", {}))
        thread_last[mid] = last_received
        provider_state["thread_last"] = thread_last
    provider_state["last_seen_at"] = datetime.now(timezone.utc).isoformat()
    return {**state, provider: provider_state}


def record_folder_cursor(state: dict, provider: str, folder_path: str, cursor: str) -> dict:
    """Return new state dict with one provider folder cursor updated."""
    provider_state = dict(state.get(provider, {}))
    folder_cursors = dict(provider_state.get("folder_cursors", {}))
    folder_cursors[folder_path] = cursor
    provider_state["folder_cursors"] = folder_cursors
    provider_state["last_seen_at"] = datetime.now(timezone.utc).isoformat()
    return {**state, provider: provider_state}


def load_state(state_file: Path) -> dict:
    if not state_file.exists():
        return {}
    state = json.loads(state_file.read_text())
    for provider_state in state.values():
        if isinstance(provider_state, dict) and "seen_ids" in provider_state:
            seen = provider_state["seen_ids"]
            if isinstance(seen, list):
                provider_state["seen_ids"] = list(dict.fromkeys(seen))
    return state


def save_state(state_file: Path, state: dict) -> None:
    state_file.parent.mkdir(parents=True, exist_ok=True)
    tmp = state_file.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    tmp.replace(state_file)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--state-file")
    p.add_argument("--provider")
    p.add_argument("--action", required=True,
                   choices=[
                       "get-cursor", "check-id", "record", "meeting-id",
                       "url-key", "url-slug", "file-key", "file-slug",
                       "conversation-key", "thread-slug",
                       "chat-key", "chat-slug",
                       "meetgeek-key",
                   ])
    p.add_argument("--meeting-id", dest="mid")
    p.add_argument("--cursor")
    p.add_argument("--subject")
    p.add_argument("--start")
    p.add_argument("--url")
    p.add_argument("--path")
    p.add_argument("--title")
    p.add_argument("--date")
    p.add_argument("--conversation-id")
    p.add_argument("--first-received")
    p.add_argument("--last-received")
    args = p.parse_args()

    if args.action == "meeting-id":
        if not args.subject or not args.start:
            print("ERROR: --subject and --start required", file=sys.stderr)
            sys.exit(1)
        print(meeting_id(args.subject, args.start))
        return

    if args.action == "url-key":
        if not args.url:
            print("ERROR: --url required for url-key", file=sys.stderr)
            sys.exit(1)
        print(url_key(args.url))
        return
    if args.action == "url-slug":
        if not args.url:
            print("ERROR: --url required for url-slug", file=sys.stderr)
            sys.exit(1)
        print(url_slug(args.url, title=args.title or "", date=args.date or ""))
        return

    if args.action == "file-key":
        if not args.path:
            print("ERROR: --path required for file-key", file=sys.stderr)
            sys.exit(1)
        print(file_key(args.path))
        return
    if args.action == "file-slug":
        if not args.path:
            print("ERROR: --path required for file-slug", file=sys.stderr)
            sys.exit(1)
        print(file_slug(args.path, title=args.title or "", date=args.date or ""))
        return

    if args.action == "chat-key":
        if not args.path:
            print("ERROR: --path required for chat-key", file=sys.stderr)
            sys.exit(1)
        print(chat_key(args.path))
        return
    if args.action == "chat-slug":
        print(chat_slug(args.date or "", title=args.title or ""))
        return

    if args.action == "conversation-key":
        if not args.conversation_id:
            print("ERROR: --conversation-id required for conversation-key", file=sys.stderr)
            sys.exit(1)
        print(conversation_key(args.conversation_id))
        return
    if args.action == "thread-slug":
        if not args.first_received or not args.subject:
            print("ERROR: --first-received and --subject required for thread-slug", file=sys.stderr)
            sys.exit(1)
        print(thread_slug(args.first_received, args.subject))
        return
    if args.action == "meetgeek-key":
        if not args.mid:
            print("ERROR: --meeting-id required for meetgeek-key", file=sys.stderr)
            sys.exit(1)
        print(meetgeek_key(args.mid))
        return

    if not args.state_file or not args.provider:
        print("ERROR: --state-file and --provider required", file=sys.stderr)
        sys.exit(1)

    state_file = Path(args.state_file)
    state = load_state(state_file)

    if args.action == "get-cursor":
        print(get_cursor(state, args.provider))

    elif args.action == "check-id":
        if not args.mid:
            print("ERROR: --meeting-id required", file=sys.stderr)
            sys.exit(1)
        print(check_id(state, args.provider, args.mid, last_received=args.last_received))

    elif args.action == "record":
        if not args.mid:
            print("ERROR: --meeting-id required", file=sys.stderr)
            sys.exit(1)
        new_state = record(state, args.provider, args.mid, args.cursor,
                           last_received=args.last_received)
        save_state(state_file, new_state)
        print("RECORDED")


if __name__ == "__main__":
    main()
