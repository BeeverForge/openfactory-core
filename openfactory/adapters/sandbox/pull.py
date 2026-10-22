"""The box image's pull credential: resolved for one pull, written for that pull alone, and never
handed to the box (#742, ADR-0037 §7.2).

ADR-0037 left open WHO HOLDS THE PULL CREDENTIAL, and its costs named the risk. Under
docker-out-of-docker every pull shares one client configuration, so a deployment serving several
projects would keep every registry login in one place, readable by every pull. This answers the
stored half. A project's registry entry names its credential by REFERENCE (`box.pull_credential`,
with the registry user in `box.pull_username`). The credential store resolves it when the image is
pulled, and the pull runs with a configuration directory of its own, made for that pull and
deleted with it. The daemon keeps the image and never the login, and the box runs the image
without seeing either.

A CONFIGURATION THIS MODULE WRITES, NOT `docker login`. `docker login` into a fresh directory hands
the secret to the machine's credential helper when one is installed (a desktop keychain), and the
helper keeps it after the directory is gone. A configuration that already holds the login is read
as it is, and nothing outlives the pull.

THE SAME DAEMON AS THE BOX (review of #822). Which daemon a docker client talks to is part of its
configuration: `currentContext` in `config.json`, resolved through the `contexts` directory beside
it (`docker context use desktop-linux`, rootless, colima). A fresh configuration has neither, so
the pull went to the default socket while `docker image inspect` and `docker run` — which keep the
person's own configuration — went to their context: the image landed in a daemon the box never
uses, and `docker run` pulled again without the login. The private configuration therefore
carries the person's `currentContext` and links their `contexts` directory, and nothing else of
theirs: not `auths`, not `credsStore`, not `credHelpers`, which are logins this pull must neither
read nor feed. `DOCKER_HOST` and `DOCKER_CONTEXT` in the environment reach the pull as they reach
the box, because the pull inherits the same environment.
"""

from __future__ import annotations

import base64
import json
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass

#: The registry an image name with no host in front of it is pulled from, and the key the docker
#: client files that registry's login under.
HUB = "docker.io"
_HUB_KEY = "https://index.docker.io/v1/"


@dataclass(frozen=True)
class PullCredential:
    """A registry login named by reference: the user name, and where its secret is stored."""

    reference: str
    username: str = ""


def pull_credential_of(box: object) -> PullCredential | None:
    """The pull credential a project's `box:` block declares, or None when it declares none."""
    reference = str(getattr(box, "pull_credential", None) or "").strip()
    if not reference:
        return None
    return PullCredential(reference=reference,
                          username=str(getattr(box, "pull_username", None) or "").strip())


def registry_of(image: str) -> str:
    """The registry `image` is pulled from, by the docker client's own rule: the part before the
    first `/` when it looks like a host (a dot, a port, or `localhost`), else the default hub."""
    first, sep, _rest = (image or "").partition("/")
    if sep and ("." in first or ":" in first or first == "localhost"):
        return first
    return HUB


def problem(credential: PullCredential) -> str:
    """Why `credential` cannot be used now, in one sentence naming the reference and never the
    secret; `""` when it can."""
    from openfactory.adapters.credential_store import registry as store

    if not credential.username:
        return (f"`box.pull_credential` names `{credential.reference}` and `box.pull_username` is "
                f"empty — a registry login is a user name and a secret, and the user name goes in "
                f"`box.pull_username`")
    if not store.source(credential.reference):
        return (f"the pull credential `{credential.reference}` does not answer — "
                f"{store.describe(credential.reference)}")
    return ""


def user_config_dir() -> str:
    """Where the docker client keeps this person's configuration: `DOCKER_CONFIG`, else
    `~/.docker` — the client's own rule, so the box's docker calls and this read agree."""
    return os.environ.get("DOCKER_CONFIG") or os.path.join(os.path.expanduser("~"), ".docker")


def _context_of(user_dir: str) -> dict[str, str]:
    """The person's `currentContext`, as their `config.json` says it, or `{}`."""
    try:
        with open(os.path.join(user_dir, "config.json"), encoding="utf-8") as fh:
            current = json.load(fh).get("currentContext")
    except (OSError, ValueError, AttributeError):
        return {}
    return {"currentContext": current} if isinstance(current, str) and current else {}


def _carry_the_daemon(config: str, user_dir: str) -> dict[str, str]:
    """Link the person's `contexts` into the private configuration `config`, and return what its
    `config.json` must say for the client to resolve the same daemon: the `currentContext`."""
    contexts = os.path.join(user_dir, "contexts")
    if os.path.isdir(contexts):
        os.symlink(contexts, os.path.join(config, "contexts"), target_is_directory=True)
    return _context_of(user_dir)


def pull(image: str, credential: PullCredential, *, timeout: int = 900,
         run: Callable[..., subprocess.CompletedProcess] = subprocess.run) -> tuple[bool, str]:
    """Pull `image` with `credential`, resolved now. `(pulled, what the client said)`; the secret
    is never in what comes back, in an argument list, or anywhere once this returns."""
    from openfactory.adapters.credential_store import registry as store

    if not credential.username:
        return False, problem(credential)
    secret = store.resolve(credential.reference)
    if not secret:
        return False, problem(credential)
    registry = registry_of(image)
    auth = base64.b64encode(f"{credential.username}:{secret}".encode()).decode()
    config = tempfile.mkdtemp(prefix="openfactory-pull-")  # 0700, this process's alone
    try:
        daemon = _carry_the_daemon(config, user_config_dir())
        fd = os.open(os.path.join(config, "config.json"), os.O_WRONLY | os.O_CREAT | os.O_EXCL,
                     0o600)
        with os.fdopen(fd, "w") as fh:
            json.dump({**daemon,
                       "auths": {_HUB_KEY if registry == HUB else registry: {"auth": auth}}}, fh)
        try:
            done = run(["docker", "--config", config, "pull", "--quiet", image],
                       capture_output=True, text=True, timeout=timeout)
        except FileNotFoundError:
            return False, "docker is not installed in this environment"
        except subprocess.SubprocessError as exc:
            return False, f"the pull did not finish ({type(exc).__name__})"
        said = ((done.stdout or "") + (done.stderr or "")).strip()
        return done.returncode == 0, said.replace(secret, "***").replace(auth, "***")[-300:]
    finally:
        shutil.rmtree(config, ignore_errors=True)
