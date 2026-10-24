"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_project_controls_work_with_the_keyboard.py'
PANEL = "openfactory/api/panel.html"

MUTATIONS = [
    ('project link becomes unfocusable', PANEL,
     '<a class="top" id=',
     '<div class="top" id='),
    ('pickup becomes a mouse-only div', PANEL,
     '<button type="button" id="pickup-',
     '<div type="button" id="pickup-'),
    ('pickup announces the opposite state', PANEL,
     'role="switch" aria-checked="${p.enabled}"',
     'role="switch" aria-checked="${!p.enabled}"'),
    ('index refresh drops keyboard focus', PANEL,
     'if(next)next.focus({preventScroll:true});',
     'if(false)next.focus({preventScroll:true});'),
]
