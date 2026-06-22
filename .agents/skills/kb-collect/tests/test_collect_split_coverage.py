import json
import re
from pathlib import Path

SKILL_DIR = Path(__file__).parent.parent
BASELINE = Path(__file__).parent / "baseline_steps.json"
SHARED = ["phases/config-check.md", "phases/report-log.md"]


def norm(s):
    s = re.sub(r"\(.*?\)", "", s)
    return re.sub(r"\s+", " ", s).strip().lower()


def steps(t):
    return {norm(m) for m in re.findall(r"- \[ \] \*\*(.+?)\*\*", t)}


def steps_for(provider):
    out = set()
    for f in SHARED:
        out |= steps((SKILL_DIR / f).read_text())
    out |= steps((SKILL_DIR / "providers" / f"{provider}.md").read_text())
    return out


def test_no_step_dropped():
    baseline = json.loads(BASELINE.read_text())
    for prov, want in baseline.items():
        missing = set(want) - steps_for(prov)
        assert not missing, f"{prov}: split dropped steps {sorted(missing)}"
