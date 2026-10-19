"""The rule "one deployment, one GitHub organisation" is written where an operator reads (#743, S3).

One process authenticates as one GitHub App installation (`OPENFACTORY_GH_APP_INSTALLATION_ID` is
process-wide) and an installation belongs to one account, so a deployment serves the projects of
one organisation. Before #743 that rule and its reason lived only in a comment in
`openfactory/registry.py` and in a test: `docs/configuration.md` §5 "Projects", the page a person
onboarding a project reads, said nothing of it, and the first they heard was `project add`
refusing their second organisation.

The guard parses the reference into sections (HTML comments and fenced code stripped first, so a
`# NOTE:` line in a YAML block is not a heading and a hidden comment does not satisfy it), and
reads the check id from `doctor.INSTALLATION_SCOPE`, the value the doctor emits.
"""

from __future__ import annotations

import re
from pathlib import Path

from openfactory import doctor

CONFIGURATION = Path(__file__).resolve().parent.parent / "docs" / "configuration.md"


def _sections(text: str) -> list[tuple[int, str, str]]:
    """`(level, heading, body)` for every heading outside fenced code, comments removed."""
    text = re.sub(r"<!--.*?-->", "", text, flags=re.S)
    sections: list[tuple[int, str, list[str]]] = []
    fenced = False
    for line in text.splitlines():
        if line.lstrip().startswith("```"):
            fenced = not fenced
            continue
        if fenced:
            continue
        heading = re.match(r"^(#{1,6})\s+(.*?)\s*$", line)
        if heading:
            sections.append((len(heading.group(1)), heading.group(2), []))
        elif sections:
            sections[-1][2].append(line)
    return [(level, title, "\n".join(body)) for level, title, body in sections]


def _under_projects(sections):
    """The sections nested under `## 5. Projects`, up to the next level-2 heading."""
    inside = False
    for level, title, body in sections:
        if level <= 2:
            inside = level == 2 and re.match(r"5\.\s+Projects\b", title) is not None
            continue
        if inside:
            yield title, body


def test_the_configuration_reference_states_the_rule_its_reason_and_the_way_to_run_two():
    """S3: "`docs/configuration.md` states the rule and its reason … and how to run one deployment
    per organisation". Before #743 §5 had no such section (the lookup found nothing): the rule
    was a comment in `registry.py` that nobody onboarding a project would read."""
    found = [(title, body) for title, body in _under_projects(_sections(CONFIGURATION.read_text()))
             if re.search(r"\bone\b.*\borgani[sz]ation\b", title, re.I)]
    assert found, (
        "docs/configuration.md §5 'Projects' has no section whose heading names one organisation")
    title, body = found[0]
    assert "OPENFACTORY_GH_APP_INSTALLATION_ID" in body, (
        f"§5 '{title}' does not name the process-wide installation id the rule follows from")
    assert doctor.INSTALLATION_SCOPE in body, (
        f"§5 '{title}' does not name the doctor line that checks it "
        f"({doctor.INSTALLATION_SCOPE!r})")
    assert "openfactory doctor" in body, (
        f"§5 '{title}' does not name the command a second deployment runs to check itself")
