// Pure visualization helpers — SVG geometry for the chart and topology graph. No DOM, no random:
// deterministic so they unit-test cleanly and render identically every frame.

export function sparklinePath(values: number[], width: number, height: number, pad = 2): string {
  if (values.length === 0) return "";
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  const stepX = values.length > 1 ? (width - pad * 2) / (values.length - 1) : 0;
  return values
    .map((v, i) => {
      const x = pad + i * stepX;
      const y = height - pad - ((v - min) / span) * (height - pad * 2);
      return `${i === 0 ? "M" : "L"}${x.toFixed(1)},${y.toFixed(1)}`;
    })
    .join(" ");
}

export function thresholdY(threshold: number, values: number[], height: number, pad = 2): number {
  const min = Math.min(...values, threshold);
  const max = Math.max(...values, threshold);
  const span = max - min || 1;
  return height - pad - ((threshold - min) / span) * (height - pad * 2);
}

export interface NodePos {
  id: string;
  x: number;
  y: number;
}

// Deterministic circular layout — nodes evenly placed on a ring; good enough for a homelab's
// handful of services and stable across renders (no physics jitter).
export function layoutTopology(
  nodes: string[], width: number, height: number, radius?: number,
): NodePos[] {
  const cx = width / 2;
  const cy = height / 2;
  const r = radius ?? Math.min(width, height) / 2 - 40;
  const n = nodes.length;
  if (n === 1) return [{ id: nodes[0], x: cx, y: cy }];
  return nodes.map((id, i) => {
    const angle = (i / n) * Math.PI * 2 - Math.PI / 2;
    return { id, x: cx + r * Math.cos(angle), y: cy + r * Math.sin(angle) };
  });
}

export function shortName(entity: string): string {
  // "container:jarvis-postgres" → "jarvis-postgres"
  return entity.includes(":") ? entity.split(":").slice(1).join(":") : entity;
}
