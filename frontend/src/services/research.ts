









import type {
  ConfidenceLevel,
  ResearchResponse,
  ValidationStatus,
} from "../types/research";

export interface ExtractedRiskInfo {
  hasRiskData: boolean;
  overallScore: number | null;
  riskLevel: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" | "NORMAL";
  redFlags: Array<{
    title: string;
    severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW";
    description: string;
    source?: string;
  }>;
  observations: string[];
}

export interface MetricDataPoint {
  label: string;
  value: number;
  formattedValue: string;
  metricName: string;
  unit?: string;
}

export interface MetricSeries {
  metricName: string;
  dataPoints: MetricDataPoint[];
}





export function extractFinancialMetricsFromResponse(
  response?: ResearchResponse | null,
): MetricSeries[] {
  if (!response || !response.claims || response.claims.length === 0) {
    return [];
  }

  const seriesMap = new Map<string, MetricDataPoint[]>();

  
  for (const claim of response.claims) {
    if (
      claim.claim_type === "METRIC" ||
      claim.claim_type === "TREND" ||
      claim.claim_type === "COMPARISON"
    ) {
      const text = claim.claim_text;

      
      const periodMatch = text.match(/(?:FY\s*|\b)(20\d{2}|Q[1-4]\s*20\d{2}|Q[1-4])\b/i);
      
      const numberMatch = text.match(/\$?\s*([\d,]+(?:\.\d+)?)\s*(billion|million|B|M|k|%|percent)?/i);

      if (periodMatch && numberMatch) {
        const period = periodMatch[0].trim();
        const rawNumStr = numberMatch[1].replace(/,/g, "");
        let numVal = parseFloat(rawNumStr);
        const multiplier = (numberMatch[2] || "").toLowerCase();

        if (multiplier === "billion" || multiplier === "b") {
          numVal = numVal * 1000; 
        } else if (multiplier === "k") {
          numVal = numVal / 1000;
        }

        
        let category = "Financial Metric";
        const lowerText = text.toLowerCase();
        if (lowerText.includes("revenue") || lowerText.includes("sales") || lowerText.includes("turnover")) {
          category = "Revenue ($M)";
        } else if (lowerText.includes("ebitda")) {
          category = "EBITDA ($M)";
        } else if (lowerText.includes("net income") || lowerText.includes("profit")) {
          category = "Net Income ($M)";
        } else if (lowerText.includes("margin")) {
          category = "Margin (%)";
        } else if (lowerText.includes("debt") || lowerText.includes("leverage")) {
          category = "Debt ($M)";
        } else if (lowerText.includes("cash flow") || lowerText.includes("fcf")) {
          category = "Free Cash Flow ($M)";
        }

        if (!seriesMap.has(category)) {
          seriesMap.set(category, []);
        }

        const list = seriesMap.get(category)!;
        
        if (!list.some((dp) => dp.label === period)) {
          list.push({
            label: period,
            value: numVal,
            formattedValue: numberMatch[0].trim(),
            metricName: category,
          });
        }
      }
    }
  }

  const result: MetricSeries[] = [];
  seriesMap.forEach((dataPoints, metricName) => {
    if (dataPoints.length >= 2) {
      
      dataPoints.sort((a, b) => a.label.localeCompare(b.label, undefined, { numeric: true }));
      result.push({ metricName, dataPoints });
    }
  });

  return result;
}




export function extractRiskInfo(
  response?: ResearchResponse | null,
): ExtractedRiskInfo {
  if (!response) {
    return {
      hasRiskData: false,
      overallScore: null,
      riskLevel: "NORMAL",
      redFlags: [],
      observations: [],
    };
  }

  const redFlags: ExtractedRiskInfo["redFlags"] = [];
  const observations: string[] = [];

  
  if (response.claims) {
    for (const claim of response.claims) {
      if (claim.claim_type === "RISK") {
        let severity: "CRITICAL" | "HIGH" | "MEDIUM" | "LOW" = "MEDIUM";
        const lower = claim.claim_text.toLowerCase();
        if (lower.includes("critical") || lower.includes("default") || lower.includes("insolven") || lower.includes("fraud")) {
          severity = "CRITICAL";
        } else if (lower.includes("high") || lower.includes("severe") || lower.includes("breach") || lower.includes("violation")) {
          severity = "HIGH";
        } else if (lower.includes("low") || lower.includes("minor")) {
          severity = "LOW";
        }

        const sourceRef = claim.evidence_refs?.[0]?.document_filename
          ? `${claim.evidence_refs[0].document_filename}${claim.evidence_refs[0].page_number ? ` (p. ${claim.evidence_refs[0].page_number})` : ""}`
          : undefined;

        redFlags.push({
          title: `Risk Observation (${claim.claim_id})`,
          severity,
          description: claim.claim_text,
          source: sourceRef,
        });
      }
    }
  }

  
  if (response.evidence_conflicts && response.evidence_conflicts.length > 0) {
    for (const conflict of response.evidence_conflicts) {
      redFlags.push({
        title: `Evidence Conflict: ${conflict.metric_or_topic}`,
        severity: "HIGH",
        description: `${conflict.description} Conflicting values: ${conflict.competing_values.join(" vs ")}.`,
      });
    }
  }

  
  if (response.limitations && response.limitations.length > 0) {
    observations.push(...response.limitations);
  }

  const hasRiskData = redFlags.length > 0 || observations.length > 0;

  
  let overallScore: number | null = null;
  let riskLevel: ExtractedRiskInfo["riskLevel"] = "NORMAL";

  if (hasRiskData) {
    const criticalCount = redFlags.filter((f) => f.severity === "CRITICAL").length;
    const highCount = redFlags.filter((f) => f.severity === "HIGH").length;
    const mediumCount = redFlags.filter((f) => f.severity === "MEDIUM").length;

    const calculatedRisk = Math.min(
      100,
      criticalCount * 35 + highCount * 20 + mediumCount * 10 + (response.evidence_conflicts?.length || 0) * 15,
    );

    overallScore = Math.max(10, calculatedRisk);

    if (overallScore >= 75 || criticalCount > 0) {
      riskLevel = "CRITICAL";
    } else if (overallScore >= 50 || highCount > 0) {
      riskLevel = "HIGH";
    } else if (overallScore >= 25 || mediumCount > 0) {
      riskLevel = "MEDIUM";
    } else {
      riskLevel = "LOW";
    }
  }

  return {
    hasRiskData,
    overallScore,
    riskLevel,
    redFlags,
    observations,
  };
}




export function getConfidenceBadgeProps(level: ConfidenceLevel | string | null | undefined): {
  label: string;
  color: string;
  bg: string;
  borderColor: string;
} {
  switch (level?.toUpperCase()) {
    case "HIGH":
      return {
        label: "High Confidence",
        color: "var(--color-emerald-500)",
        bg: "rgba(16, 185, 129, 0.12)",
        borderColor: "rgba(16, 185, 129, 0.3)",
      };
    case "MEDIUM":
      return {
        label: "Medium Confidence",
        color: "var(--color-amber-500)",
        bg: "rgba(245, 158, 11, 0.12)",
        borderColor: "rgba(245, 158, 11, 0.3)",
      };
    case "LOW":
    default:
      return {
        label: "Low Confidence",
        color: "var(--color-risk-500)",
        bg: "rgba(239, 68, 68, 0.12)",
        borderColor: "rgba(239, 68, 68, 0.3)",
      };
  }
}




export function getValidationStatusBadgeProps(status: ValidationStatus | string | null | undefined): {
  label: string;
  color: string;
  bg: string;
} {
  switch (status?.toUpperCase()) {
    case "VALID":
      return {
        label: "Validated Grounding",
        color: "var(--color-emerald-500)",
        bg: "rgba(16, 185, 129, 0.15)",
      };
    case "MODIFIED":
      return {
        label: "Sanitized & Verified",
        color: "var(--color-amber-500)",
        bg: "rgba(245, 158, 11, 0.15)",
      };
    case "REFUSED":
      return {
        label: "Evidence Insufficient",
        color: "var(--color-risk-500)",
        bg: "rgba(239, 68, 68, 0.15)",
      };
    case "INVALID":
    default:
      return {
        label: "Validation Alert",
        color: "var(--color-risk-500)",
        bg: "rgba(239, 68, 68, 0.15)",
      };
  }
}
