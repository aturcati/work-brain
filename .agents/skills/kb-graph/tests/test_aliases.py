import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from project import build_aliases


def _make_page(slug, node_type, aliases=None):
    return {"slug": slug, "type": node_type, "fm": {"aliases": aliases or []}}


def test_build_aliases_slug_entry():
    pages = [_make_page("alice-smith", "Person")]
    result = build_aliases(pages)
    assert result["by_alias"]["alice-smith"] == {"slug": "alice-smith", "type": "Person"}
    assert result["by_slug"]["alice-smith"] == "Person"


def test_build_aliases_display_name():
    pages = [_make_page("alice-smith", "Person", ["Alice Smith"])]
    result = build_aliases(pages)
    assert result["by_alias"]["alice smith"] == {"slug": "alice-smith", "type": "Person"}


def test_build_aliases_multiple_aliases():
    pages = [_make_page("widget-pricing", "Topic", ["Widget Pricing", "Widget Cost Estimate"])]
    result = build_aliases(pages)
    assert "widget pricing" in result["by_alias"]
    assert "widget cost estimate" in result["by_alias"]
    assert result["by_alias"]["widget pricing"]["slug"] == "widget-pricing"


def test_build_aliases_multiple_pages():
    pages = [
        _make_page("alice-smith", "Person", ["Alice Smith"]),
        _make_page("acme", "Org", ["Acme", "Acme Corp"]),
    ]
    result = build_aliases(pages)
    assert result["by_slug"]["acme"] == "Org"
    assert result["by_alias"]["acme corp"]["slug"] == "acme"


def test_build_aliases_no_aliases_field():
    pages = [_make_page("2026-05-11-status-review", "Meeting", [])]
    result = build_aliases(pages)
    assert "2026-05-11-status-review" in result["by_alias"]
    assert result["by_slug"]["2026-05-11-status-review"] == "Meeting"


def test_build_aliases_empty_pages():
    assert build_aliases([]) == {"by_alias": {}, "by_slug": {}}
