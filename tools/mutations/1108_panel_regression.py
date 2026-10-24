"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_panel_modals_use_the_native_dialog.py'
PANEL = "openfactory/api/panel.html"

MUTATIONS = [
    ('dialog loses native focus containment', PANEL,
     '<dialog id="modal"',
     '<div id="modal"'),
    ('dialog is shown without modal mode', PANEL,
     'el.showModal()}',
     'el.show()}'),
    ('closing no longer dismisses the dialog', PANEL,
     'function closeModal(){$("#modal").close()}',
     'function closeModal(){}'),
    ('background redraw loses the focus return target', PANEL,
     'if(opener)opener.focus();',
     'if(false)opener.focus();'),
]
