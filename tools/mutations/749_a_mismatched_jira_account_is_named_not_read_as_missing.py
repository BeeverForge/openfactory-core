"""#749: on Jira, an email and an API token of different accounts are named as such, instead of
every card reading as missing (2026-10-19).

Jira Cloud answers a Basic pair whose token is not the email's account as an anonymous request:
404 on every issue and project, 401 only on `GET /rest/api/3/myself`. The claims these cuts hold:

  - a 404 asks `myself` once, with the same credential, under `api/3` whatever family 404'd, and
    straight through `urlopen` (a `myself` that 404s does not ask again);
  - only a 401 there is the mismatch, refused with `code=401`; any other answer, or a probe that
    cannot be made, keeps the original 404;
  - no other failure asks anything, and a call that succeeds asks nothing either;
  - the sentence puts the cause first (the park line and the card's door keep 120 characters),
    never carries the token, and with no token says so instead of "different accounts";
  - a job parked on either refusal is classified as a credential, not as unknown.
"""

TEST = ("tests/test_on_jira_an_email_and_a_token_of_different_accounts_are_named_not_read_as_"
        "missing.py")
JIRA = "openfactory/adapters/tracker/jira.py"
CLASSIFY = "openfactory/techlead/classify.py"

MUTATIONS = [
    ("THE DEFECT ITSELF: a 404 never asks who is asking, and every card that exists reads as "
     "missing", JIRA,
     "            if exc.code == 404 and self._who_is_asking():",
     "            if False:"),

    ("every answer of the probe that is not a 200 reads as a mismatched pair", JIRA,
     "            return exc.code == 401",
     "            return exc.code != 200"),

    ("a probe that cannot be made at all reads as a mismatched pair", JIRA,
     "\"404, since nothing says the credential was not accepted\", str(exc)[:200])\n"
     "            return False",
     "\"404, since nothing says the credential was not accepted\", str(exc)[:200])\n"
     "            return True"),

    ("the refusal keeps the 404 code, so nothing tells it from a missing card", JIRA,
     "                                  code=401) from exc",
     "                                  code=404) from exc"),

    ("the probe runs on every failure, and a 400, 401, 403 or 500 costs one more request", JIRA,
     "            if exc.code == 404 and self._who_is_asking():",
     "            if exc.code >= 400 and self._who_is_asking():"),

    ("the probe follows the API family of the call that 404'd, and asks a route Jira lacks", JIRA,
     "f\"{self.site}/rest/api/3/myself\"",
     "f\"{self.site}/rest/{__import__('sys')._getframe(1).f_locals['api'].strip('/')}/myself\""),

    ("the probe goes through `_call`, so a `myself` that answers 404 asks itself again", JIRA,
     "            with urllib.request.urlopen(req, timeout=45):  # noqa: S310 — fixed https site\n"
     "                return False",
     "            self._call(\"GET\", \"myself\")\n"
     "            return False"),

    ("the probe asks without the credential, as nobody, and always hears 401", JIRA,
     "/rest/api/3/myself\", headers=self._headers(),",
     "/rest/api/3/myself\", headers={},"),

    ("the token is written into the refusal a person and a log read", JIRA,
     "has_token=bool(self.token)),",
     "has_token=bool(self.token)) + f\" {self.token}\","),

    ("the remedy comes before the cause, and a 120-character park line loses the cause", JIRA,
     "    return (f\"jira: the email {email} and the API token belong to different accounts, "
     "or the \"\n"
     "            f\"token was revoked — {seen} Pair the email with an API token created by "
     "that same \"\n"
     "            f\"account (id.atlassian.com → Security → API tokens), or replace a token "
     "that was \"\n"
     "            f\"revoked.\")",
     "    return (f\"Pair the email with an API token created by that same account \"\n"
     "            f\"(id.atlassian.com → Security → API tokens), or replace a token that was \"\n"
     "            f\"revoked. jira: the email {email} and the API token belong to different \"\n"
     "            f\"accounts, or the token was revoked — {seen}\")"),

    ("with no token at all, the refusal says the pair is of different accounts", JIRA,
     "    if not has_token:\n",
     "    if False:\n"),

    # Not `exc.code >= 400` above: a 200 never reaches the `except HTTPError` branch, so only a
    # probe on the success path can make a card that reads cost one request more (task 10).
    ("the probe runs on a call that succeeded, and every card that reads costs one more request",
     JIRA,
     "            return json.loads(body) if body.strip() else {}",
     "            self._who_is_asking()\n"
     "            return json.loads(body) if body.strip() else {}"),

    ("a job parked on the refusal is classified as unknown, and names no cause", CLASSIFY,
     "        r\"different accounts|no api token reached|\"\n",
     ""),
]
