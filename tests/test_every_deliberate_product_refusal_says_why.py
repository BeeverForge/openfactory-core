"""Every not-ok `WriteResult` the product module builds says why, or says that nobody decided it (#908).

WHAT WAS WRONG: `WriteResult` had no field saying WHY it was not ok, so `_write_outcome`
(`actions/catalog.py`) could not tell "this card is not yours" from "the forge is down", and
answered both as FAILED — HTTP 500. Measured on 620bb577 (2026-10-20): `product_withdraw_card` by
a product-scoped stranger answered 500 / `failed` with the module's own "only the person who asked
for #1 … can close or remove it".

WHAT IS HELD HERE, READ FROM THE SOURCE BY ITS SYNTAX TREE (a comment or a docstring naming the
field satisfies nothing): every call building a `WriteResult` — or its subclasses `adjust.Sent` and
`accept.Accepted` — with `ok=False` in `openfactory/product/*.py`, including those inside a
`lambda` and a list display, names `refusal=` with a constant of `openfactory.product.authoring`:
one of `REFUSALS` (a decision: "not yours", "already closed", …) or `NOT_REFUSED` (a write that was
tried and did not happen). The one exception is `_could_not`, the module's single failure
constructor, which never sets it: an untagged result IS a failure, and is what an older worker's
dict decodes to.
"""

from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "openfactory" / "product"

#: The constructors of a write's result: the class and the two subclasses that carry more.
_RESULTS = {"WriteResult", "Sent", "Accepted"}
#: The one failure constructor, whose `WriteResult` is untagged on purpose (`module.py`).
_THE_FAILURE = "_could_not"


def _named(func: ast.expr) -> str:
    """`WriteResult`, `adjust.Sent` → the class's own name; anything else → `""`."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _not_ok(call: ast.Call) -> bool:
    """Whether this call says `ok=False`, by keyword or as its first positional argument."""
    for kw in call.keywords:
        if kw.arg == "ok":
            return isinstance(kw.value, ast.Constant) and kw.value.value is False
    first = call.args[0] if call.args else None
    return isinstance(first, ast.Constant) and first.value is False


def _says_why(call: ast.Call, allowed: set[str]) -> bool:
    """Whether `refusal=` is a Name of `authoring` whose value is a reason or `NOT_REFUSED`."""
    value = next((kw.value for kw in call.keywords if kw.arg == "refusal"), None)
    return isinstance(value, ast.Name) and value.id in allowed


def _untagged(source: str, where: str, allowed: set[str]) -> list[str]:
    """`file:line` of every not-ok result built in `source` outside `_could_not` that says no why.

    Walks the whole tree, so a call inside a `lambda` (`found=lambda item: WriteResult(...)`), a list
    display or a nested function is read like any other."""
    tree = ast.parse(source)
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _THE_FAILURE:
            exempt.update(id(inner) for inner in ast.walk(node))
    lines = sorted(node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and id(node) not in exempt
                   and _named(node.func) in _RESULTS and _not_ok(node)
                   and not _says_why(node, allowed))
    return [f"{where}:{line}" for line in lines]


def _allowed() -> set[str]:
    """The names of `authoring`'s constants a `refusal=` may carry, read from their values: every
    reason in `REFUSALS`, and `NOT_REFUSED`. Empty where the vocabulary does not exist."""
    from openfactory.product import authoring

    reasons = set(getattr(authoring, "REFUSALS", ()) or ())
    words = reasons | ({authoring.NOT_REFUSED} if hasattr(authoring, "NOT_REFUSED") else set())
    return {name for name, value in vars(authoring).items()
            if name.isupper() and isinstance(value, str) and value in words}


def test_every_not_ok_write_result_the_product_module_builds_names_its_refusal():
    """Criterion 1: a `WriteResult` the module refuses on purpose carries why. On 620bb577 every
    site is listed here: the field and the vocabulary did not exist."""
    allowed = _allowed()
    offenders = []
    for path in sorted(PRODUCT.glob("*.py")):
        offenders += _untagged(path.read_text(encoding="utf-8"),
                               str(path.relative_to(ROOT)), allowed)

    assert offenders == [], (
        f"{len(offenders)} not-ok results name no `refusal=` from `openfactory.product.authoring` "
        f"(one of REFUSALS, or NOT_REFUSED for a write that was tried and did not happen):\n  "
        + "\n  ".join(offenders))


def test_the_detector_would_catch_one():
    """A guard nobody can fail is not a guard: one untagged site in a lambda, one in a list display,
    one positional — each found; a tagged one and `_could_not`'s own are not."""
    source = (
        "def _could_not(s):\n"
        "    return WriteResult(ok=False, detail=s)\n"
        "def f(x):\n"
        "    g(found=lambda item: WriteResult(ok=False, detail='no'))\n"
        "    out = [adjust.Sent(ok=False, detail='no')]\n"
        "    h = Accepted(False, detail='no')\n"
        "    return WriteResult(ok=False, refusal=NOT_YOURS, detail='not yours')\n"
    )

    found = _untagged(source, "synthetic.py", {"NOT_YOURS", "NOT_REFUSED"})

    assert found == ["synthetic.py:4", "synthetic.py:5", "synthetic.py:6"], found
