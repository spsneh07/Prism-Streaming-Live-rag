"""Build the final submission deck from the Samsung PRISM template.

    python scripts/build_presentation.py

Reads the template `CollegeName_TeamName_Submission.pptx` (repo root, git-ignored) and writes
`SRM_Univ_Fantastic_4_Submission.pptx`. Every benchmark number on the slides is read from
`results/benchmark.json` below and checked against the values quoted in
`docs/presentation_facts.md`; the build stops if they disagree. The dashboard images in
`docs/screenshots/` are real captures of the running app (Demo 2 and Demo 3).
The template file itself is never modified.
"""
import copy
import json
from pathlib import Path

from lxml import etree
from pptx import Presentation
from pptx.chart.data import CategoryChartData
from pptx.dml.color import RGBColor
from pptx.enum.chart import XL_CHART_TYPE, XL_LEGEND_POSITION, XL_LABEL_POSITION
from pptx.enum.dml import MSO_LINE_DASH_STYLE, MSO_PATTERN_TYPE
from pptx.enum.shapes import MSO_CONNECTOR, MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, MSO_AUTO_SIZE, PP_ALIGN
from pptx.oxml.ns import qn
from pptx.util import Inches, Pt

ROOT = Path(__file__).resolve().parents[1]
TEMPLATE = ROOT / "CollegeName_TeamName_Submission.pptx"
OUT = ROOT / "SRM_Univ_Fantastic_4_Submission.pptx"
SHOTS = ROOT / "docs" / "screenshots"

GITHUB = "https://github.com/spsneh07/Prism-Streaming-Live-rag"
GITHUB_SHORT = "github.com/spsneh07/Prism-Streaming-Live-rag"
VIDEO = "https://drive.google.com/file/d/1qTrza9E9xEB6LtJP4BIdPNYOMkvRrxV3/view?usp=sharing"
TEAM = "Fantastic 4"
COLLEGE = "SRM Univ"
MEMBERS = [("Sneh Prasad", "sp0701@srmist.edu.in"), ("Purva Jain", "pj8602@srmist.edu.in"),
           ("Agadh Khanolkar", "ak1920@srmist.edu.in"), ("Srushti More", "sm1436@srmist.edu.in")]
BENCH_LABEL = "Development benchmark · 16-document synthetic corpus"
BENCH_NOTE = (BENCH_LABEL + " · held-out split, 63 cases / 77 turns · written by the system's author; "
              "not an official Samsung evaluation")

# ---------------------------------------------------------------- numbers (single source)
bench = json.loads((ROOT / "results" / "benchmark.json").read_text(encoding="utf-8"))
S = bench["summary"]
B, P, NER = S["baseline"], S["proposed"], S["ablation_no_early_retrieval"]
NOGATE = S["ablation_hybrid_no_rerank"]
pct = lambda v: round(100 * v)
M = {
    "early_b": pct(B["early_retrieval_rate"]), "early_p": pct(P["early_retrieval_rate"]),
    "lead": P["mean_retrieval_lead_s"],
    "multi_b": pct(B["multi_intent_identification"]), "multi_p": pct(P["multi_intent_identification"]),
    "cont_b": pct(B["refinement_state_continuity"]), "cont_p": pct(P["refinement_state_continuity"]),
    "abst_b": pct(B["abstention_accuracy"]), "abst_p": pct(P["abstention_accuracy"]),
    "hit_b": pct(B["citation_hit_rate"]), "hit_p": pct(P["citation_hit_rate"]), "hit_nogate": pct(NOGATE["citation_hit_rate"]),
    "sup_b": pct(B["citation_support_rate"]), "sup_p": pct(P["citation_support_rate"]),
    "fab_p": P["fabricated_citations"],
    "unnec_b": B["unnecessary_retrieval_calls"], "unnec_p": P["unnecessary_retrieval_calls"],
    "ttft_b": round(1000 * B["ttft_s_mean"]), "ttft_p": round(1000 * P["ttft_s_mean"]), "ttft_ner": round(1000 * NER["ttft_s_mean"]),
    "keep_b": pct(B["refinement_citation_retention"]),
}
GATES = {g["gate"]: g["status"] for g in bench["gates"]}
EXPECTED = {"early_b": 0, "early_p": 90, "multi_b": 0, "multi_p": 78, "cont_b": 0, "cont_p": 100, "abst_b": 33,
            "abst_p": 83, "hit_b": 73, "hit_p": 73, "hit_nogate": 84, "sup_b": 100, "sup_p": 100, "fab_p": 0,
            "unnec_b": 8, "unnec_p": 1, "ttft_b": 14, "ttft_p": 21, "ttft_ner": 187, "keep_b": 29}
facts = (ROOT / "docs" / "presentation_facts.md").read_text(encoding="utf-8")
assert M == {**M, **EXPECTED}, {k: (M[k], v) for k, v in EXPECTED.items() if M[k] != v}
assert f"mean lead {M['lead']:.3f} s" in facts, "retrieval lead differs from presentation_facts.md"
assert all(GATES[f"G{i}"] == "PASS" for i in range(1, 7)), GATES
ABSTAINED, ANSWERABLE = 12, 63  # docs/evaluation.md §5 "Key finding" (computed by report.py)
assert f"refused {ABSTAINED} of {ANSWERABLE} answerable" in facts

# ---------------------------------------------------------------- palette (from the template)
NAVY, INK, SLATE, MUTED = "14142B", "2A2A44", "63637E", "8A8AA3"
VIOLET, TPURPLE, LAV, TINT = "6D28D9", "704EA6", "D9D3F0", "F4F1FC"
LINE, GREYT, GREY = "E3E1EE", "F3F3F7", "9C9CB0"
BLUE, BLUET = "3B5BDB", "EAF0FF"
GREEN, GREENT = "15803D", "E6F4EC"
AMBER, AMBERT = "B45309", "FDF1DC"
PURP, PURPT = "7C3AED", "EFE7FD"
WHITE = "FFFFFF"

rgb = RGBColor.from_string
I = Inches
L, R, W = 0.92, 12.42, 11.5


def _nostyle(shape):
    st = shape._element.find(qn("p:style"))
    if st is not None:
        shape._element.remove(st)
    return shape


def _runs(p, runs, size, color, bold, font, italic=False):
    for item in runs:
        text, o = (item, {}) if isinstance(item, str) else item
        r = p.add_run()
        r.text = text
        f = r.font
        f.size = Pt(o.get("size", size))
        f.bold = o.get("bold", bold)
        f.italic = o.get("italic", italic)
        f.name = o.get("font", font)
        f.color.rgb = rgb(o.get("color", color))
        if "spc" in o:
            r._r.get_or_add_rPr().set("spc", str(o["spc"]))
        if "link" in o:
            r.hyperlink.address = o["link"]


def fill_text(tf, paras, size=14, color=NAVY, bold=False, font="Calibri", align="l", anchor="t",
              margin=0.0, after=0, ls=None, italic=False):
    tf.word_wrap = True
    tf.auto_size = MSO_AUTO_SIZE.NONE
    m = I(margin)
    tf.margin_left = tf.margin_right = m
    tf.margin_top = tf.margin_bottom = I(min(margin, 0.04))
    tf.vertical_anchor = {"t": MSO_ANCHOR.TOP, "m": MSO_ANCHOR.MIDDLE, "b": MSO_ANCHOR.BOTTOM}[anchor]
    if isinstance(paras, str):
        paras = [paras]
    for i, para in enumerate(paras):
        p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        p.alignment = {"l": PP_ALIGN.LEFT, "c": PP_ALIGN.CENTER, "r": PP_ALIGN.RIGHT}[align]
        if after:
            p.space_after = Pt(after)
        if ls:
            p.line_spacing = ls
        _runs(p, [para] if isinstance(para, (str, tuple)) else para, size, color, bold, font, italic)


def tb(slide, x, y, w, h, paras, **kw):
    s = slide.shapes.add_textbox(I(x), I(y), I(w), I(h))
    fill_text(s.text_frame, paras, **kw)
    return s


def box(slide, x, y, w, h, fill=None, line=None, lw=1.0, radius=0.12, dash=None, text=None, shape=None, **kw):
    kind = shape or (MSO_SHAPE.ROUNDED_RECTANGLE if radius else MSO_SHAPE.RECTANGLE)
    s = _nostyle(slide.shapes.add_shape(kind, I(x), I(y), I(w), I(h)))
    if radius and kind == MSO_SHAPE.ROUNDED_RECTANGLE:
        s.adjustments[0] = min(0.5, radius / min(w, h))
    if fill:
        s.fill.solid()
        s.fill.fore_color.rgb = rgb(fill)
    else:
        s.fill.background()
    if line:
        s.line.color.rgb = rgb(line)
        s.line.width = Pt(lw)
        if dash:
            s.line.dash_style = dash
    else:
        s.line.fill.background()
    if text is not None:
        kw.setdefault("margin", 0.1)
        fill_text(s.text_frame, text, **kw)
    return s


def chip(slide, x, y, w, h, text, fill, color=WHITE, size=11, line=None, bold=True, dash=None, radius=None):
    return box(slide, x, y, w, h, fill=fill, line=line, radius=radius if radius is not None else h / 2, dash=dash,
               text=text, size=size, color=color, bold=bold, align="c", anchor="m", margin=0.04)


def arrow(slide, x1, y1, x2, y2, color=SLATE, w=1.5, dash=None, head=True, tail=False):
    c = _nostyle(slide.shapes.add_connector(MSO_CONNECTOR.STRAIGHT, I(x1), I(y1), I(x2), I(y2)))
    c.line.color.rgb = rgb(color)
    c.line.width = Pt(w)
    if dash:
        c.line.dash_style = dash
    ln = c.line._get_or_add_ln()
    if tail:
        etree.SubElement(ln, qn("a:headEnd"), type="triangle", w="med", len="med")
    if head:
        etree.SubElement(ln, qn("a:tailEnd"), type="triangle", w="med", len="med")
    return c


def label(slide, x, y, w, text, color=VIOLET, size=11):
    return tb(slide, x, y, w, 0.28, [(text.upper(), {"spc": 150})], size=size, color=color, bold=True)


def set_title(slide, text):
    t = slide.shapes.title
    p = t.text_frame.paragraphs[0]
    runs = p.runs
    runs[0].text = text
    for r in runs[1:]:
        p._p.remove(r._r)
    for extra in t.text_frame.paragraphs[1:]:
        t.text_frame._txBody.remove(extra._p)


def drop_body(slide):
    for sh in list(slide.placeholders):
        if sh.placeholder_format.type is not None and sh.placeholder_format.idx != 0:
            sh._element.getparent().remove(sh._element)


def footer(slide, n, total):
    tb(slide, L, 7.02, 7.0, 0.25, f"Streaming Live RAG  ·  Team {TEAM}  ·  {COLLEGE}", size=9, color=MUTED)
    tb(slide, R - 1.0, 7.02, 1.0, 0.25, f"{n} / {total}", size=9, color=MUTED, align="r")


def footnote(slide, y=6.66, text=BENCH_NOTE):
    tb(slide, L, y, W, 0.26, [(text, {"italic": True})], size=9.5, color=SLATE)


def notes(slide, text):
    slide.notes_slide.notes_text_frame.text = text


def duplicate(prs, src):
    """Append a copy of a placeholder-only template slide (no images/charts to re-link)."""
    new = prs.slides.add_slide(src.slide_layout)
    tree = new.shapes._spTree
    for el in list(tree):
        if el.tag.endswith("}sp"):
            tree.remove(el)
    for el in src.shapes._spTree:
        if el.tag.endswith("}sp"):
            tree.append(copy.deepcopy(el))
    return new


def reorder(prs, order):
    lst = prs.slides._sldIdLst
    items = list(lst)
    for el in items:
        lst.remove(el)
    for i in order:
        lst.append(items[i])


# =============================================================== build
prs = Presentation(TEMPLATE)
tpl = list(prs.slides)
# template: 0 title, 1 theme, 2 gaps, 3 solution+arch, 4 demo, 5 tools, 6 impact, 7 innovation/results/limits,
#           8 next, 9 brownie, 10 checklist, 11 thank you
arch = duplicate(prs, tpl[3])      # 12
refine = duplicate(prs, tpl[4])    # 13
results = duplicate(prs, tpl[7])   # 14
reorder(prs, [0, 1, 2, 3, 12, 4, 13, 5, 6, 14, 7, 8, 9, 10, 11])
slides = list(prs.slides)
TOTAL = len(slides)
(s_title, s_theme, s_gaps, s_sol, s_arch, s_demo, s_refine, s_tools, s_impact, s_results, s_innov,
 s_next, s_why, s_check, s_thanks) = slides
for s in slides[1:14]:
    drop_body(s)

# ---------------------------------------------------------------- 1. title
body = next(sh for sh in s_title.shapes if sh.shape_id == 95)
body.width, body.height = I(6.75), I(3.3)
txBody = body.text_frame._txBody
paras = txBody.findall(qn("a:p"))
proto_first, proto_rest = copy.deepcopy(paras[0]), copy.deepcopy(paras[1])
for p in paras:
    txBody.remove(p)
rows = [("Theme ID - ", "Theme 4 · Streaming Live RAG"), ("Project - ", "Streaming Live RAG"),
        ("Team Name - ", TEAM), ("College Name - ", COLLEGE)]
rows += [(f"Member {i} - ", f"{n}  ·  {e}") for i, (n, e) in enumerate(MEMBERS, 1)]
rows += [("Submission GitHub link - ", GITHUB_SHORT)]
for i, (lab, val) in enumerate(rows):
    p = copy.deepcopy(proto_first if i == 0 else proto_rest)
    for r in p.findall(qn("a:r")):
        p.remove(r)
    end = p.find(qn("a:endParaRPr"))
    tmpl_r = copy.deepcopy(paras[0].find(qn("a:r")))
    for text, is_val in ((lab, False), (val, True)):
        r = copy.deepcopy(tmpl_r)
        r.find(qn("a:t")).text = text
        rpr = r.find(qn("a:rPr"))
        if is_val:
            rpr.set("b", "1")
            rpr.find(qn("a:solidFill")).find(qn("a:srgbClr")).set("val", NAVY if i < 8 else VIOLET)
        if end is not None:
            end.addprevious(r)
        else:
            p.append(r)
    txBody.append(p)
# make the GitHub value a real link
for r in body.text_frame.paragraphs[-1].runs:
    r.font.size = Pt(14.5)
last = body.text_frame.paragraphs[-1].runs[-1]
last.hyperlink.address = GITHUB
notes(s_title, "Team Fantastic 4, SRM Univ. Theme 4, Streaming Live RAG. "
      "One line: retrieval that starts while the user is still speaking, splits compound requests, "
      "and refines the answer when late details arrive. All numbers in this deck come from a development "
      "benchmark on a 16-document synthetic corpus; the official Theme 4 corpus was not available.")

# ---------------------------------------------------------------- 2. theme / problem
set_title(s_theme, "Theme 4 — Streaming Live RAG")
label(s_theme, L, 1.9, 5, "The problem")
tb(s_theme, L, 2.2, 4.75, 1.1, "Natural speech is not a clean search query.", size=28, bold=True, color=NAVY,
   font="Arial", ls=0.95)
tb(s_theme, L, 3.35, 4.6, 0.7, "Conventional RAG generally waits for the complete utterance, then runs one search.",
   size=14, color=SLATE)
beh = [("Asks several questions", "in one utterance"), ("Adds an important detail", "halfway through"),
       ("Corrects itself", "mid-sentence"), ("Asks to change", "a previous answer")]
cw, ch, gx, gy, x0, y0 = 3.2, 0.95, 0.2, 0.2, 6.02, 1.95
for i, (a, b) in enumerate(beh):
    x, y = x0 + (i % 2) * (cw + gx), y0 + (i // 2) * (ch + gy)
    box(s_theme, x, y, cw, ch, fill=TINT)
    chip(s_theme, x + 0.18, y + 0.26, 0.43, 0.43, str(i + 1), VIOLET, size=13, radius=0.1)
    tb(s_theme, x + 0.78, y + 0.14, cw - 0.9, 0.7, [[(a, {"bold": True})], [(b, {"color": SLATE})]], size=14,
       anchor="m")
# two lanes
lanes = [("CONVENTIONAL RAG", GREYT, SLATE, [("Speak", GREYT, NAVY), ("Wait", WHITE, SLATE), ("Retrieve", GREYT, NAVY),
                                             ("Answer", GREYT, NAVY)]),
         ("STREAMING LIVE RAG", VIOLET, WHITE, [("Speak", TINT, NAVY), ("Partial transcript", TINT, NAVY),
                                                ("Retrieve", GREENT, GREEN), ("More speech", TINT, NAVY),
                                                ("Refine", BLUET, BLUE), ("Answer", VIOLET, WHITE)])]
for li, (name, lf, lc, steps) in enumerate(lanes):
    y = 4.42 + li * 0.95
    chip(s_theme, L, y, 2.2, 0.62, name, lf, color=lc, size=12, radius=0.1,
         line=LINE if li == 0 else None)
    sx, cwid, gap = 3.42, 1.25, 0.26
    for j, (t, f, c) in enumerate(steps):
        x = sx + j * (cwid + gap)
        chip(s_theme, x, y + 0.06, cwid, 0.5, t, f, color=c, size=12, radius=0.25,
             line=(GREY if (li == 0 and t == "Wait") else (LINE if f in (GREYT, TINT) else None)),
             dash=MSO_LINE_DASH_STYLE.DASH if (li == 0 and t == "Wait") else None)
        if j < len(steps) - 1:
            arrow(s_theme, x + cwid + 0.04, y + 0.31, x + cwid + gap - 0.04, y + 0.31, color=GREY, w=1.25)
tb(s_theme, L, 6.28, W, 0.4, [[("Objective  ", {"bold": True, "color": VIOLET}),
                              ("Retrieve useful context while the conversation is still unfolding.",
                               {"bold": True})]], size=16)
notes(s_theme, "Voice users speak one natural sentence, not a search query. It can hide several questions, "
      "a late constraint, a correction, or a request to reformat the last answer. Typical RAG waits for silence "
      "and sends the whole sentence as one query. Theme 4 asks for retrieval that works while the conversation "
      "is still unfolding.")

# ---------------------------------------------------------------- 3. existing solutions & gaps
set_title(s_gaps, "Existing Solutions & Gaps")
cols = [(L, 2.25), (L + 2.35, 4.35), (L + 6.8, 4.7)]
hy = 1.9
chip(s_gaps, cols[1][0], hy, cols[1][1], 0.46, "Typical query-then-retrieve pipelines", GREYT, color=NAVY, size=13,
     radius=0.08, line=LINE)
chip(s_gaps, cols[2][0], hy, cols[2][1], 0.46, "Streaming Live RAG (ours)", VIOLET, size=13, radius=0.08)
rows3 = [("Query handling", "Whole utterance → one query", "One utterance → N sub-queries"),
         ("Retrieval timing", "Starts after the user stops speaking",
          "Starts during speech, once the partial transcript is specific"),
         ("Multi-intent requests", "Intents blended into a single query", "Decomposed, retrieved in parallel, fused"),
         ("Late-arriving details", "Usually a fresh query over the whole context",
          "Delta-only retrieval; answer v1 → v2"),
         ("Unnecessary retrieval", "Every turn searches the corpus",
          "Presentation / chit-chat turns → SUPPRESS"),
         ("Session refinement", "Little answer state kept between turns",
          "Session memory keeps claims, citations, sub-queries"),
         ("Grounding", "Citations are often best-effort",
          "Every claim validated; calibrated abstention")]
rh, rg = 0.5, 0.055
for i, (d, a, b) in enumerate(rows3):
    y = hy + 0.46 + 0.1 + i * (rh + rg)
    tb(s_gaps, cols[0][0], y, cols[0][1], rh, [(d, {"bold": True})], size=13, anchor="m", color=NAVY)
    box(s_gaps, cols[1][0], y, cols[1][1], rh, fill=WHITE, line=LINE, radius=0.06, text=a, size=13, color=SLATE,
        anchor="m", margin=0.14)
    box(s_gaps, cols[2][0], y, cols[2][1], rh, fill=TINT, radius=0.06, text=b, size=13, color=NAVY, anchor="m",
        margin=0.14)
tb(s_gaps, L, 6.33, W, 0.3,
   [[("Measured on our conventional baseline:  ", {"bold": True, "color": NAVY}),
     (f"early retrieval {M['early_b']}%  ·  multi-intent {M['multi_b']}%  ·  {M['unnec_b']} searches on 8 no-search "
      f"turns  ·  refinement continuity {M['cont_b']}%", {})]],
   size=12, color=SLATE)
footnote(s_gaps)
notes(s_gaps, "We do not claim every existing system behaves this way; this is the typical query-then-retrieve "
      "pattern, which is also what our conventional baseline implements. The bottom line is measured on that "
      "baseline in our development benchmark.")

# ---------------------------------------------------------------- 4. our solution
set_title(s_sol, "Our Solution")
steps4 = [("01", "Incremental transcript", "chunks arrive while the user is still speaking"),
          ("02", "Retrieval controller", None),
          ("03", "Multi-intent decomposer", "one utterance → N sub-queries"),
          ("04", "Parallel retrieval", "dense + BM25 for every sub-query"),
          ("05", "Evidence fusion + reranking", ["RRF · dedup", "cross-encoder rerank"]),
          ("06", "Grounded answer", "cited claims, validated; abstains when evidence is missing")]
bw, gap, y4, h4 = 1.64, 0.332, 1.95, 1.9
for i, (n, t, d) in enumerate(steps4):
    x = L + i * (bw + gap)
    last = i == len(steps4) - 1
    box(s_sol, x, y4, bw, h4, fill=VIOLET if last else TINT, radius=0.12)
    tb(s_sol, x + 0.14, y4 + 0.14, bw - 0.28, 0.25, [(n, {"spc": 100})], size=11, bold=True,
       color=LAV if last else VIOLET)
    tb(s_sol, x + 0.14, y4 + 0.42, bw - 0.28, 0.62, t, size=14, bold=True, color=WHITE if last else NAVY, ls=0.95)
    if d:
        tb(s_sol, x + 0.14, y4 + 1.08, bw - 0.28, 0.75, d, size=11, color=LAV if last else SLATE)
    else:
        for k, (pt, pf) in enumerate((("WAIT", AMBER), ("RETRIEVE", GREEN), ("SUPPRESS", PURP))):
            chip(s_sol, x + 0.14, y4 + 1.02 + k * 0.28, 1.1, 0.23, pt, pf, size=9)
    if not last:
        arrow(s_sol, x + bw + 0.05, y4 + h4 / 2, x + bw + gap - 0.05, y4 + h4 / 2, color=VIOLET, w=1.75)
# key idea panel
py, ph = 4.2, 2.3
box(s_sol, L, py, W, ph, fill=TINT, radius=0.15)
label(s_sol, L + 0.3, py + 0.25, 4, "Key idea")
tb(s_sol, L + 0.3, py + 0.55, 4.1, 1.0, "Live retrieval before utterance end", size=24, bold=True, font="Arial",
   color=NAVY, ls=0.95)
tb(s_sol, L + 0.3, py + 1.5, 4.0, 0.75,
   "Provisional retrieval and answer-sentence scoring run while the user is talking; results are reused when "
   "they stop.", size=12, color=SLATE)
# real trace of Demo 2 (scripts/demo_stream.py --scenario multi_intent)
tx0, tx1, t_max = L + 5.05, L + W - 0.35, 2.4
X = lambda t: tx0 + (tx1 - tx0) * t / t_max
rows_y = {"Speech": py + 0.45, "Controller": py + 0.8, "Retrieval": py + 1.15, "Answer": py + 1.5}
for name, yy in rows_y.items():
    tb(s_sol, tx0 - 1.2, yy - 0.12, 0.95, 0.24, name, size=10, color=SLATE, align="r")
    arrow(s_sol, tx0, yy, tx1, yy, color=LINE, w=0.75, head=False)
for a, b in ((0.0, 0.80), (0.80, 1.61), (1.61, 2.11)):
    box(s_sol, X(a) + 0.02, rows_y["Speech"] - 0.08, X(b) - X(a) - 0.04, 0.16, fill="C9C3E6", radius=0.04)
for t, c in ((0.007, AMBER), (0.813, GREEN), (1.624, GREEN)):
    box(s_sol, X(t) - 0.08, rows_y["Controller"] - 0.08, 0.16, 0.16, fill=c, shape=MSO_SHAPE.OVAL, radius=0)
for a, b in ((0.824, 0.914), (1.640, 1.795)):
    r = box(s_sol, X(a), rows_y["Retrieval"] - 0.09, max(X(b) - X(a), 0.12), 0.18, radius=0)
    r.fill.patterned()
    r.fill.pattern = MSO_PATTERN_TYPE.WIDE_UPWARD_DIAGONAL
    r.fill.fore_color.rgb = rgb(GREEN)
    r.fill.back_color.rgb = rgb(GREENT)
box(s_sol, X(2.170) - 0.08, rows_y["Answer"] - 0.08, 0.16, 0.16, fill=VIOLET, shape=MSO_SHAPE.OVAL, radius=0)
arrow(s_sol, X(2.111), py + 0.25, X(2.111), py + 1.72, color=BLUE, w=1.5, dash=MSO_LINE_DASH_STYLE.DASH, head=False)
tb(s_sol, X(2.111) - 1.2, py + 0.08, 1.15, 0.2, "utterance end", size=9, color=BLUE, align="r")
# lead bracket
arrow(s_sol, X(0.824), py + 1.83, X(2.111), py + 1.83, color=GREEN, w=1.5, head=True, tail=True)
tb(s_sol, X(0.824) - 0.15, py + 1.9, 3.6, 0.3,
   [[("Retrieval began 1.29 s before the user finished", {"bold": True, "color": GREEN})]], size=11)
tb(s_sol, L + 0.3, py + ph + 0.06, W, 0.25,
   [("Actual trace · Demo 2 (Theme 4 guide example) · real-time pace · scripts/demo_stream.py --scenario multi_intent",
     {"italic": True})], size=9.5, color=SLATE)
notes(s_sol, "Six stages. The controller runs on every transcript chunk and decides WAIT, RETRIEVE or SUPPRESS. "
      "As soon as the partial transcript is specific, retrieval starts in the background. The panel shows the real "
      "Demo 2 trace: first chunk WAIT at 0.00 s, RETRIEVE at 0.81 s, second RETRIEVE at 1.62 s, utterance end at "
      "2.11 s. Retrieval began 1.29 s before the user finished.")

# ---------------------------------------------------------------- 5. architecture
set_title(s_arch, "System Architecture")
ry, rh5 = 2.35, 1.3
blocks = {  # key: (x, w)
    "in": (L, 1.2), "ctl": (2.40, 1.6), "dec": (4.28, 1.35), "par": (5.91, 2.1),
    "rrf": (8.29, 1.1), "rr": (9.67, 1.1), "val": (11.05, 1.37)}
cy = ry + rh5 / 2


def ablock(slide, key, num, title, sub, fill=TINT, tcol=NAVY):
    x, w = blocks[key]
    box(slide, x, ry, w, rh5, fill=fill, radius=0.1)
    tb(slide, x + 0.1, ry + 0.1, w - 0.2, 0.2, num, size=9, bold=True, color=VIOLET)
    tb(slide, x + 0.1, ry + 0.3, w - 0.2, 0.55, title, size=12, bold=True, color=tcol, ls=0.92)
    if sub:
        tb(slide, x + 0.1, ry + 0.84, w - 0.2, 0.44, sub, size=9.5, color=SLATE, ls=0.95)


ablock(s_arch, "in", "01", "Streaming transcript input", "chunks on one clock")
x, w = blocks["ctl"]
box(s_arch, x, ry, w, rh5, fill=TINT, radius=0.1)
tb(s_arch, x + 0.1, ry + 0.1, w - 0.2, 0.2, "02", size=9, bold=True, color=VIOLET)
tb(s_arch, x + 0.1, ry + 0.28, w - 0.2, 0.25, "Retrieval controller", size=12, bold=True)
for k, (pt, pf) in enumerate((("WAIT", AMBER), ("RETRIEVE", GREEN), ("SUPPRESS", PURP))):
    chip(s_arch, x + 0.12, ry + 0.58 + k * 0.23, 0.95, 0.19, pt, pf, size=8)
ablock(s_arch, "dec", "03", "Multi-intent decomposer", "segment · re-attach · carry entities")
x, w = blocks["par"]
for off in (0.12, 0.06):
    box(s_arch, x + off, ry - off, w, rh5, fill=WHITE, line="BFD0FF", radius=0.1)
box(s_arch, x, ry, w, rh5, fill=BLUET, line="BFD0FF", radius=0.1)
tb(s_arch, x + 0.1, ry + 0.08, w - 0.2, 0.3, [[("Parallel retrieval ", {"bold": True}), ("× N", {})]],
   size=10.5, color=BLUE)
for k, (n, t, sub) in enumerate((("04", "Dense", "MiniLM"), ("05", "BM25", "sparse"))):
    bx = x + 0.12 + k * 0.98
    box(s_arch, bx, ry + 0.42, 0.88, 0.76, fill=WHITE, radius=0.08)
    tb(s_arch, bx + 0.08, ry + 0.46, 0.75, 0.7, [[(n, {"size": 8.5, "color": VIOLET, "bold": True})],
                                                 [(t, {"bold": True})], [(sub, {"size": 9.5, "color": SLATE})]],
       size=12, ls=0.95)
ablock(s_arch, "rrf", "06", "RRF fusion", "quota · dedup · versions")
ablock(s_arch, "rr", "07", "Reranker", "cross-encoder")
ablock(s_arch, "val", "09", "Grounding / citation validator", "id · evidence · text · numbers")
order = ["in", "ctl", "dec", "par", "rrf", "rr", "val"]
for a, b in zip(order, order[1:]):
    xa = blocks[a][0] + blocks[a][1]
    xb = blocks[b][0]
    arrow(s_arch, xa + 0.03, cy, xb - 0.03 - (0.0 if b != "par" else 0.0), cy, color=NAVY, w=1.5)
# provisional path above the row
cx_ctl = blocks["ctl"][0] + 0.8
cx_par = blocks["par"][0] + 1.05
yp = 1.98
arrow(s_arch, cx_ctl, ry, cx_ctl, yp, color=GREEN, w=1.25, dash=MSO_LINE_DASH_STYLE.DASH, head=False)
arrow(s_arch, cx_ctl, yp, cx_par, yp, color=GREEN, w=1.25, dash=MSO_LINE_DASH_STYLE.DASH, head=False)
arrow(s_arch, cx_par, yp, cx_par, ry - 0.13, color=GREEN, w=1.25, dash=MSO_LINE_DASH_STYLE.DASH)
tb(s_arch, cx_ctl + 0.1, yp - 0.29, 6.0, 0.25,
   [("RETRIEVE during speech → provisional retrieval, reused at utterance end", {"bold": True})], size=9.5,
   color=GREEN)
# row 2
r2y, r2h = 4.3, 1.0
mx, mw = 2.40, 3.23
box(s_arch, mx, r2y, mw, r2h, fill=WHITE, line=VIOLET, lw=1.25, radius=0.1)
tb(s_arch, mx + 0.12, r2y + 0.1, mw - 0.24, 1.0,
   [[("08  ", {"size": 9, "color": VIOLET}), ("Session memory", {}), ("  (session-scoped only)",
                                                                     {"bold": False, "size": 10, "color": SLATE})],
    [("answer vN · claims · citations · per-sub-query results; 30-min idle TTL, no user id",
      {"bold": False, "size": 10, "color": SLATE})]], size=12, bold=True, ls=0.95)
ox, ow = 9.67, 2.75
box(s_arch, ox, r2y, ow, r2h, fill=VIOLET, radius=0.1)
tb(s_arch, ox + 0.12, r2y + 0.1, ow - 0.24, 1.0,
   [[("10  ", {"size": 9, "color": LAV}), ("Streaming response", {})],
    [("SSE → dashboard: answer vN + citations + uncertainty", {"bold": False, "size": 10, "color": LAV})]],
   size=12, bold=True, color=WHITE, ls=0.95)
# verticals
xc = blocks["ctl"][0] + 0.55
arrow(s_arch, xc, ry + rh5 + 0.03, xc, r2y - 0.03, color=BLUE, w=1.5)
tb(s_arch, blocks["in"][0], ry + rh5 + 0.08, xc - blocks["in"][0] - 0.08, 0.55, "late detail or presentation turn",
   size=9, color=BLUE, align="r")
xd = blocks["dec"][0] + 0.55
arrow(s_arch, xd, r2y - 0.03, xd, ry + rh5 + 0.03, color=BLUE, w=1.5)
tb(s_arch, xd + 0.1, ry + rh5 + 0.08, 1.35, 0.55, "delta sub-queries only (refinement)", size=9, color=BLUE)
xv = blocks["val"][0] + blocks["val"][1] / 2 + 0.2
arrow(s_arch, xv, ry + rh5 + 0.03, xv, r2y - 0.03, color=NAVY, w=1.5)
tb(s_arch, xv - 1.25, ry + rh5 + 0.15, 1.15, 0.3, "validated claims", size=9, color=SLATE, align="r")
# suppression path
arrow(s_arch, mx + mw + 0.03, r2y + r2h / 2, ox - 0.03, r2y + r2h / 2, color=PURP, w=1.5,
      dash=MSO_LINE_DASH_STYLE.DASH)
tb(s_arch, mx + mw + 0.2, r2y + 0.1, ox - mx - mw - 0.4, 0.4,
   [("SUPPRESS: presentation-only request", {"bold": True})], size=10, color=PURP, align="c")
tb(s_arch, mx + mw + 0.2, r2y + r2h / 2 + 0.08, ox - mx - mw - 0.4, 0.4,
   "reshape the previous answer from session memory · no corpus search", size=9.5, color=SLATE, align="c")
# telemetry
ty = 5.8
box(s_arch, L, ty, W, 0.5, fill=GREYT, radius=0.08,
    text=[[("11  ", {"size": 9, "color": VIOLET, "bold": True}), ("Telemetry  ", {"bold": True}),
           ("every stage emits events on one monotonic clock → live dashboard · SSE · JSONL export · benchmark",
            {"color": SLATE})]], size=11.5, anchor="m", margin=0.15)
for xx in (mx + mw / 2, ox + ow / 2):
    arrow(s_arch, xx, ty - 0.02, xx, (r2y + r2h + 0.02) if xx != L + 0.6 else ry + rh5 + 0.02, color=GREY, w=1,
          dash=MSO_LINE_DASH_STYLE.ROUND_DOT, head=False)
# legend
lg = [("main flow", NAVY, None), ("provisional, during speech", GREEN, MSO_LINE_DASH_STYLE.DASH),
      ("late-detail refinement", BLUE, None), ("suppression", PURP, MSO_LINE_DASH_STYLE.DASH)]
lx = L
for t, c, d in lg:
    arrow(s_arch, lx, 6.62, lx + 0.4, 6.62, color=c, w=1.5, dash=d)
    tb(s_arch, lx + 0.48, 6.5, 2.3, 0.25, t, size=10, color=SLATE)
    lx += 2.6
notes(s_arch, "Main flow left to right: transcript chunks, controller, decomposer, parallel dense and BM25 "
      "retrieval per sub-query, RRF fusion with a coverage quota, cross-encoder rerank, then the grounding "
      "validator and the SSE response. Green dashed: RETRIEVE decisions during speech start provisional "
      "retrieval in the background; results are reused at utterance end. Blue: a late detail is classified as a "
      "refinement; session memory supplies the prior sub-queries and claims and only delta sub-queries are "
      "searched. Purple: a presentation-only request is SUPPRESSED and the previous answer is reshaped from session "
      "memory with no corpus search. Session memory is process-local, 30-minute idle TTL, no user identifier. "
      "Every stage emits telemetry on one clock.")

# ---------------------------------------------------------------- 6. demo walkthrough
set_title(s_demo, "Demo & Product Walkthrough")
label(s_demo, L, 1.88, 5.4, "Demo 2 · one sentence, three searches")
trace = [("0.00 s", "“I need to plan a customer”", "WAIT", AMBER, "not specific yet"),
         ("0.80 s", "“workshop in Pune for 30 people,”", "RETRIEVE", GREEN, "q1 starts, provisional"),
         ("1.61 s", "“and I need the cancellation policy and the catering options.”", "RETRIEVE", GREEN,
          "q2, q3 start · “Pune” carried"),
         ("2.11 s", "utterance ends", "ANSWER", VIOLET, "3/3 reused · 1 duplicate dropped · 6/6 claims grounded")]
ty0, trh, trg = 2.25, 0.86, 0.1
for i, (t, q, d, c, det) in enumerate(trace):
    y = ty0 + i * (trh + trg)
    tb(s_demo, L, y + 0.08, 0.62, 0.3, t, size=10.5, bold=True, color=SLATE, font="Calibri")
    italic = i < 3
    box(s_demo, L + 0.65, y, 2.75, trh, fill=WHITE if italic else GREYT, line=LINE, radius=0.08,
        text=[(q, {"italic": italic})], size=12, color=NAVY if italic else SLATE, anchor="m", margin=0.12)
    chip(s_demo, L + 3.52, y + 0.06, 1.05, 0.28, d, c, size=9.5)
    tb(s_demo, L + 3.52, y + 0.38, 1.6, 0.5, det, size=9.5, color=SLATE, ls=0.92)
img = SHOTS / "dashboard_demo2_multi_intent.png"
iw = 5.95
pic = s_demo.shapes.add_picture(str(img), I(R - iw), I(1.88), width=I(iw))
pic.line.color.rgb = rgb(LINE)
pic.line.width = Pt(0.75)
ih = pic.height / 914400
tb(s_demo, R - iw, 1.88 + ih + 0.05, iw, 0.25,
   [("Actual dashboard, captured from the running app · Demo 2 at real-time pace", {"italic": True})], size=9.5,
   color=SLATE)
flow = ["WAIT", "RETRIEVE", "Sub-query decomposition", "Parallel retrieval", "Fusion", "Grounded answer"]
fcol = [(AMBERT, AMBER), (GREENT, GREEN), (TINT, NAVY), (BLUET, BLUE), (TINT, NAVY), (VIOLET, WHITE)]
fw, fg = 1.66, 0.308
for i, t in enumerate(flow):
    x = L + i * (fw + fg)
    chip(s_demo, x, 6.2, fw, 0.4, t, fcol[i][0], color=fcol[i][1], size=10.5, radius=0.2)
    if i < len(flow) - 1:
        arrow(s_demo, x + fw + 0.04, 6.4, x + fw + fg - 0.04, 6.4, color=GREY, w=1.25)
notes(s_demo, "This is the Theme 4 guide's own example, run live in our dashboard. The transcript arrives in three "
      "chunks. First chunk: WAIT, not specific yet. Second chunk: RETRIEVE, the first sub-query starts while the user "
      "is still talking. Third chunk: two more sub-queries, with Pune carried into both. At utterance end all three "
      "are reused, fused (one duplicate catering FAQ dropped) and answered with 6 of 6 claims grounded. The capacity sub-intent is answered with a Pune venue that fits 30 people (Baner Conference Centre, DOC_03 §S3), via the quantity-constraint check. Timings are "
      "from scripts/demo_stream.py --scenario multi_intent.")

# ---------------------------------------------------------------- 7. early retrieval + refinement
set_title(s_refine, "From First Answer to Refined Answer")
pw, ph7, py7 = 5.55, 4.55, 1.9
# left panel: Demo 1 trace (scripts/demo_stream.py --scenario early_retrieval)
box(s_refine, L, py7, pw, ph7, fill=WHITE, line=LINE, radius=0.12)
label(s_refine, L + 0.25, py7 + 0.18, 4, "01 · Early retrieval")
tb(s_refine, L + 0.25, py7 + 0.46, pw - 0.5, 0.3, "Demo 1 · the user keeps talking while evidence arrives", size=12,
   color=SLATE)
d1 = [("0.0 s", "“So I'm heading to Singapore next month”", "WAIT", AMBER),
      ("2.8 s", "“to visit a customer, and before I book anything”", "RETRIEVE", GREEN),
      ("6.0 s", "“I'd like to know the daily meal allowance”", "RETRIEVE", GREEN),
      ("8.8 s", "“for international travel.”", "RETRIEVE", GREEN)]
for i, (t, q, d, c) in enumerate(d1):
    y = py7 + 0.9 + i * 0.52
    tb(s_refine, L + 0.25, y + 0.05, 0.55, 0.3, t, size=10.5, bold=True, color=SLATE)
    tb(s_refine, L + 0.82, y + 0.03, 3.3, 0.45, [(q, {"italic": True})], size=11.5, color=NAVY)
    chip(s_refine, L + pw - 1.25, y + 0.05, 1.0, 0.26, d, c, size=9)
yE = py7 + 0.9 + 4 * 0.52 + 0.02
arrow(s_refine, L + 0.25, yE, L + pw - 0.25, yE, color=BLUE, w=1.25, dash=MSO_LINE_DASH_STYLE.DASH, head=False)
tb(s_refine, L + 0.25, yE + 0.05, pw - 0.5, 0.3, [[("10.3 s  ", {"bold": True, "color": SLATE}),
                                                  ("utterance ends → evidence already retrieved, answer cites DOC_01 §3",
                                                   {"color": NAVY})]], size=11)
box(s_refine, L + 0.25, py7 + ph7 - 0.95, pw - 0.5, 0.75, fill=GREENT, radius=0.08)
tb(s_refine, L + 0.4, py7 + ph7 - 0.9, pw - 0.8, 0.68,
   [[("Retrieval started 7.47 s before the user finished", {"bold": True, "color": GREEN, "size": 14})],
    [(f"Held-out: early retrieval on {M['early_p']}% of eligible turns, mean lead {M['lead']:.1f} s",
      {"color": SLATE, "size": 10.5})]], size=12, anchor="m")
# right panel: Demo 3
rx = R - pw
box(s_refine, rx, py7, pw, ph7, fill=WHITE, line=LINE, radius=0.12)
label(s_refine, rx + 0.25, py7 + 0.18, 4, "02 · Late detail")
tb(s_refine, rx + 0.25, py7 + 0.46, pw - 0.5, 0.3, "Demo 3 · a new constraint refines the answer", size=12,
   color=SLATE)
fl = [("Answer v1", "2 claims · reimbursement rule", TINT, NAVY),
      ("User adds", "“The trip was international and the booking was made after travel.”", AMBERT, NAVY),
      ("Delta retrieval", "refinement detected → 2 new sub-queries; prior sub-queries re-searched: 0", BLUET, NAVY),
      ("Answer v2", "2 claims kept + 4 added", VIOLET, WHITE)]
fwid, fy0, fh, fgap = 2.75, py7 + 0.9, 0.62, 0.2
for i, (h, d, f, c) in enumerate(fl):
    y = fy0 + i * (fh + fgap)
    box(s_refine, rx + 0.25, y, fwid, fh, fill=f, radius=0.08,
        text=[[(h, {"bold": True, "size": 11.5})], [(d, {"size": 9.5, "color": LAV if f == VIOLET else SLATE})]],
        color=c, anchor="m", margin=0.1, ls=0.92)
    if i < len(fl) - 1:
        arrow(s_refine, rx + 0.25 + fwid / 2, y + fh + 0.02, rx + 0.25 + fwid / 2, y + fh + fgap - 0.02,
              color=GREY, w=1.25)
shot = s_refine.shapes.add_picture(str(SHOTS / "dashboard_demo3_answer_v2.png"), I(rx + 0.25 + fwid + 0.2),
                                   I(fy0), width=I(pw - fwid - 0.7))
shot.line.color.rgb = rgb(LINE)
shot.line.width = Pt(0.75)
sh_h = shot.height / 914400
tb(s_refine, rx + 0.25 + fwid + 0.2, fy0 + sh_h + 0.04, pw - fwid - 0.7, 0.45,
   [("Actual dashboard · v2: green = added claims", {"italic": True})], size=9, color=SLATE)
tb(s_refine, rx + 0.25, py7 + ph7 - 0.42, pw - 0.5, 0.35,
   [[("No full-session restart.  ", {"bold": True, "color": VIOLET, "size": 15}),
     (f"Refinement continuity {M['cont_p']}% vs {M['cont_b']}% (baseline)", {"color": SLATE, "size": 10.5})]],
   size=12)
footnote(s_refine)
notes(s_refine, "Left, Demo 1: the controller waits on the vague opening, retrieves as soon as the request is "
      "specific, and refines the query as more words arrive. Retrieval started at 2.83 s; the utterance ended at "
      "10.30 s. Right, Demo 3: the second turn adds two constraints. It is classified as a refinement, only two delta "
      "sub-queries are searched, the v1 claims are kept and four new claims are added in v2. The session is not "
      "restarted. Continuity is 100% on the 7 held-out refinement turns vs 0% for the baseline.")

# ---------------------------------------------------------------- 8. tools
set_title(s_tools, "Tools & Technology")
cards = [("Streaming & API", [("FastAPI + Uvicorn", "async API server"), ("Server-Sent Events", "live event stream"),
                              ("asyncio", "parallel sub-query retrieval"), ("Pydantic", "request / response models")]),
         ("Retrieval & ranking", [("all-MiniLM-L6-v2", "dense embeddings"), ("BM25 (in-house)", "sparse retrieval"),
                                  ("RRF (in-house, k = 60)", "rank fusion"),
                                  ("ms-marco-MiniLM-L6-v2", "cross-encoder reranker")]),
         ("Models & processing", [("Python 3.13 · NumPy", "core pipeline"),
                                  ("PyTorch (CPU) + HF transformers", "model inference"),
                                  ("scikit-learn", "logistic regressions: controller, abstention gate")]),
         ("Frontend", [("HTML · CSS · vanilla JavaScript", "live dashboard, no framework"),
                       ("fetch stream reader", "consumes the SSE event stream")]),
         ("Testing & evaluation", [("pytest", "61 tests: 60 pass, 1 strict expected failure"),
                                   ("benchmark + report scripts", "held-out evaluation, gates"),
                                   ("matplotlib · JSONL", "plots · telemetry export")]),
         ("Deployment", [("Docker", "CPU-only image"), ("Docker Compose", "app · tests · benchmark profiles")])]
cw8, ch8, g8 = (W - 0.6) / 3, 2.15, 0.3
for i, (head, items) in enumerate(cards):
    x, y = L + (i % 3) * (cw8 + g8), 1.95 + (i // 3) * (ch8 + 0.25)
    box(s_tools, x, y, cw8, ch8, fill=TINT if i % 2 == 0 else GREYT, radius=0.12)
    label(s_tools, x + 0.22, y + 0.18, cw8 - 0.4, head)
    paras = []
    for n, d in items:
        paras.append([(n, {"bold": True, "color": NAVY}), ("  " + d, {"color": SLATE, "size": 11})])
    tb(s_tools, x + 0.22, y + 0.52, cw8 - 0.4, ch8 - 0.6, paras, size=12.5, after=5, ls=0.95)
tb(s_tools, L, 6.63, W, 0.28,
   [[("No LLM calls by default  ", {"bold": True, "color": VIOLET}),
     ("answers are extracted from the corpus; LLM cost per turn $0; runs entirely on CPU", {"color": SLATE})]],
   size=11.5)
notes(s_tools, "Only technologies actually in backend/requirements.txt and the repo. BM25 and RRF are implemented "
      "in-house. The dashboard is plain HTML, CSS and JavaScript that reads the SSE stream. There is an optional LLM "
      "synthesizer interface, but it is off by default and not used for any reported number.")

# ---------------------------------------------------------------- 9. impact & use cases
set_title(s_impact, "Impact & Use Cases")
label(s_impact, L, 1.9, 5, "Potential use cases")
uses = [("Voice & conversational assistants", "retrieval starts while the user is still talking"),
        ("Voice-driven enterprise search", "policies, travel, facilities, HR"),
        ("Device support & troubleshooting", "multi-part problem descriptions in one breath"),
        ("Enterprise knowledge assistants", "cited answers, or an explicit “not in the documents”"),
        ("Real-time information assistants", "late details refine the answer instead of restarting")]
for i, (a, b) in enumerate(uses):
    y = 2.28 + i * 0.8
    chip(s_impact, L, y + 0.08, 0.46, 0.46, chr(65 + i), TINT, color=VIOLET, size=13, radius=0.1)
    tb(s_impact, L + 0.62, y, 4.8, 0.66, [[(a, {"bold": True})], [(b, {"color": SLATE, "size": 11.5})]], size=14,
       anchor="m")
tb(s_impact, L, 6.3, 5.5, 0.3, [("Prototype only: not deployed in production.", {"italic": True})], size=10.5,
   color=SLATE)
ix = 6.75
label(s_impact, ix, 1.9, 5, "What the architecture changes")
imp = [(f"{M['early_p']}%", "turns where retrieval starts before the user finishes", "lower perceived wait"),
       (f"{M['ttft_ner']} → {M['ttft_p']} ms", "time to first token without → with early retrieval",
        "same pipeline"),
       (f"{M['multi_p']}% vs {M['multi_b']}%", "compound requests split correctly", "multiple intents"),
       (f"{M['cont_p']}% vs {M['cont_b']}%", "late details handled without restart", "incremental refinement"),
       (f"{M['unnec_p']} vs {M['unnec_b']}", "searches on turns that need none", "fewer unnecessary retrievals"),
       (f"{M['sup_p']}% · {M['fab_p']}", "claims supported · fabricated citations", "grounded answers")]
iw9, ih9, ig = (R - ix - 0.25) / 2, 1.2, 0.18
for i, (big, lab, tag) in enumerate(imp):
    x, y = ix + (i % 2) * (iw9 + 0.25), 2.28 + (i // 2) * (ih9 + ig)
    box(s_impact, x, y, iw9, ih9, fill=TINT, radius=0.1)
    tb(s_impact, x + 0.18, y + 0.1, iw9 - 0.3, 0.25, [(tag.upper(), {"spc": 80})], size=8.5, bold=True, color=VIOLET)
    tb(s_impact, x + 0.18, y + 0.33, iw9 - 0.3, 0.45, big, size=22, bold=True, font="Arial", color=NAVY)
    tb(s_impact, x + 0.18, y + 0.8, iw9 - 0.3, 0.38, lab, size=10, color=SLATE, ls=0.92)
footnote(s_impact, text=BENCH_LABEL + " · streaming Live RAG vs conventional baseline unless noted")
notes(s_impact, "These are potential use cases, not deployments. The right side shows what the architecture changes, "
      "measured on the development benchmark: retrieval before the user finishes, lower time to first token than "
      "the same pipeline without early retrieval, compound requests split, late details handled without restart, "
      "fewer unnecessary searches, and grounded answers.")

# ---------------------------------------------------------------- 10. results
set_title(s_results, "Results & Evaluation")
cd = CategoryChartData()
cd.categories = ["Early retrieval (G2)", "Multi-intent identification (G3)", "Refinement continuity (G5)",
                 "Correct abstention", "Citation hit rate", "Citation support (G4)"]
cd.add_series("Conventional RAG", (M["early_b"], M["multi_b"], M["cont_b"], M["abst_b"], M["hit_b"], M["sup_b"]))
cd.add_series("Streaming Live RAG", (M["early_p"], M["multi_p"], M["cont_p"], M["abst_p"], M["hit_p"], M["sup_p"]))
gf = s_results.shapes.add_chart(XL_CHART_TYPE.BAR_CLUSTERED, I(L - 0.1), I(1.85), I(7.2), I(4.2), cd)
ch = gf.chart
ch.font.size = Pt(11)
ch.font.name = "Calibri"
ch.font.color.rgb = rgb(NAVY)
ch.has_title = True
ch.chart_title.text_frame.text = "Conventional RAG vs Streaming Live RAG · % of held-out turns"
tp = ch.chart_title.text_frame.paragraphs[0]
tp.runs[0].font.size = Pt(12)
tp.runs[0].font.bold = True
tp.runs[0].font.color.rgb = rgb(NAVY)
ch.has_legend = True
ch.legend.position = XL_LEGEND_POSITION.BOTTOM
ch.legend.include_in_layout = False
ch.legend.font.size = Pt(11)
plot = ch.plots[0]
plot.gap_width = 55
plot.overlap = -5
for ser, col in zip(plot.series, (GREY, VIOLET)):
    ser.format.fill.solid()
    ser.format.fill.fore_color.rgb = rgb(col)
    ser.invert_if_negative = False
plot.has_data_labels = True
dl = plot.data_labels
dl.number_format = '0"%"'
dl.number_format_is_linked = False
dl.position = XL_LABEL_POSITION.OUTSIDE_END
dl.font.size = Pt(10)
dl.font.bold = True
va = ch.value_axis
va.maximum_scale, va.minimum_scale = 115, 0
va.has_major_gridlines = False
va.visible = False
ca = ch.category_axis
ca._element.find(qn("c:scaling")).find(qn("c:orientation")).set("val", "maxMin")
ca.tick_labels.font.size = Pt(11)
ca.format.line.color.rgb = rgb(LINE)
ca.has_major_gridlines = False
# gates strip
gy = 6.12
tb(s_results, L, gy + 0.04, 1.3, 0.3, [("Gates", {"bold": True})], size=12, color=NAVY)
for i in range(6):
    chip(s_results, L + 0.75 + i * 0.95, gy, 0.85, 0.34, f"G{i + 1} PASS", GREENT, color=GREEN, size=10)
tb(s_results, L + 0.75 + 6 * 0.95 + 0.05, gy + 0.04, 1.1, 0.3, "G1: Docker on dev machine only", size=8.5,
   color=SLATE)
# right cards
rx10, rw10 = 8.5, R - 8.5
box(s_results, rx10, 1.9, rw10, 1.05, fill=TINT, radius=0.1)
tb(s_results, rx10 + 0.2, 1.98, rw10 - 0.4, 0.25, [("MEAN RETRIEVAL LEAD", {"spc": 80})], size=9, bold=True,
   color=VIOLET)
tb(s_results, rx10 + 0.2, 2.22, rw10 - 0.4, 0.7,
   [[(f"{M['lead']:.1f} s", {"size": 26, "bold": True, "font": "Arial"}),
     ("  before the utterance ends", {"size": 11, "color": SLATE})]], size=12)
box(s_results, rx10, 3.1, rw10, 1.72, fill=GREYT, radius=0.1)
tb(s_results, rx10 + 0.2, 3.18, rw10 - 0.4, 0.25, [("TIME TO FIRST TOKEN AFTER SPEECH ENDS (MEAN)", {"spc": 60})],
   size=9, bold=True, color=VIOLET)
lat = [("Conventional RAG", M["ttft_b"], GREY), ("Streaming Live RAG", M["ttft_p"], VIOLET),
       ("Same pipeline, no early retrieval", M["ttft_ner"], "B8B3D6")]
for i, (n, v, c) in enumerate(lat):
    yy = 3.5 + i * 0.3
    tb(s_results, rx10 + 0.2, yy, 2.0, 0.26, n, size=10, color=NAVY)
    bwid = 0.95 * v / M["ttft_ner"]
    box(s_results, rx10 + 2.25, yy + 0.05, max(bwid, 0.03), 0.17, fill=c, radius=0)
    tb(s_results, rx10 + 2.25 + bwid + 0.06, yy, 0.6, 0.26, f"{v} ms", size=10, bold=True, color=NAVY)
tb(s_results, rx10 + 0.2, 4.4, rw10 - 0.4, 0.4,
   "The baseline is faster: it does less work per turn. Early retrieval hides most of our extra compute.",
   size=9.5, color=SLATE, ls=0.92)
box(s_results, rx10, 4.97, rw10, 1.05, fill=AMBERT, radius=0.1)
tb(s_results, rx10 + 0.2, 5.03, rw10 - 0.4, 0.25, [("TRADE-OFF: CONSERVATIVE ABSTENTION", {"spc": 60})], size=9,
   bold=True, color=AMBER)
tb(s_results, rx10 + 0.2, 5.28, rw10 - 0.4, 0.72,
   f"The gate refused {ABSTAINED} of {ANSWERABLE} answerable turns: citation hit rate {M['hit_p']}% equals the "
   f"baseline ({M['hit_nogate']}% without the gate), while correct abstention rises {M['abst_b']}% → {M['abst_p']}%.",
   size=10, color=NAVY, ls=0.92)
footnote(s_results)
notes(s_results, "All bars are from results/benchmark.json, held-out split. The first three are the Theme 4 "
      "capabilities: 90% vs 0% early retrieval, 78% vs 0% multi-intent, 100% vs 0% refinement continuity. Be explicit "
      "about the trade-off: citation hit rate is 73% for both systems, because our abstention gate is conservative "
      "and refused 12 of 63 answerable turns; without the gate the same pipeline scores 84%. Correct abstention is "
      "83% vs 33%. The baseline has a lower time to first token, 17 ms vs 47 ms, because it does less work; without "
      "early retrieval our pipeline would take 247 ms.")

# ---------------------------------------------------------------- 11. innovation + limitations
set_title(s_innov, "Innovation Highlights & Limitations")
label(s_innov, L, 1.9, 6, "Innovation highlights")
inn = [("Retrieval before utterance end", "provisional retrieval + sentence scoring during speech"),
       ("WAIT / RETRIEVE / SUPPRESS", "learned per-chunk decision, logged with its reason"),
       ("Multi-intent decomposition", "the corpus decides which clauses merge"),
       ("Parallel retrieval", "dense + BM25 for every sub-query, concurrently"),
       ("Fusion + reranking", "coverage quota · dedup · superseded docs dropped"),
       ("Session-aware refinement", "late details → delta-only retrieval"),
       ("Answer versioning", "v1 → v2 with retained / added / removed log"),
       ("Grounding validation", "id exists, was retrieved, text & numbers match"),
       ("Retrieval telemetry", "every event on one clock → UI, SSE, JSONL")]
tw, th, tg = 1.93, 1.3, 0.13
for i, (a, b) in enumerate(inn):
    x, y = L + (i % 3) * (tw + tg), 2.25 + (i // 3) * (th + tg)
    box(s_innov, x, y, tw, th, fill=TINT, radius=0.1)
    tb(s_innov, x + 0.14, y + 0.1, 0.5, 0.25, f"{i + 1:02d}", size=9.5, bold=True, color=VIOLET)
    tb(s_innov, x + 0.14, y + 0.33, tw - 0.26, 0.5, a, size=12, bold=True, color=NAVY, ls=0.92)
    tb(s_innov, x + 0.14, y + 0.82, tw - 0.26, 0.5, b, size=9.5, color=SLATE, ls=0.92)
lx11 = L + 3 * (tw + tg) + 0.3
lw11 = R - lx11
box(s_innov, lx11, 1.9, lw11, 4.62, fill=WHITE, line=LINE, radius=0.12)
label(s_innov, lx11 + 0.25, 2.05, 4, "Limitations", color=AMBER)
lim = [("Synthetic development corpus", "16 documents; corpus and all eval sets written by the system's author"),
       ("No official validation", "the official Theme 4 corpus was not available"),
       ("Conservative abstention", f"{ABSTAINED} of {ANSWERABLE} answerable held-out turns refused; citation hit "
                                   f"{M['hit_p']}% = baseline"),
       ("Off-target extractive sentences", "a second, on-topic sentence can miss the question"),
       ("Extractive, simulated", "grounded but not fluent answers; speech simulated from transcripts"),
       ("Surface-cue decomposition", "implicit multi-intent without a connective stays one query"),
       ("Docker on one machine", "verified on the development machine only")]
for i, (a, b) in enumerate(lim):
    y = 2.45 + i * 0.57
    box(s_innov, lx11 + 0.27, y + 0.1, 0.1, 0.1, fill=AMBER, shape=MSO_SHAPE.OVAL, radius=0)
    tb(s_innov, lx11 + 0.5, y, lw11 - 0.7, 0.56, [[(a, {"bold": True, "color": NAVY})],
                                                   [(b, {"color": SLATE, "size": 10})]], size=12, ls=0.92)
footnote(s_innov, text=BENCH_LABEL + " · full list: docs/limitations.md")
notes(s_innov, "Left: what is new, all implemented and shown in the demos. Right: the honest limitations from "
      "docs/limitations.md. The most important are the synthetic, same-author corpus, the lack of official "
      "validation, and the conservative abstention gate that keeps citation hit rate at the baseline level.")

# ---------------------------------------------------------------- 12. what's next
set_title(s_next, "What's Next")
tb(s_next, L, 1.85, W, 0.3, [("Planned work, not implemented yet.", {"italic": True})], size=12, color=SLATE)
cols12 = [("Validate", "Now", [("Official corpus", "run on the official Theme 4 corpus and held-out replay; "
                                                   "re-author gold labels and demos"),
                                ("Independent evaluation", "evaluation sets not written by the system's author; "
                                                           "wider coverage")]),
          ("Improve", "Next", [("Semantic abstention", "larger independent calibration set or a small NLI "
                                                       "answerability model"),
                               ("Evidence aggregation", "better answer-sentence selection; optional LLM synthesis "
                                                        "behind the validator + entailment check"),
                               ("Learned retrieval control", "learned segmenter for implicit multi-intent; more "
                                                             "controller training data")]),
          ("Scale", "Later", [("True speech streaming", "ASR with revisable partial hypotheses; cancel stale "
                                                        "provisional retrievals"),
                              ("Latency", "cut reranking cost on the critical path"),
                              ("Large corpora", "FAISS / HNSW index above ~100k chunks")])]
cw12, g12 = (W - 0.6) / 3, 0.3
for i, (h, when, items) in enumerate(cols12):
    x = L + i * (cw12 + g12)
    box(s_next, x, 2.3, cw12, 3.95, fill=TINT if i != 1 else GREYT, radius=0.12)
    chip(s_next, x + 0.22, 2.48, 0.8, 0.3, when, VIOLET, size=10)
    tb(s_next, x + 1.15, 2.44, cw12 - 1.3, 0.4, h, size=18, bold=True, color=NAVY, font="Arial")
    for k, (a, b) in enumerate(items):
        y = 3.05 + k * 1.02
        tb(s_next, x + 0.22, y, cw12 - 0.44, 1.05, [[(a, {"bold": True, "color": NAVY, "size": 13})],
                                                    [(b, {"color": SLATE})]], size=11, ls=0.95)
    if i < 2:
        arrow(s_next, x + cw12 + 0.04, 2.63, x + cw12 + g12 - 0.04, 2.63, color=VIOLET, w=1.5)
notes(s_next, "Everything here is future work from docs/limitations.md. First priority: run on the official corpus "
      "and an independently written evaluation set. Then fix the abstention trade-off and answer-sentence selection. "
      "Then real streaming ASR, lower rerank latency, and a scalable index.")

# ---------------------------------------------------------------- 13. why streaming live rag
set_title(s_why, "Why Streaming Live RAG?")
sx0, sx1 = 3.0, 8.3  # "user is speaking" region
box(s_why, sx0, 1.95, sx1 - sx0, 2.85, fill=TINT, radius=0.08)
tb(s_why, sx0, 2.0, sx1 - sx0, 0.3, [("USER IS SPEAKING", {"spc": 150})], size=10, bold=True, color=VIOLET, align="c")
tb(s_why, sx1 + 0.1, 2.0, 3.9, 0.3, [("AFTER THE USER STOPS", {"spc": 150})], size=10, bold=True, color=SLATE,
   align="c")
arrow(s_why, sx1, 1.95, sx1, 4.8, color=BLUE, w=1.25, dash=MSO_LINE_DASH_STYLE.DASH, head=False)


def lane(slide, y, name, fill, col, inside, after):
    chip(slide, L, y, 1.9, 0.62, name, fill, color=col, size=12, radius=0.1, line=LINE if fill == GREYT else None)
    n = len(inside)
    wi = (sx1 - sx0 - 0.3 - 0.22 * (n - 1)) / n
    xs = []
    for j, (t, f, c, dsh) in enumerate(inside):
        xs.append((sx0 + 0.15 + j * (wi + 0.22), wi, t, f, c, dsh))
    wa = (R - sx1 - 0.3 - 0.22 * (len(after) - 1)) / len(after)
    for j, (t, f, c, dsh) in enumerate(after):
        xs.append((sx1 + 0.15 + j * (wa + 0.22), wa, t, f, c, dsh))
    for j, (x, w, t, f, c, dsh) in enumerate(xs):
        chip(slide, x, y + 0.03, w, 0.56, t, f, color=c, size=10.5 if len(t) > 14 else 11.5, radius=0.25,
             line=GREY if dsh else (LINE if f in (WHITE, GREYT) else None), dash=MSO_LINE_DASH_STYLE.DASH if dsh else None)
        if j < len(xs) - 1:
            arrow(slide, x + w + 0.03, y + 0.31, xs[j + 1][0] - 0.03, y + 0.31, color=GREY, w=1.25)


lane(s_why, 2.5, "TRADITIONAL", GREYT, SLATE,
     [("Speak", WHITE, NAVY, False), ("Wait", WHITE, SLATE, True)],
     [("Search", GREYT, NAVY, False), ("Answer", GREYT, NAVY, False)])
lane(s_why, 3.75, "OUR SYSTEM", VIOLET, WHITE,
     [("Understand partial intent", WHITE, NAVY, False), ("Retrieve early", GREENT, GREEN, False),
      ("Continue listening", WHITE, NAVY, False), ("Decompose", WHITE, NAVY, False)],
     [("Fuse", BLUET, BLUE, False), ("Refine", BLUET, BLUE, False), ("Answer", VIOLET, WHITE, False)])
tb(s_why, L, 5.05, W, 0.7, "RAG that starts working before the user finishes speaking.", size=26, bold=True,
   font="Arial", color=NAVY, align="c")
proof = [(f"{M['early_p']}%", "early retrieval"), (f"{M['multi_p']}%", "multi-intent identified"),
         (f"{M['cont_p']}%", "refinement continuity"), (f"{M['sup_p']}%", "claims supported")]
pw13, pg13 = 2.4, 0.25
px0 = L + (W - (4 * pw13 + 3 * pg13)) / 2
for i, (a, b) in enumerate(proof):
    box(s_why, px0 + i * (pw13 + pg13), 5.9, pw13, 0.55, fill=GREYT, radius=0.1,
        text=[[(a + "  ", {"bold": True, "color": VIOLET, "size": 15, "font": "Arial"}), (b, {"color": SLATE})]],
        size=11, align="c", anchor="m")
footnote(s_why, text=BENCH_LABEL)
notes(s_why, "Same sentence, two systems. A traditional pipeline is idle while the user speaks. Ours understands the "
      "partial intent, retrieves early, keeps listening and decomposes during speech; after the user stops it only "
      "fuses, refines and answers. We do not claim a lower time to first token than the bare baseline; the point is "
      "that the work happens during speech and the answer handles multi-intent requests and late details. "
      "Closing line: RAG that starts working before the user finishes speaking.")

# ---------------------------------------------------------------- 14. checklist
set_title(s_check, "Checklist — Updated on Public GitHub")
chk = [("Working prototype code — public GitHub repo", "Y", GREEN, GREENT,
        [(GITHUB_SHORT, {"link": GITHUB, "color": VIOLET, "bold": True})]),
       ("README with reproducible setup instructions", "Y", GREEN, GREENT,
        [("README §3: exact commands from a clean clone (Windows 11, Python 3.13, CPU)", {})]),
       ("Docker", "Y", GREEN, GREENT,
        [("image built and run, health check and tests inside the container; verified on the development machine only",
          {})]),
       ("Demo video, max 5 minutes (YouTube or Drive link)", "Y", GREEN, GREENT,
        [(VIDEO, {"link": VIDEO, "color": VIOLET, "bold": True})]),
       ("Presentation file (PPT or PDF)", "Y", GREEN, GREENT, [("SRM_Univ_Fantastic_4_Submission.pptx", {})])]
for i, (item, st, c, f, det) in enumerate(chk):
    y = 2.0 + i * 0.88
    box(s_check, L, y, W, 0.74, fill=WHITE, line=LINE, radius=0.1)
    chip(s_check, L + 0.2, y + 0.19, 1.15, 0.36, st, f, color=c, size=11)
    tb(s_check, L + 1.6, y + 0.07, W - 1.8, 0.62, [[(item, {"bold": True, "size": 15, "color": NAVY})], det], size=11.5,
       color=SLATE, ls=0.95)
tb(s_check, L, 6.45, W, 0.3, [("Status as of the final build of this deck.", {"italic": True})], size=10, color=SLATE)
notes(s_check, "All items complete. Demo video: " + VIDEO + ". Docker was verified on one development machine only.")

# ---------------------------------------------------------------- 15. thank you
thanks = next(sh for sh in s_thanks.shapes if sh.shape_id == 162)
thanks.top = I(3.05)
hero = tpl[0].shapes[-1]  # template network graphic (picture)
blob = hero.image.blob
import io
s_thanks.shapes.add_picture(io.BytesIO(blob), I(8.2), I(1.4), width=I(4.3))
box(s_thanks, 1.14, 2.45, 2.65, 0.38, fill=WHITE, line=LAV, radius=0.19,
    text=[("STREAMING LIVE RAG", {"spc": 60})], size=11, bold=True, color=VIOLET, align="c", anchor="m", margin=0.02)
tb(s_thanks, 1.14, 4.1, 7.0, 0.4, [[(f"Team {TEAM}", {"bold": True, "color": NAVY}), (f"  ·  {COLLEGE}", {})]],
   size=20, color=SLATE)
tb(s_thanks, 1.14, 4.6, 7.0, 0.35, [(GITHUB, {"link": GITHUB, "color": VIOLET, "bold": True})], size=14)
tb(s_thanks, 1.14, 5.05, 7.0, 0.35, [[("Contact  ", {"bold": True, "color": NAVY}),
                                      (f"{MEMBERS[0][0]}  ·  {MEMBERS[0][1]}", {})]], size=14, color=SLATE)
tb(s_thanks, 1.14, 5.45, 7.0, 0.35, "  ·  ".join(n for n, _ in MEMBERS), size=12, color=MUTED)
notes(s_thanks, "Thank you. Repository: " + GITHUB + ". Contact: " + MEMBERS[0][0] + ", " + MEMBERS[0][1] + ".")

prs.save(OUT)
print(f"wrote {OUT.name}: {TOTAL} slides")
print({k: M[k] for k in sorted(M)})
