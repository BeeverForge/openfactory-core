"""Hold metrics and the optional CDN independently, including out-of-order visits."""

from tests.test_a_refusal_is_not_an_answer import run

STUBS = """
let _DASH=null,_dc={},_dashRead=0,_chartReady=null;
const window={},scripts=[],timers=[];let removed=0;
document.createElement=()=>({remove(){removed++}});
document.head={appendChild:s=>scripts.push(s)};
global.setTimeout=fn=>{timers.push(fn);return timers.length};global.clearTimeout=()=>{};
nodes['#dash']=node();nodes['#chartStatus']=node();
const requests=[];const applied=[];
function _renderDashShell(d){nodes['#dash'].innerHTML=d.project}
function _dashApply(){applied.push(_DASH.data.project)}
"""


def costs(scenario):
    return run(scenario, "openCosts", "closeCosts", "_ensureChart", stubs=STUBS)


def test_metrics_and_close_are_available_while_the_cdn_is_still_pending():
    got = costs("""
      routes={'/api/metrics?project=acme':[{status:200,body:{project:'acme'}}]};
      const first=openCosts('acme');const loading=nodes['#dash'].innerHTML;
      await first;const before={html:nodes['#dash'].innerHTML,applied:[...applied]};
      timers[0]();await settle();
      return {loading,before,status:nodes['#chartStatus'].textContent,removed};
    """)
    assert 'onclick="closeCosts()"' in got["loading"]
    assert got["before"] == {"html": "acme", "applied": ["acme"]}
    assert "Charts unavailable" in got["status"] and got["removed"] == 1


def test_a_late_chart_draws_the_current_data_without_another_metrics_read():
    got = costs("""
      routes={'/api/metrics':[{status:200,body:{project:'acme'}}]};
      await openCosts();window.Chart={};scripts[0].onload();await settle();
      return {calls,applied,status:nodes['#chartStatus'].textContent};
    """)
    assert got == {"calls": ["GET /api/metrics"], "applied": ["acme", "acme"], "status": ""}


def test_only_the_latest_open_dashboard_can_paint():
    got = costs("""
      const held=[];api=url=>new Promise(resolve=>held.push(resolve));
      const old=openCosts('old');const current=openCosts('current');
      held[1]({project:'current'});await current;
      held[0]({project:'old'});await old;
      closeCosts();window.Chart={};scripts[0].onload();await settle();
      return {html:nodes['#dash'].innerHTML,display:nodes['#dash'].style.display,applied,
              scripts:scripts.length};
    """)
    assert got == {"html": "current", "display": "none", "applied": ["current"], "scripts": 1}


def test_closing_while_metrics_are_pending_discards_the_response():
    got = costs("""
      let finish;api=()=>new Promise(resolve=>finish=resolve);
      const reading=openCosts();closeCosts();finish({project:'acme'});await reading;
      return {display:nodes['#dash'].style.display,applied};
    """)
    assert got == {"display": "none", "applied": []}

