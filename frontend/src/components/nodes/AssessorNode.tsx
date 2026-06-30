"use client";
import { Handle, Position } from "@xyflow/react";

interface AssessorNodeData {
  label: string;
  status: "success" | "error" | "running";
  endState: string;
  duration: string;
}

export function AssessorNode({ data }: { data: AssessorNodeData }) {
  const statusColor = data.status === "success" ? "#10b981" : data.status === "running" ? "#f59e0b" : "#ef4444";
  const endColor =
    data.endState === "containment" ? "#10b981" :
    (data.endState === "fragmented" || data.endState === "fragmented_stability") ? "#f59e0b" :
    (data.endState === "indeterminate" || data.endState === "unknown") ? "#71717a" : "#ef4444";
  return (
    <div className="px-5 py-3 rounded-full border-2 border-zinc-400 bg-zinc-800 min-w-[200px] font-mono">
      <Handle type="target" position={Position.Top} className="!bg-zinc-400" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
        <span className="text-xs text-zinc-300">{data.label}</span>
      </div>
      <div className="flex items-center justify-between text-xs">
        <span style={{ color: endColor }} className="font-bold uppercase">{data.endState?.replace(/_/g, " ") || "pending"}</span>
        <span className="text-zinc-400">{data.duration}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-400" />
    </div>
  );
}
