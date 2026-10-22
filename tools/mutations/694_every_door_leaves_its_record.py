"""Every door that changes the deployment without a catalog row leaves one audit record (#694,
PR #1039 review, hermesfelipe's follow-up, 2026-10-21), proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/694_every_door_leaves_its_record.py

The claims: `POST /api/projects`, `POST /api/messages/{project}/answer` and the commands
`project add`, `project init`, `init`, `product init` and `approver add` run inside
`actions.door_recorded`, which records how each ended — `ok`, an HTTP status and the code it
reads as (`invalid http_400`), an exit code. On c310ba28 none of them left a record; on 58cbd307
every HTTP refusal read as `failed` left the tests green (branch review, 2026-10-22).
"""

TEST = "tests/test_every_door_that_goes_around_perform_leaves_its_record.py"

_ACTIONS = "openfactory/actions/__init__.py"
_APP = "openfactory/api/app.py"
_T = TEST + "::"
_REFUSED = _T + "test_a_command_line_door_that_refuses_still_leaves_one_record"

MUTATIONS = [
    ("registering a project on the panel is not recorded", _APP,
     '    with actions.door_recorded("project_add", by=_actor(request), params=body.model_dump()):\n'
     "        return _add_project(body)\n",
     "    return _add_project(body)\n",
     _T + "test_registering_a_project_on_the_panel_leaves_one_record"),
    ("answering a question on the panel is not recorded", _APP,
     '    with actions.door_recorded("message_answer", by=_actor(request), params=params):\n'
     "        return _answer_channel_message(project, body, request)\n",
     "    return _answer_channel_message(project, body, request)\n",
     _T + "test_answering_a_question_on_the_panel_leaves_one_record"),
    ("the command line's doors are not recorded", "openfactory/cli.py",
     "            with act_layer.door_recorded(action, by=_cli_actor(who), params=kwargs):\n"
     "                return command(*args, **kwargs)\n",
     "            return command(*args, **kwargs)\n",
     _T + "test_adding_a_project_on_the_command_line_leaves_one_record"),
    ("a door that refused is recorded as ok", _ACTIONS,
     "        outcome = _door_outcome(exc)\n",
     '        outcome = done(f"{name} done")\n',
     _REFUSED),
    ("a command's exit code is not the record's reason", _ACTIONS,
     '                       data={"reason": f"exit_{code}"})\n',
     '                       data={"reason": RAISED})\n',
     _REFUSED),
    ("an HTTP status is not the record's reason", _ACTIONS,
     '                       data={"reason": f"http_{status}"})\n',
     '                       data={"reason": RAISED})\n',
     _T + "test_answering_a_question_on_the_panel_leaves_one_record"),
    ("every HTTP refusal is recorded as failed", _ACTIONS,
     "        return Outcome(ok=False, code=_DOOR_STATUS.get(status, FAILED),\n",
     "        return Outcome(ok=False, code=FAILED,\n",
     _T + "test_answering_a_question_on_the_panel_leaves_one_record"),
]
