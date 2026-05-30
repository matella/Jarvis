// Service-dependency graph — a hand-rolled SVG ring layout (no heavy graph lib). Edges are typed;
// node tint reflects live state status pulled from the state projection.

import { useMemo } from "react";

import { api } from "../lib/api";
import { usePoll } from "../lib/usePoll";
import type { Topology } from "../lib/api";
import { layoutTopology, shortName } from "../lib/viz";

const RELATION_COLOR: Record<string, string> = {
  depends_on: "#3de0d5",
  network_mode: "#4d8dff",
  same_project: "#7d93a3",
};

const W = 560;
const H = 420;

export function TopologyGraph() {
  const { data } = usePoll<Topology>(api.topology, 10000);
  const { data: state } = usePoll<Record<string, unknown>[]>(api.state, 8000);

  const statusOf = useMemo(() => {
    const map = new Map<string, string>();
    for (const r of state ?? []) map.set(String(r.entity), String(r.status ?? ""));
    return map;
  }, [state]);

  const nodes = data?.nodes ?? [];
  const positions = useMemo(() => layoutTopology(nodes, W, H), [nodes]);
  const posOf = useMemo(() => new Map(positions.map((p) => [p.id, p])), [positions]);

  if (!data) return <div className="text-xs text-steel">loading topology…</div>;
  if (nodes.length === 0)
    return <div className="text-xs text-steel">no topology yet (run `jarvis topology build`)</div>;

  const tint = (entity: string) => {
    const s = (statusOf.get(entity) ?? "").toLowerCase();
    if (/(running|ok|healthy)/.test(s)) return "#3de0d5";
    if (/(exited|dead|down|fail)/.test(s)) return "#ff7a45";
    return "#7d93a3";
  };

  return (
    <svg viewBox={`0 0 ${W} ${H}`} className="h-full w-full">
      <defs>
        <marker id="arrow" markerWidth="8" markerHeight="8" refX="7" refY="3"
                orient="auto" markerUnits="strokeWidth">
          <path d="M0,0 L7,3 L0,6" fill="rgba(61,224,213,0.5)" />
        </marker>
      </defs>
      {data.edges.map((e, i) => {
        const a = posOf.get(e.src);
        const b = posOf.get(e.dst);
        if (!a || !b) return null;
        return (
          <line
            key={i} x1={a.x} y1={a.y} x2={b.x} y2={b.y}
            stroke={RELATION_COLOR[e.relation] ?? "#7d93a3"} strokeOpacity={0.35}
            strokeWidth={1} markerEnd="url(#arrow)"
          />
        );
      })}
      {positions.map((p) => (
        <g key={p.id}>
          <circle cx={p.x} cy={p.y} r={7} fill={tint(p.id)} fillOpacity={0.85}
                  stroke={tint(p.id)} strokeOpacity={0.4} strokeWidth={6} />
          <text x={p.x} y={p.y - 14} textAnchor="middle"
                className="fill-ink" style={{ fontSize: 10, fontFamily: "IBM Plex Mono" }}>
            {shortName(p.id)}
          </text>
        </g>
      ))}
    </svg>
  );
}
