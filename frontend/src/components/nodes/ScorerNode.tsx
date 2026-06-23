"use client";
import { Handle, Position } from "@xyflow/react";

interface ScorerNodeData {
  composite: number;
  label: string;
  status: "success" | "error" | "running";
}

export function ScorerNode({ data }: { data: ScorerNodeData }) {
  const scoreColor = data.composite <= 6 ? "#10b981" : data.composite <= 12 ? "#f59e0b" : data.composite <= 20 ? "#f97316" : data.composite <= 25 ? "#ef4444" : "#e11d48";
  return (
    <div
      className="px-5 py-3 flex flex-col items-center justify-center font-mono text-xs bg-zinc-800 border border-zinc-400"
      style={{ clipPath: "polygon(50% 0%, 100% 50%, 50% 100%, 0% 50%)", width: 90, height: 84 }}
    >
      <Handle type="target" position={Position.Top} className="!bg-zinc-400" style={{ top: 0 }} />
      <span className="text-xl font-bold" style={{ color: scoreColor }}>{data.composite}</span>
      <span className="text-xs text-zinc-300 mt-0.5">{data.label}</span>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-400" style={{ bottom: 0 }} />
    </div>
  );
}
