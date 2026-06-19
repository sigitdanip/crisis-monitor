export type DotStatus = "dormant" | "activating" | "active" | "critical";

// ---------------------------------------------------------------------------
// Human-readable display names for dot keys returned by the backend.
// The backend stores raw variable keys like 'dot_1', 'em_currency'.
// ---------------------------------------------------------------------------
export const DOT_DISPLAY_NAMES: Record<string, string> = {
  dot_0: "EM Currency Stress",
  em_currency: "EM Currency Stress",
  dot_1: "Geopolitical NATO Fracture",
  dot_2: "Food Supply Crisis",
  dot_3: "Credit Contagion",
  dot_4: "China Political Stability",
  dot_5: "Global Health",
  dot_6: "Energy Storage",
  dot_7: "Sovereign Debt",
  dot_8: "Banking Stress",
  dot_9: "Social Unrest",
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

export interface Dot {
  dot_number: number;
  dot_name: string;
  status: DotStatus;
  summary: string;
  key_signals: string;
  sources?: string;
}

export interface Pathway {
  pathway: string;
  name: string;
  description: string;
  active: number;
  signals: string;
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
  dot_summary: string;
  pathway_summary: string;
  end_state: string;
  synthesis: string;
  five_questions: string | FiveQuestions;
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
  error?: string;
}

export interface PipelineStatus {
  nodes: PipelineNode[];
  edges: { source: string; target: string }[];
  last_run: string | null;
  total_duration_ms: number;
  success_count: number;
}

export interface HistoryReport {
  date: string;
  end_state: string;
  composite_score: number;
  confidence: string;
  synthesis: string;
  briefing?: string;
}
