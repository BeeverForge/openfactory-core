"""A sentence that sends a person to the product's approvers names them (#666), proven by
breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/a_refusal_names_who_can.py

The claims, each a row:
  1. no sentence tells a person to ask or tell "one of them";
  2. every sentence that sends a person to the approvers is said with their names, by a builder that
     refuses rather than names nobody;
  3. the names are the product's admins, at most three, joined as the language joins a list, or the
     person who can set one up;
  4. through the platform, every refusal is handed the names (C-12, and the five other sentences'
     callers).
"""

TEST = "tests/test_a_refusal_names_who_can.py"
VOICE = "openfactory/product/voice.py"
MODULE = "openfactory/product/module.py"
CONFIRM = "openfactory/product/confirm.py"
ENGINE = "openfactory/product/engine.py"

MUTATIONS = [
    # 1. nobody pointed at without a name
    ("TODAY'S RUN: the refusal asks one of these people", VOICE,
     '"para aprovar. Nada foi feito — peça a {names}."),',
     '"para aprovar. Nada foi feito — peça a uma dessas pessoas."),'),
    ("a close refused in English asks one of them", VOICE,
     '"can close or remove it. Nothing changed — ask {names}.",',
     '"can close or remove it. Nothing changed — ask one of them.",'),
    ("the room's sentence tells one of them", VOICE,
     '"não consegui avisar a sala do produto agora, então diga a {names} que "',
     '"não consegui avisar a sala do produto agora, então diga a um deles que "'),

    # 2. said with the names, or refused
    ("a builder handed no approvers names nobody", VOICE,
     '        raise ValueError("this sentence sends the person to the approvers: pass `approvers`")',
     "        pass"),
    ("TODAY'S RUN: the refusal names an act it did not refuse", VOICE,
     '"Posso conversar sobre isso, mas fazer isso precisa do sim de alguém com permissão "',
     '"Posso conversar sobre isso, mas registrar como requisito acordado precisa do sim de alguém '
     'com permissão "'),

    # 3. the names
    ("every admin is named, however many", VOICE,
     "    names = [str(a).strip() for a in (approvers or []) if str(a).strip()][:APPROVERS_NAMED]",
     "    names = [str(a).strip() for a in (approvers or []) if str(a).strip()]"),
    ("the names are run together with commas", VOICE,
     '    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + said["or"] + names[-1]',
     '    return ", ".join(names)'),
    ("nobody set up names nobody at all", VOICE,
     '        return said["nobody"]', '        return ""'),
    ("a product with admins is told nobody is set up", VOICE,
     "    if approvers is not None and not [a for a in approvers if str(a).strip()]:",
     "    if True:"),
    ("TODAY'S RUN: the platform hands no names to the refusal", MODULE,
     '    return [str(a) for a in (getattr(cfg, "admins", None) or []) if str(a).strip()]',
     "    return []"),

    # 4. every caller hands the names
    ("a card's close refused for someone off the list names nobody", MODULE,
     '                ref=number, how="not_yours", language=lang, approvers=approvers_of(self.project)))',
     '                ref=number, how="not_yours", language=lang))',
     "tests/test_a_card_nobody_started_can_be_closed_and_removed.py"),
    ("a card's queue control refused names nobody", MODULE,
     "                    \"note\": card_queue_not_yours(ref=number, column=queue, language=lang,\n"
     "                                                 approvers=approvers_of(self.project))}",
     "                    \"note\": card_queue_not_yours(ref=number, column=queue, language=lang)}",
     "tests/test_the_product_owner_queues_a_card_from_their_page.py"),
    ("another pass refused in the conversation names nobody", MODULE,
     '            return adjust.Prepared(said=adjust_said("not_yours", ref=number, language=lang,\n'
     "                                                    approvers=approvers_of(self.project)))",
     '            return adjust.Prepared(said=adjust_said("not_yours", ref=number, language=lang))',
     "tests/test_not_yet_at_the_last_gate_is_another_pass.py"),
]
