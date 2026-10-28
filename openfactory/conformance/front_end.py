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
  · the method is the one the call's options name (`method:"POST"`, the key quoted or not), GET
    where they name none, WS for a `new WebSocket(…)`;
  · what cannot be read off the text is written `?`, never guessed: a method in options that are
    not an object literal (`mfetch(u,o)`), or named by something other than a string literal
    (`method:m`), or that may come from a spread (`{...o}`); and an address whose route is itself
    a runtime value (`/api/${x}`, `/api/v1/${x}`), which would otherwise reach every route of one
    segment there. The suite names such a call, the way it names an address that reaches no
    route;
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

from openfactory.conformance.client import (
           SCHEMA,
           UNREAD,
           UNREAD_SEGMENT,
           Manifest,
           parse_manifest,
)

#: The page, where the package ships it.
PAGE = Path(__file__).resolve().parents[1] / "api" / "panel.html"

CLIENT = "the default front end"

_ADDRESS = re.compile(r"(['\"`])((?:\$\{[^}]*\}//\$\{[^}]*\})?/api/(?:(?!\1).)*?)\1")
_KIND = re.compile(r"\.kind\s*[!=]==\s*[\"'](\w+)[\"']")
#: The options' `method` key, bare or quoted (`method:`, `"method":`, `'method':`).
_METHOD = re.compile(r"(?:\bmethod|([\"'])method\1)\s*:\s*[\"'](\w+)[\"']")
_CALLEE = re.compile(r"(new\s+)?([A-Za-z_$][\w$]*)\s*\(\s*$")
_PLUS = re.compile(r"\s*\+\s*")
#: An address whose first segment after the API's own prefix is a runtime value.
_UNREAD_ROUTE = re.compile(r"^/api/(?:v1/)?\0")
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


def _addresses(code: str, found: re.Match) -> tuple[str, list[str], int, bool]:
    """The text just before the literal, where its callee is; the address it starts as the
    variants the page may call: the first reads an expression after a word as a query, the second
    as a further segment; the index after the address, where the call's next argument is; and
    whether the address can be read at all — one whose route is a runtime value cannot."""
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
    path = text.split("?")[0]
    before = code[max(0, found.start() - 80):found.start()]
    if _UNREAD_ROUTE.match(path):
        return before, [path.replace("\0", UNREAD_SEGMENT)], n, False
    pieces = path.split("\0")
    # an operand after a `/` is a segment; one after a word is a query or a further segment
    variants = [_join(pieces, after_a_word=""), _join(pieces, after_a_word="/x")]
    return before, list(dict.fromkeys(variants)), n, True


def _join(pieces: list[str], *, after_a_word: str) -> str:
    text = pieces[0]
    for piece in pieces[1:]:
        text += ("x" if text.endswith("/") else after_a_word) + piece
    return text


def _top_level(options: str) -> str:
    """An object literal's text with what its values nest blanked out, strings kept, so a key
    found in it is the object's own and not a header's or a body's."""
    out, depth, n = [], 0, 1
    while n < len(options) - 1:
        c = options[n]
        if c in "'\"`":
            end = _string_end(options, n)
            if depth == 0:
                out.append(options[n:end])
            n = end
            continue
        if c in _CLOSE:
            depth += 1
        elif c in ")]}":
            depth -= 1
        elif depth == 0:
            out.append(c)
        n += 1
    return "".join(out)


def _method(code: str, before: str, after: int) -> str:
    """The method of the call whose address ends at `after`, or `UNREAD` where the text cannot
    say it: options that are not an object literal, a `method` that is not a string literal, a
    spread that may carry one."""
    callee = _CALLEE.search(before)
    if callee is None:
        return "GET"  # a link, an image, a download: the browser GETs it
    if callee.group(1) and callee.group(2) == "WebSocket":
        return "WS"
    rest = code[after:_call_end(code, after)].strip()
    if not rest.startswith(","):
        return "GET"
    options = rest[1:].strip()
    if not options:
        return "GET"  # a trailing comma names nothing
    if not options.startswith("{"):
        return UNREAD
    top = _top_level(options[:_call_end(options, 1) + 1])
    named = _METHOD.search(top)
    if named:
        return named.group(2).upper()
    if "..." in top or re.search(r"(?:^|,)\s*(?:method|([\"'])method\1)\s*(?:[:,]|$)", top):
        return UNREAD
    return "GET"


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
        before, variants, after, readable = _addresses(code, found)
        method = _method(code, before, after)
        if not readable:
            out.add((method, variants[0]))
            continue
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


def declared(page: str | None = None) -> Manifest:
    """The default front end's manifest as the suite holds it: the one manifest that may carry the
    `?` and `${…}` this reader writes for what the page's text cannot say."""
    return parse_manifest(manifest(page), source="the default front end's manifest",
                          from_the_reader=True)


def main(argv: list[str] | None = None) -> int:
    """Print the default front end's manifest — an example of the shape, read from the page."""
    del argv
    print(json.dumps(manifest(), indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
