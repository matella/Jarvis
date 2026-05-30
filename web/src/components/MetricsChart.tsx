// Live metric sparklines — small multiples per container with a threshold overlay. Reads the
// recent samples from /api/metrics and extracts the chosen field (cpu/mem %). Hand-rolled SVG.

import { useMemo, useState } from "react";

import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";
import { shortName, sparklinePath, thresholdY } from "../lib/viz";

const FIELDS = [
  { key: "cpu_pct", label: "CPU %", threshold: 80 },
  { key: "mem_pct", label: "MEM %", threshold: 85 },
];
const CW = 240;
const CH = 48;

type Row = { entity: string; kind: string; sample: Record<string, number>; ts: string };

export function MetricsChart() {
  const { data } = usePoll<Row[]>(() => api.metrics(300) as Promise<Row[]>, 6000);
  const [fieldKey, setFieldKey] = useState(FIELDS[0].key);
  const field = FIELDS.find((f) => f.key === fieldKey)!;

  // group samples by entity → chronological numeric series for the chosen field
  const series = useMemo(() => {
    const byEntity = new Map<string, number[]>();
    for (const r of [...(data ?? [])].reverse()) {
      const v = r.sample?.[field.key];
      if (typeof v !== "number") continue;
      const arr = byEntity.get(r.entity) ?? [];
      arr.push(v);
      byEntity.set(r.entity, arr);
    }
    return [...byEntity.entries()]
      .filter(([, vals]) => vals.length >= 2)
      .slice(0, 6);
  }, [data, field.key]);

  return (
    <div>
      <div className="mb-2 flex gap-2">
        {FIELDS.map((f) => (
          <button
            key={f.key}
            onClick={() => setFieldKey(f.key)}
            className={`label border px-2 py-0.5 ${
              f.key === fieldKey ? "border-teal/40 !text-teal" : "border-edge"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>
      {series.length === 0 ? (
        <div className="text-xs text-steel">no metric samples yet</div>
      ) : (
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          {series.map(([entity, vals]) => {
            const last = vals[vals.length - 1];
            const ty = thresholdY(field.threshold, vals, CH);
            const breach = last >= field.threshold;
            return (
              <div key={entity} className="border border-teal/10 p-2">
                <div className="mb-1 flex items-center justify-between">
                  <span className="truncate text-xs text-ink" title={entity}>
                    {shortName(entity)}
                  </span>
                  <span className={`tabular text-xs ${breach ? "text-amber" : "text-teal"}`}>
                    {last.toFixed(0)}%
                  </span>
                </div>
                <svg viewBox={`0 0 ${CW} ${CH}`} className="w-full" height={CH}>
                  <line x1={0} x2={CW} y1={ty} y2={ty} stroke="#ffb454" strokeOpacity={0.4}
                        strokeDasharray="3 3" strokeWidth={1} />
                  <path d={sparklinePath(vals, CW, CH)} fill="none"
                        stroke={breach ? "#ffb454" : "#3de0d5"} strokeWidth={1.5} />
                </svg>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
