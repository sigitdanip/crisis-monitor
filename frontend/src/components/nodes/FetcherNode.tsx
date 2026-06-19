"use client";
import { Handle, Position } from "@xyflow/react";

interface FetcherNodeData {
  label: string;
  status: "success" | "error" | "running";
  count: string;
  duration: string;
  tooltip?: string;
  minWidth?: number;
}

export function FetcherNode({ data }: { data: FetcherNodeData }) {
  const statusColor = data.status === "success" ? "#10b981" : data.status === "running" ? "#f59e0b" : "#ef4444";
  const minW = data.minWidth ?? 140;
  return (
    <div
      className="px-4 py-3 rounded-md border border-zinc-400 bg-zinc-800 font-mono text-xs"
      style={{ minWidth: minW }}
      title={data.tooltip || data.count}
    >
      <Handle type="target" position={Position.Top} className="!bg-zinc-400" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
        <span className="text-zinc-400">{data.label}</span>
      </div>
      <div className="flex items-center justify-between text-zinc-400 text-xs">
        <span>{data.count}</span>
        <span>{data.duration}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-400" />
    </div>
  );
}
