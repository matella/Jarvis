// Insight surface — the analyst's view: topology graph, live metric charts, and the approvals
// queue, as tabs. The decision inspector opens as a modal from approvals (or the ledger).

import { ApprovalsQueue } from "./ApprovalsQueue";
import { MetricsChart } from "./MetricsChart";
import { TopologyGraph } from "./TopologyGraph";

type Tab = "topology" | "metrics" | "approvals";
const TABS: { id: Tab; label: string }[] = [
  { id: "topology", label: "Topology" },
  { id: "metrics", label: "Metrics" },
  { id: "approvals", label: "Approvals" },
];

export function InsightMode({ tab, onTab, onInspect }: {
  tab: Tab;
  onTab: (t: Tab) => void;
  onInspect: (intentId: string) => void;
}) {
  return (
    <div className="relative z-10 mx-auto flex h-full max-w-5xl flex-col p-4">
      <div className="mb-3 flex gap-1 border border-edge p-1 self-start">
        {TABS.map((t) => (
          <button
            key={t.id}
            onClick={() => onTab(t.id)}
            className={`px-3 py-1 text-[10px] uppercase tracking-widest transition ${
              tab === t.id ? "bg-teal/15 text-teal" : "text-steel hover:text-ink"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="bracket panel min-h-0 flex-1 overflow-auto p-4">
        {tab === "topology" && (
          <div className="h-full">
            <div className="label mb-2">Service dependency graph</div>
            <TopologyGraph />
          </div>
        )}
        {tab === "metrics" && <MetricsChart />}
        {tab === "approvals" && <ApprovalsQueue onInspect={onInspect} />}
      </div>
    </div>
  );
}

export type { Tab as InsightTab };
