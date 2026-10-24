"""A model reaches the harness as one token, never as a separate argument after a flag (#741).

A project's model is a value from the registry, and every harness builds a command line from it.
Passed as two tokens — `-m`, then the value, or `--model`, then the value — a value that begins
with `-` would be read by the harness as another option rather than as the model. So the flag and
the value are one token, `--model=<value>`, in every harness argv; the writer also refuses a value
that begins with `-` (`contracts/project.py::model_refused`), and this holds the other half.

THE RULE IS READ OFF THE SOURCE, like the git end-of-options guard: a `-m` or `--model` string
standing alone in a command list is the two-token shape, wherever it is built, so a harness added
later is held without editing this file.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
#: Where a harness turns a project's model into a command line.
HARNESS_DIRS = (ROOT / "openfactory" / "adapters" / "agent",
                ROOT / "openfactory" / "adapters" / "reviewer")
#: The flag spellings that take the model as the NEXT token — the shape this forbids.
SEPARATE = {"-m", "--model"}


def _bare_model_flags(text: str) -> list[tuple[int, str]]:
    """Every `-m`/`--model` string literal that sits inside a list, tuple or call — i.e. a command
    being assembled — in `text`. A docstring or comment naming `--model` is not a literal in an
    argv and is not counted; `f"--model={v}"` is a JoinedStr, not this bare Constant, so the
    one-token form passes."""
    tree = ast.parse(text)
    out: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        elts = (node.elts if isinstance(node, (ast.List, ast.Tuple))
                else node.args if isinstance(node, ast.Call) else [])
        for e in elts:
            if isinstance(e, ast.Constant) and isinstance(e.value, str) and e.value in SEPARATE:
                out.append((e.lineno, e.value))
    return out


def test_no_harness_passes_the_model_as_a_separate_token():
    offenders = {}
    for d in HARNESS_DIRS:
        for path in sorted(d.rglob("*.py")):
            bad = _bare_model_flags(path.read_text(encoding="utf-8"))
            if bad:
                offenders[path.relative_to(ROOT).as_posix()] = bad
    assert not offenders, (
        "a harness passes the model as a flag and a separate value, so a value beginning with "
        f"'-' would be read as an option: {offenders}")


def test_the_reader_tells_the_two_shapes_apart():
    """The guard is worth nothing if it cannot see the shape it forbids, so it is shown both."""
    assert _bare_model_flags('cmd += ["-m", shlex.quote(model)]') == [(1, "-m")]
    assert _bare_model_flags('[harness, "--model", model, "-p", "ok"]') == [(1, "--model")]
    assert _bare_model_flags('cmd += [shlex.quote(f"--model={model}")]') == []
    assert _bare_model_flags('[harness, f"--model={model}", "-p", "ok"]') == []
    # a mention in prose is not an argv
    assert _bare_model_flags('"""  -m, --model <MODEL>  model selection"""') == []
