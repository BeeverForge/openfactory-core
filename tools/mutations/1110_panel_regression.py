"""Prove the reported panel regression through the production handler."""

TEST = 'tests/test_revisiting_logs_reads_new_runs.py'
PANEL = "openfactory/api/panel.html"

MUTATIONS = [
    ('logs reuse the first cached list forever', PANEL,
     'const r=await api("/api/jobs");',
     'const r=_logs.rows||await api("/api/jobs");'),
    ('an older visit overwrites a newer visit', PANEL,
     'if(request!==_logs.request || location.pathname!==path)return;',
     'if(location.pathname!==path)return;'),
    ('a response paints after leaving logs', PANEL,
     'if(request!==_logs.request || location.pathname!==path)return;',
     'if(request!==_logs.request)return;'),
]
