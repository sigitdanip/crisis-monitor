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

// ponytail: explicit 24-node L→R pipeline — every source + dot is its own visible node
function buildLayout(status: PipelineStatus): { nodes: Node[]; edges: Edge[] } {
  const live = status.nodes?.length > 0;

  const COL = { source: 50, monitor: 300, dot: 540, agent: 830, pathways: 1110, endstate: 1350 };
  const sourceYStart = 40;    const sourceYSpacing = 72;
  const dotYStart = 15;       const dotYSpacing = 56;
  const agentYStart = 65;     const agentYSpacing = 115;
  const monitorY = sourceYStart + (5 * sourceYSpacing) / 2;
  const pathwaysY = agentYStart + (4 * agentYSpacing) / 2;
  const endstateY = pathwaysY;

  // ponytail: edge labels for each transition type
  function edgeLabel(sourceType: string, targetType: string): string | undefined {
    if (sourceType === "source" && targetType === "monitor") return "raw data";
    if (sourceType === "monitor" && targetType === "dot") return "identifies";
    if (sourceType === "dot" && targetType === "agent") return "assigned";
    if (sourceType === "agent" && targetType === "pathways") return "pathways";
    if (sourceType === "pathways" && targetType === "endstate") return "assesses";
    return undefined;
  }

  // ponytail: shared edge factory
  function makeEdge(source: string, target: string, sourceType: string, targetType: string, idx: number): Edge {
    return {
      id: `e-${idx}`,
      source, target,
      animated: true,
      style: { stroke: "#a1a1aa", strokeDasharray: "5 5" },
      label: edgeLabel(sourceType, targetType),
      labelStyle: { fill: "#a1a1aa", fontSize: 10, fontFamily: "monospace" },
      labelShowBg: true,
      labelBgStyle: { fill: "#18181b", fillOpacity: 0.85 },
      labelBgPadding: [4, 2] as [number, number],
      labelBgBorderRadius: 2,
    };
  }

  // ponytail: 6 source definitions — one per data source
  const SRC = [
    { id: "src-rss",    label: "RSS Feeds" },
    { id: "src-who",    label: "WHO API" },
    { id: "src-market", label: "Market Data" },
    { id: "src-em",     label: "EM Currencies" },
    { id: "src-gold",   label: "Gold Price" },
    { id: "src-news",   label: "News Agg." },
  ];

  // ponytail: 10 dot definitions
  const DOTS = [
    { id: "dot-1", label: "Dot 1" },
    { id: "dot-2", label: "Dot 2" },
    { id: "dot-3", label: "Dot 3" },
    { id: "dot-4", label: "Dot 4" },
    { id: "dot-5", label: "Dot 5" },
    { id: "dot-6", label: "Dot 6" },
    { id: "dot-7", label: "Dot 7" },
    { id: "dot-8", label: "Dot 8" },
    { id: "dot-9", label: "Dot 9" },
    { id: "dot-em", label: "Dot EM" },
  ];

  // ponytail: 5 agent definitions with dot assignments
  const AGENTS = [
    { id: "agent-geo",    label: "Geopolitical",      dots: ["dot-1", "dot-2"] },
    { id: "agent-food",   label: "Food & Debt",       dots: ["dot-3", "dot-5"] },
    { id: "agent-fin",    label: "Financial & EM",    dots: ["dot-4", "dot-em"] },
    { id: "agent-china",  label: "China & Political", dots: ["dot-6", "dot-7", "dot-8"] },
    { id: "agent-health", label: "Health",            dots: ["dot-9"] },
  ];

  // ponytail: live branch overlays backend status onto the same 24-node layout
  const beFetchers  = live ? status.nodes.filter((n: any) => n.type === "fetcher") : [];
  const beScorer    = live ? status.nodes.find((n: any) => n.type === "scorer") : undefined;
  const beAgents    = live ? status.nodes.filter((n: any) => n.type === "agent") : [];
  const beSynth     = live ? status.nodes.find((n: any) => n.type === "synthesizer") : undefined;
  const beAssessor  = live ? status.nodes.find((n: any) => n.type === "assessor") : undefined;

  function beNode(n: any) {
    return {
      status: n?.status ?? "success",
      duration: n?.duration_ms ? `${n.duration_ms}ms` : "—",
      count: n?.input_summary ?? "",
      output: n?.output_summary ?? "",
    };
  }

  // Build 24 nodes
  const nodes: Node[] = [
    // 6 source nodes
    ...SRC.map((s, i) => {
      const be = live && beFetchers[i] ? beFetchers[i] : null;
      return {
        id: s.id, type: "fetcher",
        position: { x: COL.source, y: sourceYStart + i * sourceYSpacing },
        data: { label: be?.label ?? s.label, status: be?.status ?? "success", count: be?.input_summary ?? "—", duration: be?.duration_ms ? `${be.duration_ms}ms` : "—", tooltip: s.label, minWidth: 130 },
      };
    }),
    // 1 monitor node
    {
      id: "monitor", type: "scorer",
      position: { x: COL.monitor, y: monitorY },
      data: live && beScorer
        ? { composite: 0, label: beScorer.label || "MONITOR", status: beScorer.status }
        : { composite: 0, label: "MONITOR", status: "success" },
    },
    // 10 dot nodes (always synthetic — backend has no dot entities)
    ...DOTS.map((d, i) => ({
      id: d.id, type: "fetcher",
      position: { x: COL.dot, y: dotYStart + i * dotYSpacing },
      data: { label: d.label, status: "success" as const, count: "—", duration: "—", tooltip: d.label, minWidth: 75 },
    })),
    // 5 agent nodes
    ...AGENTS.map((a, i) => {
      const be = live && beAgents[i] ? beAgents[i] : null;
      const dotLabel = a.dots.map((d: string) => d.replace("dot-", "Dot ")).join("+");
      return {
        id: a.id, type: "agent",
        position: { x: COL.agent, y: agentYStart + i * agentYSpacing },
        data: {
          label: be?.label ?? a.label,
          status: be?.status ?? "success",
          dots: be?.input_summary ?? dotLabel,
          duration: be?.duration_ms ? `${be.duration_ms}ms` : "—",
          model: (be as any)?.model ?? "pending",
        },
      };
    }),
    // 1 pathways node
    {
      id: "pathways", type: "synthesizer",
      position: { x: COL.pathways, y: pathwaysY },
      data: live && beSynth
        ? { label: beSynth.label || "PATHWAY SYNTH", status: beSynth.status, pathways: beSynth.input_summary ?? "", duration: beSynth.duration_ms ? `${beSynth.duration_ms}ms` : "—" }
        : { label: "PATHWAY SYNTH", status: "success" as const, pathways: "pending", duration: "—" },
    },
    // 1 end state node
    {
      id: "endstate", type: "assessor",
      position: { x: COL.endstate, y: endstateY },
      data: live && beAssessor
        ? { label: beAssessor.label || "END STATE", status: beAssessor.status, endState: beAssessor.output_summary ?? "", duration: beAssessor.duration_ms ? `${beAssessor.duration_ms}ms` : "—" }
        : { label: "END STATE", status: "success" as const, endState: "pending", duration: "—" },
    },
  ];

  // Build 32 edges
  const edges: Edge[] = [];
  let ei = 0;
  // 6 source → monitor
  for (const s of SRC) edges.push(makeEdge(s.id, "monitor", "source", "monitor", ei++));
  // 10 monitor → dot
  for (const d of DOTS) edges.push(makeEdge("monitor", d.id, "monitor", "dot", ei++));
  // dot → agent (10 edges based on assignments)
  for (const a of AGENTS) for (const dotId of a.dots) edges.push(makeEdge(dotId, a.id, "dot", "agent", ei++));
  // 5 agent → pathways
  for (const a of AGENTS) edges.push(makeEdge(a.id, "pathways", "agent", "pathways", ei++));
  // 1 pathways → endstate
  edges.push(makeEdge("pathways", "endstate", "pathways", "endstate", ei++));

  return { nodes, edges };
}

export function PipelinePanel() {
  const [status, setStatus] = useState<PipelineStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isMobile, setIsMobile] = useState(false);

  // ponytail: detect mobile viewport for horizontal scrolling
  useEffect(() => {
    const check = () => setIsMobile(window.innerWidth < 768);
    check();
    window.addEventListener("resize", check);
    return () => window.removeEventListener("resize", check);
  }, []);

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
      <div className={`flex-1${isMobile ? " overflow-x-auto overflow-y-hidden" : ""}`}>
        <div className={`h-full relative${isMobile ? " min-w-[1550px]" : ""}`}>
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
            fitView={!isMobile}
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
