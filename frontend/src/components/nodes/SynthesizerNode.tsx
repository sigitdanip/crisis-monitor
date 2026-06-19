"use client";
import { Handle, Position } from "@xyflow/react";

interface SynthesizerNodeData {
  label: string;
  status: "success" | "error" | "running";
  pathways: string;
  duration: string;
}

export function SynthesizerNode({ data }: { data: SynthesizerNodeData }) {
  const statusColor = data.status === "success" ? "#10b981" : data.status === "running" ? "#f59e0b" : "#ef4444";
  return (
    <div className="px-5 py-3 rounded-full border border-zinc-600 bg-zinc-800 min-w-[180px] font-mono">
      <Handle type="target" position={Position.Top} className="!bg-zinc-600" />
      <div className="flex items-center gap-2 mb-1">
        <span className="w-2 h-2 rounded-full" style={{ backgroundColor: statusColor }} />
        <span className="text-xs text-zinc-300">{data.label}</span>
      </div>
      <div className="flex items-center justify-between text-[9px] text-zinc-400">
        <span>{data.pathways}</span>
        <span>{data.duration}</span>
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-zinc-600" />
    </div>
  );
}
