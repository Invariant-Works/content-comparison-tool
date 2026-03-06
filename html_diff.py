"""Generate a human-friendly, side-by-side HTML diff for a single comparison
case.  Uses :mod:`difflib` for the heavy lifting and adds a sticky toolbar with
navigation, counts, and a toggle for unchanged lines.
"""

import difflib
import textwrap
from typing import List, Tuple


# ---------------------------------------------------------------------------
# Text wrapping
# ---------------------------------------------------------------------------

def wrap_text_to_lines(text: str, width: int = 100) -> List[str]:
    """Split *text* into lines no longer than *width* characters.

    * Existing newlines are honoured (each becomes a separate paragraph).
    * Blank lines are preserved so section breaks survive.
    * ``textwrap.wrap`` is used with word-boundary-only breaking.
    """
    paragraphs = text.split("\n")
    result: List[str] = []
    for para in paragraphs:
        stripped = para.rstrip()
        if not stripped:
            result.append("")
            continue
        wrapped = textwrap.wrap(
            stripped,
            width=width,
            break_long_words=False,
            break_on_hyphens=False,
        )
        result.extend(wrapped if wrapped else [""])
    return result


# ---------------------------------------------------------------------------
# Diff counts via SequenceMatcher opcodes
# ---------------------------------------------------------------------------

def compute_diff_counts(
    lines_a: List[str], lines_b: List[str]
) -> Tuple[int, int, int]:
    """Return ``(insertions, deletions, replacements)`` line counts."""
    sm = difflib.SequenceMatcher(None, lines_a, lines_b)
    insertions = 0
    deletions = 0
    replacements = 0
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "insert":
            insertions += j2 - j1
        elif tag == "delete":
            deletions += i2 - i1
        elif tag == "replace":
            replacements += max(i2 - i1, j2 - j1)
    return insertions, deletions, replacements


# ---------------------------------------------------------------------------
# HTML generation
# ---------------------------------------------------------------------------

_CSS = """\
*{box-sizing:border-box}
body{margin:0;font-family:system-ui,-apple-system,Segoe UI,Roboto,Arial,sans-serif;
  font-size:14px;color:#24292f;background:#fff}
/* page container */
.page{padding:12px;max-width:100%}
.diff-wrap{max-width:100%}
/* toolbar */
.toolbar{position:sticky;top:0;z-index:100;display:flex;align-items:center;gap:16px;
  padding:10px 20px;background:#f6f8fa;border-bottom:1px solid #d0d7de;flex-wrap:wrap}
.toolbar h2{margin:0;font-size:15px;font-weight:600}
.toolbar .stat{font-size:13px;color:#57606a}
.toolbar .stat b{color:#24292f}
.toolbar button{padding:4px 12px;font-size:13px;border:1px solid #d0d7de;border-radius:6px;
  background:#fff;cursor:pointer}
.toolbar button:hover{background:#f3f4f6}
.toolbar label{font-size:13px;cursor:pointer;user-select:none}
/* header meta */
.meta{padding:12px 20px;font-size:13px;color:#57606a;background:#fafbfc;border-bottom:1px solid #e8e8e8;
  word-break:break-all}
.meta code{background:#eff1f3;padding:1px 5px;border-radius:4px;font-size:12px}
/* diff table — auto layout, liquid */
table.diff{width:100% !important;table-layout:auto !important;border-collapse:collapse;
  font-family:"SFMono-Regular",Consolas,"Liberation Mono",Menlo,monospace;
  font-size:13px;line-height:1.5}
table.diff colgroup{display:none}
table.diff td,table.diff th{
  padding:2px 8px;border:1px solid #eaeef2;vertical-align:top;
  white-space:pre-wrap;overflow-wrap:anywhere;word-break:normal}
/* line-number / header columns — stay narrow */
table.diff td.diff_header,table.diff th.diff_header{
  width:3.5em;white-space:nowrap;text-align:right;
  color:#8b949e;background:#f6f8fa;user-select:none}
/* text columns grow to fill remaining space */
table.diff td:not(.diff_header),table.diff th:not(.diff_header){width:auto}
/* HtmlDiff separator column — collapse */
table.diff .diff_next{background:#f6f8fa;width:0;padding:0;border:none;font-size:0;overflow:hidden}
/* HtmlDiff highlight classes */
table.diff .diff_add{background:#dafbe1}
table.diff .diff_chg{background:#fff8c5}
table.diff .diff_sub{background:#ffdce0}
table.diff span.diff_add{background:#aceebb;padding:1px 0;border-radius:2px}
table.diff span.diff_chg{background:#fae17d;padding:1px 0;border-radius:2px}
table.diff span.diff_sub{background:#ff9da4;padding:1px 0;border-radius:2px}
/* no-diff message */
.no-diff{padding:40px 20px;text-align:center;color:#57606a;font-size:16px}
/* hidden rows when toggled */
table.diff tr.unchanged-row.hidden-unchanged{display:none}
/* responsive: stacked view on narrow screens */
@media(max-width:900px){
  table.diff,table.diff thead,table.diff tbody,table.diff tr,table.diff td,table.diff th{
    display:block;width:100% !important;max-width:100%}
  table.diff td.diff_header,table.diff .diff_next{display:none}
  table.diff td:not(.diff_header):not(.diff_next){display:block;width:100% !important}
  table.diff tr{border-bottom:2px solid #d0d7de;margin-bottom:4px}
}
"""

_JS = """\
(function(){
  var changes=document.querySelectorAll('td.diff_add,td.diff_chg,td.diff_sub');
  var idx=-1;
  function go(dir){
    if(!changes.length)return;
    idx=Math.max(0,Math.min(changes.length-1,idx+dir));
    changes[idx].scrollIntoView({behavior:'smooth',block:'center'});
    document.getElementById('pos').textContent=(idx+1)+'/'+changes.length;
  }
  document.getElementById('prev').addEventListener('click',function(){go(-1)});
  document.getElementById('next').addEventListener('click',function(){go(1)});
  /* toggle unchanged rows */
  var togBtn=document.getElementById('togUnchanged');
  togBtn.addEventListener('change',function(){
    var rows=document.querySelectorAll('tr.unchanged-row');
    for(var i=0;i<rows.length;i++){
      rows[i].classList.toggle('hidden-unchanged',togBtn.checked);
    }
  });
})();
"""


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def generate_diff_html(
    case_id: str,
    url_a: str,
    url_b: str,
    locator_a: str,
    locator_b: str,
    text_a: str,
    text_b: str,
    similarity: float,
    line_width: int = 100,
) -> str:
    """Return a complete HTML document with a side-by-side diff."""

    lines_a = wrap_text_to_lines(text_a, width=line_width)
    lines_b = wrap_text_to_lines(text_b, width=line_width)

    insertions, deletions, replacements = compute_diff_counts(lines_a, lines_b)
    total_changes = insertions + deletions + replacements

    # --- no differences ---
    if lines_a == lines_b:
        return _build_page(
            case_id, url_a, url_b, locator_a, locator_b,
            similarity, insertions, deletions, replacements,
            body_html='<div class="no-diff">&#10004; No differences found.</div>',
        )

    # --- produce side-by-side table via HtmlDiff ---
    hd = difflib.HtmlDiff(wrapcolumn=80)
    table_html = hd.make_table(
        lines_a, lines_b,
        fromdesc="System A", todesc="System B",
        context=False,
        numlines=1,
    )

    # Mark unchanged rows so JS can toggle them.
    # HtmlDiff rows that have NO diff_add/diff_chg/diff_sub td are unchanged.
    import re
    def _tag_unchanged(match):
        row = match.group(0)
        if ("diff_add" not in row and "diff_chg" not in row
                and "diff_sub" not in row):
            return row.replace("<tr>", '<tr class="unchanged-row">', 1)
        return row
    table_html = re.sub(r"<tr>.*?</tr>", _tag_unchanged, table_html, flags=re.S)

    return _build_page(
        case_id, url_a, url_b, locator_a, locator_b,
        similarity, insertions, deletions, replacements,
        body_html=table_html,
    )


def _build_page(
    case_id, url_a, url_b, locator_a, locator_b,
    similarity, insertions, deletions, replacements,
    body_html,
):
    score_pct = f"{similarity * 100:.2f}%"
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Diff — {_esc(case_id)}</title>
<style>{_CSS}</style>
</head>
<body>
<div class="toolbar">
  <h2>Diff: {_esc(case_id)}</h2>
  <span class="stat">Similarity: <b>{score_pct}</b></span>
  <span class="stat">Insertions: <b style="color:#1a7f37">{insertions}</b></span>
  <span class="stat">Deletions: <b style="color:#cf222e">{deletions}</b></span>
  <span class="stat">Replacements: <b style="color:#9a6700">{replacements}</b></span>
  <button id="prev">&larr; Prev</button>
  <span id="pos" class="stat"></span>
  <button id="next">Next &rarr;</button>
  <label><input type="checkbox" id="togUnchanged"> Show only changed lines</label>
</div>
<div class="meta">
  <strong>System A:</strong> <code>{_esc(url_a)}</code> &nbsp; locator: <code>{_esc(locator_a)}</code><br>
  <strong>System B:</strong> <code>{_esc(url_b)}</code> &nbsp; locator: <code>{_esc(locator_b)}</code>
</div>
<div class="page">
<div class="diff-wrap">
{body_html}
</div>
</div>
<script>{_JS}</script>
</body>
</html>"""
