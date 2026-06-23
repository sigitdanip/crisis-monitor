export type DotStatus = "dormant" | "activating" | "active" | "critical";

// ---------------------------------------------------------------------------
// Human-readable display names for dot keys returned by the backend.
// The backend stores raw variable keys like 'dot_1', 'em_currency'.
// ---------------------------------------------------------------------------
export const DOT_DISPLAY_NAMES: Record<string, string> = {
  // Agent 3: EM Currency stress
  dot_0: "EM Currency Stress",
  em_currency: "EM Currency Stress",
  // Agent 1: Geopolitical — NATO + Energy Security
  dot_1: "Geopolitical NATO Fracture",
  dot_2: "Energy Security",
  // Agent 2: Food + Sovereign Debt
  dot_3: "Food Supply Crisis",
  dot_5: "Sovereign Debt",
  // Agent 3: Credit/Financial
  dot_4: "Credit Contagion",
  // Agent 4: China + Political + Supply Chain
  dot_6: "China Political Stability",
  dot_7: "Social Unrest",
  dot_8: "Supply Chain Disruption",
  // Agent 5: Health/Pandemic
  dot_9: "Global Health",
};

/** Map a raw dot_name (e.g. 'dot_1', 'em_currency') to a human-readable label. */
export function getDotDisplayName(raw: string): string {
  return DOT_DISPLAY_NAMES[raw] ?? raw;
}

export interface Indicator {
  name: string;
  category: string;
  value: number | null;
  unit: string;
  status: string;
  trigger_level: string;
  fetched_at: string;
  narrative?: string;
}

export interface DotAnalysisItem {
  status: string;
  summary: string;
  key_signals: string[];
  sources?: string;
}

export type DotSummary = Record<string, DotAnalysisItem>;

export interface PathwayAnalysisItem {
  active: boolean;
  triggered_by: string[];
  name: string;
  description: string;
}

export type PathwaySummary = Record<string, PathwayAnalysisItem>;

export interface Dot {
  dot_number: number;
  dot_name: string;
  status: DotStatus;
  summary: string;
  key_signals: string[];
  sources?: string;
}

export interface Pathway {
  pathway: string;
  name: string;
  description: string;
  active: number;
  signals: string[];
}

/** Map pathway keys to human-readable names. Used as fallback when
 *  the backend name field is empty (e.g., stale rows from before
 *  this migration). Matches the pathway_synthesizer prompt names. */
export const PATHWAY_NAMES: Record<string, string> = {
  pathway_a: "Monetary Cascade",
  pathway_b: "Energy Price Shock",
  pathway_c: "Geopolitical Fracture",
  pathway_d: "Systemic Collapse",
};

/** Return the human-readable pathway name, falling back to the raw key. */
export function getPathwayName(pw: Pathway): string {
  return pw.name || PATHWAY_NAMES[pw.pathway] || pw.pathway;
}

export interface KeyQuestion {
  question: string;
  answer: string;
  verdict?: string;
  trigger_region?: string;
  trigger_probability?: number;
  probability?: number;
  assessment?: string;
  indicator?: string;
  rationale?: string;
}

export type FiveQuestions = Record<string, KeyQuestion>;

export interface Report {
  id: number;
  date: string;
  dot_summary: DotSummary;
  pathway_summary: PathwaySummary;
  end_state: string;
  synthesis: string;
  five_questions: FiveQuestions;
  confidence: string;
  composite_score: number;
  briefing?: string;
  created_at: string;
}

export interface Alert {
  id: number;
  category: string;
  indicator: string;
  message: string;
  triggered_at: string;
  acknowledged: number;
}

export interface DashboardData {
  indicators: Indicator[];
  dots: Dot[];
  pathways: Pathway[];
  report: Report | null;
  alerts: Alert[];
}

export interface PipelineNode {
  id: string;
  type: string;
  label: string;
  status: "success" | "error" | "running" | "fallback";
  duration_ms: number;
  input_summary?: string;
  output_summary?: string;
  model?: string;
  error?: string;
}

export interface PipelineProgress {
  running: boolean;
  started_at: string | null;
  elapsed_ms: number | null;
  current_node: string | null;
  completed_nodes: string[] | null;
  failed_node: string | null;
  estimated_remaining_ms: number | null;
}

export interface PipelineStatus {
  nodes: PipelineNode[];
  edges: { source: string; target: string }[];
  last_run: string | null;
  total_duration_ms: number;
  success_count: number;
  progress: PipelineProgress;
}

export interface HistoryReport {
  date: string;
  end_state: string;
  composite_score: number;
  confidence: string;
  synthesis: string;
  briefing?: string;
}

// Timeseries API types
export interface TimeseriesPoint {
  recorded_at: string;
  value: number;
  status: string;
}

export interface TimeseriesSeries {
  indicator_name: string;
  display_name: string;
  category: string;
  unit: string;
  points: TimeseriesPoint[];
}

export interface CompositeTimeseriesPoint {
  recorded_at: string;
  composite_score: number;
  interpretation: string;
}

export interface TimeseriesResponse {
  series: TimeseriesSeries[];
  composite_series: CompositeTimeseriesPoint[];
  from: string;
  to: string;
}
