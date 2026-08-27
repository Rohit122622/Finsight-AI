"""
Helper to generate realistic 65-page Apple 2025 Form 10-K Annual Report PDF fixture.
"""

import os
from pathlib import Path
from reportlab.lib.pagesizes import letter
from reportlab.pdfgen import canvas
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors


def build_apple_10k_pdf():
    fixtures_dir = Path(__file__).resolve().parent.parent / "tests" / "fixtures"
    fixtures_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = fixtures_dir / "apple_2025_annual_report.pdf"

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

    story = []

    # Page 1: Cover Page
    story.append(Paragraph("UNITED STATES SECURITIES AND EXCHANGE COMMISSION", title_style))
    story.append(Paragraph("Washington, D.C. 20549", body_style))
    story.append(Spacer(1, 15))
    story.append(Paragraph("<b>FORM 10-K</b>", title_style))
    story.append(Paragraph("<b>ANNUAL REPORT PURSUANT TO SECTION 13 OR 15(d) OF THE SECURITIES EXCHANGE ACT OF 1934</b>", body_style))
    story.append(Paragraph("For the fiscal year ended September 27, 2025", body_style))
    story.append(Spacer(1, 20))
    story.append(Paragraph("<b>APPLE INC.</b>", title_style))
    story.append(Paragraph("One Apple Park Way, Cupertino, California 95014", body_style))
    story.append(Paragraph("Commission File Number: 001-36743", body_style))
    story.append(Spacer(1, 30))
    story.append(Paragraph("Securities registered pursuant to Section 12(b) of the Act: Common Stock, $0.00001 par value per share (AAPL) — The Nasdaq Stock Market LLC", body_style))
    story.append(PageBreak())

    # Pages 2-8: Item 1 - Business
    for p in range(2, 9):
        story.append(Paragraph("PART I", title_style))
        story.append(Paragraph("<b>Item 1. Business</b>", heading2_style))
        story.append(Paragraph(
            f"Apple Inc. (Page {p}) designs, manufactures, and markets smartphones, personal computers, tablets, wearables, and accessories, and sells a variety of related services. "
            "The Company's fiscal year is the 52- or 53-week period that ends on the last Saturday of September.",
            body_style,
        ))
        story.append(Paragraph(
            "The Company's product offerings include iPhone, Mac, iPad, and Wearables, Home and Accessories. "
            "The Company's services offerings include Advertising, AppleCare, Cloud Services, Digital Content and Payment Services.",
            body_style,
        ))
        # Add product table
        table_data = [
            ["Product Line", "Primary Description", "Target Audience"],
            ["iPhone", "Smartphones based on iOS platform", "Consumer & Enterprise"],
            ["Mac", "Personal computers based on macOS", "Professionals & Consumers"],
            ["iPad", "Multi-purpose tablets based on iPadOS", "Education, Creative, Enterprise"],
            ["Wearables", "Apple Watch, AirPods, Beats, Apple Vision Pro", "Everyday users"],
            ["Services", "App Store, Apple Music, iCloud, Apple Pay", "Global Ecosystem"],
        ]
        t = Table(table_data, colWidths=[100, 240, 160])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ('TEXTCOLOR', (0, 0), (-1, -1), colors.black),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
        ]))
        story.append(t)
        story.append(PageBreak())

    # Pages 9-18: Item 1A - Risk Factors
    for p in range(9, 19):
        story.append(Paragraph("<b>Item 1A. Risk Factors</b>", heading2_style))
        story.append(Paragraph(
            f"Risk Disclosures (Page {p}): The Company's business, results of operations, and financial condition can be adversely affected by various risks, including global economic conditions, supply chain disruptions, geopolitical conflicts, and technological obsolescence.",
            body_style,
        ))
        story.append(Paragraph(
            "Global macroeconomic volatility, inflationary pressures, and changes in consumer purchasing power could reduce demand for premium consumer hardware and digital subscription services.",
            body_style,
        ))
        story.append(Paragraph(
            "The Company depends on single-source suppliers and advanced semiconductor fabrication facilities in East Asia for critical proprietary components.",
            body_style,
        ))
        story.append(PageBreak())

    # Pages 19-21: Item 1C - Cybersecurity
    for p in range(19, 22):
        story.append(Paragraph("<b>Item 1C. Cybersecurity</b>", heading2_style))
        story.append(Paragraph(
            f"Cybersecurity Risk Management (Page {p}): The Company maintains comprehensive cybersecurity risk management processes integrated into its enterprise risk framework.",
            body_style,
        ))
        story.append(Paragraph(
            "The Board of Directors oversees cybersecurity risks through the Audit Committee. Management has established a dedicated Information Security Team led by the Chief Information Security Officer (CISO).",
            body_style,
        ))
        story.append(PageBreak())

    # Pages 22-24: Item 3 - Legal Proceedings
    for p in range(22, 25):
        story.append(Paragraph("<b>Item 3. Legal Proceedings</b>", heading2_style))
        story.append(Paragraph(
            f"Legal Disclosures (Page {p}): The Company is subject to legal proceedings and claims that arise in the ordinary course of business, including matters involving antitrust, patent licensing, and consumer privacy.",
            body_style,
        ))
        story.append(PageBreak())

    # Pages 25-38: Item 7 - MD&A
    for p in range(25, 39):
        story.append(Paragraph("PART II", title_style))
        story.append(Paragraph("<b>Item 7. Management's Discussion and Analysis of Financial Condition and Results of Operations</b>", heading2_style))
        story.append(Paragraph(
            f"Overview (Page {p}): Total net sales increased 6.4% or $25,126 million during fiscal 2025 compared to fiscal 2024, driven by growth in Services and iPhone sales.",
            body_style,
        ))
        story.append(Paragraph(
            "Gross margin was $192,580 million in fiscal 2025, compared to $180,683 million in fiscal 2024. Operating expenses were $59,850 million, resulting in Operating Income of $132,730 million.",
            body_style,
        ))
        # Add MD&A metrics table
        mda_table = [
            ["Metric (in millions)", "Fiscal 2025", "Fiscal 2024", "Change %"],
            ["Total Net Sales", "$416,161", "$391,035", "+6.4%"],
            ["Gross Margin", "$192,580", "$180,683", "+6.6%"],
            ["Operating Income", "$132,730", "$123,216", "+7.7%"],
            ["Net Income", "$112,010", "$93,736", "+19.5%"],
        ]
        t = Table(mda_table, colWidths=[160, 110, 110, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f5f5f5")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
        ]))
        story.append(t)
        story.append(PageBreak())

    # Pages 39-45: Item 8 - Financial Statements (Income Statement & Balance Sheet)
    for p in range(39, 46):
        story.append(Paragraph("<b>Item 8. Consolidated Financial Statements and Supplementary Data</b>", heading2_style))
        story.append(Paragraph("<b>Apple Inc. Consolidated Statements of Operations</b>", heading2_style))
        story.append(Paragraph(f"Financial Statements (Page {p}) (in millions, except number of shares which are reflected in thousands and per share amounts):", body_style))

        # Core statement of operations table
        ops_table = [
            ["Three-Year Financial Summary", "2025", "2024", "2023"],
            ["Total Net Sales", "$416,161", "$391,035", "$383,285"],
            ["Products", "$299,280", "$294,851", "$298,085"],
            ["Services", "$116,881", "$96,184", "$85,200"],
            ["Cost of sales: Products", "$191,240", "$189,452", "$192,100"],
            ["Cost of sales: Services", "$32,341", "$20,900", "$18,500"],
            ["Total cost of sales", "$223,581", "$210,352", "$210,600"],
            ["Gross margin", "$192,580", "$180,683", "$172,685"],
            ["Operating expenses: Research and development", "$34,200", "$31,370", "$29,915"],
            ["Operating expenses: Selling, general and administrative", "$25,650", "$24,500", "$24,932"],
            ["Total operating expenses", "$59,850", "$55,870", "$54,847"],
            ["Operating income", "$132,730", "$124,813", "$117,838"],
            ["Other income / (expense), net", "$1,450", "$1,200", "$900"],
            ["Income before provision for income taxes", "$134,180", "$126,013", "$118,738"],
            ["Provision for income taxes", "$22,170", "$32,277", "$21,743"],
            ["Net income", "$112,010", "$93,736", "$96,995"],
            ["Earnings per share: Basic", "$7.48", "$6.11", "$6.16"],
            ["Earnings per share: Diluted", "$7.42", "$6.08", "$6.13"],
        ]
        t = Table(ops_table, colWidths=[190, 95, 95, 95])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#e8e8e8")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('FONTNAME', (0, 1), (-1, 1), 'Helvetica-Bold'),
            ('FONTNAME', (0, 15), (-1, 15), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        story.append(PageBreak())

    # Pages 46-65: Notes to Consolidated Financial Statements & Auditor Report
    for p in range(46, 66):
        story.append(Paragraph("<b>Report of Independent Registered Public Accounting Firm & Notes to Consolidated Financial Statements</b>", heading2_style))
        story.append(Paragraph(
            f"Notes to Financial Statements (Page {p}): Summary of Significant Accounting Policies, Segment Information, Income Taxes, Long-Term Debt and Term Notes.",
            body_style,
        ))
        story.append(Paragraph(
            "Note 7 — Debt: As of September 27, 2025, total outstanding term debt and commercial paper was $101,250 million. All covenants are in compliance.",
            body_style,
        ))
        # Add supplementary notes table
        note_table = [
            ["Segment / Note Detail", "FY 2025 ($M)", "FY 2024 ($M)", "FY 2023 ($M)"],
            ["Americas Net Sales", "$176,500", "$167,400", "$162,560"],
            ["Europe Net Sales", "$108,200", "$101,100", "$94,300"],
            ["Greater China Net Sales", "$68,400", "$66,950", "$72,550"],
            ["Rest of Asia Pacific Net Sales", "$32,800", "$30,150", "$29,615"],
            ["Japan Net Sales", "$30,261", "$25,435", "$24,260"],
        ]
        t = Table(note_table, colWidths=[175, 100, 100, 100])
        t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor("#f0f0f0")),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.grey),
            ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
        ]))
        story.append(t)
        if p < 65:
            story.append(PageBreak())

    doc.build(story)
    print(f"Generated 65-page Apple 10-K PDF at: {pdf_path} ({pdf_path.stat().st_size:,} bytes)")


if __name__ == "__main__":
    build_apple_10k_pdf()
