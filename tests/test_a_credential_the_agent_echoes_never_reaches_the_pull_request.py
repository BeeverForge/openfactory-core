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
import test_the_pull_request_says_what_the_card_says as card_says
import test_walking_skeleton as spine
from test_a_later_pass_adds_its_line_to_what_the_agent_says_it_did import PR, _pass_rows
from test_a_later_pass_adds_its_line_to_what_the_agent_says_it_did import _runner as _repairing
from test_a_later_pass_adds_its_line_to_what_the_agent_says_it_did import _Says as _Repairs
from test_what_the_agent_says_it_did_reaches_the_pull_request import (
    _names_read,
    _opened,
    _quoted_block,
    _Says,
    _section,
)

from openfactory.contracts import AgentRunResult
from openfactory.contracts.run import AGENT_PASS_WORDS_MAX
from openfactory.orchestrator import machine
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
BASIC = "dXNl" + "cjpxN1NFQ1JFVA=="
#: A SPNEGO and an NTLM negotiate message, base64 as the header carries them.
SPNEGO = "YIIB" + "hwYGKwYBBQUCoIIBezCCAXeg"
NTLM_MESSAGE = "TlRMTVNT" + "UAABAAAAB4IIog=="
#: A Digest `response=` (an MD5 hex) and an AWS SigV4 `Signature=` (a SHA-256 hex).
DIGEST_RESPONSE = "6629fae4" + "9393a053" + "97450978" + "507c4ef1"
AWS_SIGNATURE = "5d672d79" + "c15b1316" + "2d9279b0" + "855cfba6" * 2 + "789a8edb" * 3
DB_PASSWORD = "q7" + "hunter" * 3
OPAQUE = "q7" + "OPAQUE" * 5
LINK_PASSWORD = "q7" + "linkpw" * 3
#: A key of this process, PEM-shaped: three lines, its body a line no shape would catch alone.
KEY_BODY = "MIIEv" + "q7KEYBODY" * 6
PEM = "-----BEGIN " + "PRIVATE KEY-----\n" + KEY_BODY + "\n-----END " + "PRIVATE KEY-----"


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
    # review on 28e5da94: a lowercase header name (HTTP/2 and most tooling print it so), a JSON
    # key, and `=` — the forms the shape's comment claims, which no case held
    (f'{SENTINEL}: ran curl -H "authorization: token {HEX_TOKEN}" https://api.example.test/x',
     HEX_TOKEN),
    (f'{SENTINEL}: the client sends {{"Authorization": "token {HEX_TOKEN}"}}', HEX_TOKEN),
    (f"{SENTINEL}: set Authorization=Basic {BASIC} in the env file", BASIC),
    # review on 5fe330d2: a scheme the comment names and nothing held (a Discord bot's header)
    (f"{SENTINEL}: sent Authorization: Bot {HEX_TOKEN}", HEX_TOKEN),
    (f"{SENTINEL}: the proxy sent Authorization: Negotiate {SPNEGO} back", SPNEGO),
    (f"{SENTINEL}: the proxy sent Authorization: NTLM {NTLM_MESSAGE} back", NTLM_MESSAGE),
], ids=["bearer-jwt", "curl-token-hex", "bare-bearer", "lowercase-header", "json-key", "equals",
        "bot", "negotiate", "ntlm"])
def test_the_value_of_an_authorization_header_in_the_agents_message_is_withheld_and_the_body_says_so(
        repo: Path, tmp_path: Path, said: str, secret: str):
    """At 620bb577 none of these values carries a vendor prefix, and `scrub_credentials` returned
    each unchanged: a fix that only calls it would still publish them."""
    _assert_withheld_and_said(_opened(repo, tmp_path, _Says(said)), secret)


@pytest.mark.parametrize("said, secret, kept", [
    (f'{SENTINEL}: it sent Authorization: Digest username="ann", realm="api", nonce="q7nonce", '
     f'uri="/x", response="{DIGEST_RESPONSE}", qop=auth', DIGEST_RESPONSE, 'Digest username="ann"'),
    (f"{SENTINEL}: it sent Authorization: AWS4-HMAC-SHA256 "
     f"Credential=AKIDEXAMPLE/20261021/us-east-1/s3/aws4_request, SignedHeaders=host;x-amz-date, "
     f"Signature={AWS_SIGNATURE}", AWS_SIGNATURE,
     "AWS4-HMAC-SHA256 Credential=AKIDEXAMPLE/20261021/us-east-1/s3/aws4_request"),
    # review on cfe48e02: the scheme in lowercase, as a header name may be written
    (f'{SENTINEL}: it sent authorization: digest username="ann", response="{DIGEST_RESPONSE}"',
     DIGEST_RESPONSE, 'digest username="ann"'),
], ids=["digest", "aws4-hmac-sha256", "digest-lowercase"])
def test_a_signed_header_withholds_its_secret_parameter_and_keeps_the_rest(
        repo: Path, tmp_path: Path, said: str, secret: str, kept: str):
    """Review on 5fe330d2, decision 3: a `Digest` or SigV4 header is a parameter list. At d892b0a3
    the scheme shape put the marker on its FIRST parameter's name (`Digest [credential
    withheld]"ann", … response="6629fae4…"`) and quoted the response or signature — a withholding
    claimed where none happened. Only `response=` and `Signature=` are withheld now; the rest is
    quoted as written."""
    quote = _assert_withheld_and_said(_opened(repo, tmp_path, _Says(said)), secret)
    assert kept in _shown(quote), f"the header's other parameters were not quoted as written: {quote}"


# ── criterion 1: the password of a URL ──────────────────────────────────────────────────────────

@pytest.mark.parametrize("said, secret", [
    (f"{SENTINEL}: the tests use postgres://app:{DB_PASSWORD}@db:5432/app", DB_PASSWORD),
    (f"{SENTINEL}: cloned https://x-access-token:{OPAQUE}@github.com/o/r.git first", OPAQUE),
    (f"{SENTINEL}: the [db](https://u:{LINK_PASSWORD}@host/x) is up", LINK_PASSWORD),
    # review on 5fe330d2: only a userinfo of exactly `git` is left as written — a password after
    # it, or GitLab's CI user whose job token no vendor prefix matches, is withheld
    (f"{SENTINEL}: cloned ssh://git:{DB_PASSWORD}@github.com/o/r.git", DB_PASSWORD),
    (f"{SENTINEL}: CI cloned https://gitlab-ci-token:{OPAQUE}@gitlab.example.test/o/r.git", OPAQUE),
], ids=["postgres", "clone-url", "markdown-link", "git-with-password", "gitlab-ci-token"])
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


# ── criterion 1, for later passes: each pass line ───────────────────────────────────────────────

def _pass_line_after_a_ci_repair(repo: Path, tmp_path: Path, said: str) -> tuple[str, str]:
    """Drive a CI repair that pushed, as the later-pass tests do, and return the body the forge
    holds and the render of its one pass line."""
    card_says._pr_branch(repo)
    runner, forge = _repairing(repo, tmp_path, _Repairs(said))
    runner.repair_ci("#9", "CI failed: test_x", pr_url=PR)
    body = forge.opened["body"]
    rows = _pass_rows(body)
    assert len(rows) == 1, f"the CI repair added no pass line — wrong case: {rows}"
    return body, _rendered(rows[0])


@pytest.mark.parametrize("said, secret", [
    (f"{SENTINEL}: pushed with GH_TOKEN={GITHUB_TOKEN} and CI is green", GITHUB_TOKEN),
    (f"{SENTINEL}: called it with Authorization: Bearer {JWT} and it answered", JWT),
    (f"{SENTINEL}: the job reads postgres://app:{DB_PASSWORD}@db:5432/app now", DB_PASSWORD),
], ids=["github-token", "bearer-jwt", "postgres"])
def test_a_credential_in_a_later_passs_words_is_withheld_and_the_body_says_so(
        repo: Path, tmp_path: Path, said: str, secret: str):
    """At 620bb577 `_pass_words` folded the pass's final message, cut it at
    `AGENT_PASS_WORDS_MAX` and neutralised it, and nothing withheld a credential: the pass line
    carried it."""
    body, row = _pass_line_after_a_ci_repair(repo, tmp_path, said)
    assert secret not in body, f"the credential is in the pass line as written: {_pass_rows(body)}"
    assert secret not in html_lib.unescape(_rendered(body)), (
        f"the credential is in the pass line as rendered: {row}")
    assert WITHHELD_CREDENTIAL in _shown(row), f"the pass line does not say so: {row}"
    assert SENTINEL in _shown(row), f"the pass's own words did not reach its line: {row}"


def test_a_credential_cut_by_the_pass_lines_200_characters_is_withheld_whole(
        repo: Path, tmp_path: Path):
    """A token that starts 10 characters before the cut: cut first, its head is too short for any
    shape to match, and the line published `ghp_q7SECR` — measured at 620bb577, where nothing
    withheld it at all. Withholding before the cut leaves none of it."""
    start = AGENT_PASS_WORDS_MAX - 10
    lead = SENTINEL + " " + "a" * (start - len(SENTINEL) - 2)
    said = f"{lead} {GITHUB_TOKEN} was the token used"
    assert said.index(GITHUB_TOKEN) == start, "the token does not straddle the cut — wrong case"
    head = GITHUB_TOKEN[:10]  # what a cut before the withholding keeps: `ghp_q7SECR`
    body, row = _pass_line_after_a_ci_repair(repo, tmp_path, said)
    assert head not in _shown(row), f"the head of a token the cut split is in the pass line: {row}"
    assert head not in html_lib.unescape(_rendered(body)), "the token's head is in the body"


def test_a_secret_of_this_process_that_spans_lines_is_withheld_from_the_quote_and_the_pass_line(
        repo: Path, tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """A key the process holds (`_SECRET_NAME` names `…KEY_CONTENT`, as the GitHub App key is
    passed) is a value with newlines: matched line by line, or after the pass line's whitespace
    fold, it is never found whole. At 620bb577 its three lines were quoted, and folded onto the
    pass line."""
    monkeypatch.setenv("SOME_APP_KEY_CONTENT", PEM)
    said = f"{SENTINEL}: signed with\n{PEM}\nand it verified"

    (tmp_path / "opened").mkdir()
    opened = _opened(repo, tmp_path / "opened", _Says(said))
    quote = _rendered("\n".join(_quoted_block(opened)))
    assert KEY_BODY not in opened and KEY_BODY not in html_lib.unescape(_rendered(opened)), (
        f"the key is quoted: {_quoted_block(opened)}")
    assert WITHHELD_CREDENTIAL in _shown(quote), f"the quote does not say so: {quote}"

    body, row = _pass_line_after_a_ci_repair(repo, tmp_path / "repaired", said)
    assert KEY_BODY not in body and KEY_BODY not in _shown(row), f"the key is on the pass line: {row}"
    assert WITHHELD_CREDENTIAL in _shown(row), f"the pass line does not say so: {row}"


# ── "Plain prose is quoted unchanged" ───────────────────────────────────────────────────────────

#: Each a near miss of a shape the withholding reads: the scheme word with no value, a variable
#: reference where a value would stand, a word too short to be a header's value, a prefix named but not used, an address with no userinfo.
NEAR_MISSES = [
    "a Bearer header",
    "the Bearer credential every route accepts",
    "Bearer authentication",
    'curl -H "Authorization: Bearer $GH_TOKEN"',
    'curl -H "Authorization: Bearer $GH_TOKEN_2"',          # a variable whose name has the mark
    "send an Authorization: Bearer token with it",
    "- Authorization: handled centrally in middleware.py",   # a word, not a scheme (review on 28e5da94)
    "Authorization: see docs/authorization.md for details",
    # review on 5fe330d2: an English word after a named scheme, and a short value with a digit
    "Authorization: Basic authentication is kept for the legacy API",
    "Authorization: token validation now happens in middleware.py",
    "Authorization: token v2 only",
    "Authorization: Basic username/password pairs are refused now",  # review on cfe48e02
    "Authorization: requires OAuth2.0 scopes on every route",  # a word, not a scheme, before a mark
    "ghp_ is the prefix of a personal token",
    "sk-learn",
    "https://octocat.github.io/x",
    "https://github.com/@octocat",
    "a@b.com",
    "git@github.com:o/r.git",
    "ssh://git@github.com/o/r.git",                         # `git` is never a credential
    "postgres://db:5432/app",
    "see #12, @ann and foo_bar in x.py",
]


@pytest.mark.parametrize("prose", NEAR_MISSES)
def test_plain_prose_is_quoted_exactly_as_before(repo: Path, tmp_path: Path, prose: str):
    """Green at 620bb577 by design: a preservation property cannot be red before the change. It
    holds the withholding to credentials — the mutation plan's cuts that loosen the bare-`Bearer`
    condition, admit `$` to a value, or drop the userinfo's `@` turn it red. The quote is the
    neutralised message, row for row, and the pass line its neutralised fold."""
    said = f"{prose}\n\nand {prose} again"
    expected = [f"> {machine._neutralised(line)}" if line.strip() else ">"
                for line in said.splitlines()]
    assert _quoted_block(_opened(repo, tmp_path, _Says(said))) == expected

    words = machine._pass_words(AgentRunResult(ok=True, summary=said))
    assert words == machine._neutralised(" ".join(said.split())), words
