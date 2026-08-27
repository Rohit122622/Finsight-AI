"""
Helper to generate realistic Bed Bath & Beyond (BBBY) FY2022/2023 Form 10-K distress filing PDF fixture.
"""

from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def build_bbby_distress_pdf():
    fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fixtures_dir / "bbby_distress_10k.pdf"

    doc = SimpleDocTemplate(
        str(pdf_path),
        pagesize=letter,
        leftMargin=54,
        rightMargin=54,
        topMargin=54,
        bottomMargin=54,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        "DocTitle",
        parent=styles["Heading1"],
        fontSize=18,
        leading=22,
        spaceAfter=12,
    )
    heading2_style = ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13,
        leading=16,
        spaceBefore=14,
        spaceAfter=8,
    )
    body_style = ParagraphStyle(
        "Body",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13.5,
        spaceAfter=8,
    )
    callout_style = ParagraphStyle(
        "Callout",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor("#7a1010"),
        spaceAfter=8,
    )

    story = []

    # Page 1: Cover Page
    story.append(Paragraph("UNITED STATES SECURITIES AND EXCHANGE COMMISSION", title_style))
    story.append(Paragraph("Washington, D.C. 20549", body_style))
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>FORM 10-K</b>", title_style))
    story.append(Paragraph("<b>ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES EXCHANGE ACT OF 1934</b>", body_style))
    story.append(Paragraph("For the fiscal year ended February 25, 2023", body_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>BED BATH & BEYOND INC.</b>", title_style))
    story.append(Paragraph("650 Liberty Avenue, Union, New Jersey 07083", body_style))
    story.append(Paragraph("Commission File Number: 000-20214", body_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("Securities registered pursuant to Section 12(b) of the Act: Common Stock, $0.01 par value per share (BBBY) — The Nasdaq Stock Market LLC", body_style))
    story.append(PageBreak())

    # Pages 2-3: Item 1 - Business
    for p in range(2, 4):
        story.append(Paragraph("PART I", title_style))
        story.append(Paragraph("<b>Item 1. Business</b>", heading2_style))
        story.append(Paragraph(
            f"Bed Bath & Beyond Inc. (Page {p}) is an omnichannel retailer offering domestic merchandise and home furnishings. "
            "The Company operates retail stores under the names Bed Bath & Beyond and buybuy BABY, as well as various e-commerce websites.",
            body_style,
        ))
        story.append(Paragraph(
            "During fiscal 2022, the Company initiated an aggressive store footprint rationalization, closing 150 lower-producing stores and reducing corporate headcount to mitigate cash burn.",
            body_style,
        ))
        story.append(PageBreak())

    # Pages 4-6: Item 1A - Risk Factors
    for p in range(4, 7):
        story.append(Paragraph("<b>Item 1A. Risk Factors</b>", heading2_style))
        story.append(Paragraph(
            f"Liquidity and Solvency Risks (Page {p}): The Company has suffered significant recurring net losses and cash burn from operations, which raise substantial doubt about its ability to continue as a going concern.",
            callout_style,
        ))
        story.append(Paragraph(
            "Our access to trade credit and vendor financing has been severely restricted as merchandise suppliers and credit insurers have demanded cash in advance or reduced payment terms.",
            body_style,
        ))
        story.append(Paragraph(
            "If the Company is unable to execute emergency capital recapitalization or restructuring transactions, it may be forced to seek relief under Chapter 11 of the U.S. Bankruptcy Code.",
            callout_style,
        ))
        story.append(PageBreak())

    # Pages 7-10: Item 7 - MD&A
    for p in range(7, 11):
        story.append(Paragraph("PART II", title_style))
        story.append(Paragraph("<b>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</b>", heading2_style))
        story.append(Paragraph(
            f"Results of Operations (Page {p}): Net sales for fiscal 2022 were $5,345 million, compared to $7,871 million in fiscal 2021, representing a severe top-line decline of $2,526 million or 32.1%. "
            "The drop in net sales was driven by reduced customer foot traffic, widespread inventory stockouts, and brand damage.",
            body_style,
        ))
        story.append(Paragraph(
            "Gross margin compressed precipitously by 11.8 percentage points to 19.8% in fiscal 2022 from 31.6% in fiscal 2021, driven by massive clearance discounting and inventory impairment markdowns.",
            body_style,
        ))
        story.append(Paragraph(
            "The Company experienced extreme liquidity pressure, resulting in an operating loss of $(1,230) million and a net loss of $(1,400) million for fiscal 2022.",
            body_style,
        ))
        # Summary MD&A table
        mda_table = [
            ["Key Metric (in millions)", "Fiscal 2022", "Fiscal 2021", "YoY Change"],
            ["Net Sales", "$5,345", "$7,871", "-32.1%"],
            ["Gross Profit", "$1,058", "$2,487", "-57.5%"],
            ["Gross Margin %", "19.8%", "31.6%", "-11.8 pts"],
            ["Operating Loss", "$(1,230)", "$(480)", "-156.3%"],
            ["Net Loss", "$(1,400)", "$(560)", "-150.0%"],
        ]
        t = Table(mda_table, colWidths=[160, 110, 110, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#fbebeb")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(PageBreak())

    # Pages 11-14: Item 8 - Financial Statements (Operations, Balance Sheet, Cash Flows)
    for p in range(11, 15):
        story.append(Paragraph("<b>Item 8. Consolidated Financial Statements and Supplementary Data</b>", heading2_style))
        story.append(Paragraph("<b>Bed Bath & Beyond Inc. Consolidated Statements of Operations</b>", heading2_style))
        story.append(Paragraph(f"Financial Statements (Page {p}) (in millions, except per share data):", body_style))

        ops_table = [
            ["Statements of Operations", "Fiscal 2022", "Fiscal 2021"],
            ["Net Sales", "$5,345", "$7,871"],
            ["Cost of Sales", "$4,287", "$5,384"],
            ["Gross Profit", "$1,058", "$2,487"],
            ["Selling, general and administrative expenses", "$2,288", "$2,967"],
            ["Operating Loss", "$(1,230)", "$(480)"],
            ["Interest expense, net", "$170", "$80"],
            ["Net Loss", "$(1,400)", "$(560)"],
            ["Diluted Loss Per Share", "$(14.50)", "$(5.80)"],
        ]
        t = Table(ops_table, colWidths=[240, 120, 120])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(Spacer(1, 10))

        story.append(Paragraph("<b>Consolidated Balance Sheet & Cash Flow Highlights (in millions):</b>", heading2_style))
        bs_table = [
            ["Balance Sheet / Cash Flow Metric", "Fiscal 2022", "Fiscal 2021"],
            ["Total Debt (Borrowings & Senior Notes)", "$1,730", "$1,180"],
            ["Prior Total Debt", "$1,180", "$1,020"],
            ["Cash and cash equivalents", "$153", "$439"],
            ["Total Stockholders' Equity (Deficit)", "$(798)", "$150"],
            ["Operating Cash Flow (Cash used in operating activities)", "$(508)", "$(337)"],
        ]
        t2 = Table(bs_table, colWidths=[240, 120, 120])
        t2.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t2)
        story.append(PageBreak())

    # Pages 15-18: Item 8 Note 8 - Debt & Covenant Default Disclosures
    for p in range(15, 19):
        story.append(Paragraph("<b>Note 8 — Debt Financing, Credit Facilities and Covenant Breaches</b>", heading2_style))
        story.append(Paragraph(
            f"Credit Facilities and Covenant Default (Page {p}): As of February 25, 2023, total outstanding long-term debt was $1,730 million, representing a $550 million or 46.6% surge from $1,180 million in the prior year.",
            body_style,
        ))
        story.append(Paragraph(
            "During January 2023, the Company received formal default notices from JPMorgan Chase Bank, N.A., as administrative agent under the Amended Credit Agreement, citing covenant breaches and failures to maintain minimum liquidity thresholds.",
            callout_style,
        ))
        story.append(Paragraph(
            "The Company entered into temporary waiver and forbearance agreements while exploring emergency debt restructuring and equity offerings.",
            body_style,
        ))
        story.append(PageBreak())

    # Pages 19-21: Auditor Report (Going Concern Explanatory Paragraph)
    for p in range(19, 22):
        story.append(Paragraph("<b>Report of Independent Registered Public Accounting Firm</b>", heading2_style))
        story.append(Paragraph("To the Shareholders and Board of Directors of Bed Bath & Beyond Inc.", body_style))
        story.append(Paragraph(
            f"<b>Substantial Doubt About the Company's Ability to Continue as a Going Concern (Page {p})</b>",
            heading2_style,
        ))
        story.append(Paragraph(
            "The accompanying consolidated financial statements have been prepared assuming that the Company will continue as a going concern. "
            "As discussed in Note 1 to the consolidated financial statements, the Company has suffered recurring operating losses, negative cash flows from operating activities of $(508) million, and has a stockholders' deficit of $(798) million that raise substantial doubt about its ability to continue as a going concern. "
            "Management's plans in regard to these matters are also described in Note 1. The consolidated financial statements do not include any adjustments that might result from the outcome of this uncertainty.",
            callout_style,
        ))
        story.append(PageBreak())

    # Pages 22-25: Item 9A - Controls & Procedures (Material Weakness)
    for p in range(22, 26):
        story.append(Paragraph("<b>Item 9A. Controls and Procedures</b>", heading2_style))
        story.append(Paragraph(
            f"Evaluation of Disclosure Controls and Procedures (Page {p}): Management, under the supervision of the Chief Executive Officer and Chief Financial Officer, evaluated the effectiveness of disclosure controls and internal control over financial reporting (SOX 404).",
            body_style,
        ))
        story.append(Paragraph(
            "Management identified material weaknesses in internal control over financial reporting related to: (1) inadequate design of controls over complex debt and equity financing arrangements, and (2) inventory valuation and lower-of-cost-or-net-realizable-value write-down procedures. "
            "Due to these material weaknesses, internal control over financial reporting was not effective as of February 25, 2023.",
            callout_style,
        ))
        if p < 25:
            story.append(PageBreak())

    doc.build(story)
    print(f"Generated 25-page BBBY Distress Form 10-K PDF at: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_bbby_distress_pdf()
