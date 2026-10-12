"""What ADDRESSED TO THE ROLE means — the core's definition, for every transport (#266 slice 6).

ADR-0051 D14 and decision 3. In a group the role answers only when it is addressed. A room where
ten people talk to each other is ten people's conversation, not ten requests: a role that took a
turn on every line would answer what nobody asked it, and would pay for every line of chatter on
every turn after — the cost D3 avoids by keeping conversations apart.

THREE WAYS A MESSAGE IS ADDRESSED TO THE ROLE, and nothing else:

    direct    the conversation is the role and one person alone — a private conversation on the
              panel (`person:` / `visitor:`, `product/conversation.py`), a direct message on a
              chat add-on (the add-on says so: `Message.direct`)
    mention   the message names the role — each transport detects that ITS OWN WAY (a chat vendor
              has its mention syntax; the panel's room reads the role's name, `api/product_chat.py`;
              the CLI's `product say` names the role by being the command), and hands the core one
              bit (`Message.mentions_role`)
    reply     the message replies inside a conversation the role takes part in — one it has been
              addressed in, or spoken in, before (the conversation knows the first; the product's
              memory the second, `memory/transcript.py::took_part`)

WHAT IS NOT ADDRESSED TO THE ROLE is kept and can be searched — recorded in the product's memory,
marked, and found by the explicit recall (`product_recall`) — and it STARTS NO TURN and is NEVER
PUT IN A TURN'S PROMPT: the conversation's history and the recall block a turn reads both leave it
out (`transcript.recent`, `recall.recall`, `overheard=False` by default). Somebody who wants the
role to read what the room said mentions it, and says so in their own words.

WHERE THE RULE IS ASKED. At the door's side of the queue, by the conversation itself
(`runtime/temporal/conversation.py::admit`), because only the conversation knows, at the instant a
message arrives, whether the role has been addressed in it yet — a reply written while the role is
still answering the mention that brought it in is a reply inside a conversation it takes part in.
The door hands the conversation what it can know without it: whether the conversation is direct,
whether the role was mentioned, and whether the product's memory holds the role speaking there.
This module is a pure function of those, so a replay of the conversation reads every message the
way it was read the first time.
"""

from __future__ import annotations

import re
import unicodedata

#: THE ROLE'S HANDLES in a room, besides its own name: the word on the panel's dock button, and the
#: role's function — words nobody in a room says to a person. The panel's room reads them as naming
#: the role (`api/product_chat.py::mentions_the_role`), and writes the first in front of a room
#: message that names nobody (`api/panel.html::pchatAddressed`).
HANDLES = ("po", "product")

#: A MENTION: `@` and a name, not joined to a word before it (`a@b.com` is an address), with the
#: comma or colon a vocative carries on either side — "@po, pode seguir", "pode seguir, @po".
_MENTION = re.compile(r"[,;:]?\s*(?<![\w@])@([\w.-]+)[,:;]?")


def _flat(text: str) -> str:
    """Lower case, accents off — `@Nína` and `@nina` name the same role."""
    return unicodedata.normalize("NFKD", str(text or "")).encode("ascii", "ignore") \
        .decode().lower()


def role_names(project=None) -> frozenset[str]:
    """What names the role in a mention: `HANDLES`, and its name — whole, or its first word."""
    name = str(getattr(getattr(project, "product", None), "agent_name", "") or "").strip()
    names = {*HANDLES, *((_flat(name), _flat(name.split()[0])) if name else ())}
    return frozenset(n for n in names if n)


def without_the_roles_address(text: str, project=None) -> str:
    """The message without the mentions that address THE ROLE: who it is for is not what it says.

    JOURNEY 0 (#640, C-13; #667). The panel writes `@po ` in front of a room message that names
    nobody, so a late "sim" arrived as "@po sim", and `po` is no catalogued word: the yes was read
    as neither, and the person was never told the proposal had expired.

    ONLY THE ROLE'S. A mention of anybody else stays where it is: "@ana sim" in the room is somebody
    answering Ana, and read past it would execute — or, "@ana não", destroy — what that person has
    waiting (review of #667; a misread yes is #272's failure)."""
    names = role_names(project)
    return _MENTION.sub(
        lambda m: " " if _flat(m.group(1).rstrip(".-")) in names else m.group(0), text or "")
DIRECT, MENTION, REPLY = "direct", "mention", "reply"
REASONS = (DIRECT, MENTION, REPLY)


def why_addressed(*, direct: bool, mentioned: bool, in_reply_to: str,
                  takes_part: bool) -> str:
    """Why this message is addressed to the role — `direct`, `mention` or `reply` — or "" when it
    is not, and must start no turn and reach no prompt.

    `direct`: the conversation is the role and this person alone. `mentioned`: the transport
    detected the role named in the message. `in_reply_to`: the message this one replies to, as the
    transport said it. `takes_part`: the role has been addressed or has spoken in this conversation
    before."""
    if direct:
        return DIRECT
    if mentioned:
        return MENTION
    if str(in_reply_to or "").strip() and takes_part:
        return REPLY
    return ""


__all__ = ["DIRECT", "HANDLES", "MENTION", "REASONS", "REPLY", "role_names", "why_addressed",
           "without_the_roles_address"]
