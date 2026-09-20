"""
FinSentry AI — ReportLab Platypus PDF Generator Service.

Owner: Vanshika / FinSentry Engineering Team

Constructs institutional analyst-style PDF reports from the validated ReportDocument model.

CRITICAL INVARIANTS:
  1. Strict 5-section order:
     Section 1: Executive Summary
     Section 2: Key Financials
     Section 3: Red Flags
     Section 4: Company Comparison (cleanly omitted for single company)
     Section 5: Outlook
  2. Two-pass NumberedCanvas for "Page X of Y" and running headers/footers.
  3. Professional institutional styling (no overlapping text, no clipped tables).
  4. Deterministic metadata and flowable layout.
"""

import io
import logging
from typing import Any, Dict, List, Optional, Tuple

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    Image,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

from agents.report.schemas import ReportDocument

logger = logging.getLogger(__name__)

# Institutional Color Palette
PRIMARY_NAVY = colors.HexColor("#0f172a")
BRAND_EMERALD = colors.HexColor("#10b981")
ACCENT_BLUE = colors.HexColor("#2563eb")
AMBER_WARNING = colors.HexColor("#d97706")
RED_CRITICAL = colors.HexColor("#dc2626")
TEXT_MAIN = colors.HexColor("#1e293b")
TEXT_MUTED = colors.HexColor("#64748b")
BG_SURFACE = colors.HexColor("#f8fafc")
BORDER_LIGHT = colors.HexColor("#e2e8f0")


class NumberedCanvas(canvas.Canvas):
    """
    Two-pass canvas to dynamically compute and render total page count ('Page X of Y')
    along with running headers and confidential footers.
    """

    def __init__(self, *args, **kwargs) -> None:
        super().__init__(*args, **kwargs)
        self._saved_page_states: List[dict] = []

    def showPage(self) -> None:
        self._saved_page_states.append(dict(self.__dict__))
        self._startPage()

    def save(self) -> None:
        num_pages = len(self._saved_page_states)
        for state in self._saved_page_states:
            self.__dict__.update(state)
            self.draw_page_decorations(num_pages)
            super().showPage()
        super().save()

    def draw_page_decorations(self, page_count: int) -> None:
        self.saveState()

        # Running Header (on page 2 and later)
        if self._pageNumber > 1:
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawString(36, 756, "FINSENTRY AI  |  INSTITUTIONAL FINANCIAL RESEARCH REPORT")
            self.setStrokeColor(BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(36, 750, 576, 750)

        # Running Footer (all pages)
        self.setStrokeColor(BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(36, 42, 576, 42)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(36, 30, "CONFIDENTIAL  —  FOR INTERNAL RESEARCH ONLY")

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(576, 30, page_str)

        self.restoreState()


class PDFBuilder:
    """
    Builds the final analyst-style PDF from a ReportDocument model.
    """

    @classmethod
    def build_pdf(cls, report_doc: ReportDocument, chart_png_bytes: Optional[bytes] = None) -> bytes:
        """
        Assemble the complete PDF and return binary bytes.
        """
        buffer = io.BytesIO()

        # Printable width: 612 - 72 = 540 pt
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=48,
            bottomMargin=48,
        )

        # Normalize metadata for determinism
        doc.info = {
            "Title": report_doc.metadata.report_title,
            "Author": "FinSentry AI",
            "Subject": f"Financial Analysis Report for Session {report_doc.metadata.session_id}",
            "Creator": "FinSentry AI Report Agent",
            "Producer": "ReportLab PDF Library (FinSentry Engine)",
        }

        styles = cls._create_styles()
        story: List[Any] = []

        # 1. Title Banner & Session Overview
        story.extend(cls._build_header(report_doc, styles))

        # 2. Section 1: Executive Summary
        story.extend(cls._build_executive_summary(report_doc, styles))
        story.append(Spacer(1, 14))

        # 3. Section 2: Key Financials
        story.extend(cls._build_key_financials(report_doc, styles))
        story.append(Spacer(1, 14))

        # 4. Section 3: Red Flags
        story.extend(cls._build_red_flags(report_doc, styles))
        story.append(Spacer(1, 14))

        # 5. Section 4: Company Comparison (Omitted cleanly if single company)
        story.extend(cls._build_comparison(report_doc, chart_png_bytes, styles))
        story.append(Spacer(1, 14))

        # 6. Section 5: Outlook
        story.extend(cls._build_outlook(report_doc, styles))
        story.append(Spacer(1, 16))

        # 7. Disclaimers & Provenance Note
        story.extend(cls._build_provenance_footer(report_doc, styles))

        # Build document with NumberedCanvas
        doc.build(story, canvasmaker=NumberedCanvas)

        buffer.seek(0)
        return buffer.getvalue()

    # -------------------------------------------------------------------------
    # Styles Definition
    # -------------------------------------------------------------------------
    @classmethod
    def _create_styles(cls) -> Dict[str, ParagraphStyle]:
        sample = getSampleStyleSheet()

        styles = {
            "DocTitle": ParagraphStyle(
                "DocTitle",
                parent=sample["Heading1"],
                fontName="Helvetica-Bold",
                fontSize=18,
                leading=22,
                textColor=PRIMARY_NAVY,
                spaceAfter=4,
            ),
            "DocSubtitle": ParagraphStyle(
                "DocSubtitle",
                parent=sample["Normal"],
                fontName="Helvetica",
                fontSize=9,
                leading=13,
                textColor=TEXT_MUTED,
            ),
            "SectionTitle": ParagraphStyle(
                "SectionTitle",
                parent=sample["Heading2"],
                fontName="Helvetica-Bold",
                fontSize=12,
                leading=16,
                textColor=PRIMARY_NAVY,
                spaceBefore=10,
                spaceAfter=6,
            ),
            "Body": ParagraphStyle(
                "Body",
                parent=sample["BodyText"],
                fontName="Helvetica",
                fontSize=8.5,
                leading=12.5,
                textColor=TEXT_MAIN,
            ),
            "BodyBold": ParagraphStyle(
                "BodyBold",
                parent=sample["BodyText"],
                fontName="Helvetica-Bold",
                fontSize=8.5,
                leading=12.5,
                textColor=TEXT_MAIN,
            ),
            "MutedNote": ParagraphStyle(
                "MutedNote",
                parent=sample["Normal"],
                fontName="Helvetica-Oblique",
                fontSize=8,
                leading=11,
                textColor=TEXT_MUTED,
            ),
            "TableHeader": ParagraphStyle(
                "TableHeader",
                parent=sample["Normal"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=PRIMARY_NAVY,
                alignment=1,  # Centered
            ),
            "TableCell": ParagraphStyle(
                "TableCell",
                parent=sample["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                textColor=TEXT_MAIN,
            ),
            "TableCellBold": ParagraphStyle(
                "TableCellBold",
                parent=sample["Normal"],
                fontName="Helvetica-Bold",
                fontSize=8,
                leading=10,
                textColor=TEXT_MAIN,
            ),
            "TableCellNum": ParagraphStyle(
                "TableCellNum",
                parent=sample["Normal"],
                fontName="Helvetica",
                fontSize=8,
                leading=10,
                textColor=TEXT_MAIN,
                alignment=2,  # Right-aligned
            ),
        }
        return styles

    # -------------------------------------------------------------------------
    # Header Component
    # -------------------------------------------------------------------------
    @classmethod
    def _build_header(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []

        # Top Accent Line (FinSentry Emerald)
        items.append(HRFlowable(width="100%", thickness=3.5, color=BRAND_EMERALD, spaceAfter=8))

        # Title and Subtitle
        items.append(Paragraph(report_doc.metadata.report_title, styles["DocTitle"]))

        companies_str = ", ".join(report_doc.metadata.companies)
        gen_date = report_doc.metadata.generated_at.strftime("%B %d, %Y at %H:%M UTC")
        subtitle_text = f"Analyzed Entities: <b>{companies_str}</b>  |  Version: {report_doc.metadata.report_version}  |  Generated: {gen_date}"
        items.append(Paragraph(subtitle_text, styles["DocSubtitle"]))
        items.append(Spacer(1, 10))

        # Summary Info Strip
        info_data = [
            [
                Paragraph("<b>Session ID</b>", styles["TableCellBold"]),
                Paragraph(report_doc.metadata.session_id, styles["TableCell"]),
                Paragraph("<b>Composite Risk Score</b>", styles["TableCellBold"]),
                Paragraph(f"<b>{report_doc.red_flags.composite_risk_score:.1f} / 100</b>", styles["TableCellBold"]),
            ],
            [
                Paragraph("<b>Coverage</b>", styles["TableCellBold"]),
                Paragraph(f"{len(report_doc.metadata.companies)} Companies ({len(report_doc.metadata.document_ids)} Filings)", styles["TableCell"]),
                Paragraph("<b>Forensic Red Flags</b>", styles["TableCellBold"]),
                Paragraph(f"{report_doc.red_flags.total_flags} detected ({report_doc.red_flags.high_severity_count} high severity)", styles["TableCell"]),
            ],
        ]
        info_table = Table(info_data, colWidths=[100, 180, 130, 130])
        info_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, -1), BG_SURFACE),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 6),
                ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        items.append(info_table)
        items.append(Spacer(1, 12))
        return items

    # -------------------------------------------------------------------------
    # Section 1: Executive Summary
    # -------------------------------------------------------------------------
    @classmethod
    def _build_executive_summary(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("1. Executive Summary", styles["SectionTitle"]))
        items.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_NAVY, spaceAfter=6))

        sec = report_doc.executive_summary
        items.append(Paragraph(sec.narrative, styles["Body"]))
        items.append(Spacer(1, 6))

        # Two columns: Strengths vs Vulnerabilities
        bullets_data: List[List[Any]] = []
        max_rows = max(len(sec.key_strengths), len(sec.key_weaknesses), 1)

        strengths_cell = []
        if sec.key_strengths:
            strengths_cell.append(Paragraph("<b>Key Financial Strengths</b>", styles["TableCellBold"]))
            for s in sec.key_strengths:
                strengths_cell.append(Paragraph(f"• {s}", styles["TableCell"]))
        else:
            strengths_cell.append(Paragraph("<i>No significant strengths highlighted.</i>", styles["TableCell"]))

        weakness_cell = []
        if sec.key_weaknesses or sec.major_red_flags_summary:
            weakness_cell.append(Paragraph("<b>Forensic Risk Vulnerabilities</b>", styles["TableCellBold"]))
            for w in sec.key_weaknesses:
                weakness_cell.append(Paragraph(f"• {w}", styles["TableCell"]))
            for rf in sec.major_red_flags_summary[:2]:
                weakness_cell.append(Paragraph(f"• {rf}", styles["TableCell"]))
        else:
            weakness_cell.append(Paragraph("<i>No material vulnerabilities identified.</i>", styles["TableCell"]))

        side_by_side = Table([[strengths_cell, weakness_cell]], colWidths=[265, 275])
        side_by_side.setStyle(
            TableStyle([
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("BACKGROUND", (0, 0), (0, 0), colors.HexColor("#f0fdf4")),
                ("BACKGROUND", (1, 0), (1, 0), colors.HexColor("#fff1f2")),
                ("BOX", (0, 0), (0, 0), 0.5, colors.HexColor("#bbf7d0")),
                ("BOX", (1, 0), (1, 0), 0.5, colors.HexColor("#fecdd3")),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ])
        )
        items.append(side_by_side)
        return items

    # -------------------------------------------------------------------------
    # Section 2: Key Financials
    # -------------------------------------------------------------------------
    @classmethod
    def _build_key_financials(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("2. Key Financials", styles["SectionTitle"]))
        items.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_NAVY, spaceAfter=6))

        kf = report_doc.key_financials
        if not kf.metrics:
            items.append(Paragraph("No financial metrics available in the analyzed session.", styles["MutedNote"]))
            return items

        # Derive columns: Metric (160 pt), Category (100 pt), then distribute remaining 280 pt across (Company, Period)
        col_headers: List[str] = []
        comp_period_keys: List[Tuple[str, str]] = []

        for comp in kf.companies:
            for per in kf.reporting_periods:
                col_headers.append(f"{comp}<br/>{per}")
                comp_period_keys.append((comp, per))

        num_val_cols = max(len(col_headers), 1)
        val_col_width = 280.0 / num_val_cols

        col_widths = [160, 100] + [val_col_width] * num_val_cols

        # Header row
        table_rows: List[List[Any]] = []
        hdr_row = [
            Paragraph("<b>Metric</b>", styles["TableHeader"]),
            Paragraph("<b>Category</b>", styles["TableHeader"]),
        ]
        for ch in col_headers:
            hdr_row.append(Paragraph(f"<b>{ch}</b>", styles["TableHeader"]))
        table_rows.append(hdr_row)

        # Data rows
        for row_idx, m_row in enumerate(kf.metrics):
            val_map: Dict[Tuple[str, str], str] = {
                (v.company_name, v.fiscal_period): v.formatted_value for v in m_row.values
            }
            curr_row = [
                Paragraph(m_row.display_name, styles["TableCellBold"]),
                Paragraph(m_row.category, styles["TableCell"]),
            ]
            for c_key in comp_period_keys:
                fmt_v = val_map.get(c_key, "N/A")
                curr_row.append(Paragraph(fmt_v, styles["TableCellNum"]))
            table_rows.append(curr_row)

        fin_table = Table(table_rows, colWidths=col_widths, repeatRows=1)
        t_style = [
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e2e8f0")),
            ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
            ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("TOPPADDING", (0, 0), (-1, -1), 3),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]
        # Alternating row backgrounds
        for r_i in range(1, len(table_rows)):
            if r_i % 2 == 0:
                t_style.append(("BACKGROUND", (0, r_i), (-1, r_i), BG_SURFACE))

        fin_table.setStyle(TableStyle(t_style))
        items.append(fin_table)

        items.append(
            Paragraph(
                "<i>Note: Missing figures denote items not explicitly disclosed in source SEC filings and are rendered as 'N/A' (never zero).</i>",
                styles["MutedNote"],
            )
        )
        return items

    # -------------------------------------------------------------------------
    # Section 3: Red Flags
    # -------------------------------------------------------------------------
    @classmethod
    def _build_red_flags(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("3. Forensic Red Flags & Risk Assessment", styles["SectionTitle"]))
        items.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_NAVY, spaceAfter=6))

        rf = report_doc.red_flags

        if rf.is_empty_state or not rf.findings:
            empty_box = Table(
                [[Paragraph(f"<b>Status: Clean</b> — {rf.empty_state_message}", styles["TableCell"])]],
                colWidths=[540],
            )
            empty_box.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f0fdf4")),
                    ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#bbf7d0")),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ])
            )
            items.append(empty_box)
            return items

        # Overview banner
        banner_text = f"<b>Risk Assessment:</b> {rf.overall_assessment}  |  <b>Composite Risk Score:</b> {rf.composite_risk_score:.1f}/100 ({rf.total_flags} findings, {rf.high_severity_count} high severity)"
        items.append(Paragraph(banner_text, styles["Body"]))
        items.append(Spacer(1, 6))

        # Red flags table
        rf_rows: List[List[Any]] = [
            [
                Paragraph("<b>Severity</b>", styles["TableHeader"]),
                Paragraph("<b>Finding & Company</b>", styles["TableHeader"]),
                Paragraph("<b>Forensic Evidence & Citation</b>", styles["TableHeader"]),
            ]
        ]

        for finding in rf.findings:
            sev_color = RED_CRITICAL if finding.severity in ["CRITICAL", "HIGH"] else (AMBER_WARNING if finding.severity == "MEDIUM" else BRAND_EMERALD)
            sev_p = Paragraph(f"<font color='{sev_color.hexval()}'><b>{finding.severity}</b></font>", styles["TableHeader"])

            chg_str = f"<br/><font color='#b45309'>Change: {finding.change_description}</font>" if finding.change_description else ""
            finding_p = Paragraph(
                f"<b>{finding.title}</b> ({finding.company_name})<br/>"
                f"<font color='#64748b'>{finding.description}</font>{chg_str}",
                styles["TableCell"],
            )

            pg_str = f" [p. {finding.source_page}]" if finding.source_page else ""
            ev_p = Paragraph(f"<i>\"{finding.evidence}\"</i>{pg_str}", styles["TableCell"])

            rf_rows.append([sev_p, finding_p, ev_p])

        rf_table = Table(rf_rows, colWidths=[65, 235, 240], repeatRows=1)
        rf_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#fee2e2")),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 4),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                ("LEFTPADDING", (0, 0), (-1, -1), 5),
                ("RIGHTPADDING", (0, 0), (-1, -1), 5),
            ])
        )
        items.append(rf_table)
        return items

    # -------------------------------------------------------------------------
    # Section 4: Company Comparison (Omitted cleanly if single company)
    # -------------------------------------------------------------------------
    @classmethod
    def _build_comparison(
        cls,
        report_doc: ReportDocument,
        chart_png_bytes: Optional[bytes],
        styles: Dict[str, ParagraphStyle],
    ) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("4. Peer Comparison & Benchmark", styles["SectionTitle"]))
        items.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_NAVY, spaceAfter=6))

        comp = report_doc.comparison

        # Mandatory Single-Company graceful behavior
        if not comp.is_available or len(comp.compared_companies) < 2:
            unavail_msg = comp.unavailable_reason or "Company comparison is unavailable because only one company was included in this session."
            notice_box = Table(
                [[Paragraph(f"<b>Single Company Session:</b> {unavail_msg}", styles["TableCell"])]],
                colWidths=[540],
            )
            notice_box.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), BG_SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 8),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
                    ("LEFTPADDING", (0, 0), (-1, -1), 10),
                ])
            )
            items.append(notice_box)
            return items

        # Multi-company comparison table
        comp_rows: List[List[Any]] = [
            [
                Paragraph("<b>Metric</b>", styles["TableHeader"]),
                Paragraph("<b>Period</b>", styles["TableHeader"]),
                Paragraph("<b>Peer Average</b>", styles["TableHeader"]),
                Paragraph("<b>Highest Peer</b>", styles["TableHeader"]),
                Paragraph("<b>Lowest Peer</b>", styles["TableHeader"]),
            ]
        ]

        for m in comp.metrics[:8]:
            avg_str = f"{m.peer_average:,.1f}" if m.peer_average is not None else "N/A"
            hi_str = f"{m.highest_company}: {m.highest_value:,.1f}" if m.highest_company and m.highest_value is not None else "N/A"
            lo_str = f"{m.lowest_company}: {m.lowest_value:,.1f}" if m.lowest_company and m.lowest_value is not None else "N/A"

            comp_rows.append([
                Paragraph(m.display_name, styles["TableCellBold"]),
                Paragraph(m.fiscal_period, styles["TableHeader"]),
                Paragraph(avg_str, styles["TableCellNum"]),
                Paragraph(hi_str, styles["TableCell"]),
                Paragraph(lo_str, styles["TableCell"]),
            ])

        comp_table = Table(comp_rows, colWidths=[140, 70, 100, 115, 115], repeatRows=1)
        comp_table.setStyle(
            TableStyle([
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#e0e7ff")),
                ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("INNERGRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                ("TOPPADDING", (0, 0), (-1, -1), 3),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
            ])
        )
        items.append(comp_table)

        # Embedded Matplotlib Chart Image
        if chart_png_bytes:
            items.append(Spacer(1, 8))
            chart_img = Image(io.BytesIO(chart_png_bytes), width=510, height=195)
            items.append(chart_img)

        return items

    # -------------------------------------------------------------------------
    # Section 5: Outlook
    # -------------------------------------------------------------------------
    @classmethod
    def _build_outlook(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []
        items.append(Paragraph("5. Outlook & Grounded Research Observations", styles["SectionTitle"]))
        items.append(HRFlowable(width="100%", thickness=1, color=PRIMARY_NAVY, spaceAfter=6))

        out = report_doc.outlook
        if out.is_empty_state or not out.findings:
            items.append(Paragraph(out.empty_state_message, styles["MutedNote"]))
            return items

        for f in out.findings:
            box_content = [
                Paragraph(f"<b>Research Query / Topic:</b> {f.topic}", styles["TableCellBold"]),
                Paragraph(f.observation, styles["Body"]),
            ]
            box = Table([[box_content]], colWidths=[540])
            box.setStyle(
                TableStyle([
                    ("BACKGROUND", (0, 0), (-1, -1), BG_SURFACE),
                    ("BOX", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                    ("TOPPADDING", (0, 0), (-1, -1), 6),
                    ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                    ("LEFTPADDING", (0, 0), (-1, -1), 8),
                    ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ])
            )
            items.append(box)
            items.append(Spacer(1, 6))

        return items

    # -------------------------------------------------------------------------
    # Footer & Provenance
    # -------------------------------------------------------------------------
    @classmethod
    def _build_provenance_footer(cls, report_doc: ReportDocument, styles: Dict[str, ParagraphStyle]) -> List[Any]:
        items: List[Any] = []
        docs_str = ", ".join(report_doc.metadata.document_ids)
        footer_text = (
            f"<b>Data Provenance & Audit Trail:</b> Source filings: [{docs_str}]. "
            "Report compiled deterministically by FinSentry AI multi-agent orchestration pipeline. "
            "No financial figures or metric calculations were synthesized by artificial intelligence. "
            "All quantitative indicators strictly reflect canonical corporate filings."
        )
        items.append(Paragraph(footer_text, styles["MutedNote"]))
        return items
