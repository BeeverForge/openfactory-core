"""Read the interactive elements the production project renderer actually emits."""

from html.parser import HTMLParser

import pytest

from tests.test_a_refusal_is_not_an_answer import run


class Controls(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.links = []
        self.switches = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a":
            self.links.append(attrs)
        if attrs.get("role") == "switch":
            self.switches.append((tag, attrs))


@pytest.mark.parametrize("enabled", [True, False])
def test_each_project_has_a_native_link_and_a_named_native_switch(enabled):
    html = run("""
      projects=[{name:'qa project',enabled:ENABLED,tracker:'local',forge:'local'}];
      renderIndex();return nodes['#app'].innerHTML;
    """.replace("ENABLED", str(enabled).lower()), "renderIndex", "boxChip", stubs="""
      const inbox=[];function needsYouHtml(){return ''}
      nodes['#app']=node();
    """)
    controls = Controls(html)
    assert len(controls.links) == 1
    assert controls.links[0]["href"] == "/p/qa%20project"
    assert controls.links[0]["aria-label"] == "Open project qa project"
    assert len(controls.switches) == 1
    tag, switch = controls.switches[0]
    assert tag == "button" and switch["type"] == "button"
    assert switch["aria-checked"] == str(enabled).lower()
    assert switch["aria-label"] == "Pickup for qa project"


@pytest.mark.parametrize("control", ["project-acme", "pickup-acme"])
def test_a_live_refresh_keeps_focus_on_the_same_project_control(control):
    got = run("""
      document.activeElement={id:'CONTROL',closest:()=>true};
      renderIndex();return focused;
    """.replace("CONTROL", control), "renderIndex", "boxChip", stubs="""
      const inbox=[];function needsYouHtml(){return ''}
      const focused=[];nodes['#app']=node();
      document.getElementById=id=>({focus:options=>focused.push({id,options})});
    """)
    assert got == [{"id": control, "options": {"preventScroll": True}}]

