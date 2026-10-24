"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_a_card_save_network_failure_is_visible.py'
PANEL = "openfactory/api/panel.html"

MUTATIONS = [
    ('network rejection escapes without feedback', PANEL,
     '  } catch(e){\n    // A lost response',
     '  } catch(e){ throw e;\n    // A lost response'),
    ('lost response erases the draft', PANEL,
     '    r = {ok:false, unconfirmed:true,',
     '    _bd.form=null;r = {ok:false, unconfirmed:true,'),
]
