"""#788 (the nit from #783's review): every entry of the Kimi refusal table turns its guard red.

`tests/test_kimi_flags_are_a_combination_the_cli_accepts.py` holds the Kimi row's command to the
option table of `kimi-code` 0.31.1, the version `docker/worker.Dockerfile` pins. Its tables are
data, so an entry softened out of them (a flag dropped from `REFUSED_WITH_PROMPT`, a pair dropped
from `REFUSED_TOGETHER`) would leave the test green with nothing proving it was ever load-bearing.
One cut per entry, each in `kimi.py::_cli`, each aimed at the test function that holds it, so a
softened entry makes exactly its own cut survive:

  - R1-R6. Each flag 0.31.1's `validateOptions` refuses beside `-p` (`--auto`, `--yolo`, and the
    `-y`, `--yes`, `--auto-approve` spellings of yolo, and `--plan`) is put back beside the prompt
    on every shape. Held by `test_no_flag_the_pinned_cli_refuses_beside_the_prompt`.
  - P1. `-c` beside `-S` on a resumed run. `-c` alone is not refused beside `-p`, so only the
    continue+session row of `REFUSED_TOGETHER` can see it.
  - P2. `--agent-file` beside `-S` on a resumed run: the agent-file+session row (no `--agent` is
    sent, so the agent+agent-file row cannot see it).
  - P3. `--agent` and `--agent-file` together on every shape: the agent+agent-file row.
    P1-P3 are held by `test_no_pair_the_pinned_cli_refuses_together`.
  - V1. `--output-format text` instead of `stream-json`, the only format the row parses.
  - V2. The `-m` line dropped: the configured model never reaches the CLI.
  - V3. A blank prompt (`-p ''`), which 0.31.1 refuses.
    V1-V3 are held by `test_every_value_is_one_the_pinned_cli_accepts`.

  - D1. A new public door (`review`, through `_run`) added to `KimiAdapter`. `SHAPES` was written
    by hand, so no shape reached it and all three tables stayed green (19 passed, measured on
    59c5727b, before the row). Held by `test_every_door_that_builds_a_command_has_a_shape`,
    which reads the doors off the class (review round 2 on dc0efac4, point 5).

NOT A ROW: `-S` -> `-r`. `-r` (and `--resume`) are hidden aliases of `--session` that 0.31.1
accepts, so a guard that turned red on it would call an accepted command refused. The yolo+auto
pair has no row of its own either: every member of both sides is already refused beside `-p`,
which R1-R6 prove, and every command this row builds carries `-p`.
"""

TEST = "tests/test_kimi_flags_are_a_combination_the_cli_accepts.py"
BESIDE_PROMPT = TEST + "::test_no_flag_the_pinned_cli_refuses_beside_the_prompt"
TOGETHER = TEST + "::test_no_pair_the_pinned_cli_refuses_together"
VALUES = TEST + "::test_every_value_is_one_the_pinned_cli_accepts"
DOORS = TEST + "::test_every_door_that_builds_a_command_has_a_shape"

KIMI = "openfactory/adapters/agent/kimi.py"

_HEAD = '        cmd = [*head, "--output-format", "stream-json"]\n'
_SESSION = '            cmd += ["-S", shlex.quote(resume_session)]\n'
_MODEL = '            cmd += ["-m", shlex.quote(model)]\n'
_PROMPT = 'else shlex.quote(prompt)]\n'
_DOORS = "    # ---- command construction (exact, from kimi-code 0.31.1's option table) "


def _beside_prompt(n: int, flag: str) -> tuple[str, str, str, str, str]:
    return (f"R{n} the row sends {flag} beside -p, which kimi-code 0.31.1 refuses", KIMI,
            _HEAD, f'        cmd = [*head, "--output-format", "stream-json", "{flag}"]\n',
            BESIDE_PROMPT)


MUTATIONS = [
    # ── R1-R6: one per member of REFUSED_WITH_PROMPT ─────────────────────────────────────────
    _beside_prompt(1, "--auto"),
    _beside_prompt(2, "--yolo"),
    _beside_prompt(3, "-y"),
    _beside_prompt(4, "--yes"),
    _beside_prompt(5, "--auto-approve"),
    _beside_prompt(6, "--plan"),

    # ── P1-P3: one per row of REFUSED_TOGETHER that a command could reach ────────────────────
    ("P1 a resumed run sends -c beside -S (continue+session)", KIMI,
     _SESSION, '            cmd += ["-c", "-S", shlex.quote(resume_session)]\n',
     TOGETHER),

    ("P2 a resumed run sends --agent-file beside -S (agent-file+session)", KIMI,
     _SESSION,
     '            cmd += ["--agent-file", "/x.md", "-S", shlex.quote(resume_session)]\n',
     TOGETHER),

    ("P3 every run sends --agent beside --agent-file (agent+agent-file)", KIMI,
     _HEAD,
     '        cmd = [*head, "--output-format", "stream-json", '
     '"--agent", "explore", "--agent-file", "/x.md"]\n',
     TOGETHER),

    # ── V1-V3: the values the row hands the CLI ──────────────────────────────────────────────
    ("V1 the output format is text, not the stream-json the row parses", KIMI,
     _HEAD, '        cmd = [*head, "--output-format", "text"]\n',
     VALUES),

    ("V2 the configured model never reaches the CLI (the -m line dropped)", KIMI,
     _MODEL, "            pass\n",
     VALUES),

    ("V3 the prompt is blank", KIMI,
     _PROMPT, "else \"''\"]\n",
     VALUES),

    # ── D1: the shapes close themselves (review round 2 on dc0efac4, point 5) ────────────────
    ("D1 a new public door builds a command no shape exercises", KIMI,
     _DOORS,
     "    def review(\n"
     "        self, *, sandbox: SandboxAdapter, workspace: Workspace, prompt: str\n"
     "    ) -> AgentRunResult:\n"
     "        return self._run(sandbox, workspace, prompt, model=self.model, phase=\"review\")\n"
     "\n" + _DOORS,
     DOORS),
]
