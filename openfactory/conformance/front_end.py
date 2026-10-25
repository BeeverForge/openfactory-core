"""The default front end's manifest, read from the page the package ships — never written by hand.

The default front end is a client of the API like any other, and it is held to the same suite: its
manifest is what `panel.html` calls, read from the page each time it is asked for, so the page and
the manifest cannot drift — there is no second copy for either to drift from. The core's own tests
run the suite with it against the app, and `openfactory conformance-client` runs it against a
deployment when no `--manifest` is given.

HOW A CALL IS READ. The page has no build step and no module graph, so there is nothing to import;
what it calls is read from its code, with its comments left out, the way the contract's own test
reads the addresses (`tests/test_the_front_end_api_is_a_contract.py`):

  · an address is a string that starts `/api/` (a socket's starts with the page's own host), with
    what the page concatenates to it: a `${…}` or an expression after a `/` is one segment, and an
    expression after a word is a query or a further segment, so the route either would reach is
    claimed — the further one only where the release has it;
  · the method is the one the call's options name (`method:"POST"`), GET where they name none, WS
    for a `new WebSocket(…)`;
  · the event kinds are the ones the page compares a frame's `kind` with (`m.kind==="said"`).

Each address becomes the release's route it reaches. One that reaches none stays as the page
writes it, so the suite names it: a page calling a route the API does not have is the finding.

WHAT IT DOES NOT READ YET: the fields. The page reads a body through variables a reading of the text
cannot follow, so the default front end's manifest names its routes and its event kinds, and no
field; a client of one's own names its fields in its own manifest.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

from openfactory.conformance.client import SCHEMA

#: The page, where the package ships it.
PAGE = Path(__file__).resolve().parents[1] / "api" / "panel.html"

CLIENT = "the default front end"

_ADDRESS = re.compile(r"(['\"`])((?:\$\{[^}]*\}//\$\{[^}]*\})?/api/(?:(?!\1).)*?)\1")
_KIND = re.compile(r"\.kind\s*[!=]==\s*[\"'](\w+)[\"']")
_METHOD = re.compile(r"\bmethod\s*:\s*[\"'](\w+)[\"']")
_CALLEE = re.compile(r"(new\s+)?([A-Za-z_$][\w$]*)\s*\(\s*$")
_PLUS = re.compile(r"\s*\+\s*")
_CLOSE = {"(": ")", "[": "]", "{": "}"}


def _code(page: str) -> str:
    """The page with its comments left out — the explanation of a call is not a call."""
    code = re.sub(r"/\*.*?\*/|<!--.*?-->", "", page, flags=re.S)
    return "\n".join(line for line in code.splitlines() if not line.strip().startswith("//"))


def _string_end(code: str, at: int) -> int:
    """The index after the string literal opening at `at`."""
    quote, n = code[at], at + 1
    while n < len(code) and code[n] != quote:
        n += 2 if code[n] == "\\" else 1
    return n + 1


def _expression_end(code: str, at: int) -> int:
    """The index after one operand of a `+`, brackets and strings read through."""
    depth, n = 0, at
    while n < len(code):
        c = code[n]
        if c in "'\"`":
            n = _string_end(code, n)
            continue
        if c in _CLOSE:
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return n
            depth -= 1
        elif depth == 0 and c in "+,;?:\n":
            return n
        n += 1
    return n


def _call_end(code: str, at: int) -> int:
    """The index of the `)` closing the call whose arguments continue at `at`."""
    depth, n = 0, at
    while n < len(code):
        c = code[n]
        if c in "'\"`":
            n = _string_end(code, n)
            continue
        if c in _CLOSE:
            depth += 1
        elif c in ")]}":
            if depth == 0:
                return n
            depth -= 1
        n += 1
    return n


def _addresses(code: str, found: re.Match) -> tuple[str, list[str]]:
    """The text just before the literal, where its callee is, and the address it starts as the
    variants the page may call: the first reads an expression after a word as a query, the second
    as a further segment."""
    text = re.sub(r"\$\{[^}]*\}", "\0", found.group(2))
    text = re.sub(r"^\0//\0", "", text)
    n = found.end()
    while True:
        plus = _PLUS.match(code, n)
        if not plus:
            break
        n = plus.end()
        if code[n] in "'\"`":
            end = _string_end(code, n)
            text += re.sub(r"\$\{[^}]*\}", "\0", code[n + 1:end - 1])
        else:
            end = _expression_end(code, n)
            text += "\0"
        n = end
    pieces = text.split("?")[0].split("\0")
    # an operand after a `/` is a segment; one after a word is a query or a further segment
    variants = [_join(pieces, after_a_word=""), _join(pieces, after_a_word="/x")]
    return code[max(0, found.start() - 80):found.start()], list(dict.fromkeys(variants))


def _join(pieces: list[str], *, after_a_word: str) -> str:
    text = pieces[0]
    for piece in pieces[1:]:
        text += ("x" if text.endswith("/") else after_a_word) + piece
    return text


def _method(code: str, before: str, found: re.Match) -> str:
    callee = _CALLEE.search(before)
    if callee is None:
        return "GET"  # a link, an image, a download: the browser GETs it
    if callee.group(1) and callee.group(2) == "WebSocket":
        return "WS"
    named = _METHOD.search(code[found.end():_call_end(code, found.end())])
    return named.group(1).upper() if named else "GET"


def _reaches(called: str, route: str) -> bool:
    """Whether an address the page writes can be `route`, segment by segment: an `x` the page fills
    may be any segment, a route's `{parameter}` any segment the page writes, `{…:path}` the rest."""
    mine, theirs = called.strip("/").split("/"), route.strip("/").split("/")
    for n, segment in enumerate(theirs):
        if segment.endswith(":path}"):
            return len(mine) > n
        if n >= len(mine) or not (mine[n] == "x" or segment.startswith("{")
                                  or mine[n] == segment):
            return False
    return len(mine) == len(theirs)


def _release_routes() -> set[tuple[str, str]]:
    from fastapi.routing import APIRoute, APIWebSocketRoute

    from openfactory.api.app import app

    routes = set()
    for r in app.routes:
        if isinstance(r, APIWebSocketRoute):
            routes.add(("WS", r.path))
        elif isinstance(r, APIRoute):
            routes.update((m, r.path) for m in r.methods or ())
    return {(m, p) for m, p in routes if p.startswith("/api/")}


def calls(page: str) -> set[tuple[str, str]]:
    """Every `(method, route)` the page calls: the release's route each address reaches, or the
    address as the page writes it when it reaches none."""
    code = _code(page)
    routes = _release_routes()
    out = set()
    for found in _ADDRESS.finditer(code):
        before, variants = _addresses(code, found)
        method = _method(code, before, found)
        for n, address in enumerate(variants):
            reached = {(m, p) for m, p in routes if m == method and _reaches(address, p)}
            if reached:
                out |= reached
            elif n == 0:
                out.add((method, address))
    return out


def manifest(page: str | None = None) -> dict:
    """The default front end's manifest, as `openfactory.conformance.client` reads one."""
    page = PAGE.read_text(encoding="utf-8") if page is None else page
    return {"schema": SCHEMA, "client": CLIENT,
            "routes": [{"method": m, "path": p} for m, p in sorted(calls(page))],
            "events": [{"kind": k} for k in sorted(set(_KIND.findall(_code(page))))]}


def main(argv: list[str] | None = None) -> int:
    """Print the default front end's manifest — an example of the shape, read from the page."""
    del argv
    print(json.dumps(manifest(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
