




import type { ConfidenceLevel } from "../../types/research";
import { getConfidenceBadgeProps } from "../../services/research";

interface ConfidenceBadgeProps {
  level?: ConfidenceLevel | string | null;
  score?: number | null;
  showScore?: boolean;
}

export function ConfidenceBadge({
  level,
  score,
  showScore = true,
}: ConfidenceBadgeProps) {
  if (!level && (score === undefined || score === null)) {
    return null;
  }

  const badgeProps = getConfidenceBadgeProps(level);
  const formattedScore =
    score !== undefined && score !== null
      ? `${Math.round(score <= 1.0 ? score * 100 : score)}%`
      : null;

  return (
    <div
      style={{
        display: "inline-flex",
        alignItems: "center",
        gap: "0.375rem",
        padding: "0.2rem 0.5rem",
        borderRadius: "9999px",
        backgroundColor: badgeProps.bg,
        border: `1px solid ${badgeProps.borderColor}`,
        fontSize: "0.6875rem",
        fontWeight: 600,
        color: badgeProps.color,
      }}
      title={`Confidence level: ${badgeProps.label}${formattedScore ? ` (${formattedScore})` : ""}`}
    >
      <span
        style={{
          width: "6px",
          height: "6px",
          borderRadius: "50%",
          backgroundColor: badgeProps.color,
        }}
      />
      <span>{badgeProps.label}</span>
      {showScore && formattedScore && (
        <span
          className="font-tabular"
          style={{ opacity: 0.9, marginLeft: "2px", fontWeight: 700 }}
        >
          [{formattedScore}]
        </span>
      )}
    </div>
  );
}
