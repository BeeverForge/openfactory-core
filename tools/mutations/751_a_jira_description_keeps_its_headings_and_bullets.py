"""#751: a Jira description is read in the shapes the parser reads: headings, flat bullets, blanks.

The claims, each held by the test a row names (`JiraTracker._text`, the block renderer in
`openfactory/adapters/tracker/jira.py`):

  - C1. A `heading` reads as `#` x its level plus all of its inline text on one line; a missing or
    out-of-range level is a plain line. Held by the three heading tests in `TEST`, and through
    each vendor's `get_ticket` and the gate by `CROSS` (the jira params).
  - C2. Every list item, bulleted or numbered, nested or not, is a flat `- ` line, with its inline
    marks on that line, whatever block it opens with (a paragraph, a code block, an image then a
    paragraph, a nested list: all four are shapes `@atlaskit/adf-schema` 57.7.18 allows). Held by
    the list tests in `TEST`, and by `CROSS`.
  - C4. A list ends on a blank line, so the paragraph after it is not read into its last
    criterion. Held by a schema-shaped document with no empty paragraph after the list, so the
    blank line can only come from the renderer, not from the editor's own empty paragraph (KAN-4).
  - C5. Containers (table, expand, panel) and `hardBreak` never lose their text (ADR-0022 §4).
  - C6, the second instance. An empty paragraph is a blank line, so a body the factory wrote with
    `_adf` reads back byte-identical and a split child's out-of-scope keeps its own line. Held by
    `ROUND`, whose bodies come from `_child_body` itself.

M1 is the defect itself, as it was on 1be1835 for headings; M3 is the same for list items.
"""

TEST = "tests/test_a_jira_description_keeps_its_headings_and_bullets.py"
CROSS = "tests/test_a_card_written_in_jiras_editor_passes_the_gate_it_passes_on_github.py"
ROUND = "tests/test_what_the_factory_writes_to_jira_reads_back_as_it_wrote_it.py"
NEUTRAL = ("tests/test_tracker_is_vendor_neutral.py"
           "::test_jira_reads_a_description_written_with_rich_formatting")
JIRA = "openfactory/adapters/tracker/jira.py"

_PREFIX = 'prefix = ("#" * level + " ") if type(level) is int and 1 <= level <= 6 else ""'
_ITEM_HEAD = 'out.append("- " + inline(child))'
_JOIN = 'return "".join(inline(child) for child in node)'
_LIST_END = ("                if not nested:\n"
             "                    out.append(\"\")\n"
             "                    list_blank[0] = len(out) - 1\n")
# re-pinned 2026-10-19 (task 9): `item` now opens on whatever block gives its first line.
_NESTED = ("                start = len(out)\n"
           "                blocks(child, nested=True)\n")
_OPENS = '                        out[start] = "- " + out[start]\n'
_OWN_DASH = '                    if kind not in ("bulletList", "orderedList"):\n'
_GAVE_A_LINE = "                if not opened and len(out) > start:\n"
_EMPTY_PARAGRAPH = ("                out.append(line)\n"
                    "            elif kind == \"heading\":")
_GENERIC = ("            else:\n"
            "                blocks(node.get(\"content\") or [], nested)\n")

MUTATIONS = [
    ("M1 THE DEFECT: a heading is drawn without its # marker", JIRA,
     _PREFIX, 'prefix = ""',
     TEST + "::test_a_heading_reads_as_its_level_in_hashes_and_its_text"),

    ("M1 THE DEFECT, through get_ticket and the gate: a heading is drawn without its # marker", JIRA,
     _PREFIX, 'prefix = ""',
     CROSS),

    ("M2 the level is ignored: every heading is drawn as ## ", JIRA,
     _PREFIX,
     'prefix = "## " if type(level) is int and 1 <= level <= 6 else ""',
     TEST + "::test_a_heading_reads_as_its_level_in_hashes_and_its_text"),

    ("M3 THE DEFECT for lists: a list item is drawn without its - ", JIRA,
     _ITEM_HEAD, "out.append(inline(child))",
     TEST + "::test_a_bullet_list_reads_as_one_dash_line_per_item"),

    ("M3 THE DEFECT for lists, through get_ticket and the gate: no - before an item", JIRA,
     _ITEM_HEAD, "out.append(inline(child))",
     CROSS),

    ("M4 inline runs are joined with a newline: a bold run splits the heading", JIRA,
     _JOIN, 'return "\\n".join(inline(child) for child in node)',
     TEST + "::test_a_heading_written_with_bold_and_code_is_one_line"),

    ("M4 inline runs are joined with a newline: a code run splits the criterion", JIRA,
     _JOIN, 'return "\\n".join(inline(child) for child in node)',
     TEST + "::test_an_inline_mark_inside_a_bullet_does_not_split_the_criterion"),

    ("M5 no blank line after a list: the next paragraph joins the last criterion", JIRA,
     _LIST_END, "",
     TEST + "::test_a_paragraph_after_a_list_is_not_read_into_its_last_criterion"),

    ("M6 an orderedList is not a list: it falls through to the generic walk", JIRA,
     'elif kind in ("bulletList", "orderedList"):', 'elif kind in ("bulletList",):',
     TEST + "::test_a_numbered_list_reads_as_bullets_the_gate_counts"),

    ("M7 a list nested in an item is skipped (stop descending, read literally)", JIRA,
     _NESTED,
     ("                if kind in (\"bulletList\", \"orderedList\"):\n"
      "                    continue\n" + _NESTED),
     TEST + "::test_a_nested_list_item_is_a_criterion_of_its_own"),

    ("M8 an empty paragraph is dropped: the factory's blank lines are lost", JIRA,
     _EMPTY_PARAGRAPH,
     ("                if line:\n"
      "                    out.append(line)\n"
      "            elif kind == \"heading\":"),
     ROUND + "::test_a_body_the_factory_wrote_reads_back_byte_identical"),

    ("M8 an empty paragraph is dropped: the auto-split line joins the out-of-scope item", JIRA,
     _EMPTY_PARAGRAPH,
     ("                if line:\n"
      "                    out.append(line)\n"
      "            elif kind == \"heading\":"),
     ROUND + "::test_a_split_childs_out_of_scope_does_not_swallow_the_auto_split_line_on_jira"),

    ("M9 a hardBreak is ignored: the two halves are glued into one word", JIRA,
     '            if kind == "hardBreak":\n                return "\\n"\n',
     '            if kind == "hardBreak":\n                return ""\n',
     TEST + "::test_a_hard_break_is_a_line_break_not_a_glued_word"),

    ("M10 an unknown container is not walked: a table and an expand lose their text", JIRA,
     _GENERIC, "            else:\n                pass\n",
     TEST + "::test_a_table_cell_and_an_expand_still_give_up_their_text"),

    ("M10 an unknown container is not walked: the rich-formatting description reads empty", JIRA,
     _GENERIC, "            else:\n                pass\n",
     NEUTRAL),

    ("M11 a heading with no or an invalid level is drawn as ## ", JIRA,
     _PREFIX,
     'prefix = ("#" * level + " ") if type(level) is int and 1 <= level <= 6 else "## "',
     TEST + "::test_a_heading_with_no_level_is_read_as_a_plain_line"),

    ("M11 a heading with no level is drawn as \"#\" * 0 plus a space", JIRA,
     _PREFIX,
     'prefix = ("#" * (level if type(level) is int and level <= 6 else 0) + " ")',
     TEST + "::test_a_heading_with_no_level_is_read_as_a_plain_line"),

    ("M11 the 1..6 bound is dropped: level 9 is drawn as nine hashes", JIRA,
     _PREFIX,
     'prefix = ("#" * level + " ") if type(level) is int else ""',
     TEST + "::test_a_heading_with_no_level_is_read_as_a_plain_line"),

    ("M12 an item's - comes only from a first paragraph: a code block or image opens no item", JIRA,
     _OPENS, "                        pass\n",
     TEST + "::test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own"),

    ("M13 a nested list opening an item gets a second - before its own", JIRA,
     _OWN_DASH, "                    if True:\n",
     TEST + "::test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own"),

    ("M14 an image, which gives no line, is taken as the item's opening (raises IndexError)", JIRA,
     _GAVE_A_LINE, "                if not opened:\n",
     TEST + "::test_a_list_item_that_opens_with_another_block_is_still_a_criterion_of_its_own"),
    ("M15 a text node met by the block walk is dropped: an action item's text is lost", JIRA,
     '                out.append(str(node.get("text", "")))\n            else:',
     '                pass\n            else:',
     TEST + "::test_an_action_item_and_a_decision_still_give_up_their_text"),
]
