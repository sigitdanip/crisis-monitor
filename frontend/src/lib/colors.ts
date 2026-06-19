import type { DotStatus } from "@/types";

export const STATUS_COLORS: Record<DotStatus, { bg: string; text: string; border: string; dot: string }> = {
  dormant:   { bg: "bg-zinc-900", text: "text-zinc-400", border: "border-zinc-700", dot: "bg-zinc-500" },
  activating: { bg: "bg-amber-950", text: "text-amber-400", border: "border-amber-600", dot: "bg-amber-400" },
  active:    { bg: "bg-orange-950", text: "text-orange-400", border: "border-orange-600", dot: "bg-orange-400" },
  critical:  { bg: "bg-red-950", text: "text-red-400", border: "border-red-500", dot: "bg-red-500" },
};

export const STATUS_ORDER: Record<DotStatus, number> = {
  critical: 0,
  active: 1,
  activating: 2,
  dormant: 3,
};

export const END_STATE_COLORS: Record<string, string> = {
  containment: "bg-emerald-600",
  fragmented: "bg-amber-500",
  collapse: "bg-red-600",
  unknown: "bg-zinc-600",
};

export const COMPOSITE_ZONES = [
  { max: 4, label: "Monitor", color: "text-emerald-400", bg: "bg-emerald-500/20" },
  { max: 8, label: "Elevated", color: "text-amber-400", bg: "bg-amber-500/20" },
  { max: 12, label: "High", color: "text-orange-400", bg: "bg-orange-500/20" },
  { max: 16, label: "Crisis", color: "text-red-400", bg: "bg-red-500/20" },
];

export function compositeColor(score: number) {
  if (score <= 4) return { stroke: "#10b981", text: "text-emerald-400", label: "Monitor" };
  if (score <= 8) return { stroke: "#f59e0b", text: "text-amber-400", label: "Elevated" };
  if (score <= 12) return { stroke: "#f97316", text: "text-orange-400", label: "High" };
  return { stroke: "#ef4444", text: "text-red-400", label: "Crisis" };
}

export const CATEGORY_NAMES: Record<string, string> = {
  geopolitical: "Geopolitical",
  energy: "Energy",
  food: "Food & Fertilizer",
  financial: "Financial",
  debt: "Debt & Sovereign",
  china: "China",
  political: "Political & Social",
  "em_currency": "EM Currency & Banking",
  supply_chain: "Supply Chain & Shipping",
  health: "Health",
};

/** Pathway color scheme — matched to pathway names in the synthesizer prompt.
 *  Active pathway gets its brand color; inactive gets zinc-700 muted. */
export const PATHWAY_COLORS: Record<string, { active: string; inactive: string; label: string }> = {
  pathway_a: { active: "bg-amber-500", inactive: "bg-zinc-700", label: "Monetary Cascade" },
  pathway_b: { active: "bg-orange-500", inactive: "bg-zinc-700", label: "Energy Price Shock" },
  pathway_c: { active: "bg-red-500", inactive: "bg-zinc-700", label: "Geopolitical Fracture" },
  pathway_d: { active: "bg-purple-500", inactive: "bg-zinc-700", label: "Systemic Collapse" },
};
