// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from "vitest";
import React from "react";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import SessionDetail from "../pages/SessionDetail";
import * as sessionStore from "../store/sessionStore";
import * as sessionsApi from "../api/sessions";
import * as documentsApi from "../api/documents";
import * as analysisApi from "../api/analysis";
import * as researchApi from "../api/research";
import * as extractionApi from "../api/extraction";
import * as comparisonApi from "../api/comparison";

vi.mock("../store/sessionStore");
vi.mock("../api/sessions");
vi.mock("../api/documents");
vi.mock("../api/analysis");
vi.mock("../api/research");
vi.mock("../api/extraction");
vi.mock("../api/comparison");
vi.mock("../hooks/useWebSocket", () => ({
  useSessionWebSocket: () => ({
    isConnected: true,
    latestJobProgress: null,
    agentEvents: [],
  }),
}));

// Mock child view components to test tab routing and mounting cleanly
vi.mock("../components/DocumentUploadZone", () => ({
  DocumentUploadZone: () => <div data-testid="document-upload-zone">DocumentUploadZoneMock</div>,
}));
vi.mock("../components/DocumentList", () => ({
  DocumentList: () => <div data-testid="document-list">DocumentListMock</div>,
}));
vi.mock("../components/LiveAgentDashboard", () => ({
  LiveAgentDashboard: () => <div data-testid="live-agent-dashboard">LiveAgentDashboardMock</div>,
}));
vi.mock("../components/AnalysisReportViewer", () => ({
  AnalysisReportViewer: () => <div data-testid="analysis-report-viewer">AnalysisReportViewerMock</div>,
}));
vi.mock("../components/chat/ResearchChat", () => ({
  ResearchChat: () => <div data-testid="research-chat">ResearchChatMock (with Red Flag)</div>,
}));
vi.mock("../components/comparison/CompanyComparisonViewer", () => ({
  CompanyComparisonViewer: () => <div data-testid="company-comparison-viewer">CompanyComparisonViewerMock</div>,
}));
vi.mock("../components/extraction/ExtractionViewer", () => ({
  ExtractionViewer: () => <div data-testid="extraction-viewer">ExtractionViewerMock</div>,
}));
vi.mock("../components/agents/AgentPipelineView", () => ({
  AgentPipelineView: () => <div data-testid="agent-pipeline-view">AgentPipelineViewMock</div>,
}));
vi.mock("../components/redflag/RedFlagViewer", () => ({
  RedFlagViewer: () => <div data-testid="red-flag-viewer">RedFlagViewerMock</div>,
}));
vi.mock("../components/report/PerCompanyReports", () => ({
  PerCompanyReports: () => <div data-testid="per-company-reports">PerCompanyReportsMock</div>,
}));

describe("Phase 5F: Session Navigation, Tabs & Views", () => {
  const mockSession = {
    session_id: "sess_test_123",
    name: "Test Financial Workspace",
    description: "Forensic financial intelligence",
    created_at: new Date().toISOString(),
    documents: [],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(sessionStore.useSessionStore).mockReturnValue({
      activeSession: mockSession,
      fetchSession: vi.fn().mockResolvedValue({}),
      isLoading: false,
    } as any);

    vi.mocked(sessionsApi.getSessionApi).mockResolvedValue(mockSession as any);

    vi.mocked(documentsApi.listDocumentsApi).mockResolvedValue({
      documents: [
        {
          document_id: "doc_1",
          filename: "apple_10k.pdf",
          company_name: "Apple Inc.",
          status: "completed",
          created_at: new Date().toISOString(),
        } as any,
      ],
    });

    vi.mocked(analysisApi.listReportsApi).mockResolvedValue({ reports: [] });
    vi.mocked(researchApi.getSessionResearchHistoryApi).mockResolvedValue({ messages: [] });
    vi.mocked(extractionApi.getExtractedMetricsApi).mockResolvedValue({
      session_id: "sess_test_123",
      status: "completed",
      documents: [],
    });
    vi.mocked(comparisonApi.getComparisonResultApi).mockResolvedValue({
      status: "completed",
      comparison: {
        session_id: "sess_test_123",
        companies: [],
        fiscal_periods: [],
        metrics: [],
      },
    });
  });

  const renderComponent = () => {
    return render(
      <MemoryRouter initialEntries={["/sessions/sess_test_123"]}>
        <Routes>
          <Route path="/sessions/:sessionId" element={<SessionDetail />} />
        </Routes>
      </MemoryRouter>
    );
  };

  it("renders all core navigation tabs incl. Red Flag: Document | Extraction | Comparison | Red Flag | Research | Report", async () => {
    renderComponent();

    await waitFor(() => {
      expect(screen.getByText("Test Financial Workspace")).toBeDefined();
    });

    const docTab = screen.getByRole("button", { name: /document/i });
    const extractTab = screen.getByRole("button", { name: /extraction/i });
    const compareTab = screen.getByRole("button", { name: /comparison/i });
    const redFlagTab = screen.getByRole("button", { name: /red flag/i });
    const researchTab = screen.getByRole("button", { name: /research/i });
    const reportTab = screen.getByRole("button", { name: /^report$/i });

    expect(docTab).toBeDefined();
    expect(extractTab).toBeDefined();
    expect(compareTab).toBeDefined();
    expect(redFlagTab).toBeDefined();
    expect(researchTab).toBeDefined();
    expect(reportTab).toBeDefined();
  });

  it("switches to Red Flag tab and mounts the per-document Red Flag viewer", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const redFlagTab = screen.getByRole("button", { name: /red flag/i });
    fireEvent.click(redFlagTab);

    await waitFor(() => {
      expect(screen.getByTestId("red-flag-viewer")).toBeDefined();
    });
  });

  it("shows the Live Multi-Agent dashboard on the Overview tab (not the Report page)", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const overviewTab = screen.getByRole("button", { name: /overview/i });
    fireEvent.click(overviewTab);

    await waitFor(() => {
      expect(screen.getByTestId("live-agent-dashboard")).toBeDefined();
    });
  });

  it("switches to Document tab and mounts document upload & list components", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const docTab = screen.getByRole("button", { name: /document/i });
    fireEvent.click(docTab);

    await waitFor(() => {
      expect(screen.getByTestId("document-list")).toBeDefined();
      expect(screen.getByTestId("document-upload-zone")).toBeDefined();
    });
  });

  it("switches to Extraction tab and mounts financial extraction viewer", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const extractTab = screen.getByRole("button", { name: /extraction/i });
    fireEvent.click(extractTab);

    await waitFor(() => {
      expect(screen.getByTestId("extraction-viewer")).toBeDefined();
    });
  });

  it("switches to Comparison tab and mounts company comparison viewer", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const compareTab = screen.getByRole("button", { name: /comparison/i });
    fireEvent.click(compareTab);

    await waitFor(() => {
      expect(screen.getByTestId("company-comparison-viewer")).toBeDefined();
    });
  });

  it("switches to Research tab and mounts chat with Red Flag risk component integration", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const researchTab = screen.getByRole("button", { name: /research/i });
    fireEvent.click(researchTab);

    await waitFor(() => {
      expect(screen.getByTestId("research-chat")).toBeDefined();
    });
  });

  it("switches to Report tab and mounts per-company reports and the combined reports viewer", async () => {
    renderComponent();
    await waitFor(() => expect(screen.getByText("Test Financial Workspace")).toBeDefined());

    const reportTab = screen.getByRole("button", { name: /^report$/i });
    fireEvent.click(reportTab);

    await waitFor(() => {
      expect(screen.getByTestId("per-company-reports")).toBeDefined();
      expect(screen.getByTestId("analysis-report-viewer")).toBeDefined();
    });
  });
});
