"use client";
import { Handle, Position } from "@xyflow/react";

interface AgentNodeData {
  label: string;
  status: "success" | "error" | "running";
  dots: string;
  duration: string;
  model: string;
}

export function AgentNode({ data }: { data: AgentNodeData }) {
  const statusColor = data.status === "success" ? "#10b981" : data.status === "running" ? "#f59e0b" : "#ef4444";
  return (
    <div className="px-4 py-2.5 rounded-full border border-zinc-400 bg-zinc-800 min-w-[150px] font-mono">
      <Handle type="target" position={Position.Top} className="!bg-zinc-400" />
      <div className="flex items-center gap-2">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
        <span className="text-xs text-zinc-300">{data.label}</span>
      </div>
      <div className="flex items-center justify-between text-xs text-zinc-400 mt-0.5 px-1">
        <span>{data.dots}</span>
        <span>{data.duration} · {data.model}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-400" />
    </div>
  );
}
