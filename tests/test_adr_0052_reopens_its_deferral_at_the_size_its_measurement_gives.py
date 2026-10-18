"""ADR-0052 reopens the deferral of a relevance filter at the number of sources its own measurement
gives (#369, criterion 5: "a measurement that reopens it").

The view and the map check cost about 5.5 ms per source per turn inside the window, measured at
N = 40 in `docs/measurements/369-the-window/after-n40.json`. A second per turn is therefore near
1000 / 5.5 = 180 sources. The ADR said "near 300" in "What would make it wrong" and "a few hundred"
in the D16 note, so the deferral would have been reopened about 60 % too late (review of #369,
2026-10-18). The measurement is read from the JSON, not from the ADR's prose about it.
"""

from __future__ import annotations

import json
import re
import statistics
from pathlib import Path

import pytest

ROOT = Path(__file__).parent.parent
ADR_0052 = ROOT / "docs" / "adr" / "0052-the-owners-view.md"
MEASURED = ROOT / "docs" / "measurements" / "369-the-window" / "after-n40.json"
A_SECOND_MS = 1000.0


def measured_ms_per_source() -> float:
    """The median view-plus-map cost per source of the turns inside the window (turn 1 clones)."""
    turns = json.loads(MEASURED.read_text(encoding="utf-8"))["window"][1:]
    per_turn = [(t["split"]["view"] + t["split"]["map"]) / t["sources"] for t in turns]
    return statistics.median(per_turn) * 1000


def named_sources(text: str, sentence: str) -> int | None:
    """The number of sources `sentence` (a pattern with one group) names in `text`, comments out."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    found = re.search(sentence, re.sub(r"\s+", " ", text))
    return int(found.group(1)) if found else None


@pytest.mark.parametrize("where,sentence", [
    ("What would make it wrong", r"That is near (\d+) sources at the [\d.]+ ms per source"),
    ("the D16 note", r"the cost reaches a second per turn only near (\d+) sources"),
])
def test_adr_0052_reopens_the_deferral_at_the_sources_a_second_per_turn_takes(where, sentence):
    threshold = A_SECOND_MS / measured_ms_per_source()

    said = named_sources(ADR_0052.read_text(encoding="utf-8"), sentence)

    assert said is not None, f"ADR-0052's {where} names no number of sources a second takes"
    assert abs(said - threshold) <= 0.1 * threshold, (
        f"ADR-0052's {where} says {said} sources; the measurement gives {threshold:.0f}")


def test_and_the_threshold_guard_can_SEE_the_figure_it_replaced():
    """Verify the verifier: the sentence as it stood at 238737f, and one hidden in a comment."""
    old = "That is near 300 sources at the 5.5 ms per source measured on the fixture"
    pattern = r"That is near (\d+) sources at the [\d.]+ ms per source"

    assert named_sources(old, pattern) == 300
    assert abs(300 - A_SECOND_MS / measured_ms_per_source()) > 0.1 * 300
    assert named_sources(f"<!-- {old} -->", pattern) is None
