"""
FinSentry AI — ReportLab Platypus PDF Generator for Multi-Company Comparison.

Owner: FinSentry Engineering Team

Constructs institutional peer comparison PDF audits from ComparisonOutput.
"""

import io
import logging
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from reportlab.lib import colors
from reportlab.lib.pagesizes import letter
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.pdfgen import canvas
from reportlab.platypus import (
    HRFlowable,
    KeepTogether,
    PageBreak,
    Paragraph,
    SimpleDocTemplate,
    Spacer,
    Table,
    TableStyle,
)

logger = logging.getLogger(__name__)

PRIMARY_NAVY = colors.HexColor("#0f172a")
BRAND_EMERALD = colors.HexColor("#10b981")
ACCENT_BLUE = colors.HexColor("#2563eb")
AMBER_WARNING = colors.HexColor("#d97706")
TEXT_MAIN = colors.HexColor("#1e293b")
TEXT_MUTED = colors.HexColor("#64748b")
BG_SURFACE = colors.HexColor("#f8fafc")
BG_HEADER = colors.HexColor("#1e293b")
BORDER_LIGHT = colors.HexColor("#e2e8f0")


class ComparisonNumberedCanvas(canvas.Canvas):
    """Two-pass canvas for Page X of Y and running headers/footers."""

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

        # Running Header on page 2+
        if self._pageNumber > 1:
            self.setFont("Helvetica", 7.5)
            self.setFillColor(TEXT_MUTED)
            self.drawString(36, 756, "FINSENTRY AI  |  COMPARATIVE FINANCIAL AUDIT")
            self.setStrokeColor(BORDER_LIGHT)
            self.setLineWidth(0.5)
            self.line(36, 750, 576, 750)

        # Running Footer
        self.setStrokeColor(BORDER_LIGHT)
        self.setLineWidth(0.5)
        self.line(36, 42, 576, 42)

        self.setFont("Helvetica", 7.5)
        self.setFillColor(TEXT_MUTED)
        self.drawString(36, 30, "CONFIDENTIAL  —  FOR INSTITUTIONAL AUDIT ONLY")

        page_str = f"Page {self._pageNumber} of {page_count}"
        self.drawRightString(576, 30, page_str)

        self.restoreState()


class ComparisonPDFBuilder:
    """Deterministic ReportLab generator for Comparative Financial Audit reports."""

    def __init__(self) -> None:
        self.styles = getSampleStyleSheet()
        self._init_styles()

    def _init_styles(self) -> None:
        self.title_style = ParagraphStyle(
            "CompTitle",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=20,
            leading=24,
            textColor=PRIMARY_NAVY,
            spaceAfter=6,
        )
        self.subtitle_style = ParagraphStyle(
            "CompSubtitle",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=10,
            leading=14,
            textColor=TEXT_MUTED,
            spaceAfter=12,
        )
        self.h2_style = ParagraphStyle(
            "CompH2",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=13,
            leading=16,
            textColor=PRIMARY_NAVY,
            spaceBefore=12,
            spaceAfter=6,
        )
        self.cell_style = ParagraphStyle(
            "CompCell",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=TEXT_MAIN,
        )
        self.cell_bold = ParagraphStyle(
            "CompCellBold",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=TEXT_MAIN,
        )
        self.cell_header = ParagraphStyle(
            "CompCellHeader",
            parent=self.styles["Normal"],
            fontName="Helvetica-Bold",
            fontSize=8,
            leading=10,
            textColor=colors.white,
        )
        self.cell_muted = ParagraphStyle(
            "CompCellMuted",
            parent=self.styles["Normal"],
            fontName="Helvetica",
            fontSize=8,
            leading=10,
            textColor=TEXT_MUTED,
        )

    def build_pdf(
        self,
        comparison_data: Dict[str, Any],
        title: str = "Comparative Financial Audit",
    ) -> bytes:
        """
        Generate binary PDF bytes from comparison dictionary.
        """
        buffer = io.BytesIO()
        doc = SimpleDocTemplate(
            buffer,
            pagesize=letter,
            leftMargin=36,
            rightMargin=36,
            topMargin=54,
            bottomMargin=54,
        )

        flowables = []

        # 1. Header Section
        flowables.append(Paragraph(title, self.title_style))
        gen_time = datetime.now(timezone.utc).strftime("%B %d, %Y • %H:%M UTC")
        session_id = comparison_data.get("session_id", "N/A")
        flowables.append(
            Paragraph(
                f"Generated: {gen_time} &nbsp;|&nbsp; Session: {session_id[:12]}",
                self.subtitle_style,
            )
        )
        flowables.append(HRFlowable(width="100%", thickness=1.5, color=BRAND_EMERALD, spaceAfter=14))

        # 2. Companies Overview
        companies = comparison_data.get("companies", [])
        if companies:
            flowables.append(Paragraph("Participating Companies", self.h2_style))
            comp_table_data = [
                [
                    Paragraph("Company", self.cell_header),
                    Paragraph("Document / Filing", self.cell_header),
                    Paragraph("Currency", self.cell_header),
                    Paragraph("Scale", self.cell_header),
                ]
            ]
            for c in companies:
                c_name = c.get("company_name", "Unknown") if isinstance(c, dict) else str(c)
                f_type = c.get("filing_type") or "Annual Filing" if isinstance(c, dict) else "Filing"
                curr = c.get("reporting_currency") or "USD" if isinstance(c, dict) else "USD"
                scale = c.get("reporting_scale") or "Millions" if isinstance(c, dict) else "Millions"
                comp_table_data.append(
                    [
                        Paragraph(c_name, self.cell_bold),
                        Paragraph(f_type, self.cell_style),
                        Paragraph(curr, self.cell_style),
                        Paragraph(scale.title(), self.cell_style),
                    ]
                )
            comp_table = Table(comp_table_data, colWidths=[150, 150, 100, 140])
            comp_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
                        ("TOPPADDING", (0, 0), (-1, -1), 4),
                        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_SURFACE]),
                    ]
                )
            )
            flowables.append(comp_table)
            flowables.append(Spacer(1, 14))

        # 3. Fiscal Period Alignment Notice (if no common periods)
        has_common = comparison_data.get("has_common_periods", True)
        common_pers = comparison_data.get("common_periods", [])
        if not has_common or len(common_pers) == 0:
            notice_style = ParagraphStyle(
                "CompNotice",
                parent=self.styles["Normal"],
                fontName="Helvetica",
                fontSize=8.5,
                leading=12,
                textColor=colors.HexColor("#92400e"),
            )
            comp_note = comparison_data.get("comparison_note") or (
                "No common fiscal reporting periods exist across the selected companies. "
                "Individual company metrics are displayed for reference; peer-relative benchmarks (Peer Average, Highest, Lowest) "
                "require overlapping periods and are therefore unavailable."
            )
            notice_p = Paragraph(
                f"<b>Notice on Fiscal Period Alignment:</b> {comp_note}",
                notice_style,
            )
            notice_table = Table([[notice_p]], colWidths=[540])
            notice_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#fef3c7")),
                        ("BOX", (0, 0), (-1, -1), 1, colors.HexColor("#f59e0b")),
                        ("TOPPADDING", (0, 0), (-1, -1), 6),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
                        ("LEFTPADDING", (0, 0), (-1, -1), 8),
                        ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                    ]
                )
            )
            flowables.append(notice_table)
            flowables.append(Spacer(1, 10))

        # 4. Peer Comparison Matrix
        metrics = comparison_data.get("metrics", [])
        if metrics:
            flowables.append(Paragraph("Financial Metrics Comparison Matrix", self.h2_style))

            # Build headers: Metric, Period, Comp1, Comp2..., Peer Avg, Highest, Lowest, Rank
            c_names = [c.get("company_name", f"Company {i+1}") if isinstance(c, dict) else str(c) for i, c in enumerate(companies)]
            
            # Group into manageable columns
            header_row = [
                Paragraph("Metric", self.cell_header),
                Paragraph("Period", self.cell_header),
            ]
            for cn in c_names:
                header_row.append(Paragraph(cn[:12], self.cell_header))
            header_row.extend([
                Paragraph("Peer Avg", self.cell_header),
                Paragraph("Highest", self.cell_header),
                Paragraph("Lowest", self.cell_header),
            ])

            matrix_table_data = [header_row]

            for m in metrics:
                if not isinstance(m, dict):
                    continue
                disp_name = m.get("display_name") or m.get("metric_name", "").replace("_", " ").title()
                if not disp_name or disp_name.lower().startswith("prior_"):
                    continue

                periods = m.get("periods", [])
                for p in periods:
                    if not isinstance(p, dict):
                        continue
                    p_label = p.get("fiscal_period", "N/A")
                    vals = p.get("values", [])
                    p_stats = p.get("peer_statistics", {}) or {}

                    row = [
                        Paragraph(disp_name, self.cell_bold),
                        Paragraph(p_label, self.cell_style),
                    ]

                    # Company values
                    for cn in c_names:
                        val_obj = next((v for v in vals if isinstance(v, dict) and v.get("company_name") == cn), None)
                        if val_obj and val_obj.get("value") is not None and val_obj.get("available", True):
                            v_num = val_obj["value"]
                            unit = val_obj.get("unit") or ""
                            val_str = f"{v_num:,.2f}{'%' if '%' in unit else ''}" if isinstance(v_num, (int, float)) else str(v_num)
                            row.append(Paragraph(val_str, self.cell_style))
                        else:
                            row.append(Paragraph("N/A", self.cell_muted))

                    # Stats (strictly N/A when valid_count < 2 or peer_average is None)
                    valid_cnt = p_stats.get("valid_count", 0)
                    avg_val = p_stats.get("peer_average") if valid_cnt >= 2 else None
                    avg_str = f"{avg_val:,.2f}" if avg_val is not None else "N/A"
                    row.append(Paragraph(avg_str, self.cell_style if avg_val is not None else self.cell_muted))

                    high_obj = p_stats.get("highest") or {}
                    high_val = high_obj.get("value") if isinstance(high_obj, dict) and valid_cnt >= 2 else None
                    high_str = f"{high_val:,.2f}" if high_val is not None else "N/A"
                    row.append(Paragraph(high_str, self.cell_style if high_val is not None else self.cell_muted))

                    low_obj = p_stats.get("lowest") or {}
                    low_val = low_obj.get("value") if isinstance(low_obj, dict) and valid_cnt >= 2 else None
                    low_str = f"{low_val:,.2f}" if low_val is not None else "N/A"
                    row.append(Paragraph(low_str, self.cell_style if low_val is not None else self.cell_muted))

                    matrix_table_data.append(row)

            # Calculate col widths
            total_cols = len(header_row)
            metric_col_w = 110
            period_col_w = 45
            rem_width = 540 - metric_col_w - period_col_w
            stat_cols = 3
            comp_cols = len(c_names)
            col_w = rem_width / max(1, (comp_cols + stat_cols))

            col_widths = [metric_col_w, period_col_w] + [col_w] * (comp_cols + stat_cols)

            matrix_table = Table(matrix_table_data, colWidths=col_widths, repeatRows=1)
            matrix_table.setStyle(
                TableStyle(
                    [
                        ("BACKGROUND", (0, 0), (-1, 0), BG_HEADER),
                        ("ALIGN", (0, 0), (-1, -1), "LEFT"),
                        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
                        ("TOPPADDING", (0, 0), (-1, -1), 3),
                        ("GRID", (0, 0), (-1, -1), 0.5, BORDER_LIGHT),
                        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, BG_SURFACE]),
                    ]
                )
            )
            flowables.append(matrix_table)
            flowables.append(Spacer(1, 14))

        # 5. Summary Insights
        insights = comparison_data.get("summary_insights", [])
        if insights:
            flowables.append(Paragraph("Key Comparison Takeaways", self.h2_style))
            for insight in insights:
                bullet_p = Paragraph(f"• &nbsp; {insight}", self.cell_style)
                flowables.append(bullet_p)
                flowables.append(Spacer(1, 3))

        # Build document
        doc.build(flowables, canvasmaker=ComparisonNumberedCanvas)
        pdf_bytes = buffer.getvalue()
        buffer.close()
        return pdf_bytes


comparison_pdf_builder = ComparisonPDFBuilder()
