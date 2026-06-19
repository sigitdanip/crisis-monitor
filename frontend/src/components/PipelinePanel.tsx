"use client";
import { useState, useEffect, useCallback } from "react";
import {
  ReactFlow,
  Background,
  Controls,
  MiniMap,
  useNodesState,
  useEdgesState,
  type Node,
  type Edge,
} from "@xyflow/react";
import "@xyflow/react/dist/style.css";
import type { PipelineStatus } from "@/types";
import { fetchPipeline } from "@/lib/api";
import { FetcherNode } from "./nodes/FetcherNode";
import { ScorerNode } from "./nodes/ScorerNode";
import { AgentNode } from "./nodes/AgentNode";
import { SynthesizerNode } from "./nodes/SynthesizerNode";
import { AssessorNode } from "./nodes/AssessorNode";

const nodeTypes = {
  fetcher: FetcherNode,
  scorer: ScorerNode,
  agent: AgentNode,
  synthesizer: SynthesizerNode,
  assessor: AssessorNode,
};

// ponytail: static layout — computed once, not recalculated on resize
function buildLayout(status: PipelineStatus): { nodes: Node[]; edges: Edge[] } {
  const live = status.nodes?.length > 0;

  // Column x-positions for L→R flow
  const COL = { fetcher: 80, scorer: 300, agent: 520, synthesizer: 750, assessor: 950 };
  const agentYStart = 40;
  const agentYSpacing = 100;

  // ponytail: edge label derived from source→target type pair
  function edgeLabel(sourceType: string, targetType: string): string | undefined {
    if (sourceType === "fetcher" && targetType === "scorer") return "fetches indicators";
    if (sourceType === "scorer" && targetType === "agent") return "dispatches dots";
    if (sourceType === "agent" && targetType === "synthesizer") return "pathways";
    if (sourceType === "synthesizer" && targetType === "assessor") return "assesses end state";
    return undefined;
  }

  function nodeData(n: any) {
    return {
      label: n.label,
      status: n.status,
      count: n.input_summary ?? "",
      duration: n.duration_ms ? `${n.duration_ms}ms` : "",
      dots: n.input_summary ?? "",
      model: "",
      pathways: "",
      endState: n.output_summary ?? "",
      composite: 0,
    };
  }

  if (live) {
    // ponytail: position nodes by type into columns; same-type nodes stack vertically
    const typeCounters: Record<string, number> = {};
    const nodes = status.nodes.map((n) => {
      const idx = typeCounters[n.type] ?? 0;
      typeCounters[n.type] = idx + 1;
      const y = n.type === "agent"
        ? agentYStart + idx * agentYSpacing
        : 260; // ponytail: non-stacked types centered vertically
      return {
        id: n.id,
        type: n.type,
        position: { x: COL[n.type as keyof typeof COL] ?? 300, y },
        data: nodeData(n),
      };
    });

    // ponytail: build type lookup for edge labels
    const typeMap = new Map(nodes.map((n) => [n.id, n.type as string]));
    const edges = status.edges.map((e, i) => ({
      id: `e-${i}`,
      source: e.source,
      target: e.target,
      animated: true,
      style: { stroke: "#a1a1aa", strokeDasharray: "5 5" },
      label: edgeLabel(typeMap.get(e.source) ?? "", typeMap.get(e.target) ?? ""),
      labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" },
      labelShowBg: true,
      labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 2,
    }));

    return { nodes, edges };
  }

  // Default static layout — 5-column L→R flow
  return {
    nodes: [
      { id: "fetchers", type: "fetcher", position: { x: COL.fetcher, y: 260 }, data: { label: "DATA FETCHERS", status: "success", count: "0/11", duration: "—" } },
      { id: "scorer", type: "scorer", position: { x: COL.scorer, y: 260 }, data: { composite: 0, label: "MONITOR", status: "success" } },
      { id: "agent1", type: "agent", position: { x: COL.agent, y: agentYStart }, data: { label: "GEOPOLITICAL", status: "success", dots: "Dots 1+2", duration: "—", model: "pending" } },
      { id: "agent2", type: "agent", position: { x: COL.agent, y: agentYStart + agentYSpacing }, data: { label: "FOOD & DEBT", status: "success", dots: "Dots 3+5", duration: "—", model: "pending" } },
      { id: "agent3", type: "agent", position: { x: COL.agent, y: agentYStart + agentYSpacing * 2 }, data: { label: "FINANCIAL & EM", status: "success", dots: "Dot 4+EM", duration: "—", model: "pending" } },
      { id: "agent4", type: "agent", position: { x: COL.agent, y: agentYStart + agentYSpacing * 3 }, data: { label: "CHINA & POLITICAL", status: "success", dots: "Dots 6-8", duration: "—", model: "pending" } },
      { id: "agent5", type: "agent", position: { x: COL.agent, y: agentYStart + agentYSpacing * 4 }, data: { label: "HEALTH", status: "success", dots: "Dot 9", duration: "—", model: "pending" } },
      { id: "synthesizer", type: "synthesizer", position: { x: COL.synthesizer, y: 260 }, data: { label: "PATHWAY SYNTH", status: "success", pathways: "pending", duration: "—" } },
      { id: "assessor", type: "assessor", position: { x: COL.assessor, y: 260 }, data: { label: "END STATE", status: "success", endState: "pending", duration: "—" } },
    ],
    edges: [
      { id: "e1", source: "fetchers", target: "scorer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "fetches indicators", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e2", source: "scorer", target: "agent1", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "dispatches dots", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e3", source: "scorer", target: "agent2", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "dispatches dots", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e4", source: "scorer", target: "agent3", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "dispatches dots", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e5", source: "scorer", target: "agent4", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "dispatches dots", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e6", source: "scorer", target: "agent5", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "dispatches dots", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e7", source: "agent1", target: "synthesizer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "pathways", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e8", source: "agent2", target: "synthesizer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "pathways", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e9", source: "agent3", target: "synthesizer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "pathways", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e10", source: "agent4", target: "synthesizer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "pathways", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e11", source: "agent5", target: "synthesizer", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "pathways", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
      { id: "e12", source: "synthesizer", target: "assessor", animated: true, style: { stroke: "#a1a1aa", strokeDasharray: "5 5" }, label: "assesses end state", labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" }, labelShowBg: true, labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 }, labelBgPadding: [4, 2] as [number, number], labelBgBorderRadius: 2 },
    ],
  };
}

export function PipelinePanel() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const layout = buildLayout(status ?? { nodes: [], edges: [], last_run: null, total_duration_ms: 0, success_count: 0 });
  const [nodes, setNodes, onNodesChange] = useNodesState(layout.nodes as any);
  const [edges, setEdges, onEdgesChange] = useEdgesState(layout.edges as any);

  const load = useCallback(async () => {
    try {
      const data = await fetchPipeline();
      setStatus(data);
      const l = buildLayout(data);
      setNodes(l.nodes as any);
      setEdges(l.edges as any);
    } catch (err: any) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [setNodes, setEdges]);

  useEffect(() => { load(); }, [load]);

  // ponytail: auto-refresh every 30s — enough for a daily pipeline
  useEffect(() => {
    const i = setInterval(load, 30000);
    return () => clearInterval(i);
  }, [load]);

  if (loading) {
    return (
      <div className="flex-1 flex items-center justify-center">
        <span className="text-sm font-mono text-zinc-600 animate-pulse">Loading pipeline...</span>
      </div>
    );
  }

  return (
    <div className="flex-1 flex flex-col">
      {/* Pipeline Graph */}
      <div className="flex-1 relative">
        {error && (
          <div className="absolute top-2 left-2 z-10 bg-red-900/80 text-red-300 text-[10px] font-mono px-2 py-1 rounded">
            {error}
          </div>
        )}
        <ReactFlow
          nodes={nodes}
          edges={edges}
          onNodesChange={onNodesChange}
          onEdgesChange={onEdgesChange}
          nodeTypes={nodeTypes}
          fitView
          fitViewOptions={{ padding: 0.3 }}
          minZoom={0.4}
          maxZoom={2}
          proOptions={{ hideAttribution: true }}
        >
          <Background color="#27272a" gap={20} />
          <Controls className="!bg-zinc-900 !border-zinc-700 !fill-zinc-400" />
          <MiniMap
            nodeColor="#27272a"
            maskColor="rgba(9, 9, 11, 0.7)"
            className="!bg-zinc-900 !border-zinc-700"
          />
        </ReactFlow>
      </div>

      {/* Footer Bar */}
      <div className="flex items-center justify-between px-4 py-2 border-t border-zinc-800 bg-zinc-950 text-[10px] font-mono text-zinc-600 shrink-0">
        <span>
          Last run: {status?.last_run ? new Date(status.last_run).toLocaleString() : "Never"}
        </span>
        <span>Duration: {status?.total_duration_ms ? `${status.total_duration_ms}ms` : "—"}</span>
        <span>Success: {status?.success_count ?? 0}/{(status?.nodes?.length ?? 7)}</span>
        <span>Next: daily 08:00</span>
      </div>
    </div>
  );
}
