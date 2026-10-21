"""Every not-ok `WriteResult` the product module builds says why, or says that nobody decided it (#908).

WHAT WAS WRONG: `WriteResult` had no field saying WHY it was not ok, so `_write_outcome`
(`actions/catalog.py`) could not tell "this card is not yours" from "the forge is down", and
answered both as FAILED — HTTP 500. Measured on 620bb577 (2026-10-20): `product_withdraw_card` by
a product-scoped stranger answered 500 / `failed` with the module's own "only the person who asked
for #1 … can close or remove it".

WHAT IS HELD HERE, READ FROM THE SOURCE BY ITS SYNTAX TREE (a comment or a docstring naming the
field satisfies nothing): every call building a `WriteResult` — or its subclasses `adjust.Sent` and
`accept.Accepted` — with `ok=False` in `openfactory/product/*.py`, including those inside a
`lambda` and a list display, names `refusal=` with a constant of `openfactory.product.authoring`:
one of `REFUSALS` (a decision: "not yours", "already closed", …) or `NOT_REFUSED` (a write that was
tried and did not happen). The one exception is `_could_not`, the module's single failure
constructor, which never sets it: an untagged result IS a failure, and is what an older worker's
dict decodes to.

AND THE WORD IS THE ONE ITS SENTENCE DECIDES (review of PR #970): the sentence each site answers
with — `card_said('not_found')`, `unauthorized_message()`, `said['no_title']`, also the one handed
to `_could_not` or `_held` — is read off the same tree, and `SENTENCES` says which word it decides;
a sentence nobody classified fails, and so does a decision handed to the failure constructor.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PRODUCT = ROOT / "openfactory" / "product"

#: The constructors of a write's result: the class and the two subclasses that carry more.
_RESULTS = {"WriteResult", "Sent", "Accepted"}
#: The one failure constructor, whose `WriteResult` is untagged on purpose (`module.py`).
_THE_FAILURE = "_could_not"


def _named(func: ast.expr) -> str:
    """`WriteResult`, `adjust.Sent` → the class's own name; anything else → `""`."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return ""


def _not_ok(call: ast.Call) -> bool:
    """Whether this call says `ok=False`, by keyword or as its first positional argument."""
    for kw in call.keywords:
        if kw.arg == "ok":
            return isinstance(kw.value, ast.Constant) and kw.value.value is False
    first = call.args[0] if call.args else None
    return isinstance(first, ast.Constant) and first.value is False


def _says_why(call: ast.Call, allowed: set[str]) -> bool:
    """Whether `refusal=` is a Name of `authoring` whose value is a reason or `NOT_REFUSED`."""
    value = next((kw.value for kw in call.keywords if kw.arg == "refusal"), None)
    return isinstance(value, ast.Name) and value.id in allowed


def _untagged(source: str, where: str, allowed: set[str]) -> list[str]:
    """`file:line` of every not-ok result built in `source` outside `_could_not` that says no why.

    Walks the whole tree, so a call inside a `lambda` (`found=lambda item: WriteResult(...)`), a list
    display or a nested function is read like any other."""
    tree = ast.parse(source)
    exempt: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == _THE_FAILURE:
            exempt.update(id(inner) for inner in ast.walk(node))
    lines = sorted(node.lineno for node in ast.walk(tree)
                   if isinstance(node, ast.Call) and id(node) not in exempt
                   and _named(node.func) in _RESULTS and _not_ok(node)
                   and not _says_why(node, allowed))
    return [f"{where}:{line}" for line in lines]


def _allowed() -> set[str]:
    """The names of `authoring`'s constants a `refusal=` may carry, read from their values: every
    reason in `REFUSALS`, and `NOT_REFUSED`. Empty where the vocabulary does not exist."""
    from openfactory.product import authoring

    reasons = set(getattr(authoring, "REFUSALS", ()) or ())
    words = reasons | ({authoring.NOT_REFUSED} if hasattr(authoring, "NOT_REFUSED") else set())
    return {name for name, value in vars(authoring).items()
            if name.isupper() and isinstance(value, str) and value in words}


def test_every_not_ok_write_result_the_product_module_builds_names_its_refusal():
    """Criterion 1: a `WriteResult` the module refuses on purpose carries why. On 620bb577 every
    site is listed here: the field and the vocabulary did not exist."""
    allowed = _allowed()
    offenders = []
    for path in sorted(PRODUCT.glob("*.py")):
        offenders += _untagged(path.read_text(encoding="utf-8"),
                               str(path.relative_to(ROOT)), allowed)

    assert offenders == [], (
        f"{len(offenders)} not-ok results name no `refusal=` from `openfactory.product.authoring` "
        f"(one of REFUSALS, or NOT_REFUSED for a write that was tried and did not happen):\n  "
        + "\n  ".join(offenders))


def test_the_detector_would_catch_one():
    """A guard nobody can fail is not a guard: one untagged site in a lambda, one in a list display,
    one positional — each found; a tagged one and `_could_not`'s own are not."""
    source = (
        "def _could_not(s):\n"
        "    return WriteResult(ok=False, detail=s)\n"
        "def f(x):\n"
        "    g(found=lambda item: WriteResult(ok=False, detail='no'))\n"
        "    out = [adjust.Sent(ok=False, detail='no')]\n"
        "    h = Accepted(False, detail='no')\n"
        "    return WriteResult(ok=False, refusal=NOT_YOURS, detail='not yours')\n"
    )

    found = _untagged(source, "synthetic.py", {"NOT_YOURS", "NOT_REFUSED"})

    assert found == ["synthetic.py:4", "synthetic.py:5", "synthetic.py:6"], found


# ------------------------------------------------------------------------------------------------
# THE WORD IS THE RIGHT ONE, NOT ONLY A WORD (review of PR #970, robertocsp point 2). The guard
# above held that a site names a word of the vocabulary; it did not hold WHICH. On a647d604 five
# one-line cuts each put one deliberate refusal back to 500 and survived every module that names
# its symbol (`_held` → NOT_REFUSED: 5634 passed; `correct_card`'s closed card,
# `capability_retired`, `decision_on_retired`, `_remove_one`'s not-found, each → NOT_REFUSED). So
# the sentence a site answers with is read off the same tree, and the table below decides the
# word for it.


#: The two helpers that build a not-ok result from a sentence handed to them, and the word that
#: result names: `_could_not` is the failure, `_held` the hold. Each one's word is held by its own
#: test below (`test_the_failure_names_no_word_and_a_hold_names_not_waiting`); the sentences handed
#: to them are classified by SENTENCES like any other, so a decision cannot hide in `_could_not`.
_FUNNELS = {_THE_FAILURE: "NOT_REFUSED", "_held": "NOT_WAITING"}

#: EVERY SENTENCE A NOT-OK RESULT OF THE PRODUCT MODULE ANSWERS WITH, AND THE WORD IT DECIDES —
#: the PR body's "Site → reason" table, executable. Read by the sentence, never by the site: what
#: the person is told is what decides whether nobody decided it (`NOT_REFUSED`, a 500 with a
#: reference) or which refusal it is. A sentence added tomorrow is classified nowhere and fails
#: here until somebody decides it.
SENTENCES = {
    # not yours: the person may not make this write (403)
    "unauthorized_message()": "NOT_YOURS",
    "_not_the_requester()": "NOT_YOURS",
    "card_withdrawn_result()": "NOT_YOURS",
    "adjust_said('not_yours')": "NOT_YOURS",
    # not found: what the write names does not exist (404)
    "requirement_not_found()": "NOT_FOUND",
    "card_said('not_found')": "NOT_FOUND",
    "card_said('survivor_missing')": "NOT_FOUND",
    "correction_refused('not_found')": "NOT_FOUND",
    "record_said('capability_not_found')": "NOT_FOUND",
    "_w('accept_not_found')": "NOT_FOUND",
    "_w('decision_not_found')": "NOT_FOUND",
    "_w('drop_not_found')": "NOT_FOUND",
    # not waiting: the state does not admit it now (409)
    "breakdown_said('retired')": "NOT_WAITING",
    "record_said('decision_on_retired')": "NOT_WAITING",
    "record_said('capability_retired')": "NOT_WAITING",
    "ticket_held_for_its_requirement()": "NOT_WAITING",
    "refine_would_be_ignored()": "NOT_WAITING",
    "correction_refused('started')": "NOT_WAITING",
    "correction_refused('unmapped')": "NOT_WAITING",
    "board_move_said('outside_the_slice')": "NOT_WAITING",
    "filing_held('queue')": "NOT_WAITING",
    "breakdown_said('held')": "NOT_WAITING",
    "breakdown_said('carried_meanwhile')": "NOT_WAITING",
    "breakdown_said('out_of_time')": "NOT_WAITING",
    # a product that started before its code: the breakdown waits for its first source (#992)
    "breakdown_waits_for_code()": "NOT_WAITING",
    # already closed (409)
    "card_said('already_closed')": "ALREADY_CLOSED",
    "card_said('survivor_closed')": "ALREADY_CLOSED",
    "correction_refused('closed')": "ALREADY_CLOSED",
    # already there: the fact, the answer, the requirement exists (409)
    "record_said('fact_known')": "ALREADY_THERE",
    "record_said('answer_just_noted')": "ALREADY_THERE",
    "just_noted()": "ALREADY_THERE",
    "just_asked_for_a_requirement()": "ALREADY_THERE",
    "_w('twin_agreed')": "ALREADY_THERE",
    # not valid: what was asked cannot be written as asked (400)
    "said['no_title']": "NOT_VALID",
    "said['title_too_long_ticket']": "NOT_VALID",
    "said['title_too_long_defect']": "NOT_VALID",
    "breakdown_said('not_vetted')": "NOT_VALID",
    "adjust_said('empty')": "NOT_VALID",
    "adjust_said('too_long')": "NOT_VALID",
    "board_move_said('unrankable')": "NOT_VALID",
    "correction_refused('board')": "NOT_VALID",
    "correction_refused('requirement')": "NOT_VALID",
    "correction_refused('rename')": "NOT_VALID",
    "record_said('not_a_capability')": "NOT_VALID",
    "record_said('capability_is_a_link')": "NOT_VALID",
    "_not_a_promise()": "NOT_VALID",
    "nothing_to_build()": "NOT_VALID",
    "_w('staged_outside')": "NOT_VALID",
    "_w('fact_outside')": "NOT_VALID",
    "_w('no_decision')": "NOT_VALID",
    # nobody decided it: a write that was tried and did not happen, or could not see (500)
    "unavailable()": "NOT_REFUSED",
    "semaphore_busy()": "NOT_REFUSED",
    "too_much_at_once()": "NOT_REFUSED",
    "filing_held('unread')": "NOT_REFUSED",
    "filing_held('undeclared')": "NOT_REFUSED",
    "board_move_said('unreachable')": "NOT_REFUSED",
    "board_move_said('order_failed')": "NOT_REFUSED",
    "board_move_said('queue_failed')": "NOT_REFUSED",
    "said['queue_refused']": "NOT_REFUSED",
    "said['queue_retried']": "NOT_REFUSED",
    "said['ticket_failed']": "NOT_REFUSED",
    "said['defect_failed']": "NOT_REFUSED",
    "breakdown_said('unbroken')": "NOT_REFUSED",
    "breakdown_said('unstamped')": "NOT_REFUSED",
    "breakdown_said('file_failed')": "NOT_REFUSED",
    "card_said('board_unreadable')": "NOT_REFUSED",
    "card_said('no_criteria')": "NOT_REFUSED",
    "card_said('no_criteria_from')": "NOT_REFUSED",
    "card_said('refine_failed')": "NOT_REFUSED",
    "card_said('align_failed')": "NOT_REFUSED",
    "card_said('close_failed')": "NOT_REFUSED",
    "card_said('remove_failed')": "NOT_REFUSED",
    "card_said('repoint_failed')": "NOT_REFUSED",
    "correction_refused('failed')": "NOT_REFUSED",
    "record_said('undrafted')": "NOT_REFUSED",
    "record_said('unsurveyed')": "NOT_REFUSED",
    "record_said('no_code_copy')": "NOT_REFUSED",
    "record_said('capability_unreadable')": "NOT_REFUSED",
    "record_said('propose_failed')": "NOT_REFUSED",
    "record_said('accept_failed')": "NOT_REFUSED",
    "record_said('drop_failed')": "NOT_REFUSED",
    "record_said('capability_failed')": "NOT_REFUSED",
    "record_said('decision_failed')": "NOT_REFUSED",
    "record_said('answer_failed')": "NOT_REFUSED",
    "record_said('fact_failed')": "NOT_REFUSED",
    "record_said('distillate_failed')": "NOT_REFUSED",
    "record_said('document_failed')": "NOT_REFUSED",
    "record_said('survey_failed')": "NOT_REFUSED",
    "_w('branches_unreadable')": "NOT_REFUSED",
    "_w('prior_unreadable')": "NOT_REFUSED",
    "_w('already_pushed')": "NOT_REFUSED",
    "_w('supersede_failed')": "NOT_REFUSED",
    "_w('pr_failed')": "NOT_REFUSED",
    "_w('not_direct')": "NOT_REFUSED",
    "_w('not_direct_by_hand')": "NOT_REFUSED",
    "_w('decision_no_section')": "NOT_REFUSED",
    "_w('baseline_unreadable')": "NOT_REFUSED",
    "_w('baseline_stuck')": "NOT_REFUSED",
    "_w('baseline_pr_failed')": "NOT_REFUSED",
    "f'could not clone '": "NOT_REFUSED",
    "f'could not create '": "NOT_REFUSED",
    "f'could not push '": "NOT_REFUSED",
    "f'nothing to commit: '": "NOT_REFUSED",
    "f'the repository does not take a direct commit ('": "NOT_REFUSED",
}

#: Where the sentence does not decide the word — a parameter the helper was handed, or a helper
#: whose own branch picks between a decision and a failure for the same sentence function — and the
#: tests that hold each word instead.
DECIDED_ELSEWHERE = {
    "_held:sentence": ("tests/test_every_deliberate_product_refusal_says_why.py::"
                       "test_the_failure_names_no_word_and_a_hold_names_not_waiting",),
    "_the_door_said:moved.refused": (
        "tests/test_a_product_write_that_failed_is_still_a_failure_logged_with_a_reference.py::"
        "test_a_card_its_door_could_not_read_is_a_failure_with_a_reference_not_a_conflict",
        "tests/test_a_product_write_that_failed_is_still_a_failure_logged_with_a_reference.py::"
        "test_a_promotion_the_cards_door_refuses_by_its_column_answers_409_not_500"),
    "_the_gate_said:detail": ("tests/test_a_merge_gates_answer_is_a_refusal_or_a_failure_as_it_is"
                              ".py::test_a_gate_word_is_a_refusal_or_a_failure_as_it_is",),
    "_accept_refusal()": (
        "tests/test_requirement_can_be_dropped.py::"
        "test_accepting_something_the_CLIENT_dropped_never_calls_their_decision_an_unreadable_file",
        "tests/test_requirement_can_be_dropped.py::"
        "test_a_requirement_file_NOBODY_can_parse_is_still_ours_to_fix_and_still_an_error"),
    "_drop_refusal()": (
        "tests/test_requirement_can_be_dropped.py::"
        "test_dropping_a_requirement_another_already_replaced_is_a_refusal_with_a_next_step",
        "tests/test_requirement_can_be_dropped.py::"
        "test_dropping_a_requirement_file_NOBODY_can_parse_is_a_failure"),
}


@dataclass(frozen=True)
class _Site:
    """One not-ok result as the source builds it: where, the word it names (`_could_not`'s is
    `NOT_REFUSED`: it is the failure), and the keys of the sentence it answers with — two when the
    sentence's own key is an `a if … else b` — or the parameter it was handed (`held`)."""

    where: str
    word: str
    keys: tuple[str, ...]
    held: str = ""


def _constructor_keys(node: ast.expr) -> tuple[str, ...]:
    """The table's keys for a sentence built in place: `card_said('not_found')` for a constructor
    called with its key, `_w('drop_already')` for `authoring`'s table (the key is its second
    argument), `said['no_title']` for a subscript, `unauthorized_message()` for one with no key,
    and the literal head of an f-string (`f'could not push {…}'` → `f'could not push '`).
    `.format(…)` is read through. A key spelled `a if … else b` gives both."""
    if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) \
            and node.func.attr == "format":
        return _constructor_keys(node.func.value)
    if isinstance(node, ast.Call):
        name = _named(node.func)
        for arg in node.args:
            if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                return (f"{name}({arg.value!r})",)
            if isinstance(arg, ast.IfExp):
                branches = (arg.body, arg.orelse)
                if all(isinstance(b, ast.Constant) and isinstance(b.value, str) for b in branches):
                    return tuple(f"{name}({b.value!r})" for b in branches)
        return (f"{name}()",)
    if isinstance(node, ast.Subscript):
        holder, key = ast.unparse(node.value), node.slice
        if isinstance(key, ast.Constant):
            return (f"{holder}[{key.value!r}]",)
        if isinstance(key, ast.IfExp):
            return tuple(f"{holder}[{b.value!r}]" for b in (key.body, key.orelse)
                         if isinstance(b, ast.Constant))
    if isinstance(node, ast.JoinedStr):
        head = node.values[0] if node.values else None
        if isinstance(head, ast.Constant):
            return (f"f{head.value!r}",)
    return ()


def _sentence(node: ast.expr | None, scopes: list[ast.AST]) -> tuple[tuple[str, ...], str]:
    """`(keys, held)` for a site's sentence: built in place, or assigned to a name in one of the
    enclosing functions (`failed = correction_refused('failed', …)` in `correct_card`, read from
    its nested `write()`); a PARAMETER of the enclosing function, or an attribute of one, is
    `held` — `_held:sentence`, `_the_door_said:moved.refused` — and decided by its own test."""
    if node is None:
        return (), ""
    if isinstance(node, (ast.Name, ast.Attribute)):
        root = node
        while isinstance(root, ast.Attribute):
            root = root.value
        name = root.id if isinstance(root, ast.Name) else ""
        for scope in scopes:
            params = {a.arg for a in (*scope.args.posonlyargs, *scope.args.args,
                                      *scope.args.kwonlyargs)}
            if name in params:
                return (), f"{scope.name}:{ast.unparse(node)}"
            for inner in ast.walk(scope):
                if isinstance(inner, ast.Assign) and isinstance(node, ast.Name) and any(
                        isinstance(t, ast.Name) and t.id == name for t in inner.targets):
                    return _constructor_keys(inner.value), ""
        return (), ""
    return _constructor_keys(node), ""


def _sites(source: str, where: str) -> list[_Site]:
    """Every not-ok result `source` builds outside the two funnels, and every sentence it hands
    to one (`_could_not(sentence, act=…)`, `_held(sentence, act=…)`)."""
    tree = ast.parse(source)
    parent: dict[int, ast.AST] = {}
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            parent[id(child)] = node

    def scopes(node: ast.AST) -> list[ast.AST]:
        out, at = [], parent.get(id(node))
        while at is not None:
            if isinstance(at, (ast.FunctionDef, ast.AsyncFunctionDef)):
                out.append(at)
            at = parent.get(id(at))
        return out

    found = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        enclosing = scopes(node)
        funnel = _FUNNELS.get(_named(node.func))
        if funnel and any(kw.arg == "act" for kw in node.keywords):
            keys, held = _sentence(node.args[0] if node.args else None, enclosing)
            found.append(_Site(f"{where}:{node.lineno}", funnel, keys, held))
        elif _named(node.func) in _RESULTS and _not_ok(node) and not any(
                f.name == _THE_FAILURE for f in enclosing):
            word = next((kw.value for kw in node.keywords if kw.arg == "refusal"), None)
            detail = next((kw.value for kw in node.keywords if kw.arg == "detail"), None)
            keys, held = _sentence(detail, enclosing)
            found.append(_Site(f"{where}:{node.lineno}",
                               word.id if isinstance(word, ast.Name) else "", keys, held))
    return found


def _misread(sites: list[_Site], table: dict[str, str], elsewhere: dict) -> list[str]:
    """Each site whose word is not the one its sentence's row decides, whose sentence nobody has
    classified, or whose sentence was handed in by a helper no test is named for."""
    wrong = []
    for site in sites:
        if site.held:
            if site.held not in elsewhere:
                wrong.append(f"{site.where}: its sentence is the parameter {site.held!r}, and no "
                             f"test is named for it in DECIDED_ELSEWHERE")
            continue
        if not site.keys:
            wrong.append(f"{site.where}: a sentence this guard cannot read — build it with a "
                         f"constructor of `voice` (or `_w`), or hand it to a helper that is named "
                         f"in DECIDED_ELSEWHERE")
        for key in site.keys:
            if key in elsewhere:
                continue
            if key not in table:
                wrong.append(f"{site.where}: {key} is classified nowhere — add it to SENTENCES "
                             f"with the word its sentence decides")
            elif table[key] != site.word:
                wrong.append(f"{site.where}: {key} names {site.word or 'no word'}, and its "
                             f"sentence decides {table[key]}")
    return wrong


def _every_site() -> list[_Site]:
    return [site for path in sorted(PRODUCT.glob("*.py"))
            for site in _sites(path.read_text(encoding="utf-8"), str(path.relative_to(ROOT)))]


def test_every_not_ok_result_names_the_word_its_sentence_decides():
    """Criterion 1, held per sentence (review of PR #970, point 2): each site's word is the one
    SENTENCES decides for what it tells the person, and a sentence nobody classified fails. The five
    cuts the review measured green on a647d604 (`_remove_one`'s `card_said('not_found')`,
    `correct_card`'s `correction_refused('closed')`, `capability_retired`, `decision_on_retired`,
    each → `NOT_REFUSED`) are each one line of this list."""
    wrong = _misread(_every_site(), SENTENCES, DECIDED_ELSEWHERE)

    assert wrong == [], "\n  ".join([f"{len(wrong)} sites answer a word their sentence does not "
                                     f"decide:", *wrong])


def test_every_row_of_the_table_is_a_sentence_some_site_answers_with():
    """The table cannot rot into a list of sentences nobody says: each key is read off a site."""
    seen = {key for site in _every_site() for key in site.keys}

    assert set(SENTENCES) - seen == set(), sorted(set(SENTENCES) - seen)


def test_every_test_named_for_a_sentence_decided_elsewhere_exists():
    """DECIDED_ELSEWHERE is a promise that a test holds those words; each one it names is a test
    function in the file it names."""
    missing = []
    for tests in DECIDED_ELSEWHERE.values():
        for target in tests:
            file, _, name = target.partition("::")
            tree = ast.parse((ROOT / file).read_text(encoding="utf-8"))
            if name not in {n.name for n in tree.body if isinstance(n, ast.FunctionDef)}:
                missing.append(target)

    assert missing == [], missing


def test_the_table_reader_would_catch_a_wrong_word_and_an_unclassified_sentence():
    """The positive twin: a site whose word is not its sentence's, a decision handed to the failure
    constructor, a sentence nobody classified, and a parameter no test is named for — each found;
    a right one, read through a name assigned in an enclosing function, is not."""
    source = (
        "def _could_not(s, *, act):\n"
        "    return WriteResult(ok=False, detail=s)\n"
        "def verb(n, given):\n"
        "    failed = card_said('close_failed', number=n)\n"
        "    def write():\n"
        "        return _could_not(failed, act='close')\n"
        "    a = WriteResult(ok=False, refusal=NOT_REFUSED, detail=card_said('not_found'))\n"
        "    b = _could_not(said['no_title'], act='file')\n"
        "    c = WriteResult(ok=False, refusal=NOT_VALID, detail=card_said('brand_new'))\n"
        "    d = WriteResult(ok=False, refusal=NOT_WAITING, detail=given)\n"
        "    return WriteResult(ok=False, refusal=NOT_FOUND, detail=card_said('not_found'))\n"
    )
    table = {"card_said('not_found')": "NOT_FOUND", "card_said('close_failed')": "NOT_REFUSED",
             "said['no_title']": "NOT_VALID"}

    wrong = _misread(_sites(source, "synthetic.py"), table, {})

    assert [w.split(":")[1] for w in wrong] == ["7", "8", "9", "10"], wrong


def test_the_failure_names_no_word_and_a_hold_names_not_waiting():
    """The two funnels' own words, which every sentence handed to them inherits: `_could_not` is
    nobody's decision (a 500 with a reference), `_held` is a hold (`not_waiting`, 409). The review
    of PR #970 measured `_held` → `NOT_REFUSED` green over 148 modules (5634 passed) on a647d604."""
    from openfactory.product.authoring import NOT_REFUSED, NOT_WAITING
    from openfactory.product.module import _could_not, _held

    held = _held("held on the front it builds on", act="break down", why="front 2 builds on 1")
    failed = _could_not("I could not close it", act="close", cause="the forge is down")

    assert (held.ok, held.refusal, held.detail) == (False, NOT_WAITING,
                                                    "held on the front it builds on")
    assert (failed.ok, failed.refusal, failed.detail) == (False, NOT_REFUSED,
                                                          "I could not close it")
    assert _FUNNELS == {_THE_FAILURE: "NOT_REFUSED", "_held": "NOT_WAITING"}


def test_a_write_result_refuses_a_word_outside_its_vocabulary():
    """`WriteResult.__post_init__` refuses any word that is not a refusal nor `NOT_REFUSED`, by
    name — so a typo at a site raises where it is built, not as a 500 three layers up. The PR body
    claimed it on a647d604 and no test held it: the review's `if False:` cut survived 40 modules."""
    from openfactory.product.authoring import NOT_REFUSED, REFUSALS, WriteResult

    with pytest.raises(ValueError, match="not_yours") as raised:
        WriteResult(ok=False, refusal="anything_else", detail="no")
    assert "anything_else" in str(raised.value)
    for word in sorted(REFUSALS | {NOT_REFUSED}):
        assert WriteResult(ok=False, refusal=word, detail="no").refusal == word
