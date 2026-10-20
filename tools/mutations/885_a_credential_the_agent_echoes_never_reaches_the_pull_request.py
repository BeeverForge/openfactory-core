"""A credential the implementing agent echoes never reaches the pull request: it is shown as
`[credential withheld]`, and the body says so (#885).

Claims:
  - the executor's quote withholds a credential — a token by its prefix, the value of an
    `Authorization` header, a URL's userinfo, a secret of this process — on the RAW text, whole:
    before `_neutralised` (which escapes `_`, so `ghp\\_…` matches nothing and renders whole) and
    before `splitlines` (a key that spans lines is never found line by line);
  - each later pass's line withholds it too, before the whitespace fold (the multi-line key) and
    before the 200-character cut (a token the cut splits leaves a head no shape matches);
  - a URL's userinfo is REPLACED by the marker in the body, never silently dropped;
  - `scrub_credentials` withholds an `Authorization` value after a NAMED scheme (any word there is
    prose: "Authorization: handled centrally …"), in any case, after `:` or `=`, a JSON key's
    quote included; a header value only from 8 characters; a bare `Bearer` value only when it is
    16 token68 characters with a digit; `$` is never part of a value, so `Bearer $GH_TOKEN` stays
    prose;
  - the userinfo pattern needs its `@`, so a URL with no userinfo keeps its host;
  - the platform's `_redact` regex (https userinfo only) is no substitute;
  - the claim above the quote names the withholding.
"""

TEST = "tests/test_a_credential_the_agent_echoes_never_reaches_the_pull_request.py"
MACHINE = "openfactory/orchestrator/machine.py"
MODEL = "openfactory/product/model.py"
#: The preservation property: the cuts that withhold too much must turn THIS test red.
PROSE = TEST + "::test_plain_prose_is_quoted_exactly_as_before"

MUTATIONS = [
    # ── the executor's quote ────────────────────────────────────────────────────────────────────
    ("the quote withholds nothing", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n'),
    ("the quote withholds after neutralising each line", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_without_credentials(_neutralised(line))}" if line.strip() else ">"\n'
     "            for line in text.splitlines()]\n"),
    ("the quote withholds line by line", MACHINE,
     "    text = _without_credentials(text)\n"
     '    return [f"> {_neutralised(line)}" if line.strip() else ">" for line in text.splitlines()]\n',
     '    return [f"> {_neutralised(_without_credentials(line))}" if line.strip() else ">"\n'
     "            for line in text.splitlines()]\n"),
    # ── a later pass's line ─────────────────────────────────────────────────────────────────────
    ("a pass line withholds nothing", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n',
     '    words = " ".join(final_text(res).split())\n'),
    ("a pass line withholds after the 200-character cut", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n'
     "    if not words:\n"
     '        return "the pass ended without a final message"\n'
     "    cut = words[:AGENT_PASS_WORDS_MAX]\n",
     '    words = " ".join(final_text(res).split())\n'
     "    if not words:\n"
     '        return "the pass ended without a final message"\n'
     "    cut = _without_credentials(words[:AGENT_PASS_WORDS_MAX])\n"),
    ("a pass line withholds after the whitespace fold", MACHINE,
     '    words = " ".join(_without_credentials(final_text(res)).split())\n',
     '    words = _without_credentials(" ".join(final_text(res).split()))\n'),
    # ── what is withheld, and how it is said ────────────────────────────────────────────────────
    ("a URL's userinfo is dropped with no marker", MACHINE,
     '    return scrub_credentials(text, userinfo=WITHHELD_CREDENTIAL + "@")\n',
     "    return scrub_credentials(text)\n"),
    ("no Authorization value is withheld", MODEL,
     "    text = _AUTHORIZATION.sub(lambda m: (m.group(1) or m.group(2)) + WITHHELD_CREDENTIAL, "
     "text)\n",
     ""),
    ("any word after Bearer is withheld", MODEL,
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"|(\\bBearer[ \\t]+)[\\w.~+/-]+=*", re.IGNORECASE)\n', PROSE),
    ("a variable reference is read as a value", MODEL,
     '[ \\t]+)[\\w.~+/-]{8,}=*"\n',
     '[ \\t]+)[\\w.~+/$-]{8,}=*"\n', PROSE),
    ("a word after an Authorization scheme is withheld", MODEL,
     '[ \\t]+)[\\w.~+/-]{8,}=*"\n',
     '[ \\t]+)[\\w.~+/-]+=*"\n', PROSE),
    ("any word is read as an Authorization scheme", MODEL,
     '(?:Bearer|Basic|Digest|token|Bot|Negotiate|NTLM"\n'
     '    r"|AWS4-HMAC-SHA256)',
     "[A-Za-z][\\w-]*", PROSE),
    # review on 28e5da94: the forms the shape's comment claims, each its own cut
    ("a lowercase header name is not read", MODEL,
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", re.IGNORECASE)\n',
     '    r"|(\\bBearer[ \\t]+)(?=[\\w.~+/-]*\\d)[\\w.~+/-]{16,}=*", 0)\n'),
    ("a JSON key's closing quote ends the shape", MODEL,
     '(\\bAuthorization[\\"\']?\\s*',
     '(\\bAuthorization\\s*'),
    ("Authorization= is not read", MODEL,
     '\\s*[:=]\\s*',
     '\\s*:\\s*'),
    ("a URL with no userinfo loses its host", MODEL,
     '_USERINFO = re.compile(r"(\\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^\\s/@]+@")\n',
     '_USERINFO = re.compile(r"(\\b[a-zA-Z][a-zA-Z0-9+.-]*://)[^\\s/@]+")\n', PROSE),
    ("the adapters' _redact stands in for the withholding", MACHINE,
     '    return scrub_credentials(text, userinfo=WITHHELD_CREDENTIAL + "@")\n',
     '    return re.sub(r"(https?://)[^@/\\s]+@", r"\\1***@", text)\n'),
    # ── the claim ───────────────────────────────────────────────────────────────────────────────
    ("the claim names no withholding", MACHINE,
     '_CLAIM = ("This is the implementing agent\'s own account, as it wrote it, with any credential '
     'in it "\n'
     '          f"shown as {WITHHELD_CREDENTIAL}. No gate checked it, and the reviewer was not shown '
     'it.")\n',
     '_CLAIM = ("This is the implementing agent\'s own account, as it wrote it. No gate checked it, '
     'and "\n'
     '          "the reviewer was not shown it.")\n'),
]
