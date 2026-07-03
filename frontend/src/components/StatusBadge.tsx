type StatusBadgeProps = {
  ok?: boolean;
  label?: string;
};

export function StatusBadge({ ok, label }: StatusBadgeProps) {
  const text = label ?? (ok ? "通过" : "失败");
  return <span className={ok ? "badge ok" : "badge fail"}>{text}</span>;
}

