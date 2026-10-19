"""A shared credential is who it is, whatever a request says about itself.

Two rules, one root. A shared board or product token keeps its scope when no `X-OpenFactory-Actor`
is sent, by every transport the gate admits (the Bearer header, the credential cookie, `?token=`):
`_subject` answered `UNKNOWN`, with no group, and the action layer saw an unscoped administrator.
And that header is a display hint, carried as `Actor.label`: it is never the actor's id or
display, who answered, who pressed, who vouched, or the person the product gate is asked about.
The first three rows put the old `_subject` back, the fourth its Bearer-only read; each row after
them is one other way the rules could come undone, and the guard must go red on each.
"""

TEST = "tests/test_a_shared_credential_is_who_it_is.py"

_APP = "openfactory/api/app.py"
_CATALOG = "openfactory/actions/catalog.py"
_ACTIONS = "openfactory/actions/__init__.py"
_LABEL_TEST = "tests/test_who_is_asking.py"
_CARD_TEST = TEST + "::test_a_shared_credential_is_no_operator_on_a_card_of_the_product_view"

_SUBJECT_RETURN = (
    '    return type(subject)(id="", display=subject.display or UNKNOWN.display,\n'
    '                         via=subject.via or UNKNOWN.via,\n'
    '                         groups=tuple(getattr(subject, "groups", ()) or ()))\n')

_OLD_SUBJECT_RETURN = (
    '    label = (request.headers.get("x-openfactory-actor") or "").strip()[:80]\n'
    '    return UNKNOWN if not label else type(subject)(\n'
    '        id="", display=label, via=subject.via, groups=subject.groups)\n')

MUTATIONS = [
    ("THE DEFECT: `_subject`'s old branch — no label is `UNKNOWN`, which carries no group, and a "
     "label becomes the subject's display",
     _APP, _SUBJECT_RETURN, _OLD_SUBJECT_RETURN),

    ("THE DEFECT, seen from the existing label test: the old branch makes the label the display",
     _APP, _SUBJECT_RETURN, _OLD_SUBJECT_RETURN, _LABEL_TEST),

    ("THE DEFECT, on a row inside the area: the old branch makes the shared product token an "
     "operator, and the card's control closes a card somebody else asked for",
     _APP, _SUBJECT_RETURN, _OLD_SUBJECT_RETURN, _CARD_TEST),

    ("THE DEFECT BY ANOTHER TRANSPORT: `_subject` reads the Bearer header alone, so a credential "
     "the gate admitted by its cookie or `?token=` is `UNKNOWN`",
     _APP, "    subject = _subject_of(_credential_of(request))\n",
     '    token = (request.headers.get("authorization") or "").removeprefix("Bearer ").strip()\n'
     "    subject = _subject_of(token)\n"),

    ("the card's control vouches for any admin, scoped or not",
     _CATALOG, "    operator = bool(by.admin) and by.may_enter(FLOOR)\n",
     "    operator = bool(by.admin)\n", _CARD_TEST),

    ("an anonymous subject drops the groups its credential asserts, and nothing else changes",
     _APP, '                         groups=tuple(getattr(subject, "groups", ()) or ()))\n',
     '                         groups=())\n'),

    ("the answer route records the label as who answered",
     _APP, "    by = user or who.display\n",
     "    by = user or _label_of(request) or who.display\n"),

    ("the answer route asks the product gate about the label as the person deciding",
     _APP, 'approved=(answer == "approve"), user=user, via="panel")',
     'approved=(answer == "approve"), user=_label_of(request) or by, via="panel")'),

    ("the answer route asks the product gate about the record's name (`user=by`), so a credential "
     "naming nobody is asked about as its display",
     _APP, 'approved=(answer == "approve"), user=user, via="panel")',
     'approved=(answer == "approve"), user=by, via="panel")'),

    ("`run_staged` records the label as who pressed",
     _CATALOG, 'answer="approve", by=str(by.id or by.display))',
     'answer="approve", by=str(by.id or by.label or by.display))'),

    ("the label becomes the actor's display, so `str(by)` and every row's `by` are the label",
     _APP, '                         display=subject.display or subject.id or "panel",\n',
     '                         display=label or subject.display or subject.id or "panel",\n'),

    ("the label becomes the anonymous actor's id, so it vouches for an invitation",
     _APP, '    return actions.Actor(id=(subject.id or "") if known else "",\n',
     '    return actions.Actor(id=(subject.id or "") if known else label,\n'),

    ("a subject its provider marked anonymous keeps the id it filled in",
     _APP, '    return actions.Actor(id=(subject.id or "") if known else "",\n',
     '    return actions.Actor(id=subject.id or "",\n'),

    ("a named person keeps the label they sent",
     _APP, '                         label="" if known else label)\n',
     '                         label=label)\n'),

    ("the header is read a second time, outside `_label_of`",
     _APP, "    return _actor_of(request, _subject(request), label=_label_of(request))\n",
     '    return _actor_of(request, _subject(request),\n'
     '                     label=request.headers.get("x-openfactory-actor", ""))\n'),

    ("the label is not carried at all, so a script on a shared token cannot say what it is",
     _APP, "    return _actor_of(request, _subject(request), label=_label_of(request))\n",
     '    return _actor_of(request, _subject(request), label="")\n', _LABEL_TEST),

    ("the audit line no longer prints the label",
     _ACTIONS,
     '             f" label={label!r}" if label else "", outcome.ok, outcome.code or "-",\n',
     '             "", outcome.ok, outcome.code or "-",\n', _LABEL_TEST),
]
