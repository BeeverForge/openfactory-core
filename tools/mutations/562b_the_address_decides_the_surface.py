"""The address decides the surface, not the credential (#562, the default front end's half),
proven by breaking it.

Run:  .venv/bin/python tools/mutate.py tools/mutations/562b_the_address_decides_the_surface.py

The claims, each a row:

  1. the boot sends the product owner at `/p/<project>/board` to the board, a card or preview link
     and the product page to their own page, and a board credential at `/product/<project>` to a
     refusal — and the administrator's `null` scopes reach both;
  2. the product owner's board is read only: no clock, no floor read, no new card, nothing dragged,
     a card opened on their own page;
  3. the refusal names the board it may open, and the product owner's Board tab links to it.
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
    ("a card on the read-only board opens the board again", PAGE,
     "      const open=()=>{location.href=`/p/${encodeURIComponent(_bd.project)}/card/",
     "      const open=()=>{location.href=`/p/${encodeURIComponent(_bd.project)}/board/"),

    # 3. the refusal and the link
    ("the refusal leaves the floor's banner waiting for a read never made", PAGE,
     '  _surface="refused";\n  for(const id of ["#floor","#costs","#board"])',
     '  _surface="refused";\n  for(const id of [])'),
    ("the refusal names no board", PAGE,
     "    credential, or the administrator's.${name?", "    credential, or the administrator's.${false?"),
    ("the product owner's Board tab has no way to the board", PAGE,
     '\n            <a class="btn sm ghost" id="pbWhole" href="/p/${encodeURIComponent(name)}/board">'
     "The whole board</a>", ""),
]
