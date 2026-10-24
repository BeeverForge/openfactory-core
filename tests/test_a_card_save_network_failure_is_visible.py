"""A lost save response keeps the complete draft and gives an informed retry path."""

import pytest

from tests.test_a_refusal_is_not_an_answer import run

STUBS = """
let _bd={project:'acme',card:'7',form:null};const saved=[];let refreshes=0;
let fail=true;
async function act(name,params){saved.push({name,params});
  if(fail)throw new TypeError('Failed to fetch');return {ok:true,data:{issue:'8'}}}
function _bbody(){return _bd.form.raw}
async function boardOpenCard(ref){saved.push({opened:ref})}
async function refreshBoard(){refreshes++}
"""


@pytest.mark.parametrize("mode", ["new", "edit"])
def test_a_network_failure_is_reported_without_erasing_the_draft_and_can_be_retried(mode):
    got = run("""
      const draft=_bd.form={mode:'MODE',title:'Retain this title',raw:'Retain every body field'};
      await boardSaveCard();
      const after={same:_bd.form===draft,title:draft.title,body:draft.raw,refreshes};
      fail=false;await boardSaveCard();
      return {after,toasts,saved,form:_bd.form,refreshes};
    """.replace("MODE", mode), "boardSaveCard", stubs=STUBS)
    assert got["after"] == {"same": True, "title": "Retain this title",
                            "body": "Retain every body field", "refreshes": 0}
    assert got["toasts"][0] == [
        "Save not confirmed",
        "The connection failed. Your draft is kept; check the board before retrying Save.", "err",
    ]
    assert got["saved"][:2] == [{
        "name": "card_create" if mode == "new" else "card_edit",
        "params": {"project": "acme", "title": "Retain this title",
                   "body": "Retain every body field", **({"issue": "7"} if mode == "edit" else {})},
    }] * 2
    assert got["form"] is None
    assert got["refreshes"] == (0 if mode == "new" else 1)

