import type { DotStatus } from "@/types";
import { STATUS_COLORS } from "@/lib/colors";

export function StatusBadge({ status }: { status: DotStatus }) {
  const c = STATUS_COLORS[status];
  return (
    <span className={`inline-flex items-center gap-1.5 px-2 py-0.5 text-xs font-mono rounded ${c.bg} ${c.text} border ${c.border}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot} ${status === "critical" ? "animate-ping" : ""}`} />
      {status}
    </span>
  );
}
