"""#738: the CLI image builds with an extra root, and its pip trusts that root beside the system's.

THE FIRST ROW IS THE SHIPPED DEFECT RESTORED: the append target is `certifi.where()` again, which
`python:3.12-slim` cannot answer. It is cut twice, once against the sandbox guard and once against
the docker guard, because only the second builds the base image the defect lived in — and that one
needs a daemon: run this plan where `docker version` answers, or row 2 skips and prints green.

The rest are the properties the fix must keep: pip's file holds the root AND the system roots; no
pip.conf without a root (the public build, every time — the one new test that is green on main);
a missing store refused rather than created holding one root; and the guard's own hygiene, that it
builds from a copy and never writes into the checkout's `docker/extra-ca/`.
"""

TEST = "tests/test_the_cli_image_trusts_an_extra_root_without_certifi.py"
DOCKER_TEST = "tests/test_the_cli_image_builds_with_an_extra_root_ca.py"
CLI = "docker/cli.Dockerfile"

_APPEND = "      cat /usr/local/share/openfactory/extra-ca.crt >> /etc/ssl/certs/ca-certificates.crt; \\\n"
_CERTIFI = ("      cat /usr/local/share/openfactory/extra-ca.crt >> \\\n"
            "        \"$(python -c 'import certifi; print(certifi.where())')\"; \\\n")
_PIP_CONF = "      printf '[global]\\ncert = /etc/ssl/certs/ca-certificates.crt\\n' > /etc/pip.conf; \\\n"
_CHECK = ("      [ -s /etc/ssl/certs/ca-certificates.crt ] || { \\\n"
          "        echo \"docker/extra-ca/ holds a root certificate, but the base image carries no "
          "system trust store at /etc/ssl/certs/ca-certificates.crt for it to join; build FROM an "
          "image that ships Debian's ca-certificates (python:3.12-slim does).\" >&2; \\\n"
          "        exit 1; }; \\\n")

MUTATIONS = [
    # ── the shipped defect ─────────────────────────────────────────────────────────────────────
    ("the shipped defect restored: the append target is certifi.where() again", CLI,
     _APPEND, _CERTIFI),
    ("the same cut, in the base image itself: the build fails at the trust step", CLI,
     _APPEND, _CERTIFI, DOCKER_TEST),

    # ── what pip is pointed at ─────────────────────────────────────────────────────────────────
    ("pip.conf names the staging extra-ca.crt, so pip trusts the extra root alone", CLI,
     _PIP_CONF,
     "      printf '[global]\\ncert = /usr/local/share/openfactory/extra-ca.crt\\n' > /etc/pip.conf; \\\n"),
    ("the append is dropped and pip.conf is still written", CLI, _APPEND, ""),

    # ── the public build: no root, nothing written ─────────────────────────────────────────────
    ("pip.conf is written outside the branch, for every build", CLI,
     "    fi; \\\n    rm -rf /tmp/extra-ca",
     "    fi; \\\n" + _PIP_CONF.replace("      ", "    ", 1) + "    rm -rf /tmp/extra-ca"),

    # ── the store is checked, not assumed ──────────────────────────────────────────────────────
    ("the store-presence check is removed, so >> creates a store of one root", CLI, _CHECK, ""),

    # ── the guard's own hygiene ────────────────────────────────────────────────────────────────
    ("the context builder writes the throwaway into the checkout's docker/extra-ca, not the copy",
     DOCKER_TEST,
     '    (dest / f"docker/extra-ca/{THROWAWAY}.crt").write_text(pem)',
     '    (ROOT / f"docker/extra-ca/{THROWAWAY}.crt").write_text(pem)',
     DOCKER_TEST),

    # ── CI's switch: under TEST_REQUIRE_DOCKER the guard fails, it never skips (review of #738) ──
    ("the daemon probe ignores TEST_REQUIRE_DOCKER, so a CI without a daemon skips the build",
     DOCKER_TEST,
     '    if os.environ.get("TEST_REQUIRE_DOCKER"):\n        return True\n',
     "",
     DOCKER_TEST),
    ("an image that cannot be pulled skips even under TEST_REQUIRE_DOCKER", DOCKER_TEST,
     "        if os.environ.get(\"TEST_REQUIRE_DOCKER\"):\n            pytest.fail(why)\n",
     "        if os.environ.get(\"TEST_REQUIRE_DOCKER\"):\n            pytest.skip(why)\n",
     DOCKER_TEST),
]
