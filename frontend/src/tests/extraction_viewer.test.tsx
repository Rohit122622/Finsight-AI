// @vitest-environment jsdom
import { describe, it, expect, vi } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { ExtractionViewer } from "../components/extraction/ExtractionViewer";
import * as extractionApi from "../api/extraction";

vi.mock("../api/extraction");

describe("Phase 5F: ExtractionViewer", () => {
  const mockExtractionData: extractionApi.ExtractionResponse = {
    session_id: "sess_123",
    status: "completed",
    documents: [
      {
        document_id: "doc_apple",
        filename: "Apple_10K_FY2025.pdf",
        company_name: "Apple Inc.",
        fiscal_year: "FY2025",
        metrics_count: 3,
        metrics: [
          {
            metric_name: "revenue",
            value: 391035.0,
            unit: "USD Millions",
            period: "FY2025",
            prior_period: "FY2024",
            prior_value: 383285.0,
            confidence: 0.98,
            source_citation: "Consolidated Statements of Operations, Item 8",
            evidence_snippet: "Total net sales 391,035 383,285",
            raw_text: "Total net sales 391,035",
            source_page: 28,
            notes: "Grounded in table",
          },
          {
            metric_name: "net_income",
            value: 93736.0,
            unit: "USD Millions",
            period: "FY2025",
            confidence: 0.96,
            evidence_snippet: "Net income 93,736",
          },
          {
            metric_name: "eps",
            value: 7.46,
            unit: "USD",
            period: "FY2025",
            confidence: 0.99,
            evidence_snippet: "Diluted earnings per share 7.46",
          }
        ],
        multi_year_data: {
          "FY2025": { revenue: 391035.0, net_income: 93736.0, eps: 7.46 },
          "FY2024": { revenue: 383285.0, net_income: 96995.0, eps: 6.08 }
        },
        extraction_metadata: {
          execution_time_ms: 450,
          model_used: "gpt-4o-mini",
        }
      }
    ]
  };

  it("renders loading state initially", async () => {
    vi.mocked(extractionApi.getExtractedMetricsApi).mockReturnValue(new Promise(() => {}));
    const { container } = render(<ExtractionViewer sessionId="sess_123" documents={[]} />);
    expect(container.querySelector(".animate-spin")).toBeDefined();
  });

  it("renders extracted company metrics and EPS correctly", async () => {
    vi.mocked(extractionApi.getExtractedMetricsApi).mockResolvedValue(mockExtractionData);
    render(<ExtractionViewer sessionId="sess_123" documents={[]} />);

    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeDefined();
    });

    expect(screen.getByText(/Revenue \/ Net Sales/i)).toBeDefined();
    expect(screen.getByText(/Net Income/i)).toBeDefined();
    expect(screen.getByText(/Diluted EPS/i)).toBeDefined();
    const epsElements = screen.getAllByText("7.46");
    expect(epsElements.length).toBeGreaterThanOrEqual(1);
  });

  it("handles error state gracefully without crash", async () => {
    vi.mocked(extractionApi.getExtractedMetricsApi).mockRejectedValue(new Error("Network Error occurred"));
    render(<ExtractionViewer sessionId="sess_123" documents={[]} />);

    await waitFor(() => {
      expect(screen.getByText(/network error occurred/i)).toBeDefined();
    });
    expect(screen.getByText(/refresh data/i)).toBeDefined();
  });

  it("triggers re-extraction when Re-Extract Current button is clicked", async () => {
    vi.mocked(extractionApi.getExtractedMetricsApi).mockResolvedValue(mockExtractionData);
    vi.mocked(extractionApi.extractMetricsApi).mockResolvedValue(mockExtractionData);

    render(<ExtractionViewer sessionId="sess_123" documents={[]} />);
    await waitFor(() => {
      expect(screen.getByText("Apple Inc.")).toBeDefined();
    });

    const reExtractBtn = screen.getByText(/re-extract current/i);
    fireEvent.click(reExtractBtn);

    await waitFor(() => {
      expect(extractionApi.extractMetricsApi).toHaveBeenCalled();
    });
  });
});
