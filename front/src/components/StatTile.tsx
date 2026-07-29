export function StatTile({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: "good" | "critical";
}) {
  return (
    <div className="stat-tile">
      <div className="label">{label}</div>
      <div className={`value${tone ? ` ${tone}` : ""}`}>{value}</div>
    </div>
  );
}
