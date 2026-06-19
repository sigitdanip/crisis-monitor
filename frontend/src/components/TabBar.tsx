"use client";

const TABS = [
  { id: "overview", label: "Overview" },
  { id: "dots", label: "Dots" },
  { id: "indicators", label: "Indicators" },
  { id: "report", label: "Report" },
  { id: "alerts", label: "Alerts" },
  { id: "history", label: "History" },
  { id: "pipeline", label: "Pipeline" },
] as const;

export type TabId = (typeof TABS)[number]["id"];

interface TabBarProps {
  active: TabId;
  onChange: (tab: TabId) => void;
}

export function TabBar({ active, onChange }: TabBarProps) {
  return (
    <nav className="flex border-b border-zinc-800 bg-zinc-950/90 backdrop-blur shrink-0">
      {TABS.map((tab) => (
        <button
          key={tab.id}
          type="button"
          onClick={() => onChange(tab.id)}
          className={`px-5 py-2.5 text-sm font-mono transition-colors border-b-2 -mb-px ${
            active === tab.id
              ? "border-emerald-400 text-emerald-400 bg-emerald-400/5"
              : "border-transparent text-zinc-500 hover:text-zinc-300 hover:border-zinc-700"
          }`}
        >
          {tab.label}
        </button>
      ))}
    </nav>
  );
}
