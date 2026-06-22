# /// script
# requires-python = ">=3.9,<3.14"
# dependencies = []
# ///
import re
from pathlib import Path


def find_matching_meeting(slug: str, wiki_meetings_dir: Path) -> "Path | None":
    exact = wiki_meetings_dir / f"{slug}.md"
    if exact.exists():
        return exact
    # Strip hex suffix (MeetGeek API files: <base-title>-<6hexchars>) and try base slug
    base_slug = re.sub(r"-[0-9a-f]{6}$", "", slug)
    if base_slug != slug:
        base_exact = wiki_meetings_dir / f"{base_slug}.md"
        if base_exact.exists():
            return base_exact
    return None
