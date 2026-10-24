"""The browser owns modal focus containment, Escape, and focus restoration."""

from html.parser import HTMLParser

from tests.test_a_refusal_is_not_an_answer import PAGE, run


def test_the_modal_container_is_a_native_dialog():
    class Modal(HTMLParser):
        tag = None

        def handle_starttag(self, tag, attrs):
            if dict(attrs).get("id") == "modal":
                self.tag = tag

    parser = Modal()
    parser.feed(PAGE)
    assert parser.tag == "dialog"


def test_opening_uses_modal_mode_and_updates_keep_the_dialog_named_and_focused():
    got = run("""
      modal('<h3>New project</h3><input id="name">');
      const first={open:el.open,shows,attributes:{...el.attributes}};
      document.activeElement={id:'name'};
      modal('<h3>New project</h3><input id="name">');
      const updated={shows,focused};closeModal();
      return {first,updated,open:el.open,closes};
    """, "modal", "closeModal", stubs="""
      let shows=0,closes=0,focused=0,_modalOpener='';
      const input={focus(){focused++}},title={id:''};
      const el=nodes['#modal']={open:false,attributes:{},
        contains:x=>!!x,querySelector:q=>q==='h3'?title:input,
        setAttribute(k,v){this.attributes[k]=v},removeAttribute(k){delete this.attributes[k]},
        show(){this.open=true},showModal(){shows++;this.open=true},
        close(){closes++;this.open=false}};
      document.getElementById=()=>input;
    """)
    assert got == {
        "first": {"open": True, "shows": 1, "attributes": {"aria-labelledby": "modalTitle"}},
        "updated": {"shows": 1, "focused": 1}, "open": False, "closes": 1,
    }


def test_closing_after_the_trigger_was_redrawn_returns_focus_to_its_replacement():
    got = run("""
      document.activeElement={id:'registerProject'};
      modal('<h3>New project</h3>');closeModal();modalClosed();
      return {returned,html:el.innerHTML,kind:el.dataset.kind,opener:_modalOpener};
    """, "modal", "closeModal", "modalClosed", stubs="""
      let _modalOpener='';const returned=[];
      const el=nodes['#modal']={open:false,dataset:{kind:'new'},contains:()=>false,
        querySelector:()=>({id:''}),setAttribute(){},
        showModal(){this.open=true},close(){this.open=false}};
      document.getElementById=id=>({focus:()=>returned.push(id)});
    """)
    assert got == {"returned": ["registerProject"], "html": "", "kind": "", "opener": ""}

