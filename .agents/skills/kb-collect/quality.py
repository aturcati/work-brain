"""kb-collect quality filters — email/meeting noise gates, MeetGeek
detection, Outlook folder selection. Imported by collect.py; not run directly.
"""
from __future__ import annotations

import html as _html
import re

_EMAIL_PREFIX_RE = re.compile(
    r"^\s*(?:(?:re|fwd|fw)\s*:\s*|\[(?:external|ext)\]\s*:?\s*)",
    re.IGNORECASE,
)


def _strip_email_prefixes(subject: str) -> str:
    """Repeatedly strip common leading email reply/forward/external prefixes."""
    stripped = subject.strip()
    while True:
        next_stripped = _EMAIL_PREFIX_RE.sub("", stripped, count=1)
        if next_stripped == stripped:
            return stripped
        stripped = next_stripped


COLLECT_ALWAYS_DOMAINS: set[str] = {"meetgeek.ai"}

_NOREPLY_RE = re.compile(
    r"(noreply|no[-_]reply|donotreply|notifications?@|alerts?@|mailer-daemon|postmaster)",
    re.IGNORECASE,
)

_NOISE_SUBJECTS: list[str] = [
    "has invited you",
    "automatic reply",
    "out of office",
    "unsubscribe",
    "meeting recording is now available",
    "your receipt",
    "order confirmation",
]


def _thread_from_address(thread: dict) -> str:
    msgs = thread.get("messages_sorted") or []
    if not msgs:
        return ""
    return _sender_address(msgs[0])


def _thread_word_count(thread: dict) -> int:
    return sum(
        len((m.get("body_text") or m.get("bodyPreview") or "").split())
        for m in (thread.get("messages_sorted") or [])
    )


def _is_noreply_sender(address: str) -> bool:
    return bool(_NOREPLY_RE.search(address))


def _is_noise_subject(subject: str) -> bool:
    stripped = _strip_email_prefixes(subject).lower()
    return any(pattern in stripped for pattern in _NOISE_SUBJECTS)


def email_quality_tier(thread: dict) -> str:
    from_addr = _thread_from_address(thread)
    domain = from_addr.split("@")[-1].lower() if "@" in from_addr else ""

    if any(domain == d or domain.endswith("." + d) for d in COLLECT_ALWAYS_DOMAINS):
        return "keep"

    if _is_noreply_sender(from_addr):
        return "drop"

    subject = thread.get("subject", "")
    if _is_noise_subject(subject):
        return "drop"

    message_count = thread.get("message_count", len(thread.get("messages_sorted") or []))
    word_count = _thread_word_count(thread)

    if message_count == 1 and word_count < 80:
        return "drop"
    if message_count == 1 and word_count >= 80:
        return "triage"

    return "keep"


def is_meetgeek_summary(thread: dict) -> bool:
    from_addr = _thread_from_address(thread)
    domain = from_addr.split("@")[-1].lower() if "@" in from_addr else ""
    if domain == "meetgeek.ai" or domain.endswith(".meetgeek.ai"):
        return True
    subject = _strip_email_prefixes(thread.get("subject", ""))
    return subject.startswith("Meeting Summary:") or subject.startswith("MeetGeek:")


_EXCLUDED_OUTLOOK_FOLDER_SEGMENTS = {
    "deleted items",
    "deleteditems",
    "drafts",
    "junk email",
    "junkemail",
}


def _folder_path(folder: dict) -> str:
    """Return the stable display path exposed by the Outlook connector."""
    return str(folder.get("path") or folder.get("displayName") or folder.get("name") or "")


def _normalise_folder_segment(segment: str) -> str:
    return re.sub(r"\s+", " ", segment.strip().lower())


def select_outlook_email_folders(folders: list[dict]) -> list[dict]:
    """Return non-hidden Outlook folders eligible for Acme email collection."""
    selected: list[dict] = []
    for folder in folders:
        if folder.get("isHidden") or folder.get("is_hidden"):
            continue
        path = _folder_path(folder)
        segments = [_normalise_folder_segment(segment) for segment in path.split("/") if segment.strip()]
        if any(segment in _EXCLUDED_OUTLOOK_FOLDER_SEGMENTS for segment in segments):
            continue
        selected.append(folder)
    return selected


def _sender_address(msg: dict) -> str:
    sender = ((msg.get("from") or msg.get("sender")) or {}).get("emailAddress") or {}
    return str(sender.get("address") or "")


def sender_matches_domain(msg: dict, domain: str) -> bool:
    """Return true when the message sender address belongs to `domain`."""
    address = _sender_address(msg).strip().lower()
    domain = domain.strip().lower().lstrip("@")
    return bool(address and domain and address.endswith(f"@{domain}"))



# Teams invite boilerplate: underscore-rule-delimited join block plus stray
# join/ID/passcode lines that survive outside the block.
_TEAMS_INVITE_BLOCK = re.compile(r"_{20,}.*?_{20,}", re.S)
_TEAMS_BOILERPLATE_LINE = re.compile(
    r"^\s*(microsoft teams[ -]|join[: ]|teilnehmen[: ]|meeting id[: ]|besprechungs-id[: ]"
    r"|passcode[: ]|need help|meeting options|system reference|for organi[sz]ers)",
    re.I,
)
_URL = re.compile(r"https?://\S+")


def meeting_description_word_count(body_html: str) -> int:
    """Word count of an event body with HTML markup, entities, URLs, and
    Teams-invite boilerplate stripped.

    The raw `body.content` of any Teams meeting contains a several-hundred-word
    HTML join block, so counting it verbatim makes the <20-word quality-gate
    branch unreachable. Count only the human-written description.
    """
    text = re.sub(r"<[^>]+>", " ", body_html or "")
    text = _html.unescape(text)
    text = _TEAMS_INVITE_BLOCK.sub(" ", text)
    text = _URL.sub(" ", text)
    kept = [
        line for line in text.splitlines()
        if line.strip() and not _TEAMS_BOILERPLATE_LINE.match(line.strip())
    ]
    return len(" ".join(kept).split())


def is_low_quality_meeting(
    has_transcript: bool,
    attendee_count: int,
    description_word_count: int,
) -> bool:
    """description_word_count must come from meeting_description_word_count()
    (HTML-stripped), never from raw body.content.split()."""
    return (
        not has_transcript
        and attendee_count < 3
        and description_word_count < 20
    )

