"""Every git call the core makes that reaches a remote pins the transports it may use (#931).

A git call reads which transports it may use from the machine's git configuration. A machine
that sets `protocol.ext.allow=always` lets a remote named `ext::sh -c …` run a command on the
host the moment the core clones, fetches, lists or pushes it. `openfactory.gitpin` puts
`-c protocol.<name>.allow=…` in front of the subcommand: https, ssh and file are allowed, ext,
fd, http, git and anything else are refused, whatever the machine says.

The proofs run real git under a hostile global configuration that allows every transport, with a
control run that shows the hostile configuration is live. No probe leaves the machine: the
network ones point at a closed port on 127.0.0.1.
"""

from __future__ import annotations

import ast
import subprocess
from pathlib import Path

import pytest

from openfactory import gitpin
from tests.the_tree_read_once import could_say, parsed, source_text

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def hostile(tmp_path, monkeypatch):
    """A machine whose git configuration allows every transport by name."""
    config = tmp_path / "hostile.gitconfig"
    config.write_text("[protocol]\n\tallow = always\n"
                      + "".join(f'[protocol "{name}"]\n\tallow = always\n'
                                for name in ("ext", "fd", "http", "git")))
    monkeypatch.setenv("GIT_CONFIG_GLOBAL", str(config))
    monkeypatch.setenv("GIT_CONFIG_NOSYSTEM", "1")
    monkeypatch.setenv("GIT_TERMINAL_PROMPT", "0")
    monkeypatch.setenv("GIT_SSH_COMMAND", "false")
    monkeypatch.delenv("GIT_ALLOW_PROTOCOL", raising=False)
    return tmp_path


def _ext(marker: Path) -> str:
    """An `ext::` remote that, when git runs it, creates `marker` (`% ` is git's quoted space)."""
    return f"ext::sh -c touch% {marker}"


def _run(argv: list[str]) -> subprocess.CompletedProcess:
    return subprocess.run(argv, capture_output=True, text=True, timeout=20, check=False)


def test_the_hostile_configuration_is_live(hostile):
    """THE CONTROL: without the pin, the same machine runs the ext remote's command."""
    marker = hostile / "ran"

    _run(["git", "ls-remote", _ext(marker)])

    assert marker.exists(), "the hostile configuration did not take; the proofs below prove nothing"


@pytest.mark.parametrize("remote", ["ext", "fd::0", "http://127.0.0.1:9/x.git"])
def test_a_pinned_call_refuses_ext_fd_and_http_the_machine_allows(hostile, remote):
    marker = hostile / "ran"
    url = _ext(marker) if remote == "ext" else remote

    done = _run(gitpin.argv(["ls-remote", "--", url]))

    assert done.returncode != 0
    assert "not allowed" in done.stderr, done.stderr
    assert not marker.exists()


def test_a_pinned_clone_refuses_an_ext_remote(hostile):
    marker = hostile / "ran"

    done = _run(gitpin.argv(["clone", "--no-local", "--", _ext(marker), str(hostile / "c")]))

    assert done.returncode != 0 and "not allowed" in done.stderr, done.stderr
    assert not marker.exists()


@pytest.mark.parametrize("remote", ["https://127.0.0.1:9/x.git", "ssh://git@127.0.0.1:9/x.git"])
def test_a_pinned_call_does_not_refuse_https_or_ssh(hostile, remote):
    """Nothing answers on the port, so the call fails — but on the connection, not the pin."""
    done = _run(gitpin.argv(["ls-remote", "--", remote]))

    assert done.returncode != 0
    assert "not allowed" not in done.stderr, done.stderr


def test_a_pinned_clone_of_a_file_remote_succeeds(hostile):
    src = hostile / "src"
    subprocess.run(["git", "init", "-q", "-b", "main", str(src)], check=True)
    subprocess.run(["git", "-C", str(src), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-q", "--allow-empty", "-m", "a"], check=True)

    by_path = _run(gitpin.argv(["clone", "--no-local", "-q", "--", str(src), str(hostile / "a")]))
    by_url = _run(gitpin.argv(["clone", "--no-local", "-q", "--", src.as_uri(),
                               str(hostile / "b")]))

    assert by_path.returncode == 0, by_path.stderr
    assert by_url.returncode == 0, by_url.stderr


def test_a_pinned_clone_cannot_recurse_into_a_local_submodule(hostile):
    sub = hostile / "sub"
    top = hostile / "top"
    for repo in (sub, top):
        subprocess.run(["git", "init", "-q", "-b", "main", str(repo)], check=True)
        subprocess.run(["git", "-C", str(repo), "-c", "user.name=t", "-c", "user.email=t@t",
                        "commit", "-q", "--allow-empty", "-m", "a"], check=True)
    subprocess.run(["git", "-C", str(top), "-c", "protocol.file.allow=always",
                    "submodule", "add", "-q", str(sub), "s"], check=True)
    subprocess.run(["git", "-C", str(top), "-c", "user.name=t", "-c", "user.email=t@t",
                    "commit", "-qm", "add submodule"], check=True)

    done = _run(gitpin.argv(["clone", "--recurse-submodules", "--", str(top),
                              str(hostile / "recursive")]))

    assert done.returncode != 0
    assert "transport 'file' not allowed" in done.stderr, done.stderr


def test_a_pin_survives_a_runner_that_adds_git_itself(hostile):
    marker = hostile / "ran"

    done = _run(["git", *gitpin.pinned(["ls-remote", "--", _ext(marker)])])

    assert done.returncode != 0 and not marker.exists()


# ── the core's own calls ────────────────────────────────────────────────────────────────────────

def test_the_core_s_remote_probe_never_runs_an_ext_remote(hostile):
    from openfactory.runtime.repo_cache import remote_default_branch

    marker = hostile / "ran"

    assert remote_default_branch(_ext(marker)) == ""
    assert not marker.exists()


def test_the_preview_s_head_read_never_runs_an_ext_remote(hostile):
    from openfactory.preview.demand import ls_remote

    marker = hostile / "ran"

    assert ls_remote(_ext(marker), "main") is None
    assert not marker.exists()


def test_the_repo_cache_never_clones_an_ext_remote(hostile):
    from openfactory.runtime.repo_cache import RepoCache

    marker = hostile / "ran"

    RepoCache(root=hostile / "cache").sync("p", _ext(marker), "main")

    assert not marker.exists()


# ── subcommand ──────────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize(("args", "sub"), [
    (["git", "clone", "x"], "clone"),
    (["clone", "x"], "clone"),
    (gitpin.argv(["clone", "x"]), "clone"),
    (gitpin.pinned(["push", "x"]), "push"),
    (gitpin.argv(["-C", "/d", "fetch", "--", "o"]), "fetch"),
    (["git", "-C", "/d", "-c", "a=b", "remote", "set-url"], "remote"),
    (["git"], None),
    ([], None),
    (["-C", "/d"], None),
])
def test_subcommand_skips_git_and_its_option_pairs(args, sub):
    assert gitpin.subcommand(args) == sub


def test_the_pin_sets_each_transport_by_name():
    """A `-c` overrides only its own key: `protocol.allow=never` alone loses to a machine's
    `protocol.ext.allow=always`."""
    settings = dict(w.split("=", 1) for w in gitpin.PIN[1::2])
    assert gitpin.PIN[::2] == ("-c",) * len(settings)
    assert settings == {"protocol.allow": "never",
                        "protocol.https.allow": "always", "protocol.ssh.allow": "always",
                        "protocol.file.allow": "user",
                        "protocol.ext.allow": "never", "protocol.fd.allow": "never",
                        "protocol.http.allow": "never", "protocol.git.allow": "never",
                        "protocol.ftp.allow": "never", "protocol.ftps.allow": "never"}
    assert gitpin.argv(["fetch"]) == ["git", *gitpin.PIN, "fetch"]
    assert gitpin.pinned(("fetch",)) == [*gitpin.PIN, "fetch"]


# ── the guard ───────────────────────────────────────────────────────────────────────────────────

REMOTE = ("clone", "fetch", "ls-remote", "push", "pull", "submodule")
WRAPPERS = ("pinned", "argv")


def _is_remote(words: list[str | None]) -> bool:
    """Find a remote command even past options, variables and starred argument lists."""
    if not words or words[0] not in (None, "git", "remote", *REMOTE):
        return False
    return any(word in REMOTE or words[i:i + 2] == ["remote", "set-url"]
               for i, word in enumerate(words))


def _is_wrapper(call: ast.Call) -> bool:
    f = call.func
    if isinstance(f, ast.Attribute):
        return f.attr in WRAPPERS and isinstance(f.value, ast.Name) and f.value.id == "gitpin"
    return isinstance(f, ast.Name) and f.id in WRAPPERS


def _unpinned(tree: ast.AST) -> list[str]:
    """`<line>` for every remote-reaching git argv in `tree` that is not the direct argument
    of `gitpin.pinned` / `gitpin.argv`."""
    wrapped = {id(a) for node in ast.walk(tree)
               if isinstance(node, ast.Call) and _is_wrapper(node) for a in node.args}
    found = []
    for node in ast.walk(tree):
        if isinstance(node, ast.List | ast.Tuple):
            items = node.elts
        elif isinstance(node, ast.Call) and not _is_wrapper(node):
            items = node.args
        else:
            continue
        words = [e.value if isinstance(e, ast.Constant) else None for e in items]
        if _is_remote(words) and id(node) not in wrapped:
            found.append(node.lineno)
    return [str(n) for n in sorted(found)]


def test_every_remote_reaching_git_call_goes_through_the_pin():
    """A GUARD ON THE CLASS: the next remote call written into the core is pinned too."""
    missing = [f"{path.relative_to(ROOT)}:{line}"
               for path in sorted((ROOT / "openfactory").rglob("*.py"))
               if path.name != "gitpin.py"
               if could_say(source_text(path), r"clone|fetch|ls-remote|push|pull|submodule|set-url")
               for line in _unpinned(parsed(path))]
    assert missing == [], f"a remote-reaching git call reads the machine's transports: {missing}"


def test_the_guard_sees_each_shape_of_a_remote_call():
    """THE GUARD CALLS ITS OWN RULE on the shapes the core reaches a remote in."""
    caught = ('_git(["clone", "--no-local", url, str(tmp)])\n'
              'subprocess.run(["git", "-C", x, "fetch", "--", url])\n'
              '_git("push", "--", "origin", b)\n'
              'shallow = ["clone", "--no-local", url]\n'
              '_git(["remote", "set-url", "--", "origin", u])\n'
              'run(("git", "ls-remote", "--", u))\n'
              'fetch = ["fetch", "--", u] if u else []\n'
              'subprocess.run(["git", "-C", str(root), *ident, "push", "--", "origin", b])\n'
              '_git(repo, "fetch", "--", url)\n'
              'subprocess.run(["git", "-c", "http.extraHeader=x", "clone", "--", u, d])\n'
              'subprocess.run(["git", "pull", "--", u])\n'
              '_git(["submodule", "update", "--init"])\n')
    passed = ('_git(gitpin.pinned(["clone", "--no-local", url, str(tmp)]))\n'
              'subprocess.run(gitpin.argv(["-C", x, "fetch", "--", url]))\n'
              '_git(*gitpin.pinned(["push", "--", "origin", b]))\n'
              'shallow = pinned(["clone", "--no-local", url])\n'
              '_git(["remote", "get-url", "origin"])\n'
              '_git(["rev-parse", "HEAD"])\n'
              'fetch = gitpin.pinned(["fetch", "--", u]) if u else []\n')
    assert _unpinned(ast.parse(caught)) == [str(i) for i in range(1, 13)]
    assert _unpinned(ast.parse(passed)) == []


# ── docs and release note ───────────────────────────────────────────────────────────────────────

def test_the_operations_guide_names_the_pinned_transports_and_the_gap():
    text = (ROOT / "docs" / "operations.md").read_text(encoding="utf-8")
    start = text.index("### Which transports the core's git calls may use")
    section = text[start:text.find("\n## ", start) if "\n## " in text[start:] else None]
    for word in ("https", "ssh", "file", "ext", "fd", "http", "GIT_ALLOW_PROTOCOL", "#931",
                 "openfactory/gitpin.py"):
        assert word in section, word


def test_the_pin_carries_its_release_note():
    note = (ROOT / "changes" / "931.security.md").read_text(encoding="utf-8").strip()
    assert note
    assert not note.splitlines()[0].rstrip().endswith("(#931)")
    upgrade = (ROOT / "changes" / "931.upgrade.md").read_text(encoding="utf-8")
    for word in ("http://", "git://", "https://", "ssh"):
        assert word in upgrade


# ── the pin in an error's text ──────────────────────────────────────────────────────────────────

def test_an_error_s_text_reads_without_the_pin():
    """A CalledProcessError spells its whole argv, and a log line keeps its first 120 characters:
    the pin would fill them and push out the command a person needs to read."""
    import subprocess as sp

    exc = sp.CalledProcessError(128, gitpin.argv(["clone", "--", "https://h/r.git", "/t"]))
    line = " ".join(gitpin.argv(["fetch", "--", "origin"]))

    assert gitpin.without_pin(str(exc)) == (
        "Command '['git', 'clone', '--', 'https://h/r.git', '/t']' returned non-zero exit "
        "status 128.")
    assert gitpin.without_pin(line) == "git fetch -- origin"
    assert gitpin.without_pin("git clone x") == "git clone x"


@pytest.mark.parametrize("door", ["context", "product_start"])
@pytest.mark.parametrize("failed_command", ["clone", "push"])
def test_a_failed_context_seed_names_the_command(door, failed_command, monkeypatch, caplog):
    from types import SimpleNamespace

    from openfactory import registry
    from openfactory.actions import catalog
    from openfactory.adapters.forge import registry as forge_registry
    from openfactory.product import before_code

    project = SimpleNamespace(name="acme")

    class Forge:
        def create_repository(self, **kwargs):
            return "acme-context", True

        def clone_url(self, *args, **kwargs):
            return "/srv/acme-context"

    class Registry:
        def __init__(self):
            self.project = project if door == "context" else None

        def get(self, name):
            if self.project is None:
                raise KeyError(name)
            return self.project

        def add(self, row):
            self.project = row

    def run(argv, **kwargs):
        command = gitpin.subcommand(argv)
        if command == failed_command:
            raise subprocess.CalledProcessError(128, argv, stderr="rejected")
        return subprocess.CompletedProcess(argv, 1 if command == "rev-parse" else 0,
                                           stdout="", stderr="")

    monkeypatch.setattr(registry, "ProjectRegistry", Registry)
    monkeypatch.setattr(forge_registry, "build_forge", lambda project: Forge())
    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(before_code, "_reachable", lambda *args: (False, "unreachable"))
    monkeypatch.setattr(before_code, "_link", lambda *args: (False, "", "unlinked"))

    if door == "context":
        step = catalog._the_context_step("acme")
        assert step["state"] == "failed"
        assert failed_command in step["said"]
        assert "protocol.allow" not in step["said"]
    else:
        before_code.start_before_code("acme", "acme-context", provider="local")

    assert failed_command in caplog.text
    assert "protocol.allow" not in caplog.text


def test_a_failed_push_in_the_declaration_step_names_push(tmp_path, monkeypatch):
    """The step names the git subcommand that failed, read past the pin: `git -c failed` tells a
    person nothing."""
    from types import SimpleNamespace

    from openfactory.actions import catalog
    from openfactory.product import onboard as po

    def _run(argv, **kw):
        failed = gitpin.subcommand(argv) == "push"
        return subprocess.CompletedProcess(argv, 1 if failed else 0, stdout="main\n",
                                           stderr="rejected" if failed else "")

    monkeypatch.setattr(subprocess, "run", _run)
    monkeypatch.setattr(po, "context_clone_url", lambda project, repo: "/srv/acme-context")
    monkeypatch.setattr(po, "plan", lambda project, root, sources=None: SimpleNamespace(
        refusal="", already_correct=False, docs_repo="acme-context", requirements_dir="reqs",
        product_yaml="product: acme\n", todo=[]))
    step = catalog._the_declaration_step(
        SimpleNamespace(name="acme"), "acme-context", tmp_path, sources=[], write=True,
        made_now=False, shown={}, withhold=[])

    assert step["state"] == "failed", step
    assert step["said"] == "git push failed: rejected", step
