"""#204: a project nobody registered is a 404 in one sentence — one helper, and a sweep of every route."""

TEST = "tests/test_a_project_nobody_registered_is_never_a_500.py"
APP = "openfactory/api/app.py"
CATALOG = "openfactory/actions/catalog.py"

# RE-PINNED 2026-10-21 (#988): the helper's 404 became `_no_such_project`, the one sentence a
# product read also answers a project with no product role in — same claims, the lines moved there.
_REFUSAL = "        raise _no_such_project(project) from None"

MUTATIONS = [
    # ── the defect ───────────────────────────────────────────────────────────────────────────────
    ("the approval dialog's prefetch stops asking for the project before it builds anything", APP,
     "    p = _project_or_404(project)\n    try:\n        _, manifest, forge = _forge_and_manifest(",
     "    p = None\n    try:\n        _, manifest, forge = _forge_and_manifest("),

    # ── the helper ───────────────────────────────────────────────────────────────────────────────
    ("the helper lets the registry's KeyError out: every route that asks it is a 500 again", APP,
     _REFUSAL,
     "        raise"),

    ("the helper answers in one of the old spellings", APP,
     'detail=f"no project named {project!r} in this deployment")',
     'detail=f"no project called {project!r}")'),

    ("the helper refuses everybody — a registered project is a 404 too", APP,
     "    try:\n        return ProjectRegistry().get(project)\n    except KeyError:\n"
     "        raise _no_such_project(project) from None",
     "    try:\n        ProjectRegistry().get(project)\n        raise KeyError(project)\n"
     "    except KeyError:\n        raise _no_such_project(project) from None"),

    # ── the four routes that spelled it by hand: each one forgets ────────────────────────────────
    ("the board looks the project up by hand again, and forgets the refusal", APP,
     "    proj = _project_or_404(project)\n    token = tracker_token_for(proj)",
     "    proj = ProjectRegistry().get(project)\n    token = tracker_token_for(proj)"),

    # RE-PINNED 2026-09-24 (#298): the read now sits in a `try` that answers a remote box it could
    # not read as a 503. The cut is the same one — the refusal leaves the route.
    ("a run's log forgets the refusal", APP,
     "    _project_or_404(project)\n    try:\n        return _events(project, issue)",
     "    try:\n        return _events(project, issue)"),

    ("a run's stream forgets the refusal", APP,
     "    path = events_file(_project_or_404(project), issue)",
     "    path = events_file(ProjectRegistry().get(project), issue)"),

    ("the answer to a staged proposal forgets the refusal", APP,
     "        proj = _project_or_404(project)\n        code, sentence",
     "        proj = ProjectRegistry().get(project)\n        code, sentence"),

    # ── the sweep is not a list ──────────────────────────────────────────────────────────────────
    # RE-PINNED 2026-09-24 (#267 slice 3): the loops are read through the agenda's filter now
    # (nobody else's private items), and the room it needs is looked up with the refusal handled
    ("a route nobody listed starts looking the project up, and forgets the refusal", APP,
     # RE-PINNED 2026-10-11 (#564): the list leaves out what a breakdown did not file
     "    loops = [x for x in waiting(agenda.visible(loop_store.read(project), viewer, room=room))",
     "    ProjectRegistry().get(project)\n"
     "    loops = [x for x in waiting(agenda.visible(loop_store.read(project), viewer, room=room))"),

    # ── the action layer ─────────────────────────────────────────────────────────────────────────
    ("promote goes straight to the forge again: FAILED, a 500 carrying an exception's repr", CATALOG,
     "    _, bad = _project(project)\n    if bad:\n        return bad\n"
     "    p, manifest, forge = _forge_and_manifest(project)",
     "    p, manifest, forge = _forge_and_manifest(project)"),

    ("a row nobody listed stops asking `_project`", CATALOG,
     "    found, bad = _project(project)\n    if bad:\n        return bad\n"
     "    ProjectRegistry().set_enabled(found.name, bool(enabled))",
     "    found = ProjectRegistry().get(project)\n"
     "    ProjectRegistry().set_enabled(found.name, bool(enabled))"),
]
