"""The address decides the surface, not the credential (#562, the default front end's half),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/562b_the_address_decides_the_surface.py

The claims, each a row:

  1. the boot sends the product owner at `/p/<project>/board` to the board, a card or preview link
     and the product page to their own page, and a board credential at `/product/<project>` to a
     refusal — and the administrator's `null` scopes reach both;
  2. the product owner's board is read only: no clock, no floor read, no new card, nothing dragged,
     a card opened on their own page, a step back through the boot again — with the way out and,
     after a reload from another tab's sign-in, the reason;
  3. the refusal names the board it may open, and only to a credential that may open it; the
     product owner's Board tab links to it;
  4. a product page whose credential loses the product area goes through the boot again, leaving
     no reason behind for the next one, and that credential gets no product chat.
"""

TEST = "tests/test_the_address_decides_the_surface.py"
PAGE = "openfactory/api/panel.html"

MUTATIONS = [
    # 1. the boot
    ("TODAY'S RULE: the product owner at the board address gets their own page again", PAGE,
     "  if(productOnly()&&asked&&asked.project&&!asked.card&&!asked.pr){ bootBoardRead(",
     "  if(false){ bootBoardRead("),
    ("a card link opens the read-only board instead of the card", PAGE,
     "  if(productOnly()&&asked&&asked.project&&!asked.card&&!asked.pr){ bootBoardRead(",
     "  if(productOnly()&&asked&&asked.project&&!asked.pr){ bootBoardRead("),
    ("TODAY'S RULE: the board credential gets the product owner's page", PAGE,
     "  if(curProduct()!==null&&noProductArea()){ refuseTheProductPage(curProduct()); return; }",
     "  if(false){ refuseTheProductPage(curProduct()); return; }"),
    ("the administrator's null scopes read as no product area", PAGE,
     '  return !!(me && Array.isArray(me.scopes) && me.scopes.indexOf("product")<0);',
     '  return !!(me && (me.scopes||[]).indexOf("product")<0);'),

    # 2. the read-only board
    ("the read-only board's refusals reload into another page", PAGE,
     '  _surface="product";_boardReadOnly=true;', '  _surface="floor";_boardReadOnly=true;'),
    ("the board is not read only for the product owner", PAGE,
     '  _surface="product";_boardReadOnly=true;', '  _surface="product";'),
    ("the read-only board reads the floor", PAGE,
     "  $(\"#app\").innerHTML=\"\";\n  await openBoard(name);",
     "  $(\"#app\").innerHTML=\"\";\n  await api(\"/api/projects\");await openBoard(name);"),
    ("the read-only board offers a new card", PAGE,
     "  const head = _boardReadOnly ? `", "  const head = false ? `"),
    ("a card on the read-only board can be dragged", PAGE,
     'draggable="${_boardReadOnly?"false":"true"}"', 'draggable="true"'),
    ("the read-only board wires the moves", PAGE,
     "  if(_boardReadOnly){\n    // READ ONLY (#562)", "  if(false){\n    // READ ONLY (#562)"),
    ("the read-only board leaves the floor's chrome on", PAGE,
     "  hideFloorChrome();\n  // A STEP BACK", "  // A STEP BACK"),
    ("a step back on the read-only board renders the floor", PAGE,
     "  window.onpopstate=()=>location.reload();\n", ""),
    ("the read-only board has no way out", PAGE,
     '      ${(me&&me.logout)?`<a class="btn ghost" href="${esc(safeUrl(me.logout))}">Sign out</a>`:""}\n'
     "    </div>${movedNotice(", "    </div>${movedNotice("),
    ("the read-only board does not say why it arrived", PAGE,
     '</div>${movedNotice("the board, read only")}`', "</div>`"),
    ("the notice says the product page wherever it landed", PAGE,
     '${esc(landed||"the product page")}', "the product page"),
    ("a card on the read-only board opens the board again", PAGE,
     "      const open=()=>{location.href=`/p/${encodeURIComponent(_bd.project)}/card/",
     "      const open=()=>{location.href=`/p/${encodeURIComponent(_bd.project)}/board/"),

    # 3. the refusal and the link
    ("the refusal leaves the floor's banner waiting for a read never made", PAGE,
     '  _surface="refused";\n  hideFloorChrome();', '  _surface="refused";'),
    ("the refusal names no board", PAGE,
     "the administrator's.${board&&name?`", "the administrator's.${false?`"),
    ("a credential scoped to no area is sent to a board it is refused", PAGE,
     'const board=!!(me&&Array.isArray(me.scopes)&&me.scopes.indexOf("floor")>=0);',
     "const board=true;"),
    ("a credential scoped to no area is told it is the board's", PAGE,
     '${board?"is for the board":"is scoped to no area"}', "is for the board"),
    ("the product owner's Board tab has no way to the board", PAGE,
     '\n            <a class="btn sm ghost" id="pbWhole" href="/p/${encodeURIComponent(name)}/board">'
     "The whole board</a>", ""),

    # 4. the credential that changes under the tab
    ("the product owner's page polls on under a credential their area refuses", PAGE,
     '  if(noProductArea()&&_surface==="product"&&takeBootsRoute(false))return me;',
     "  if(false)return me;"),
    ("the reload leaves a reason for the next product page to say", PAGE,
     '_surface==="product"&&takeBootsRoute(false))return me;',
     '_surface==="product"&&takeBootsRoute())return me;'),
    ("the route ignores what it was told about saying why", PAGE,
     'if(say)sessionStorage.setItem(MOVED_KEY+".say","1")',
     'sessionStorage.setItem(MOVED_KEY+".say","1")'),
    ("a credential with no product area gets the product chat", PAGE,
     "  if(noProductArea())return;\n  try{_pc.room=", "  try{_pc.room="),
]
