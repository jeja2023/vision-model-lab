type StatusBadgeTone = "ok" | "warn" | "neutral" | "fail";

type StatusBadgeProps = {
  ok?: boolean;
  tone?: StatusBadgeTone;
  label?: string;
};

export function StatusBadge({ ok, tone, label }: StatusBadgeProps) {
  const resolvedTone = tone ?? (ok ? "ok" : "fail");
  const text = label ?? (resolvedTone === "ok" ? "通过" : resolvedTone === "warn" ? "进行中" : resolvedTone === "neutral" ? "已取消" : "失败");
  return <span className={`badge ${resolvedTone}`}>{text}</span>;
}
