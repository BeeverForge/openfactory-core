"""The docs say what each remote box's launcher is handed, in the words the code exports (#903).

Criterion 5 of #903: "`configuration.md` and the remote-box section of the extensibility docs say
which launchers receive what."

WHAT THE DOCS SAID BEFORE. Measured on `87875fc9` (2026-10-21), with the code of this change
already in: `docs/reference/configuration.md`'s "A remote box" paragraph said a stored secret is
refused for a remote box "until a launcher can declare that it resolves credential references
itself", a declaration that by then existed; it named neither the attribute a launcher sets, nor
the doctor's line, nor what `fargate` is handed. `docs/core/07-extensibility.md` had no section on
what a launcher is handed at all.

EVERY CLAIM IS READ FROM THE CODE, NEVER FROM A LITERAL HERE: the attribute is
`registry.RESOLVES_REFERENCES_ATTR`; the keyword is what `ResolvesReferences.launch` takes beyond
`RemoteBox.launch`; the words for "references" and "values" are the doctor's own
(`doctor.LAUNCHER_SAID`); the line's name is the check `diagnose` reports for the probe; the
refusal the docs quote is compared with the sentence `box_launch_credentials` raises. Rename any of
them and these tests go red until the docs follow (`tools/mutations/903_…py`). The Markdown is
read by section, with HTML comments stripped, so a note about the docs cannot stand in for them.
"""

from __future__ import annotations

import inspect
import re
from pathlib import Path

import pytest
from pinned_probes import a_fully_pinned_probe_set

from openfactory import credentials, doctor
from openfactory.adapters.credential_store import registry as store_registry
from openfactory.adapters.credential_store.file import DIR_VAR
from openfactory.adapters.sandbox import registry
from openfactory.adapters.sandbox.timeouts import LAUNCHER_TIMEOUT
from openfactory.contracts.project import Project, ProviderRef

ROOT = Path(__file__).resolve().parents[1]
CONFIGURATION = ROOT / "docs" / "reference" / "configuration.md"
EXTENSIBILITY = ROOT / "docs" / "core" / "07-extensibility.md"

#: The configuration reference's section, and the paragraph in it that the remote box owns.
CONFIGURATION_SECTION = "The credential store"
REMOTE_PARAGRAPH_LEAD = "**A remote box**"
#: The extensibility doc's subsection on the launcher's hand-over.
EXTENSIBILITY_SECTION = "What a remote box's launcher is handed"

#: A fictitious secret; the refusal must never carry it.
SECRET = "fictitious-stored-secret-903docs"


def _markdown(path: Path) -> str:
    """The file's text with HTML comments removed, so a comment cannot satisfy a claim."""
    return re.sub(r"<!--.*?-->", "", path.read_text(encoding="utf-8"), flags=re.DOTALL)


def _section(path: Path, title: str) -> str:
    """The body under the heading whose text ends with `title`, up to the next heading of the same
    or a higher level. Fails naming the heading when the doc has none."""
    lines = _markdown(path).splitlines()
    for i, line in enumerate(lines):
        heading = re.match(r"^(#+)\s+(.*?)\s*$", line)
        if heading and heading.group(2).endswith(title):
            level = len(heading.group(1))
            body = []
            for rest in lines[i + 1:]:
                deeper = re.match(r"^(#+)\s", rest)
                if deeper and len(deeper.group(1)) <= level:
                    break
                body.append(rest)
            return "\n".join(body)
    pytest.fail(f"{path.relative_to(ROOT)} has no heading ending with {title!r}")


def _remote_paragraph() -> str:
    """The paragraph of configuration.md's credential-store section that opens with
    `REMOTE_PARAGRAPH_LEAD`, joined onto one line."""
    for paragraph in re.split(r"\n\s*\n", _section(CONFIGURATION, CONFIGURATION_SECTION)):
        if paragraph.lstrip().startswith(REMOTE_PARAGRAPH_LEAD):
            return " ".join(paragraph.split())
    pytest.fail(f"configuration.md's {CONFIGURATION_SECTION!r} section has no paragraph opening "
                f"with {REMOTE_PARAGRAPH_LEAD}")


def _flat(text: str) -> str:
    return " ".join(text.split())


def _docs() -> dict[str, str]:
    return {"configuration.md, " + REMOTE_PARAGRAPH_LEAD: _remote_paragraph(),
            "07-extensibility.md, " + EXTENSIBILITY_SECTION: _flat(
                _section(EXTENSIBILITY, EXTENSIBILITY_SECTION))}


def _remote_kinds() -> list[str]:
    """The core's own remote rows, read from `BOXES`: today `fargate`."""
    return sorted(kind for kind, row in registry.BOXES.items() if row[0].remote)


def _added_keywords() -> set[str]:
    """What a declaring launcher's `launch` takes that every launcher's does not."""
    declaring = inspect.signature(registry.ResolvesReferences.launch).parameters
    every = inspect.signature(registry.RemoteBox.launch).parameters
    return set(declaring) - set(every)


def _doctor_check_name() -> str:
    """The name `diagnose` reports for the launcher probe, read off a finding whose message only
    that probe could have written."""
    sentinel = "the launcher probe's own sentinel message"
    report = doctor.diagnose(a_fully_pinned_probe_set(
        launcher_credentials=lambda: (True, sentinel, "")))
    names = [f.check for f in report.findings if f.message == sentinel]
    assert len(names) == 1, names
    return names[0]


class _DeclaresNothing:
    """A launcher with the signature every launcher had before the declaration."""

    def launch(self, box, *, journal=None, variant="", extra_env=None,
               timeout=LAUNCHER_TIMEOUT, run_id=None):
        raise AssertionError("the hand-over is refused before launch")

    def stop(self, box):
        return 0

    def tail(self, project, issue):
        raise AssertionError("never tailed")


def _refusal(kind: str, tmp_path: Path, monkeypatch) -> str:
    """The sentence `box_launch_credentials` raises for a `kind` launcher that declares nothing,
    when the project's forge secret sits in a `file:` store (modes explicit: the umask must not
    decide, #822's review)."""
    monkeypatch.delenv(store_registry.STORE_VAR, raising=False)
    directory = tmp_path / "credentials"
    directory.mkdir(parents=True)
    directory.chmod(0o700)
    (directory / "acme-forge-token").write_text(SECRET)
    (directory / "acme-forge-token").chmod(0o600)
    monkeypatch.setenv(DIR_VAR, str(directory))
    project = Project(name="deskline", repo_path="/tmp/deskline",
                      tracker=ProviderRef(kind="local", repo="deskline"),
                      forge=ProviderRef(kind="github", repo="acme/deskline",
                                        options={"token_env": f"{store_registry.FILE}:"
                                                              "acme-forge-token"}))
    with pytest.raises(credentials.CredentialUnavailable) as refused:
        credentials.box_launch_credentials(project, kind, _DeclaresNothing())
    assert SECRET not in str(refused.value)
    return _flat(str(refused.value))


def test_the_docs_name_the_declaration_the_code_exports():
    """Both sections name the attribute a launcher sets, as the code reads it, and the
    extensibility section names the protocol and the keyword a declaring launcher must take."""
    declaration = f"`{registry.RESOLVES_REFERENCES_ATTR} = True`"
    for where, text in _docs().items():
        assert declaration in text, f"{where} does not name the declaration {declaration}"
    keywords = _added_keywords()
    assert keywords, "ResolvesReferences.launch takes nothing RemoteBox.launch does not"
    extensibility = _docs()["07-extensibility.md, " + EXTENSIBILITY_SECTION]
    assert f"`{registry.ResolvesReferences.__name__}`" in extensibility
    for keyword in sorted(keywords):
        assert f"`{keyword}`" in extensibility, (
            f"the extensibility section does not name the `{keyword}` keyword a declaring "
            f"launcher's `launch` takes")


def test_the_docs_say_what_a_launcher_is_handed_in_the_doctors_words():
    """Both sections say "references" and "values" in the doctor's own words, and the remote-box
    paragraph names the doctor's line and every remote row the core describes."""
    for where, text in _docs().items():
        for answer in ("references", "values"):
            assert doctor.LAUNCHER_SAID[answer] in text, (
                f"{where} does not say {doctor.LAUNCHER_SAID[answer]!r}, the doctor's words for "
                f"a launcher handed {answer}")
    paragraph = _remote_paragraph()
    assert f"`{_doctor_check_name()}`" in paragraph
    for kind in _remote_kinds():
        assert f"`{kind}`" in paragraph, f"the remote-box paragraph does not say what `{kind}` " \
                                         f"is handed"


def test_the_refusal_the_docs_quote_is_the_one_a_job_meets(tmp_path, monkeypatch):
    """The remote-box paragraph quotes the refusal for the core's remote row, and every fragment of
    the quote (split at an ellipsis) is in the sentence the launch raises."""
    paragraph = _remote_paragraph()
    quotes = [q for q in re.findall(r'"([^"]+)"', paragraph) if credentials.RESOLVES_REFERENCES in q]
    assert quotes, ("the remote-box paragraph quotes no refusal containing "
                    f"{credentials.RESOLVES_REFERENCES!r}")
    for kind in _remote_kinds():
        quoted = [q for q in quotes if f"`{kind}`" in q]
        assert quoted, f"no quoted refusal names the `{kind}` box"
        refusal = _refusal(kind, tmp_path / kind, monkeypatch)
        for quote in quoted:
            for fragment in (f.strip(" ,;") for f in quote.split("…")):
                assert fragment in refusal, (fragment, refusal)
