"""A product that starts before its code (#992) — the act that begins that state and the act that
ends it.

WHY THIS EXISTS. Every product the core knew was born with code: `project add` requires a
repository, and the context repository's `.openfactory/product.yaml` lists the product's sources.
A product whose requirements and design come first — written with the product owner, imported,
brought in by any client — had no code repository to register, and people created an empty one so
the command had something to point at. The factory then held a repository nobody asked for, and
everything that reads code read an empty tree as if it were the product.

THE STATE IS ONE FIELD. `contracts.project.before_its_code`: the registry names no code repository
(`repo_path` is empty) and the product's context repository is set. What works then is everything
that lives in the context — the product owner's conversation, writing and accepting requirements,
the documents and decisions; what needs code waits, by name: `perform` refuses every row that
`needs_code`, the poller does not pick the project up, a box is not proved for it, and a
breakdown into cards says it waits (`voice.breakdown_waits_for_code`).

TWO ACTS, BOTH CATALOGUE ROWS, so the command line and `POST /api/act/{name}` reach the same code:

    start_before_code   register the project with its context repository and no code
                        repository
    first_source        give it its code repository: the first entry of `sources:`, then the
                        registry's `repo_path` and axes — and the breakdown needs no other step

THE REGISTRY ASKED, THE CONTEXT WRITTEN, THE REGISTRY WRITTEN — in that order, and the order is
what makes a half-done first source safe to run again. Every refusal the registry would make (a
code repository given twice, a deployment spanning two GitHub organisations) is asked before
anything is pushed (`ProjectRegistry.check_code`). Then the context: written the other way, a
registry that names the code while `sources:` does not list it is a product the module refuses as
a membership conflict — the role goes off. Written this way, a context that lists the source while
the registry does not yet is a product whose role stays off until the next run records it. Only a
registry somebody else changed during the push can still refuse after it, and its sentence names
what changed.

ONE DECLARATION PER ACT. A context whose `sources:` already lists repositories is a product that
has started: the first source is found there when its context lists it, and refused when the
context lists others and not it, because listing it would make the membership and the
authorisation in one act (ADR-0019 keeps them two declarations that check each other).

NOT A PLACEHOLDER. Nothing here creates a code repository: the factory would then maintain one
nobody asked for. On the runtime whose forge is this machine the CONTEXT repository is created
when it does not exist, as `project init` creates one there — it is a directory the installation
owns, so there is nobody to ask (ADR-0049 D9). On a hosted forge the context repository is the
organisation's to create, as it always was.
"""

from __future__ import annotations

import logging
import subprocess
import tempfile
from dataclasses import dataclass, field
from pathlib import Path

from openfactory import gitpin

log = logging.getLogger("openfactory.product.before_code")

#: The kinds of refusal these acts make, in the action layer's words — the row maps them.
INVALID = "invalid"
CONFLICT = "conflict"
UNAVAILABLE = "unavailable"

#: How long a git command against the context repository may take. A clone of a context
#: repository is documents, never a codebase.
_GIT_TIMEOUT = 180


class Refused(Exception):
    """Nothing was done, or nothing more than the sentence says, and why — in one of the three
    kinds above."""

    def __init__(self, kind: str, message: str) -> None:
        super().__init__(message)
        self.kind = kind
        self.message = message


@dataclass(frozen=True)
class Started:
    """A product started before its code: where its context is, and whether it can be read."""

    project: str
    docs_repo: str
    kind: str
    #: registered by this call; False when it found the same product already started (a retry)
    registered: bool
    #: the context repository was created on this runtime by this call
    created: bool = False
    reachable: bool = False
    why: str = ""
    #: whether the product module is on for it now, and the module's own reason when it is not
    active: bool = False
    reason: str = ""
    #: the link's own kind (`product.config.ProductLink.kind`) — `conflict` is a context that
    #: belongs to another product, which no declaration written into it would fix
    link: str = ""


@dataclass(frozen=True)
class Sourced:
    """A product's first source: what `sources:` lists for it and where its code is."""

    project: str
    repo_path: str
    entry: str
    docs_repo: str
    #: `sources:` gained the entry in this call; False when the context already listed it
    listed_now: bool
    #: the accepted requirements whose breakdown waited for the code, in number order
    waiting: tuple[int, ...] = field(default_factory=tuple)


# ── start ──────────────────────────────────────────────────────────────────────────────────────

def context_kind(ref: str, provider: str = "") -> str:
    """The forge kind a context repository reference belongs to, by a rule somebody can state:

    1. **the operator named a kind** — theirs, once the address may belong to it (`foreign_host`);
    2. **a URL** — the kind whose host it is, and a host nobody implements is refused by name;
    3. **`owner/name`** — GitHub's shape;
    4. **one bare name** — the runtime whose forge is this machine, where a context repository is
       a short name the installation owns (`project init` names one `<project>-context`).

    An Azure DevOps context is reached by (2): its clone URL is what carries its organisation and
    project. RAISES `Refused`."""
    from openfactory import doors

    chosen = (provider or "").strip().lower()
    raw = (ref or "").strip()
    try:
        foreign = doors.foreign_host(raw, provider=chosen)
    except ValueError as exc:
        raise Refused(INVALID, str(exc)) from None
    if foreign:
        raise Refused(INVALID, doors.foreign_refusal(foreign))
    if chosen:
        return chosen
    if "://" in raw or raw.startswith("git@"):
        return doors.host_owner(raw) or "github"
    return "github" if "/" in raw.strip("/") else "local"


def context_axes(name: str, ref: str, kind: str, *, token_env: str = "") -> tuple[str, dict]:
    """`(docs_repo, axes)` for a project of `kind` whose only repository is the context at `ref`.

    EVERY AXIS NAMES NO CODE REPOSITORY, on every kind, and that is the state: `_source_repo` reads
    nothing for a hosted kind, so no repository of the project's is a member of anything until its
    first source. A local project's axes carry its own name as their `repo`, as `project add`
    writes them, because the local rows key their board and their pull requests by it. RAISES
    `Refused`."""
    from openfactory import doors
    from openfactory.contracts.project import ProviderRef
    from openfactory.product.config import normalize_repo

    options = {"token_env": token_env} if token_env else {}
    raw = (ref or "").strip()
    if kind == "local":
        coordinate = raw.strip("/")
        if coordinate == name:
            # ON THIS RUNTIME THE PROJECT'S OWN NAME IS ITS CODE: the local forge answers it with
            # the project's `repo_path`, so a context of the same name would resolve to nothing
            raise Refused(INVALID, f"a context repository cannot be called {name!r} on this "
                                   f"runtime — that name is the project's own code; call it "
                                   f"`{name}-context`")
        local = {"kind": "local", "repo": name, "options": {}}
        return coordinate, {"tracker": ProviderRef(**local), "forge": ProviderRef(**local),
                            "ci": ProviderRef(kind="none", repo=name, options={})}
    if kind == "azure_devops":
        org, ado_project, repository = doors.ado_coordinates(raw)
        if not (org and ado_project and repository):
            raise Refused(INVALID, f"{ref!r} carries no organisation and project — on this "
                                   f"forge a context repository is named by its clone URL, "
                                   f"which carries both")
        return repository, {
            "tracker": ProviderRef(kind=kind, repo=None, options={"organization": org,
                                                                  **options}),
            "forge": ProviderRef(kind=kind, repo=None, options={"organization": org,
                                                                "project": ado_project,
                                                                **options})}
    coordinate = (doors.infer_repo(raw) if ("://" in raw or raw.startswith("git@"))
                  else raw.strip("/"))
    if not normalize_repo(coordinate) or (kind == "github" and "/" not in coordinate):
        raise Refused(INVALID, f"{ref!r} is not a repository reference — the owner and the "
                               f"name, `owner/name`, or the repository's clone URL")
    axes = {"tracker": ProviderRef(kind=kind, repo=None, options=options)}
    if kind != "github":
        axes["forge"] = ProviderRef(kind=kind, repo=None, options=dict(options))
    return coordinate, axes


def start_before_code(name: str, docs_repo: str, *, provider: str = "", token_env: str = "",
                      language: str = "") -> Started:
    """Register `name` as a product that started before its code, its context at `docs_repo`.

    CONVERGES, like `project init`: a project already started on the same context is found, not
    refused, so a run that failed after registering is finished by running it again. A project of
    that name in any other state is refused — this act never changes a registered project's code
    or context. RAISES `Refused`."""
    from openfactory.contracts.product import ProductConfig
    from openfactory.contracts.project import Project, before_its_code
    from openfactory.product.config import normalize_repo
    from openfactory.registry import ProjectRegistry

    name = (name or "").strip()
    ref = (docs_repo or "").strip()
    if not name:
        raise Refused(INVALID, "name the project: `openfactory product start <name> "
                               "<context-repository>`")
    if not ref:
        raise Refused(INVALID, f"name {name}'s context repository: `openfactory product start "
                               f"{name} <owner/repo>`")
    if ref.startswith("-"):
        # A VALUE THAT LOOKS LIKE AN OPTION never reaches git, which reads the context with it
        raise Refused(INVALID, f"a repository is named `owner/repo`, not {docs_repo!r}")
    kind = context_kind(ref, provider)
    coordinate, axes = context_axes(name, ref, kind, token_env=token_env)

    registry = ProjectRegistry()
    try:
        existing = registry.get(name)
    except KeyError:
        existing = None
    if existing is not None:
        theirs = getattr(getattr(existing, "product", None), "docs_repo", "") or ""
        if not before_its_code(existing):
            raise Refused(CONFLICT, f"{name} is already registered with its code "
                                    f"({existing.repo_path}) — a product that has code is not "
                                    f"started before it; its context is declared with "
                                    f"`openfactory product declare {name} <owner/repo>`")
        if normalize_repo(theirs) != normalize_repo(coordinate):
            raise Refused(CONFLICT, f"{name} already started before its code on {theirs} — "
                                    f"declare another context with `openfactory product declare "
                                    f"{name} <owner/repo>`")
        project, registered = existing, False
    else:
        row: dict = {"name": name, "repo_path": "", **axes,
                     "product": ProductConfig(docs_repo=coordinate)}
        if language:
            row["language"] = language
        try:
            registry.add(Project(**row))
        except ValueError as exc:
            raise Refused(CONFLICT, str(exc)) from None
        project, registered = registry.get(name), True

    created = False
    if kind == "local":
        # CREATED HERE, ON THIS RUNTIME ONLY, and seeded with no source: `sources: []` is a
        # product that has not started, which the module reads as such
        from openfactory.product.onboard import seed_context_repository

        try:
            created, _ = seed_context_repository(project, coordinate, sources=[])
        except Exception as exc:  # noqa: BLE001 — the project is registered; the reason is said
            log.warning("could not create the context repository %s for %s (%s)", coordinate,
                        name, gitpin.without_pin(str(exc))[:200])
    reachable, why = _reachable(project, coordinate)
    active, link, reason = _link(project)
    return Started(project=name, docs_repo=coordinate, kind=kind, registered=registered,
                   created=created, reachable=reachable, why=why, active=active, reason=reason,
                   link=link)


def _reachable(project, docs_repo: str) -> tuple[bool, str]:
    """`product.onboard.context_reachability`, never raising: DECLARED IS NOT REACHED, so both
    credentials that will read the context are tried while somebody is watching."""
    from openfactory.product.onboard import context_reachability

    try:
        return context_reachability(project, docs_repo)
    except Exception as exc:  # noqa: BLE001 — could not ask is an answer, said
        log.warning("could not ask whether %s is reachable (%s)", docs_repo, str(exc)[:200])
        return False, f"it could not be asked ({type(exc).__name__})"


def _link(project) -> tuple[bool, str, str]:
    """`(active, kind, reason)`: whether the product module is on for `project` now, the link's
    kind, and its own reason when it is not."""
    from openfactory.product.loader import load_product_context

    try:
        link = load_product_context(project).link
    except Exception as exc:  # noqa: BLE001 — a link nobody could read is off, and said
        log.warning("could not read the product link of %s (%s)", getattr(project, "name", "?"),
                    str(exc)[:200])
        return False, "", f"its context could not be read ({type(exc).__name__})"
    return (bool(link.active), str(getattr(link, "kind", "") or ""),
            "" if link.active else str(link.reason or ""))


# ── the first source ───────────────────────────────────────────────────────────────────────────

def first_source(name: str, repo_path: str, *, token_env: str = "", board_owner: str = "",
                 board_number: str = "") -> Sourced:
    """Give `name`, a product that started before its code, its code repository at `repo_path`.

    THE SAME AXES `project add` WRITES (`doors.axes_for`), on the forge the context lives on: the
    context repository is read through the project's forge (`product.onboard.context_forge`), so a
    code repository on another vendor would leave the requirements unreadable. RAISES `Refused`,
    and `KeyError` for a name nobody registered."""
    from openfactory import doors
    from openfactory.contracts.project import Project, before_its_code
    from openfactory.product.config import _source_repo, normalize_repo
    from openfactory.registry import ProjectRegistry

    registry = ProjectRegistry()
    project = registry.get(name)
    if not before_its_code(project):
        raise Refused(CONFLICT, f"{name} already has its code repository ({project.repo_path}) "
                                f"— a first source is given once; another repository of the "
                                f"product is listed with `openfactory product init {name} "
                                f"--source <repository>`")
    ref = (repo_path or "").strip()
    if not ref:
        raise Refused(INVALID, f"name {name}'s code repository: `openfactory product "
                               f"first-source {name} <repository>`")
    if ref.startswith("-"):
        raise Refused(INVALID, f"a code repository is a path or a clone URL, not {repo_path!r}")
    forge = getattr(project, "forge", None) or project.tracker
    kind = (getattr(forge, "kind", "") or "github").strip().lower()
    # ON THE CONTEXT'S FORGE, OR NOT AT ALL: the question is never "what kind is this address"
    # but "is it the kind the context is read through" — a host of another kind is refused in
    # this act's words, never in a flag the action layer does not have
    try:
        foreign = doors.foreign_host(ref, provider=kind)
    except ValueError:
        foreign = ref
    if foreign:
        raise Refused(INVALID, f"{ref!r} is not on the {kind} forge {name}'s context repository "
                               f"is read through — its code goes on the same forge, so one "
                               f"credential reads both")
    inherited = (token_env or (getattr(forge, "options", None) or {}).get("token_env")
                 or (project.tracker.options or {}).get("token_env") or "")
    try:
        axes = doors.axes_for(name, ref, provider=kind, token_env=inherited,
                              board_owner=board_owner, board_number=board_number)
    except doors.MissingCoordinates as exc:
        raise Refused(INVALID, f"{exc} — the code repository's clone URL carries them") from None
    docs_repo = project.product.docs_repo
    if kind == "azure_devops":
        docs_repo = _same_organisation(project, axes, docs_repo)
    row = {**project.model_dump(mode="json"), "repo_path": ref, "forge": None, "ci": None,
           **{axis: ref_.model_dump(mode="json") for axis, ref_ in axes.items()}}
    row["product"] = {**row["product"], "docs_repo": docs_repo}
    would_be = Project(**row)
    entry = _source_repo(would_be)
    if not normalize_repo(entry):
        raise Refused(INVALID, f"{ref!r} names no repository this deployment's {kind} forge can "
                               f"address — on a hosted forge, give the code repository's clone "
                               f"URL")
    # THE REGISTRY'S ANSWER BEFORE THE PUSH (review of 9f18a788): a refusal it made only after
    # the context was written left a source listed there that every later run was refused over
    try:
        registry.check_code(name, would_be)
    except ValueError as exc:
        raise Refused(CONFLICT, f"{exc} — nothing was written") from None
    listed_now = _list_in_context(project, would_be, entry)
    try:
        registry.set_code(name, would_be)
    except ValueError as exc:
        raise Refused(CONFLICT, str(exc)) from None
    return Sourced(project=name, repo_path=ref, entry=entry, docs_repo=docs_repo,
                   listed_now=listed_now, waiting=_waiting(would_be))


def _same_organisation(project, axes: dict, docs_repo: str) -> str:
    """The context's name as the code's Azure DevOps project will address it. One organisation —
    the context repository is read with the code's credential; another project of it qualifies the
    name (`Project/repo`), which every later read follows, as `product declare` documents."""
    forge = getattr(project, "forge", None)
    theirs = dict(getattr(forge, "options", None) or {})
    code = dict(getattr(axes.get("forge"), "options", None) or {})
    if (theirs.get("organization") or "").lower() != (code.get("organization") or "").lower():
        raise Refused(INVALID, f"{project.name}'s context repository is in the organisation "
                               f"{theirs.get('organization')!r} and this code repository in "
                               f"{code.get('organization')!r} — a product's code and context are "
                               f"read with one organisation's credential")
    if "/" in docs_repo or (theirs.get("project") or "") == (code.get("project") or ""):
        return docs_repo
    return f"{theirs.get('project')}/{docs_repo}"


def _list_in_context(project, would_be, entry: str) -> bool:
    """Add `entry` to `sources:` in the context's `.openfactory/product.yaml`, under the product's
    semaphore. True when it was written now, False when the context already listed it; RAISES
    `Refused` when the context lists other repositories and not this one.

    THE FILE IS WRITTEN BY `onboard.plan`, the function `product init` writes it with: everything
    the client had in it survives, `sources:` gains the entry, and a context that does not name
    this product is refused rather than renamed. PUSHED ONTO THE CONTEXT'S BRANCH, NOT PROPOSED:
    the breakdown is meant to start with no other step, and a write the platform makes into the
    context — a requirement, a decision, a fact — lands there under this same semaphore."""
    from openfactory import namespace
    from openfactory.credentials import bot_identity
    from openfactory.onboarding.propose_manifest import scrub
    from openfactory.product import semaphore
    from openfactory.product.config import MATCH_EXACT, repo_match
    from openfactory.product.onboard import PRODUCT_YAML, context_clone_url, plan

    cfg = project.product
    url = context_clone_url(project, cfg.docs_repo)
    branch = getattr(cfg, "declared_docs_branch", "") or ""
    bot = bot_identity()
    ident = ["-c", f"user.name={bot.name}", "-c", f"user.email={bot.email}"]

    def git(*args: str, cwd: Path) -> subprocess.CompletedProcess:
        return subprocess.run(["git", "-C", str(cwd), *ident, *args], capture_output=True,
                              text=True, timeout=_GIT_TIMEOUT, check=False)

    try:
        with semaphore.held(project), tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "context"
            cloned = subprocess.run(
                gitpin.argv(["clone", "--no-local", "-q", *(["--branch", branch] if branch else []),
                             "--", url, str(root)]),
                capture_output=True, text=True, timeout=_GIT_TIMEOUT, check=False)
            if cloned.returncode != 0:
                raise Refused(UNAVAILABLE, f"{project.name}'s context repository "
                                           f"{cfg.docs_repo} could not be read: "
                                           f"{scrub(cloned.stderr or '').strip()[-200:]} — "
                                           f"nothing was written")
            from openfactory.product.loader import _read_docs_manifest

            # LISTED IN ANY SPELLING IS LISTED: `plan` merges by the written string, so `MyApp` in
            # the file and `myapp` here would be one repository listed twice
            docs, _ = _read_docs_manifest(root)
            if docs is not None and any(repo_match(entry, s) == MATCH_EXACT
                                        for s in docs.sources):
                return False
            if docs is not None and docs.sources:
                # A PRODUCT THAT HAS MEMBERS ADMITS ANOTHER BY ITS CONTEXT LISTING IT — written
                # there by whoever writes the context, as a scaffold does — never by the act that
                # also registers it (review of 9f18a788)
                listed = ", ".join(repr(s) for s in docs.sources[:3]) + (
                    ", …" if len(docs.sources) > 3 else "")
                raise Refused(CONFLICT, f"{cfg.docs_repo} already lists {listed} in `sources:`, "
                                        f"and not {entry} — a product that has sources admits "
                                        f"another repository when its context lists it, not when "
                                        f"the act that registers the repository writes it there. "
                                        f"List {entry} in `sources:` and run this again, or start "
                                        f"{project.name} on a context of its own. Nothing was "
                                        f"written")
            result = plan(would_be, root, sources=[entry])
            if result.refusal:
                raise Refused(CONFLICT, result.refusal)
            if result.already_correct:
                return False
            target = namespace.resolve(root, PRODUCT_YAML, project=project.name)
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(result.product_yaml, encoding="utf-8")
            head = git("symbolic-ref", "--short", "HEAD", cwd=root)
            onto = (head.stdout or "").strip() if head.returncode == 0 else ""
            onto = branch or onto or "main"
            for args in (["add", "--", PRODUCT_YAML],
                         ["commit", "-qm", f"{project.name}: its first source, {entry}"],
                         gitpin.pinned(["push", "-q", "--", "origin", f"HEAD:{onto}"])):
                done = git(*args, cwd=root)
                if done.returncode != 0:
                    raise Refused(UNAVAILABLE, f"`sources:` in {cfg.docs_repo} could not be "
                                               f"written ({gitpin.subcommand(args)}: "
                                               f"{scrub(done.stderr or '').strip()[-200:]}) — "
                                               f"the registry was not changed, so running this "
                                               f"again is safe")
            return True
    except semaphore.Busy as exc:
        raise Refused(UNAVAILABLE, str(exc)) from None


def _waiting(project) -> tuple[int, ...]:
    """The accepted requirements whose breakdown waited for the code — every promise the product
    holds that was not read off the code, since nothing could have been broken down before it."""
    from openfactory.product.loader import load_product_context

    try:
        corpus = load_product_context(project).corpus
    except Exception as exc:  # noqa: BLE001 — the source is recorded; this is a courtesy
        log.warning("could not read %s's requirements after its first source (%s)",
                    getattr(project, "name", "?"), str(exc)[:200])
        return ()
    if corpus is None:
        return ()
    return tuple(sorted(r.number for r in corpus.requirements
                        if r.is_promise and not r.came_from_the_code))
