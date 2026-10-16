"""Generate realistic mock Indian annual report PDFs plus eval questions with known answers.

Companies are fictional. The layout copies patterns seen in real reports: two-column narrative pages,
borderless financial tables with a unit line above, running headers/footers, Indian digit grouping,
current and previous year columns.

    uv run python scripts/make_mock_reports.py            # writes ../data/pdfs and evals/questions.json
"""

import json
import random
from dataclasses import dataclass
from pathlib import Path

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import (
    BaseDocTemplate,
    Frame,
    NextPageTemplate,
    PageBreak,
    PageTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

ROOT = Path(__file__).resolve().parents[2]
YEARS = [2022, 2023, 2024]  # reports; FY2021 exists only as FY2022's comparative column
ALL_YEARS = [2021, 2022, 2023, 2024]


def inr(n: float, decimals: int = 0) -> str:
    """Indian digit grouping: 240893 -> 2,40,893."""
    neg = n < 0
    s = f"{abs(n):.{decimals}f}"
    whole, _, frac = s.partition(".")
    if len(whole) > 3:
        head, tail = whole[:-3], whole[-3:]
        parts = []
        while len(head) > 2:
            parts.insert(0, head[-2:])
            head = head[:-2]
        if head:
            parts.insert(0, head)
        whole = ",".join(parts + [tail])
    out = whole + (f".{frac}" if frac else "")
    return f"({out})" if neg else out


@dataclass
class Company:
    ticker: str
    name: str
    sector: str
    base_revenue: float  # FY2021, Rs crore
    growth: list[float]  # FY22, FY23, FY24 growth
    margin: float  # PBT margin
    employees: int
    risks: list[tuple[str, str]]
    segments: list[str]


COMPANIES = [
    Company(
        "BHIT",
        "Bharat Infotech Limited",
        "IT services",
        140000,
        [0.121, 0.114, 0.086],
        0.245,
        312000,
        [
            (
                "Attrition of skilled employees",
                "High attrition in digital roles could raise costs and delay projects.",
            ),
            (
                "Currency fluctuation",
                "Most revenue is in US dollars, so a stronger rupee reduces reported margins.",
            ),
            ("Client concentration", "The top ten clients contribute a large share of revenue."),
        ],
        ["North America", "Europe", "India and Rest of World"],
    ),
    Company(
        "SAGR",
        "Sagar Pharma Limited",
        "Pharmaceuticals",
        33000,
        [0.145, 0.162, 0.121],
        0.198,
        41500,
        [
            (
                "Regulatory action by US FDA",
                "Observations at manufacturing sites could delay product approvals.",
            ),
            (
                "Price erosion in generics",
                "Intense competition lowers realisations in the US generics market.",
            ),
            (
                "Raw material cost volatility",
                "Active pharmaceutical ingredient prices depend on imports.",
            ),
        ],
        ["Formulations", "Active ingredients", "Contract research"],
    ),
    Company(
        "NAVM",
        "Navbharat Motors Limited",
        "Automobiles",
        54000,
        [0.18, 0.211, 0.074],
        0.108,
        58200,
        [
            ("Semiconductor supply disruption", "Chip shortages can halt production lines."),
            (
                "Transition to electric vehicles",
                "Changing regulation requires heavy capital expenditure.",
            ),
            ("Cyclical demand", "Vehicle demand is sensitive to interest rates and fuel prices."),
        ],
        ["Passenger vehicles", "Commercial vehicles", "Spare parts and services"],
    ),
]


def build_data(c: Company) -> dict[int, dict]:
    rnd = random.Random(c.ticker)
    rev = {2021: c.base_revenue}
    for y, g in zip(YEARS, c.growth, strict=True):
        rev[y] = round(rev[y - 1] * (1 + g))
    out = {}
    for i, y in enumerate(ALL_YEARS):
        r = rev[y]
        other = round(r * rnd.uniform(0.008, 0.02))
        total_income = r + other
        pbt = round(total_income * (c.margin + rnd.uniform(-0.01, 0.01) + 0.004 * i))
        emp = round(total_income * rnd.uniform(0.28, 0.36))
        fin = round(total_income * rnd.uniform(0.004, 0.012))
        dep = round(total_income * rnd.uniform(0.02, 0.035))
        oth = total_income - pbt - emp - fin - dep
        tax = round(pbt * 0.255)
        pat = pbt - tax
        shares = round(c.base_revenue / 40)  # crore shares
        out[y] = dict(
            revenue=r,
            other_income=other,
            total_income=total_income,
            employee=emp,
            finance=fin,
            depreciation=dep,
            other_exp=oth,
            total_exp=total_income - pbt,
            pbt=pbt,
            tax=tax,
            pat=pat,
            eps=round(pat / shares * 1.0, 2),
            shares=shares,
            margin=round(pbt / total_income * 100, 1),
            equity=round(pat * rnd.uniform(3.4, 4.2)),
            borrowings=round(r * rnd.uniform(0.02, 0.06)),
            cash=round(r * rnd.uniform(0.07, 0.13)),
            total_assets=round(pat * rnd.uniform(5.2, 6.4)),
            employees=round(c.employees * (0.93 + 0.035 * i)),
            dividend=round(rnd.uniform(14, 48) + 3 * i, 1),
            segments=_split(r, len(c.segments), rnd),
        )
    return out


def _split(total: int, n: int, rnd: random.Random) -> list[int]:
    w = [rnd.uniform(0.2, 0.5) for _ in range(n)]
    s = sum(w)
    parts = [round(total * x / s) for x in w[:-1]]
    return parts + [total - sum(parts)]


# ---------- PDF rendering ----------
styles = getSampleStyleSheet()
BODY = ParagraphStyle("body", parent=styles["BodyText"], fontSize=9.2, leading=12.5)
H1 = ParagraphStyle(
    "h1", parent=styles["Heading1"], fontSize=16, textColor=colors.HexColor("#14325c")
)
H2 = ParagraphStyle(
    "h2", parent=styles["Heading2"], fontSize=11.5, textColor=colors.HexColor("#14325c")
)
UNIT = ParagraphStyle("unit", parent=BODY, fontSize=8.5, textColor=colors.grey)

FILLER = [
    "The Board of Directors comprises a balanced mix of executive, non-executive and independent directors, "
    "and met five times during the year. All committees functioned in accordance with applicable regulations.",
    "The Company is committed to the highest standards of corporate governance, including transparent disclosures, "
    "an effective whistle-blower mechanism and a robust internal financial control framework.",
    "During the year the Company invested in community initiatives in education, healthcare and skill development "
    "as part of its corporate social responsibility programme.",
    "The Company has adopted a risk management framework overseen by the Risk Management Committee, which reviews "
    "strategic, operational, financial and compliance risks on a quarterly basis.",
    "The statutory auditors have issued an unmodified opinion on the financial statements. The secretarial auditor "
    "has confirmed compliance with the provisions of the Companies Act, 2013.",
]


def fin_table(rows: list[list[str]], fy: int, bold_rows: set[int] = frozenset()) -> Table:
    header = ["Particulars", f"FY{fy}", f"FY{fy - 1}"]
    t = Table([header] + rows, colWidths=[95 * mm, 38 * mm, 38 * mm])
    style = [
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("ALIGN", (1, 0), (-1, -1), "RIGHT"),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, colors.black),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]
    for r in bold_rows:
        style += [
            ("FONTNAME", (0, r + 1), (-1, r + 1), "Helvetica-Bold"),
            ("LINEABOVE", (0, r + 1), (-1, r + 1), 0.3, colors.grey),
        ]
    t.setStyle(TableStyle(style))
    return t


def render(c: Company, data: dict[int, dict], fy: int, path: Path) -> None:
    cur, prev = data[fy], data[fy - 1]
    label = f"{fy - 1}-{str(fy)[2:]}"
    growth = (cur["revenue"] / prev["revenue"] - 1) * 100

    def header_footer(canvas, doc):
        canvas.saveState()
        canvas.setFont("Helvetica", 8)
        canvas.setFillColor(colors.grey)
        canvas.drawString(20 * mm, 287 * mm, f"{c.name}  |  Annual Report {label}")
        canvas.drawRightString(190 * mm, 12 * mm, f"{doc.page}")
        canvas.restoreState()

    doc = BaseDocTemplate(
        str(path),
        pagesize=A4,
        leftMargin=20 * mm,
        rightMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
    )
    w, h = A4
    one = Frame(20 * mm, 18 * mm, w - 40 * mm, h - 40 * mm, id="one")
    colw = (w - 40 * mm - 8 * mm) / 2
    left = Frame(20 * mm, 18 * mm, colw, h - 40 * mm, id="l")
    right = Frame(20 * mm + colw + 8 * mm, 18 * mm, colw, h - 40 * mm, id="r")
    doc.addPageTemplates(
        [
            PageTemplate("single", [one], onPage=header_footer),
            PageTemplate("double", [left, right], onPage=header_footer),
        ]
    )

    s: list = []
    s += [
        Spacer(1, 60 * mm),
        Paragraph(c.name, ParagraphStyle("t", parent=H1, fontSize=26)),
        Paragraph(f"Integrated Annual Report {label}", H2),
        Paragraph(f"{c.sector} | Mumbai, India", BODY),
        NextPageTemplate("double"),
        PageBreak(),
    ]

    s += [
        Paragraph("Chairman's Message", H1),
        Paragraph(
            f"Dear Shareholders, the financial year ended March 31, {fy} was a year of disciplined execution "
            f"for {c.name}. Revenue from operations grew {growth:.1f}% to Rs {inr(cur['revenue'])} crore from "
            f"Rs {inr(prev['revenue'])} crore in the previous year. Profit after tax stood at Rs "
            f"{inr(cur['pat'])} crore. Our employee strength was {inr(cur['employees'])} as on March 31, {fy}.",
            BODY,
        ),
        Spacer(1, 4),
    ] + [Paragraph(f, BODY) for f in FILLER[:2]]
    s += [Paragraph("Strategy and Outlook", H2)] + [Paragraph(f, BODY) for f in FILLER[2:4]] * 2
    s += [NextPageTemplate("single"), PageBreak()]

    s += [
        Paragraph("Financial Highlights", H1),
        Paragraph(
            f"Key financial performance of the Company for the year ended March 31, {fy} is summarised below.",
            BODY,
        ),
        Paragraph("(Rs in crore, unless otherwise stated)", UNIT),
        fin_table(
            [
                ["Revenue from operations", inr(cur["revenue"]), inr(prev["revenue"])],
                ["Profit before tax", inr(cur["pbt"]), inr(prev["pbt"])],
                ["Profit after tax", inr(cur["pat"]), inr(prev["pat"])],
                ["Pre-tax margin (%)", f"{cur['margin']}", f"{prev['margin']}"],
                ["Earnings per share (Rs)", f"{cur['eps']:.2f}", f"{prev['eps']:.2f}"],
                ["Dividend per share (Rs)", f"{cur['dividend']}", f"{prev['dividend']}"],
            ],
            fy,
        ),
        Spacer(1, 10),
        Paragraph("Segment Performance", H2),
        Paragraph("(Rs in crore)", UNIT),
        fin_table(
            [
                [seg, inr(cur["segments"][i]), inr(prev["segments"][i])]
                for i, seg in enumerate(c.segments)
            ]
            + [["Total revenue", inr(cur["revenue"]), inr(prev["revenue"])]],
            fy,
            bold_rows={len(c.segments)},
        ),
        NextPageTemplate("double"),
        PageBreak(),
    ]

    s += [
        Paragraph("Management Discussion and Analysis", H1),
        Paragraph(
            f"The Company's {c.sector.lower()} business delivered steady results. The Board has recommended a "
            f"dividend of Rs {cur['dividend']} per equity share for the financial year {fy}.",
            BODY,
        ),
    ]
    s += [Paragraph(f, BODY) for f in FILLER]
    s += [Paragraph("Risks and Concerns", H1)]
    for name, desc in c.risks:
        s.append(Paragraph(f"<b>{name}.</b> {desc}", BODY))
    s += [Paragraph(f, BODY) for f in FILLER[:3]] + [NextPageTemplate("single"), PageBreak()]

    s += [
        Paragraph("Standalone Statement of Profit and Loss", H1),
        Paragraph(f"For the year ended March 31, {fy}", BODY),
        Paragraph("(Rs in crore)", UNIT),
        fin_table(
            [
                ["Revenue from operations", inr(cur["revenue"]), inr(prev["revenue"])],
                ["Other income", inr(cur["other_income"]), inr(prev["other_income"])],
                ["Total income", inr(cur["total_income"]), inr(prev["total_income"])],
                ["Employee benefits expense", inr(cur["employee"]), inr(prev["employee"])],
                ["Finance costs", inr(cur["finance"]), inr(prev["finance"])],
                [
                    "Depreciation and amortisation expense",
                    inr(cur["depreciation"]),
                    inr(prev["depreciation"]),
                ],
                ["Other expenses", inr(cur["other_exp"]), inr(prev["other_exp"])],
                ["Total expenses", inr(cur["total_exp"]), inr(prev["total_exp"])],
                ["Profit before tax", inr(cur["pbt"]), inr(prev["pbt"])],
                ["Tax expense", inr(cur["tax"]), inr(prev["tax"])],
                ["Profit for the year", inr(cur["pat"]), inr(prev["pat"])],
                ["Earnings per equity share (Rs)", f"{cur['eps']:.2f}", f"{prev['eps']:.2f}"],
            ],
            fy,
            bold_rows={2, 7, 8, 10},
        ),
        PageBreak(),
        Paragraph("Standalone Balance Sheet", H1),
        Paragraph(f"As at March 31, {fy}", BODY),
        Paragraph("(Rs in crore)", UNIT),
        fin_table(
            [
                ["Total equity", inr(cur["equity"]), inr(prev["equity"])],
                ["Borrowings", inr(cur["borrowings"]), inr(prev["borrowings"])],
                ["Cash and cash equivalents", inr(cur["cash"]), inr(prev["cash"])],
                ["Total assets", inr(cur["total_assets"]), inr(prev["total_assets"])],
            ],
            fy,
            bold_rows={3},
        ),
        Spacer(1, 10),
        Paragraph("Notes to the financial statements", H2),
    ] + [Paragraph(f, BODY) for f in FILLER]
    doc.build(s)


def find_page(pdf: Path, needle: str) -> int:
    """1-based page of `pdf` whose text contains `needle` (gold pages come from the real PDFs)."""
    import pymupdf

    with pymupdf.open(pdf) as doc:
        for i, page in enumerate(doc, start=1):
            if needle in page.get_text():
                return i
    raise ValueError(f"{needle!r} not found in {pdf.name}")


def questions(all_data: dict[str, dict[int, dict]], pdf_dir: Path) -> list[dict]:
    """Eval set with known answers. Every item records WHY it is hard (category, difficulty) and
    where the answer lives (gold pages) so retrieval and generation can be scored separately."""
    qs: list[dict] = []
    cos = {c.ticker: c for c in COMPANIES}
    short = {"BHIT": "Bharat Infotech", "SAGR": "Sagar Pharma", "NAVM": "Navbharat Motors"}
    pages_cache: dict[tuple[str, int, str], int] = {}

    def page(t: str, fy: int, section: str) -> int:
        key = (t, fy, section)
        if key not in pages_cache:
            needle = {
                "chair": "Chairman's Message",
                "highlights": "Financial Highlights",
                "risks": "Risks and Concerns",
                "pnl": "Standalone Statement of Profit and Loss",
                "bs": "Standalone Balance Sheet",
            }[section]
            pages_cache[key] = find_page(pdf_dir / f"{t}_FY{fy}.pdf", needle)
        return pages_cache[key]

    def gold(t: str, fy: int, *sections: str) -> dict:
        return {"ticker": t, "fiscal_year": fy, "pages": sorted({page(t, fy, s) for s in sections})}

    def add(cat, diff, reasoning, q, groups=None, gold_=None, unanswerable=False, history=None):
        item = {
            "id": f"{cat}-{sum(1 for x in qs if x['category'] == cat) + 1:02d}",
            "category": cat,
            "difficulty": diff,
            "reasoning": reasoning,
            "question": q,
        }
        if history:
            item["history"] = history
        if unanswerable:
            item["unanswerable"] = True
        else:
            item["expected_contains"] = groups
            item["gold"] = gold_
            item["expected_sources"] = [
                {"ticker": g["ticker"], "fiscal_year": g["fiscal_year"]} for g in gold_
            ]
        qs.append(item)

    for t, d in all_data.items():
        n = cos[t].name
        s = short[t]
        # --- single fact lookups (answer is in one place) ---
        add(
            "single_fact",
            "easy",
            "lookup",
            f"What was {n}'s revenue from operations in FY2024?",
            [[inr(d[2024]["revenue"])]],
            [gold(t, 2024, "chair", "highlights", "pnl")],
        )
        add(
            "single_fact",
            "easy",
            "lookup",
            f"What was the profit after tax of {n} in FY2023?",
            [[inr(d[2023]["pat"])]],
            [gold(t, 2023, "chair", "highlights", "pnl")],
        )
        add(
            "single_fact",
            "easy",
            "lookup",
            f"How many employees did {n} have as on March 31, 2024?",
            [[inr(d[2024]["employees"])]],
            [gold(t, 2024, "chair")],
        )
        add(
            "single_fact",
            "easy",
            "lookup",
            f"What dividend per share did {n} recommend for FY2024?",
            [[str(d[2024]["dividend"])]],
            [gold(t, 2024, "highlights", "risks")],
        )
        add(
            "single_fact",
            "easy",
            "lookup",
            f"What were the total assets of {n} as at March 31, 2024?",
            [[inr(d[2024]["total_assets"])]],
            [gold(t, 2024, "bs")],
        )
        add(
            "single_fact",
            "easy",
            "lookup",
            f"How much cash and cash equivalents did {n} hold at the end of FY2023?",
            [[inr(d[2023]["cash"])]],
            [gold(t, 2023, "bs")],
        )
        # --- multi-year trends (needs several reports) ---
        g = (d[2024]["revenue"] / d[2023]["revenue"] - 1) * 100
        add(
            "multi_year",
            "medium",
            "calculation",
            f"By what percentage did {n}'s revenue grow from FY2023 to FY2024?",
            [[f"{g:.1f}", f"{int(g * 10) / 10:.1f}"]],
            [gold(t, 2023, "highlights", "pnl"), gold(t, 2024, "highlights", "pnl")],
        )
        add(
            "multi_year",
            "medium",
            "aggregation",
            f"What was {n}'s revenue in FY2022 and in FY2024?",
            [[inr(d[2022]["revenue"])], [inr(d[2024]["revenue"])]],
            [
                gold(t, 2022, "chair", "highlights", "pnl"),
                gold(t, 2024, "chair", "highlights", "pnl"),
            ],
        )
        add(
            "multi_year",
            "medium",
            "aggregation",
            f"What was {n}'s pre-tax margin in FY2022, FY2023 and FY2024?",
            [[str(d[y]["margin"])] for y in YEARS],
            [gold(t, y, "highlights") for y in YEARS],
        )
        # --- derived metrics (needs the calculator, not just reading) ---
        cagr = ((d[2024]["revenue"] / d[2022]["revenue"]) ** 0.5 - 1) * 100
        add(
            "calculation",
            "hard",
            "calculation",
            f"What was the compound annual growth rate of {n}'s revenue between FY2022 and FY2024?",
            [[f"{cagr:.1f}", f"{int(cagr * 10) / 10:.1f}"]],
            [gold(t, 2022, "highlights", "pnl"), gold(t, 2024, "highlights", "pnl")],
        )
        npm = d[2024]["pat"] / d[2024]["revenue"] * 100
        add(
            "calculation",
            "hard",
            "calculation",
            f"What was {n}'s net profit margin (profit after tax as a percentage of revenue from operations) in FY2024?",
            [[f"{npm:.1f}", f"{int(npm * 10) / 10:.1f}"]],
            [gold(t, 2024, "highlights", "pnl")],
        )
        de = d[2024]["borrowings"] / d[2024]["equity"]
        add(
            "calculation",
            "hard",
            "calculation",
            f"What was {n}'s debt-to-equity ratio (borrowings divided by total equity) at March 31, 2024?",
            [[f"{de:.2f}", f"{int(de * 100) / 100:.2f}"]],
            [gold(t, 2024, "bs")],
        )
        # --- same facts, different words (retrieval robustness) ---
        # --- segments ---
        segs = d[2024]["segments"]
        top = max(range(len(segs)), key=lambda i: segs[i])
        add(
            "segments",
            "medium",
            "aggregation",
            f"Which segment contributed the most revenue to {n} in FY2024, and how much?",
            [[cos[t].segments[top].lower()], [inr(segs[top])]],
            [gold(t, 2024, "highlights")],
        )
        # --- risks ---
        add(
            "risks",
            "medium",
            "summarisation",
            f"What are the key risks mentioned by {n} in its FY2024 report?",
            [[r[0].lower().split()[0]] for r in cos[t].risks[:2]],
            [gold(t, 2024, "risks")],
        )
        add(
            "risks",
            "hard",
            "retrieval across companies",
            f"Which company flags '{cos[t].risks[0][0].lower()}' as a risk in its FY2024 report?",
            [[s.lower().replace(" ", "")]],
            [gold(t, 2024, "risks")],
        )

    # --- paraphrases: different vocabulary for the same facts ---
    b, sg, nv = "BHIT", "SAGR", "NAVM"
    add(
        "paraphrase",
        "medium",
        "lookup",
        "What was the turnover of Bharat Infotech in FY2024?",
        [[inr(all_data[b][2024]["revenue"])]],
        [gold(b, 2024, "chair", "highlights", "pnl")],
    )
    add(
        "paraphrase",
        "medium",
        "lookup",
        "What was Sagar Pharma's net profit for the year ended March 2023?",
        [[inr(all_data[sg][2023]["pat"])]],
        [gold(sg, 2023, "chair", "highlights", "pnl")],
    )
    add(
        "paraphrase",
        "medium",
        "lookup",
        "What was the head count at Navbharat Motors in March 2024?",
        [[inr(all_data[nv][2024]["employees"])]],
        [gold(nv, 2024, "chair")],
    )
    # --- multi-company comparisons ---
    names = {c.ticker: c.name for c in COMPANIES}
    for x, y in [(b, sg), (sg, nv), (b, nv)]:
        add(
            "multi_company",
            "medium",
            "comparison",
            f"Compare the FY2024 profit after tax of {names[x]} and {names[y]}.",
            [[inr(all_data[x][2024]["pat"])], [inr(all_data[y][2024]["pat"])]],
            [gold(x, 2024, "highlights", "pnl"), gold(y, 2024, "highlights", "pnl")],
        )
    growth = {t: all_data[t][2024]["revenue"] / all_data[t][2023]["revenue"] for t in all_data}
    best = max(growth, key=growth.get)
    add(
        "multi_company",
        "hard",
        "comparison",
        "Which of the three companies had the highest revenue growth in FY2024 over FY2023?",
        [[short[best].lower().replace(" ", "")]],
        [gold(t, fy, "highlights", "pnl") for t in all_data for fy in (2023, 2024)],
    )
    margin = {t: all_data[t][2024]["margin"] for t in all_data}
    best = max(margin, key=margin.get)
    add(
        "multi_company",
        "hard",
        "comparison",
        "Which company had the highest pre-tax margin in FY2024?",
        [[short[best].lower().replace(" ", "")]],
        [gold(t, 2024, "highlights") for t in all_data],
    )

    # --- follow-ups that depend on the conversation ---
    def turn(q, a):
        return [{"role": "user", "content": q}, {"role": "assistant", "content": a}]

    add(
        "follow_up",
        "hard",
        "conversation memory",
        "And what was it in FY2023?",
        [[inr(all_data[b][2023]["revenue"])]],
        [gold(b, 2023, "chair", "highlights", "pnl")],
        history=turn(
            "What was Bharat Infotech's revenue from operations in FY2024?",
            f"Rs {inr(all_data[b][2024]['revenue'])} crore [BHIT FY2024 p.3].",
        ),
    )
    add(
        "follow_up",
        "hard",
        "conversation memory",
        "How about their employee count?",
        [[inr(all_data[sg][2024]["employees"])]],
        [gold(sg, 2024, "chair")],
        history=turn(
            "What was Sagar Pharma's profit after tax in FY2024?",
            f"Rs {inr(all_data[sg][2024]['pat'])} crore [SAGR FY2024 p.3].",
        ),
    )
    add(
        "follow_up",
        "hard",
        "conversation memory",
        "Now do the same for Navbharat Motors.",
        [[inr(all_data[nv][2024]["pat"])]],
        [gold(nv, 2024, "highlights", "pnl")],
        history=turn(
            "What was Bharat Infotech's profit after tax in FY2024?",
            f"Rs {inr(all_data[b][2024]['pat'])} crore [BHIT FY2024 p.3].",
        ),
    )
    # --- must refuse: not in the reports ---
    for q in [
        "What will Bharat Infotech's revenue be in FY2026?",
        "What is the current share price of Sagar Pharma?",
        "What was Infosys's revenue in FY2024?",
        "Should I buy Navbharat Motors shares?",
        "What was the salary of the Managing Director of Sagar Pharma in FY2024?",
        "What was Bharat Infotech's revenue in FY2025?",
    ]:
        add("unanswerable", "medium", "refusal", q, unanswerable=True)
    return qs


def main() -> None:
    out_dir = ROOT / "data" / "pdfs"
    out_dir.mkdir(parents=True, exist_ok=True)
    all_data = {}
    for c in COMPANIES:
        data = build_data(c)
        all_data[c.ticker] = data
        for fy in YEARS:  # each report shows FY and FY-1 columns
            render(c, data, fy, out_dir / f"{c.ticker}_FY{fy}.pdf")
    names_file = out_dir.parent / "companies.json"  # merge, so real companies you added are kept
    names = json.loads(names_file.read_text()) if names_file.exists() else {}
    names_file.write_text(json.dumps({**names, **{c.ticker: c.name for c in COMPANIES}}, indent=2))
    qs = questions(all_data, out_dir)
    (Path(__file__).resolve().parents[1] / "evals" / "questions.json").write_text(
        json.dumps(qs, indent=2)
    )
    (Path(__file__).resolve().parents[1] / "evals" / "mock_truth.json").write_text(
        json.dumps({t: {str(y): v for y, v in d.items()} for t, d in all_data.items()}, indent=2)
    )
    print(f"wrote {len(COMPANIES) * len(YEARS)} PDFs to {out_dir} and {len(qs)} questions")


if __name__ == "__main__":
    main()
