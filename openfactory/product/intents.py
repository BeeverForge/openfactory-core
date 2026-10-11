"""What a person can ASK the product role to do, beyond talking.

The announcement, the board triage and the Needs Action sweep are things this role can do on its
own. Until something schedules them they are functions nobody calls — so the cheapest way to make
them real is to let a person ask, in the channel, in their own words.

IT LIVED IN `openfactory/runtime/slack/` UNTIL #105, and nothing about it was ever Slack: 587 lines
whose
only import is `re`, matching a client's own sentence to an intent. Not one line of this file
changed on the way out, which is the evidence — a module that needed editing to leave a vendor's
package would have been coupled to it. ADR-0038 rule 3 says that package renders and parses; this
parses a PERSON, not a transport, and every word below already said "the channel" rather than
"Slack". A guard now scans that package for modules indifferent to Slack
(`test_provider_seams.py::test_nothing_in_the_slack_package_is_INDIFFERENT_TO_slack`), because the
seam guard that existed skipped the whole directory and could never have seen this.

MATCHED CONSERVATIVELY. These are the few messages that must NOT be answered as conversation, and
the cost of the two mistakes is not symmetric: a missed intent means somebody rephrases, while a
false one means the role answers a question by running a board sweep. So the patterns are anchored
and specific, and anything unrecognised falls through to the conversation — which is the path that
handles being wrong gracefully.

THE READING ONES NEVER WRITE. Triage reports, the sweep reports, the announcement announces —
the first-pass rule from ADR-0019, and it holds for the same reason: on request or on a schedule,
this role has the least context exactly when it is asked to look at everything at once.

AND THE WRITING ONES ARE GONE (#565). This file's premise — "a missed intent means somebody
rephrases" — is false in a conversation with a model: the person does not know there is a sentence
to find, and the model that understood them had no act to hand it to. `accept`, `drop`, `decision`
and `fact` left first (slice a); `close`, `correct`, `align`, `breakdown` and `refine` followed
(slices b and c). The role proposes each with a marker (`role.ACTS`), staged for the person's yes
by the same branch of `engine._run_intent` these rows reached. Breakdown and refine wrote on the
match alone, an exception this file argued for; they are staged like the rest now, at the price it
named for that: one extra message. What is left reads, or proposes the queue — which is staged —
and every row anchors at the start of the message, so the guards that kept a scan honest went with
the rows that scanned.
"""

from __future__ import annotations

import re

#: An optional VOCATIVE before the verb. People address a named agent — "Nina, faz a triagem" — and
#: anchoring hard at the start made every one of those a miss, which is the most obvious way anyone
#: would actually phrase it. Deliberately narrow: one short token followed by a comma or a colon, so
#: "o que a triagem disse semana passada" (no comma) stays a question.
_VOCATIVE = r"(?:[@<]?[\w.-]{1,20}[>,:]\s*)?"

#: intent → pattern. Anchored at the start so "what did the triage say last week?" stays a question.
_START = r"^\s*" + _VOCATIVE

#: Typographic quotes, stripped off captures in `match_intent`: a trailing » left inside a capture
#: is written onward as the person's words.
_QUOTES = "«»\"“”'‘’"

#: THE GESTURES AS THEY READ, each anchored at the start of the message.
_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("announce", re.compile(
        _START + r"(se apresent|apresent[ae]([- ]se)?|quem (é|e) voc[êe]"
                 r"|introduce yourself|who are you)", re.IGNORECASE)),
    ("triage", re.compile(
        _START + r"(faz(er)?|faça|roda(r)?|rode|revis(a|ar|e)|organiz(a|ar|e)|run|do)\b"
                 r".{0,30}\b(triagem|board|quadro|casa|house|triage)s?\b", re.IGNORECASE)),
    ("needs_action", re.compile(
        _START + r"(olh(a|ar|e)|v[êe]|ver|revis(a|ar|e)|check|look)\b"
                 r".{0,30}\b(needs?[- ]action|impedimentos?|parad[ao]s?|bloquead[ao]s?)\b",
        re.IGNORECASE)),
    # RETIRED 2026-10-10 (#565): `accept`, `decision` and `drop` are acts the role proposes —
    # `[[ACORDO: REQ-N]]`, `[[REGISTRO: REQ-N; …]]`, `[[DESCARTE: REQ-N; …]]`
    # (`role.REQUIREMENT_ACTS`). On a live run "pode aceitar o 66" and "sim, concordo com o
    # requisito 66" matched none of these rows, and the model that understood both had no act
    # to hand them to. What the rows guarded — said, not asked, planned or refused; the
    # decision and the reason in the person's own words — is in each marker's instruction,
    # and the branches that stage them are unchanged.
    # RETIRED 2026-10-11 (#565 slices b and c): `close`, `correct`, `align`, `breakdown` and
    # `refine` are acts the role proposes — `[[FECHAR: …]]`, `[[CORRIGIR: …]]`, `[[TITULO: …]]`,
    # `[[ALINHAR: …]]`, `[[QUEBRAR: …]]`, `[[REFINAR: …]]` (`role.ACTS`). On the run, "pode fechar o
    # final 9" matched none of these rows and the role, which understood it, said only the person
    # could close a card. What the rows guarded — said, not asked or planned; the card and the
    # requirement named, never guessed — is in each marker's instruction, and the branches that
    # stage them are the ones these rows reached; breakdown and refine now wait for the yes too.
    # the brownfield first pass
    # Two shapes, because people say both: the verb ("documenta o que existe") and the noun with a
    # helper verb ("faz o levantamento do código"). Anchoring on only one of them missed the other,
    # which is the sort of gap that reads as "it just doesn't work".
    ("baseline", re.compile(
        _START + r"(?:(faz(er)?|faça|roda(r)?|rode|come[çc](a|ar|e)|start)\s+(o|a|um|uma)?\s*)?"
                 r"(document\w*|levant\w*|mapei\w*|mapeamento|engenharia reversa|survey)\b"
                 r".{0,40}\b(produto|c[óo]digo|codigo|que (j[áa] )?existe|sistema|code|product)\b",
        re.IGNORECASE)),
    # RETIRED 2026-10-10 (#565): `fact` is an act the role proposes, `[[FATO: …]]`
    # (`role.REQUIREMENT_ACTS`). What this row guarded — only what the person told the role to
    # note down, never a hypothesis discussed or a rhetorical question — is in that marker's
    # instruction; the branch it reached (`engine._run_intent`) still refuses a question.
    # "o que entra agora?" — the product owner's own question, and the one that keeps a factory
    # from sitting idle beside a full backlog.
    # The queue-word group is REQUIRED. Optional, it made bare "o que fazemos" a trigger — so
    # "o que fazemos com esse erro de ontem?" answered with a queue proposal ending in "Aprovo?",
    # and STAGED a pending whose admin "sim" would promote tickets (spend money) in a thread where
    # nobody mentioned the queue. A question about an incident must never arm the spend gate.
    ("queue", re.compile(
        _START + r"(?:(o )?que (entra|vem|fazemos|come[çc]amos)|pr[óo]xim[ao]s?|"
                 r"sugere?|sugir|monta|prioriz\w*|what.s next|next up)\b"
                 r".{0,30}\b(agora|seguir|fila|todo|to-?do|sequ[êe]ncia|next|queue)\b",
        re.IGNORECASE)),
    # "pode começar?" / "vamos tocar isso" / "bora começar" — HOW A CLIENT ASKS FOR THE THING the
    # queue gesture above is named after. Every word in that pattern is operator vocabulary
    # ("próximos", "fila", "TO-DO", "sequência"), and a client saying the ordinary sentence fell
    # through to conversation — where the role reads it as A REQUEST and offers to draft a NEW
    # REQUIREMENT to somebody who just asked to start the work already agreed. Answering "shall I
    # write that down?" to "can we start?" is the surface admitting its vocabulary is not the
    # client's.
    #
    # THE SAME GESTURE, SO THE SAME GATE: this stages a queue proposal, and an approver's yes is
    # what spends money. Nothing here reaches the pipeline on the match alone.
    #
    # END-ANCHORED, unlike its sibling above, and that is the whole defence. "vamos começar" IS the
    # gesture; "vamos começar a discutir o relatório de julho" is a plan for a conversation, and
    # arming the spend gate off it is precisely what the queue pattern's own comment warns about.
    # So the clause must END at the verb, give or take a particle people actually append.
    # THIS IS A SHORTCUT, NOT A GATE — and that changed after it failed on the first real use.
    # "podemos avançar?" carried none of these verbs, so the gesture fell through to conversation.
    # The list below is now an OPTIMISATION (one model call instead of two when it matches); the
    # escape is `role.QUEUE_MARKER`, declared by the model that reads every word of the message.
    # Adding verbs here is still worth it — it is free and it keeps the common phrasings cheap —
    # but a word missing from it costs a round trip now, not the gesture.
    ("queue", re.compile(
        _START + r"(?:pode(?:mos)?|posso|podia|vamos|bora|d[áa]\s+pra|"
                 r"can\s+we|shall\s+we|let'?s|should\s+we)\s+"
                 r"(?:j[áa]\s+)?(?:come[çc]ar|iniciar|tocar|arrancar|avan[çc]ar|seguir|"
                 r"prosseguir|andar|start|begin|proceed|move\s+on|get\s+going)\b"
                 r"(?:\s+(?:isso|iss[ao]\s+a[íi]|o\s+trabalho|as\s+tarefas|this|the\s+work))?"
                 r"(?:\s+(?:ent[ãa]o|j[áa]|agora|logo|hoje|amanh[ãa]|now|then|today))?"
                 r"\s*[?!.…]*\s*$",
        re.IGNORECASE)),
    # End-anchored: "como está A CORREÇÃO DAQUELE PROBLEMA?" is a question about one thing and
    # deserves an answer about that thing, not the whole board's status line.
    ("status", re.compile(
        _START + r"(status|situa[çc][ãa]o|como (est(á|a)|estamos|vai))\s*[?!.\s]*$",
        re.IGNORECASE)),
)


#: EVERY ROW ANCHORS AT THE START OF THE MESSAGE (#565): the gestures that named a card or a
#: requirement were scanned anywhere in it, behind a clause anchor, a bridge, a negation lookbehind
#: and a question test — all four left with them.
_INTENTS: tuple[tuple[str, re.Pattern[str]], ...] = _PATTERNS


def _asks_rather_than_tells(text: str, end: int) -> bool:
    """Whether the gesture that ended at `end` sits inside a question — read by the floor's own
    gestures (`actions/floor_intents.py`), which still scan a message.

    The CLAUSE decides, not the message: "o que você acha? faz o merge do #12" is a question
    followed by an instruction, and reading the whole message would throw the instruction away.
    """
    terminator = re.search(r"[.!?;\n]", text[end:])
    return bool(terminator) and terminator.group(0) == "?"


def _unquote(value: str) -> str:
    """A capture with the quotation the person copied around it taken off: a capture is free text
    that travels onward, and a stray » must not travel with it."""
    return value.strip().strip(_QUOTES).strip()


def match_intent(text: str) -> tuple[str, dict] | None:
    """`(intent, captures)` for the first row the message matches, or None."""
    body = text or ""
    for name, pattern in _INTENTS:
        m = pattern.search(body)
        if not m:
            continue
        captures = {}
        for key, value in (m.groupdict() or {}).items():
            trimmed = _unquote(value) if value else ""
            if trimmed:
                captures[key] = trimmed
        return name, captures
    return None
