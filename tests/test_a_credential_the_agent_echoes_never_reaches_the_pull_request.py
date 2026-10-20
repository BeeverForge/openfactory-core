"""A credential the implementing agent echoes never reaches the pull request: it is shown as
`[credential withheld]`, and the body says so (#885).

MEASURED AT 620bb577. Since #859 the pull request body ends with `## What the agent says it did`:
the executor's whole final message quoted (`_account_of` → `_quoted`) and one line per later pass
(`_pass_words`). Nothing between the agent's final message and the forge withheld a credential —
`orchestrator/machine.py` imported no scrub and called no `_redact` — so a token the agent pasted
from a log, a `curl` it ran, or a clone URL it printed was published on the forge.

The platform's own scrub, `product.model.scrub_credentials`, measured with `.venv/bin/python` at
620bb577 on the synthetic values these tests build, would not have been enough either:
- `ghp_…`, `github_pat_…`: withheld, `[credential withheld]` (`_CREDENTIAL_SHAPES`);
- `Authorization: Bearer <JWT>`, `-H "Authorization: token <40 hex>"`, `Bearer <32 characters>`:
  returned UNCHANGED — only a value carrying a known prefix (`Bearer ghp_…`) was caught;
- `postgres://app:<pw>@db:5432/app`, `https://x-access-token:<opaque>@github.com/o/r.git`,
  `[db](https://u:<pw>@host/x)`: the userinfo DROPPED SILENTLY (`postgres://db:5432/app`) — the
  secret gone, nothing saying so, which fails "the body says it was redacted".

Every guard drives the real `JobRunner.run` and reads the body the forge was handed, and every
absence is asserted on the raw body AND its CommonMark render: the source escapes `_`
(`ghp\\_…`), so a raw-text search misses a token the reader sees whole (lessons 4 and 9).

Synthetic credentials are built at run time, never written whole (as `tests/the_product_bed.py`
plants its own), so no secret scanner or push protection reads a literal in this file.
"""

from __future__ import annotations

import html as html_lib
import os
import re
from pathlib import Path

import pytest
import test_walking_skeleton as spine
from test_what_the_agent_says_it_did_reaches_the_pull_request import (
    _names_read,
    _opened,
    _quoted_block,
    _Says,
    _section,
)

from openfactory.product import model
from openfactory.product.model import WITHHELD_CREDENTIAL

repo = spine.repo

CLAIM_WORDS = "No gate checked it, and the reviewer was not shown it."
#: A word of the agent's that is no credential: it must reach the quote, so a fix that drops the
#: whole message cannot pass for one that withholds the credential in it.
SENTINEL = "SENTINEL-885"

GITHUB_TOKEN = "ghp_" + "q7" + "SECRET" * 6
GITHUB_PAT = "github_pat_" + "11AB" + "q7SECRET" * 4
JWT = ("eyJ" + "hbGciOiJIUzI1NiJ9") + "." + ("eyJ" + "zdWIiOiIxMjM0In0") + "." + ("q7" + "SECRETsig" * 3)
HEX_TOKEN = "5e" + "c4e7" * 9 + "a1"
BARE_BEARER = "q7SECRET" * 4
DB_PASSWORD = "q7" + "hunter" * 3
OPAQUE = "q7" + "OPAQUE" * 5
LINK_PASSWORD = "q7" + "linkpw" * 3


@pytest.fixture(autouse=True)
def _no_secret_of_this_process(monkeypatch: pytest.MonkeyPatch) -> None:
    """A secret-named variable of the machine running the suite (`GH_TOKEN` on a person's box or
    in CI) must not change what is withheld: these tests hold the SHAPES, not the environment."""
    for name in list(os.environ):
        if model._SECRET_NAME.search(name):
            monkeypatch.delenv(name, raising=False)


def _rendered(markdown: str) -> str:
    markdown_it = pytest.importorskip("markdown_it", reason="markdown-it-py renders the body")
    return markdown_it.MarkdownIt("commonmark").render(markdown)


def _shown(fragment_html: str) -> str:
    """The text a reader sees: the tags dropped, the entities decoded."""
    return html_lib.unescape(re.sub(r"<[^>]+>", "", fragment_html))


def _assert_withheld_and_said(body: str, secret: str) -> str:
    """`secret` is nowhere in the body (its source, or its render, attributes included), the
    marker stands in the agent's quote, and the agent's other words are still quoted. Returns the
    quote's render."""
    assert secret not in body, f"the credential is in the pull request body as written: {body}"
    whole = html_lib.unescape(_rendered(body))
    assert secret not in whole, f"the credential is in the pull request body as rendered: {whole}"
    quote = _rendered("\n".join(_quoted_block(body)))
    assert WITHHELD_CREDENTIAL in _shown(quote), (
        f"the quote does not say a credential was withheld: {_quoted_block(body)}")
    assert SENTINEL in _shown(quote), f"the agent's own words did not reach the quote: {quote}"
    return quote


# ── criterion 1: a token by its prefix ───────────────────────────────────────────────────────────

@pytest.mark.parametrize("token", [GITHUB_TOKEN, GITHUB_PAT], ids=["ghp", "github_pat"])
def test_a_github_token_in_the_agents_message_is_withheld_and_the_body_says_so(
        repo: Path, tmp_path: Path, token: str):
    """At 620bb577 the executor's message was quoted with the token in it: `_neutralised` escaped
    its `_`, so the source read `ghp\\_q7…` and GitHub rendered the whole token."""
    said = f"{SENTINEL}: pushed with GH_TOKEN={token} and the remote accepted it"
    _assert_withheld_and_said(_opened(repo, tmp_path, _Says(said)), token)


# ── criterion 1: the value of an Authorization header ───────────────────────────────────────────

@pytest.mark.parametrize("said, secret", [
    (f"{SENTINEL}: I called it with Authorization: Bearer {JWT} and it answered 200", JWT),
    (f'{SENTINEL}: ran curl -H "Authorization: token {HEX_TOKEN}" https://api.example.test/x',
     HEX_TOKEN),
    (f"{SENTINEL}: the route accepts Bearer {BARE_BEARER} for now", BARE_BEARER),
], ids=["bearer-jwt", "curl-token-hex", "bare-bearer"])
def test_the_value_of_an_authorization_header_in_the_agents_message_is_withheld_and_the_body_says_so(
        repo: Path, tmp_path: Path, said: str, secret: str):
    """At 620bb577 none of these values carries a vendor prefix, and `scrub_credentials` returned
    each unchanged: a fix that only calls it would still publish them."""
    _assert_withheld_and_said(_opened(repo, tmp_path, _Says(said)), secret)


# ── criterion 1: the password of a URL ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("said, secret", [
    (f"{SENTINEL}: the tests use postgres://app:{DB_PASSWORD}@db:5432/app", DB_PASSWORD),
    (f"{SENTINEL}: cloned https://x-access-token:{OPAQUE}@github.com/o/r.git first", OPAQUE),
    (f"{SENTINEL}: the [db](https://u:{LINK_PASSWORD}@host/x) is up", LINK_PASSWORD),
], ids=["postgres", "clone-url", "markdown-link"])
def test_the_password_of_a_url_in_the_agents_message_is_withheld_and_the_body_says_so(
        repo: Path, tmp_path: Path, said: str, secret: str):
    """At 620bb577 the password was quoted; `scrub_credentials` would have dropped it with nothing
    in its place, so the body could not say it withheld anything. A markdown link's destination is
    kept raw by `_neutralised`, so a scrub after it would miss the third. The host left after the
    marker must notify nobody."""
    quote = _assert_withheld_and_said(_opened(repo, tmp_path, _Says(said)), secret)
    assert _names_read(quote) == [], f"a name in the withheld URL is read: {quote}"


# ── criterion 1: "the body says it was redacted" — the platform's own sentence stays true ───────

def test_the_claim_above_the_quote_says_credentials_in_it_are_withheld(repo: Path, tmp_path: Path):
    """At 620bb577 the claim read "This is the implementing agent's own account, as it wrote it.":
    false once a credential in it is shown as the marker."""
    body = _opened(repo, tmp_path, _Says(f"{SENTINEL}: did the work"))
    claim = _section(body)[1]
    assert CLAIM_WORDS in claim, f"the row after the heading is not the claim: {claim!r}"
    assert WITHHELD_CREDENTIAL in claim, f"the claim names no withholding: {claim!r}"
