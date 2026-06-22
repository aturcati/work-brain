import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from validate import person_requires_works_at


def test_person_requires_works_at_false_for_external_tag():
    fm = {"type": "Person", "slug": "erin-lee98", "tags": ["external"]}
    assert person_requires_works_at(fm) is False


def test_person_requires_works_at_true_without_external_tag():
    fm = {"type": "Person", "slug": "alice-smith", "tags": []}
    assert person_requires_works_at(fm) is True


def test_person_requires_works_at_true_when_tags_missing():
    fm = {"type": "Person", "slug": "alice-smith"}
    assert person_requires_works_at(fm) is True


def test_person_requires_works_at_true_for_mapping_tags():
    fm = {"type": "Person", "slug": "alice-smith", "tags": {"external": True}}
    assert person_requires_works_at(fm) is True


def test_person_requires_works_at_true_for_non_string_list_item():
    fm = {"type": "Person", "slug": "alice-smith", "tags": [123]}
    assert person_requires_works_at(fm) is True
