"""Every git call the core makes that reaches a remote pins the transports it may use (#931,
slice 1), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/931_a_remote_git_call_pins_its_transports.py

The claims, each a row:

  1. the pin refuses ext, fd and http by name, so a machine's `protocol.<name>.allow=always`
     cannot widen it, and lets https, ssh and file through;
  2. the core's own remote calls carry it (the cache's probe and clone, the preview's head read);
  3. the guard sees every shape a remote call is written in, and `subcommand` reads past the pin;
  4. an error's text reads without the pin, so a log line keeps the command.
"""

TEST = "tests/test_a_remote_git_call_uses_only_https_ssh_and_file.py"
PIN = "openfactory/gitpin.py"
CACHE = "openfactory/runtime/repo_cache.py"
DEMAND = "openfactory/preview/demand.py"

MUTATIONS = [
    # 1. the pin itself
    ("the pin sets only the default, which a machine's per-transport setting overrides", PIN,
     '    *(w for name in REFUSED for w in ("-c", f"protocol.{name}.allow=never")),\n',
     ""),
    ("ext is no longer named, so a machine that allows it runs the remote's command", PIN,
     'REFUSED = ("ext", "fd", "http", "git", "ftp", "ftps")',
     'REFUSED = ("fd", "http", "git", "ftp", "ftps")'),
    ("plain http is allowed beside https", PIN,
     'ALLOWED = ("https", "ssh")\nREFUSED = ("ext", "fd", "http", "git", "ftp", "ftps")',
     'ALLOWED = ("https", "ssh", "http")\nREFUSED = ("ext", "fd", "git", "ftp", "ftps")'),
    ("the pin forgets file, and a clone of the cache directory is refused", PIN,
     '    "-c", "protocol.file.allow=user",\n', ''),
    ("file is always allowed, including in recursive submodule clones", PIN,
     '"protocol.file.allow=user"', '"protocol.file.allow=always"'),
    ("the pin goes after the subcommand, where `clone -c` writes the new repository's config", PIN,
     '    return ["git", *PIN, *args]', '    return ["git", *args[:1], *PIN, *args[1:]]'),

    # 2. the core's calls
    ("the cache's remote probe reads the machine's transports again", CACHE,
     '    rc, out = _git(gitpin.pinned(["ls-remote", "--symref", "--", clone_url, "HEAD"]))',
     '    rc, out = _git(["ls-remote", "--symref", "--", clone_url, "HEAD"])'),
    ("the preview's head read reads the machine's transports again", DEMAND,
     '        done = subprocess.run(gitpin.argv(["ls-remote", "--heads", "--", remote,\n'
     '                                           f"refs/heads/{branch}"]),',
     '        done = subprocess.run(["git", "ls-remote", "--heads", "--", remote,\n'
     '                               f"refs/heads/{branch}"],'),

    # 3. the guard and subcommand
    ("the guard reads lists and never a call's own arguments", TEST,
     "        elif isinstance(node, ast.Call) and not _is_wrapper(node):\n            items = node.args\n",
     ""),
    ("the guard only sees a subcommand at the start", TEST,
     'for i, word in enumerate(words))', 'for i, word in enumerate(words[:1]))'),
    ("the guard does not see `remote set-url`", TEST,
     ' or words[i:i + 2] == ["remote", "set-url"]',
     ""),
    ("`subcommand` stops at the pin's first `-c`", PIN,
     '    while i < len(words) and words[i] in ("-c", "-C"):',
     '    while i < len(words) and words[i] == "-C":'),

    # 4. the pin in an error's text
    ("an error's text keeps the pin, and the log line loses the command", PIN,
     '    return text.replace(listed, "").replace(spoken, "")',
     "    return text"),
]
