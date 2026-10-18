"""A resumed Codex job is handed only options `codex exec resume` takes (#636).

`-s/--sandbox` is an option of `codex exec` alone at 0.146.0, the pinned `HARNESS_CODEX`, so the
resumed default-mode command exited 2 before it called a model. The resumed path now says its
sandbox as `-c sandbox_mode="<mode>"` — said again because a resume re-derives its sandbox from
the invocation, and with nothing said it records `read-only` (measured on 0.146.0 and 0.157.1).
Each row below is one way that could come undone, and the guard must go red on each.
"""

TEST = "tests/test_a_resumed_codex_job_is_handed_only_flags_exec_resume_takes.py"

_CODEX = "openfactory/adapters/agent/codex.py"

MUTATIONS = [
    ("the resumed path hands `-s` again, so `exec resume` exits 2 at the CLI as it did on main",
     _CODEX, "        elif resume_session:\n", "        elif False:\n"),

    ("the resumed path hands no sandbox at all, so the session resumes under the `read-only` the "
     "bare invocation derives — the job comes back unable to write, and nothing says so",
     _CODEX,
     "            cmd += [\"-c\", shlex.quote(f'sandbox_mode=\"{sandbox_mode}\"')]\n",
     "            pass\n"),

    ("the override names a key codex does not read as the sandbox, so it is ignored silently",
     _CODEX, "f'sandbox_mode=\"{sandbox_mode}\"'", "f'sandbox=\"{sandbox_mode}\"'"),

    ("the override hardcodes `read-only` instead of the mode the first run chose",
     _CODEX, "f'sandbox_mode=\"{sandbox_mode}\"'", "'sandbox_mode=\"read-only\"'"),

    ("full access is checked after resume, so a resumed full-access job loses its bypass",
     _CODEX,
     "        if self.full_access:\n"
     "            cmd += [\"--dangerously-bypass-approvals-and-sandbox\"]\n"
     "        elif resume_session:\n"
     "            cmd += [\"-c\", shlex.quote(f'sandbox_mode=\"{sandbox_mode}\"')]\n",
     "        if resume_session:\n"
     "            cmd += [\"-c\", shlex.quote(f'sandbox_mode=\"{sandbox_mode}\"')]\n"
     "        elif self.full_access:\n"
     "            cmd += [\"--dangerously-bypass-approvals-and-sandbox\"]\n"),

    ("full access hands `-s danger-full-access` instead of the bypass, which `exec resume` refuses",
     _CODEX, "            cmd += [\"--dangerously-bypass-approvals-and-sandbox\"]\n",
     "            cmd += [\"-s\", \"danger-full-access\"]\n"),

    ("an option of `exec` alone joins the shared list, so every resumed command is refused while "
     "every fresh one still starts — the tables must tell the two subcommands apart",
     _CODEX, "            \"--skip-git-repo-check\",",
     "            \"--color\", \"never\",\n            \"--skip-git-repo-check\","),

    ("the fresh path loses `-s` for the override, so `plan` and `ask` are no longer read-only by "
     "the one option ADR-0018's table names",
     _CODEX, "            cmd += [\"-s\", sandbox_mode]\n",
     "            cmd += [\"-c\", shlex.quote(f'sandbox_mode=\"{sandbox_mode}\"')]\n"),

    ("the worker image moves to another codex while the tables still say 0.146.0",
     "docker/worker.Dockerfile", "@openai/codex@0.146.0", "@openai/codex@0.147.0"),
]
