"""`file:<name>` — a secret file mounted into the process, the way container platforms deliver one.

THE DIRECTORY IS THE DEPLOYMENT'S, THE NAME IS THE REFERENCE'S. `OPENFACTORY_CREDENTIAL_DIR` says
where the secrets are mounted (`/run/secrets` is the usual place) and a reference names one file
in it, never a path: a name with a separator, or one starting with a dot, is refused, and so is a
name whose file resolves outside the directory. A registry entry can therefore point only at
what the operator mounted, which is the same reason the registry names a variable rather than
holding a value.

READ AT EACH USE, NEVER KEPT. Each `resolve` opens the file, reads it and closes it: a rotated
secret is the one the next use reads, and no copy outlives the call that asked for it.

WHAT IS CHECKED, AND WHY EACH:

  · the directory is a directory, and nobody but its owner may write to it unless it is sticky.
    Whoever can write there can replace a secret. A cluster's secret volume is world-writable AND
    sticky, so a file in it can be removed or replaced only by its owner;
  · the file, followed through links, stays inside the directory. A cluster's secret volume links
    each name to a dated copy so it can swap them at once, so a link is ordinary, and one that
    leaves the directory is not;
  · it is a regular file, opened without blocking, so a pipe or a device named like a secret
    cannot hang the worker;
  · neither its group nor anyone else may write to it, for the reason the directory may not be
    writable by them;
  · in a directory anyone can write to, it belongs to root or to this process's user, because
    in such a directory a file somebody else created is not the deployment's;
  · it is no larger than a credential: a token, a private key or a small pool of tokens.

Its content, with the surrounding whitespace removed (`echo` and editors end a file with a
newline), is the secret. An empty file holds nothing.
"""

from __future__ import annotations

import os
import re
import stat

from openfactory.adapters.credential_store.base import CredentialRefused

#: Where the deployment's secret files are mounted. A locator, and so a reach to every file under
#: it: the worktree box withholds it from the workload (`sandbox/worktree.py::_PANEL_SECRET_VARS`).
DIR_VAR = "OPENFACTORY_CREDENTIAL_DIR"

#: The most a credential file may weigh. A private key is about 3 KB and a pool of tokens a few
#: hundred bytes each; a file past this is not a credential, and reading it whole is how a wrong
#: reference becomes a worker holding a log file in memory.
MAX_BYTES = 64 * 1024

#: What a reference may name: one file, no path. The same characters a cluster allows in a secret's
#: key, without the leading dot its volume uses for its own bookkeeping.
_NAME = re.compile(r"[A-Za-z0-9_][A-Za-z0-9._-]{0,254}")


def _writers(mode: int) -> str:
    """Who besides the owner may write, as a person reads it — `""` when nobody may."""
    return " and ".join(who for bit, who in ((stat.S_IWGRP, "its group"),
                                             (stat.S_IWOTH, "everyone")) if mode & bit)


class FileStore:
    """The files in one directory, read at each use."""

    def __init__(self, directory: str | os.PathLike | None = None) -> None:
        raw = directory if directory is not None else os.environ.get(DIR_VAR)
        self.directory = str(raw or "").strip()

    def _root(self) -> tuple[str, bool]:
        """`(the directory, resolved; whether anyone may write to it)`, or a refusal naming what
        is wrong with it."""
        if not self.directory:
            raise CredentialRefused(f"{DIR_VAR} names no directory to read secret files from")
        root = os.path.realpath(self.directory)
        try:
            found = os.stat(root)
        except OSError as exc:
            raise CredentialRefused(f"{DIR_VAR} names {self.directory}, which cannot be read "
                                    f"({exc.strerror})") from None
        if not stat.S_ISDIR(found.st_mode):
            raise CredentialRefused(f"{DIR_VAR} names {self.directory}, which is not a directory")
        sticky = bool(found.st_mode & stat.S_ISVTX)
        writers = _writers(found.st_mode)
        if writers and not sticky:
            raise CredentialRefused(f"{self.directory} is writable by {writers}, so anyone who "
                                    f"can write there can replace a secret")
        return root, sticky and bool(found.st_mode & stat.S_IWOTH)

    def _located(self, name: str) -> tuple[str, bool]:
        """`(the file's resolved path, whether the directory is one anyone can write to)`, or a
        refusal naming what is wrong with the directory or the name."""
        if not _NAME.fullmatch(name or ""):
            raise CredentialRefused(f"`{name}` is not a file name the credential directory can "
                                    f"hold: letters, digits, `.`, `_` and `-`, not starting with "
                                    f"`.`")
        root, shared = self._root()
        path = os.path.realpath(os.path.join(root, name))
        if os.path.commonpath([root, path]) != root or path == root:
            raise CredentialRefused(f"the file `{name}` in {self.directory} leads outside it")
        return path, shared

    def unusable(self) -> str:
        """Why no file can be read from this store at all, or `""` — what `openfactory doctor`
        asks of a store a deployment declares, before any credential is named. OPTIONAL on the
        port: a store that has nothing to say about itself does not define it."""
        try:
            self._root()
        except CredentialRefused as exc:
            return str(exc)
        return ""

    def _checked(self, name: str, found: os.stat_result, shared: bool) -> None:
        where = f"the file `{name}` in {self.directory}"
        if not stat.S_ISREG(found.st_mode):
            raise CredentialRefused(f"{where} is not a regular file")
        writers = _writers(found.st_mode)
        if writers:
            raise CredentialRefused(f"{where} is writable by {writers}, and a secret somebody "
                                    f"else can rewrite is not this deployment's")
        owner = getattr(os, "geteuid", lambda: 0)()
        if shared and found.st_uid not in (0, owner):
            raise CredentialRefused(f"{where} belongs to another user, in a directory anyone "
                                    f"can write to")
        if found.st_size > MAX_BYTES:
            raise CredentialRefused(f"{where} holds {found.st_size} bytes, and a credential is "
                                    f"at most {MAX_BYTES}")

    def resolve(self, name: str) -> str | None:
        path, shared = self._located(name)
        flags = os.O_RDONLY | getattr(os, "O_NONBLOCK", 0) | getattr(os, "O_NOFOLLOW", 0)
        try:
            fd = os.open(path, flags)
        except FileNotFoundError:
            return None
        except OSError as exc:
            raise CredentialRefused(f"the file `{name}` in {self.directory} could not be opened "
                                    f"({exc.strerror})") from None
        try:
            # ASKED OF THE OPEN FILE, not of the path, so what is checked is what is read.
            self._checked(name, os.fstat(fd), shared)
            chunks: list[bytes] = []
            size = 0
            while size <= MAX_BYTES:
                chunk = os.read(fd, MAX_BYTES + 1 - size)
                if not chunk:
                    break
                chunks.append(chunk)
                size += len(chunk)
        finally:
            os.close(fd)
        data = b"".join(chunks)
        if len(data) > MAX_BYTES:
            raise CredentialRefused(f"the file `{name}` in {self.directory} grew past "
                                    f"{MAX_BYTES} bytes while it was read")
        try:
            text = data.decode("utf-8")
        except UnicodeDecodeError:
            raise CredentialRefused(f"the file `{name}` in {self.directory} is not text") from None
        return text.strip() or None

    def describe(self, name: str) -> str:
        if not self.directory:
            return f"the file `{name}` in the credential directory, which {DIR_VAR} does not name"
        try:
            held = self.resolve(name) is not None
        except CredentialRefused as exc:
            return f"the file `{name}` in {self.directory}, refused: {exc}"
        return f"the file `{name}` in {self.directory} ({'present' if held else 'missing'})"
