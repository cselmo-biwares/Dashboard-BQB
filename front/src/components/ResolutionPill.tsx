import type { Resolution } from "../types";

const LABELS: Record<Resolution, string> = {
  resolved: "Resuelto",
  partial: "Parcial",
  unresolved: "No resuelto",
  unknown: "Desconocido",
};

export function ResolutionPill({ resolution }: { resolution: Resolution }) {
  return <span className={`pill ${resolution}`}>{LABELS[resolution]}</span>;
}
