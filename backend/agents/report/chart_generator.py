"""
FinSentry AI — Deterministic Chart Generator Service.

Owner: Vanshika / FinSentry Engineering Team

Generates static PNG chart images from Comparison Agent's chart-ready data
for embedding into the PDF report via ReportLab Platypus.

CRITICAL INVARIANTS:
  1. Uses ONLY persisted comparison_results (ZERO recalculation).
  2. Deterministic layout, fixed DPI, fixed color mapping.
  3. Single-company or unavailable comparison cleanly returns None (no empty charts).
"""

import io
import logging
from typing import Dict, List, Optional

import matplotlib
# Headless backend for thread-safe server-side rendering
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from agents.report.schemas import CompanyComparisonSection

logger = logging.getLogger(__name__)

# Institutional FinSentry Color Palette
BRAND_COLORS = [
    "#10b981",  # Emerald (Primary)
    "#3b82f6",  # Blue (Secondary)
    "#f59e0b",  # Amber (Accent 1)
    "#8b5cf6",  # Purple (Accent 2)
    "#ec4899",  # Pink (Accent 3)
    "#06b6d4",  # Cyan (Accent 4)
]


class ChartGenerator:
    """
    Renders deterministic static chart images from comparison outputs.
    """

    @classmethod
    def generate_comparison_bar_chart(
        cls,
        comparison_section: CompanyComparisonSection,
        metric_name_target: str = "revenue",
    ) -> Optional[bytes]:
        """
        Generate a horizontal or grouped bar chart comparing companies across a core metric.
        Returns PNG bytes or None if comparison data is unavailable.
        """
        if not comparison_section.is_available or not comparison_section.metrics:
            return None

        # Find the target metric or fallback to the first available metric
        target_metric = None
        for m in comparison_section.metrics:
            if m.metric_name == metric_name_target and m.company_values:
                target_metric = m
                break

        if not target_metric:
            for m in comparison_section.metrics:
                if m.company_values:
                    target_metric = m
                    break

        if not target_metric or not target_metric.company_values:
            return None

        # Filter companies with valid values
        valid_pairs = [
            (comp, val)
            for comp, val in target_metric.company_values.items()
            if val is not None
        ]
        if len(valid_pairs) < 2:
            return None

        # Deterministic sorting by company name
        valid_pairs.sort(key=lambda x: x[0])
        companies = [p[0] for p in valid_pairs]
        values = [p[1] for p in valid_pairs]

        fig, ax = plt.subplots(figsize=(6.8, 2.6), dpi=150)
        fig.patch.set_facecolor("#ffffff")
        ax.set_facecolor("#f8fafc")

        # Set up bars
        y_pos = np.arange(len(companies))
        bar_colors = [BRAND_COLORS[i % len(BRAND_COLORS)] for i in range(len(companies))]

        bars = ax.barh(y_pos, values, height=0.5, color=bar_colors, edgecolor="none", zorder=3)

        # Labels & Styling
        ax.set_yticks(y_pos)
        ax.set_yticklabels(companies, fontsize=9, fontweight="bold", color="#1e293b")
        ax.invert_yaxis()  # Top-down order

        unit_str = f" ({target_metric.unit})" if target_metric.unit else ""
        title_text = f"Peer Comparison: {target_metric.display_name} [{target_metric.fiscal_period}]{unit_str}"
        ax.set_title(title_text, fontsize=10, fontweight="bold", color="#0f172a", pad=12)

        # Peer average reference line
        if target_metric.peer_average is not None and target_metric.peer_average > 0:
            ax.axvline(
                target_metric.peer_average,
                color="#64748b",
                linestyle="--",
                linewidth=1.2,
                label=f"Peer Avg ({target_metric.peer_average:,.1f})",
                zorder=4,
            )
            ax.legend(loc="lower right", fontsize=7, framealpha=0.9, facecolor="#ffffff", edgecolor="#cbd5e1")

        # Value annotations on bars
        for bar in bars:
            width = bar.get_width()
            val_text = f" {width:,.1f}" if abs(width) < 10_000 else f" ${width:,.0f}"
            ax.text(
                width,
                bar.get_y() + bar.get_height() / 2,
                val_text,
                va="center",
                ha="left" if width >= 0 else "right",
                fontsize=8,
                fontweight="bold",
                color="#334155",
            )

        # Subtle gridlines
        ax.xaxis.grid(True, linestyle=":", alpha=0.6, color="#cbd5e1", zorder=1)
        ax.set_axisbelow(True)

        # Clean spines
        for spine in ["top", "right"]:
            ax.spines[spine].set_visible(False)
        ax.spines["left"].set_color("#cbd5e1")
        ax.spines["bottom"].set_color("#cbd5e1")
        ax.tick_params(axis="x", colors="#64748b", labelsize=8)

        plt.tight_layout()

        buffer = io.BytesIO()
        plt.savefig(buffer, format="png", dpi=150, facecolor=fig.get_facecolor(), bbox_inches="tight")
        plt.close(fig)

        buffer.seek(0)
        return buffer.getvalue()
