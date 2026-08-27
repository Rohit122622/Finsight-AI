






import { useState } from "react";
import type { ResearchResponse } from "../../types/research";
import { extractFinancialMetricsFromResponse } from "../../services/research";

interface FinancialChartsProps {
  response?: ResearchResponse | null;
}

export function FinancialCharts({ response }: FinancialChartsProps) {
  const seriesList = extractFinancialMetricsFromResponse(response);
  const [selectedSeriesIdx, setSelectedSeriesIdx] = useState(0);

  if (seriesList.length === 0) {
    return null;
  }

  const activeSeries = seriesList[selectedSeriesIdx] || seriesList[0];
  const dataPoints = activeSeries.dataPoints;

  
  const chartWidth = 320;
  const chartHeight = 160;
  const padding = { top: 20, right: 20, bottom: 30, left: 45 };
  const innerWidth = chartWidth - padding.left - padding.right;
  const innerHeight = chartHeight - padding.top - padding.bottom;

  const maxVal = Math.max(...dataPoints.map((d) => d.value), 1);

  return (
    <div
      style={{
        backgroundColor: "var(--color-bg-surface)",
        border: "1px solid var(--color-border-subtle)",
        borderRadius: "0.5rem",
        padding: "1rem",
        display: "flex",
        flexDirection: "column",
        gap: "0.75rem",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <span style={{ fontSize: "0.6875rem", fontWeight: 600, color: "var(--color-text-secondary)", textTransform: "uppercase", letterSpacing: "0.05em" }}>
          Verified Financial Trends
        </span>
        <span style={{ fontSize: "0.625rem", color: "var(--color-emerald-500)", fontWeight: 600 }}>
          Structured Data ({dataPoints.length} points)
        </span>
      </div>

      {}
      {seriesList.length > 1 && (
        <div style={{ display: "flex", gap: "0.375rem", flexWrap: "wrap" }}>
          {seriesList.map((s, idx) => (
            <button
              key={s.metricName}
              onClick={() => setSelectedSeriesIdx(idx)}
              style={{
                fontSize: "0.6875rem",
                padding: "0.2rem 0.5rem",
                borderRadius: "4px",
                border: "none",
                cursor: "pointer",
                backgroundColor:
                  idx === selectedSeriesIdx
                    ? "var(--color-emerald-600)"
                    : "var(--color-bg-surface-alt)",
                color: idx === selectedSeriesIdx ? "#ffffff" : "var(--color-text-secondary)",
                transition: "all 0.15s ease",
              }}
            >
              {s.metricName}
            </button>
          ))}
        </div>
      )}

      {}
      <h4 style={{ fontSize: "0.8125rem", fontWeight: 600, color: "var(--color-text-primary)" }}>
        {activeSeries.metricName}
      </h4>

      {}
      <div style={{ width: "100%", overflowX: "auto" }}>
        <svg
          viewBox={`0 0 ${chartWidth} ${chartHeight}`}
          style={{ width: "100%", height: "auto", display: "block" }}
        >
          {}
          <line
            x1={padding.left}
            y1={padding.top}
            x2={chartWidth - padding.right}
            y2={padding.top}
            stroke="var(--color-border-subtle)"
            strokeDasharray="2,2"
          />
          <line
            x1={padding.left}
            y1={padding.top + innerHeight / 2}
            x2={chartWidth - padding.right}
            y2={padding.top + innerHeight / 2}
            stroke="var(--color-border-subtle)"
            strokeDasharray="2,2"
          />
          <line
            x1={padding.left}
            y1={chartHeight - padding.bottom}
            x2={chartWidth - padding.right}
            y2={chartHeight - padding.bottom}
            stroke="var(--color-border-subtle)"
          />

          {}
          <text
            x={padding.left - 6}
            y={padding.top + 4}
            fill="var(--color-text-secondary)"
            fontSize="8"
            textAnchor="end"
            className="font-tabular"
          >
            {maxVal.toFixed(0)}
          </text>
          <text
            x={padding.left - 6}
            y={chartHeight - padding.bottom}
            fill="var(--color-text-secondary)"
            fontSize="8"
            textAnchor="end"
            className="font-tabular"
          >
            0
          </text>

          {}
          {dataPoints.map((dp, i) => {
            const barWidth = Math.min(36, (innerWidth / dataPoints.length) * 0.6);
            const slotWidth = innerWidth / dataPoints.length;
            const x = padding.left + i * slotWidth + (slotWidth - barWidth) / 2;
            const barHeight = Math.max(4, (dp.value / maxVal) * innerHeight);
            const y = chartHeight - padding.bottom - barHeight;

            return (
              <g key={dp.label}>
                {}
                <rect
                  x={x}
                  y={y}
                  width={barWidth}
                  height={barHeight}
                  rx="3"
                  fill="var(--color-emerald-500)"
                  opacity="0.85"
                />

                {}
                <text
                  x={x + barWidth / 2}
                  y={y - 4}
                  fill="var(--color-text-primary)"
                  fontSize="8"
                  fontWeight="600"
                  textAnchor="middle"
                  className="font-tabular"
                >
                  {dp.formattedValue}
                </text>

                {}
                <text
                  x={x + barWidth / 2}
                  y={chartHeight - padding.bottom + 14}
                  fill="var(--color-text-secondary)"
                  fontSize="8"
                  textAnchor="middle"
                >
                  {dp.label}
                </text>
              </g>
            );
          })}
        </svg>
      </div>

      {}
      <div style={{ marginTop: "0.25rem" }}>
        <table style={{ width: "100%", fontSize: "0.6875rem", borderCollapse: "collapse" }}>
          <thead>
            <tr style={{ borderBottom: "1px solid var(--color-border-subtle)" }}>
              <th style={{ textAlign: "left", padding: "0.25rem 0", color: "var(--color-text-secondary)" }}>Period</th>
              <th style={{ textAlign: "right", padding: "0.25rem 0", color: "var(--color-text-secondary)" }}>Verified Value</th>
            </tr>
          </thead>
          <tbody>
            {dataPoints.map((dp) => (
              <tr key={dp.label} style={{ borderBottom: "1px solid rgba(255,255,255,0.03)" }}>
                <td style={{ padding: "0.25rem 0", color: "var(--color-text-primary)" }}>{dp.label}</td>
                <td className="font-tabular" style={{ textAlign: "right", padding: "0.25rem 0", color: "var(--color-emerald-500)", fontWeight: 600 }}>
                  {dp.formattedValue}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
