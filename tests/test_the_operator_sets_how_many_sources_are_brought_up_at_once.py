"""The operator sets how many of a product's sources are brought up at once, and the default stays
eight (#369, criterion 4).

`sources.check_out` brought every source up on a pool fixed at `PARALLEL = 8`. Each is one git
process talking to one forge, so at a few hundred sources eight is the bound that decides how long
a first turn waits — and a deployment could not move it. It is `OPENFACTORY_SOURCES_PARALLEL` now,
read when the sources are brought up, and a value nobody can read is eight, said once.

THE PEAK IS REACHED, NOT MERELY ALLOWED. Every stand-in checkout waits on a barrier of `k`: below
`k` at once the barrier breaks, the source is not placed, and the test fails on that; above `k` the
peak counted on entry is more than `k`. No sleep anywhere.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path

import pytest

from openfactory.product import sources

#: A multiple of every `k` below, so each batch of `k` fills its barrier.
N = 24


def _bring_up(k: int, *, calls: int = 1) -> tuple[int, list[sources.Checkouts]]:
    """`check_out` over N sources, `calls` times, through a checkout that waits for `k` at once:
    the peak in flight, and what each call placed."""
    gate = threading.Barrier(k)
    lock = threading.Lock()
    flight = {"now": 0, "peak": 0}

    def checkout(coordinate: str, spelling: str, own: bool) -> sources.Checkout:
        with lock:
            flight["now"] += 1
            flight["peak"] = max(flight["peak"], flight["now"])
        try:
            gate.wait(timeout=10)
        finally:
            with lock:
                flight["now"] -= 1
        return sources.Checkout(path=Path("/nowhere") / coordinate)

    found = sources.Declared(sources=tuple((f"acme/s{i}", f"acme/s{i}") for i in range(N)))
    got = [sources.check_out("", found, checkout) for _ in range(calls)]
    return flight["peak"], got


def test_the_operator_sets_how_many_sources_are_brought_up_at_once(monkeypatch):
    monkeypatch.setenv("OPENFACTORY_SOURCES_PARALLEL", "3")

    peak, [got] = _bring_up(3)

    assert len(got.placed) == N, got.missing
    assert peak == 3


def test_eight_sources_are_brought_up_at_once_when_the_operator_says_nothing(monkeypatch):
    """The criterion keeps the default: this pins it, so moving it is a decision and not a slip."""
    monkeypatch.delenv("OPENFACTORY_SOURCES_PARALLEL", raising=False)

    peak, [got] = _bring_up(8)

    assert len(got.placed) == N, got.missing
    assert peak == 8


@pytest.mark.parametrize(("value", "said"), [("0", 1), ("-2", 1), ("zero", 1), (" ", 0)])
def test_a_parallelism_nobody_can_read_is_eight_and_is_said_once(monkeypatch, caplog, value,
                                                                   said):
    """A bound nobody can read must not become no bound, nor one source at a time — and must not
    be silent. Said once, not once per turn: two turns here, one line. A blank value is unset."""
    monkeypatch.setattr(sources, "_PARALLEL_SAID", set(), raising=False)
    monkeypatch.setenv("OPENFACTORY_SOURCES_PARALLEL", value)
    caplog.set_level(logging.WARNING, logger="openfactory.product")

    peak, got = _bring_up(8, calls=2)

    assert all(len(g.placed) == N for g in got)
    assert peak == 8
    lines = [r.getMessage() for r in caplog.records if r.levelno >= logging.WARNING]
    named = [line for line in lines if "OPENFACTORY_SOURCES_PARALLEL" in line]
    assert len(named) == said, lines
    assert all("8" in line and repr(value) in line for line in named), named
