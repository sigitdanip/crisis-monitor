import type { Tier } from "@/types";
import { TIER_COLORS } from "@/lib/colors";

const TIER_LABELS: Record<Tier, string> = {
  live: "LIVE",
  mixed: "MIXED",
  qualitative: "QUALITATIVE",
};

export function TierBadge({ tier }: { tier?: Tier | string | null }) {
  const t = (tier || "live") as Tier;
  const c = TIER_COLORS[t] ?? TIER_COLORS.live;
  const label = TIER_LABELS[t] ?? t.toUpperCase();

  return (
    <span
      className={`inline-flex items-center gap-1 px-1.5 py-0.5 text-[10px] font-mono rounded border ${c.bg} ${c.text} ${c.border}`}
    >
      <span className={`w-1 h-1 rounded-full ${c.dot}`} />
      {label}
    </span>
  );
}
