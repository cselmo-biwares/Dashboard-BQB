import type { VolumeTrendPoint } from "./types";

export type Interval = "day" | "week" | "month";

/** Turn a `<input type="date">` value ("YYYY-MM-DD") into an inclusive ISO range bound. */
export function dateInputToFrom(value: string): string | undefined {
  return value ? `${value}T00:00:00` : undefined;
}

export function dateInputToTo(value: string): string | undefined {
  return value ? `${value}T23:59:59.999` : undefined;
}

/** [from, to] ISO bounds covering exactly the bucket this point represents. */
export function periodBounds(point: VolumeTrendPoint, interval: Interval): { from: string; to: string } {
  const start = new Date(point.period_start);
  const end = new Date(start);
  if (interval === "day") end.setDate(end.getDate() + 1);
  else if (interval === "week") end.setDate(end.getDate() + 7);
  else end.setMonth(end.getMonth() + 1);
  const inclusiveEnd = new Date(end.getTime() - 1);
  return { from: start.toISOString(), to: inclusiveEnd.toISOString() };
}

/** Bounds for the immediately preceding period of the same length — for delta comparisons. */
export function previousPeriodBounds(point: VolumeTrendPoint, interval: Interval): { from: string; to: string } {
  const { from, to } = periodBounds(point, interval);
  const durationMs = new Date(to).getTime() - new Date(from).getTime();
  const prevEnd = new Date(new Date(from).getTime() - 1);
  const prevStart = new Date(prevEnd.getTime() - durationMs);
  return { from: prevStart.toISOString(), to: prevEnd.toISOString() };
}

export function formatPeriodLabel(point: VolumeTrendPoint, interval: Interval): string {
  const start = new Date(point.period_start);
  if (interval === "day") {
    return start.toLocaleDateString("es-AR", { day: "2-digit", month: "long", year: "numeric" });
  }
  if (interval === "month") {
    return start.toLocaleDateString("es-AR", { month: "long", year: "numeric" });
  }
  const { to } = periodBounds(point, interval);
  const end = new Date(to);
  return `Semana del ${start.toLocaleDateString("es-AR", { day: "2-digit", month: "short" })} al ${end.toLocaleDateString("es-AR", { day: "2-digit", month: "short" })}`;
}
