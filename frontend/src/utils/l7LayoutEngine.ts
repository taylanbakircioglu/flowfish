/**
 * L7 Service Map layout engine — pure-math layouts with zero extra dependencies.
 * Dagre is handled externally; this module provides the alternative layouts.
 * Ported and adapted from Map.tsx (L4) layout algorithms.
 */
import type { Node } from '@xyflow/react';

export type L7LayoutType =
  | 'dagre-tb'
  | 'dagre-lr'
  | 'namespace-cluster'
  | 'concentric'
  | 'organic'
  | 'error-centric'
  | 'hub'
  | 'force'
  | 'radial'
  | 'circle'
  | 'grid'
  | 'tree'
  | 'star'
  | 'mesh'
  | 'layered'
  | 'tier'
  | 'flow';

export const LAYOUT_LABELS: Record<L7LayoutType, string> = {
  'dagre-tb': 'Dagre (Top → Bottom)',
  'dagre-lr': 'Dagre (Left → Right)',
  'namespace-cluster': 'Namespace Cluster',
  concentric: 'Concentric (Connections)',
  organic: 'Organic / Spiral',
  'error-centric': 'Error-Centric',
  hub: 'Hub (Centrality)',
  force: 'Force-Directed',
  radial: 'Radial Rings',
  circle: 'Circle',
  grid: 'Grid',
  tree: 'Tree (Hierarchical)',
  star: 'Star',
  mesh: 'Mesh (Hexagonal)',
  layered: 'Layered (Bands)',
  tier: 'Tier (Layers)',
  flow: 'Flow (L→R)',
};

const NODE_W = 228;
const NODE_H = 102;
const PADDING = 48;

interface LayoutEdge {
  source: string;
  target: string;
}

interface LayoutNodeData {
  namespace?: string;
  errorRate?: number;
  kind?: string;
  workloadName?: string;
}

function getDegrees(nodes: Node[], edges: LayoutEdge[]): Map<string, number> {
  const deg = new Map<string, number>();
  nodes.forEach((n) => deg.set(n.id, 0));
  edges.forEach((e) => {
    if (deg.has(e.source)) deg.set(e.source, deg.get(e.source)! + 1);
    if (deg.has(e.target)) deg.set(e.target, deg.get(e.target)! + 1);
  });
  return deg;
}

function getInOutDegrees(edges: LayoutEdge[]): { inDeg: Map<string, number>; outDeg: Map<string, number> } {
  const inDeg = new Map<string, number>();
  const outDeg = new Map<string, number>();
  edges.forEach((e) => {
    outDeg.set(e.source, (outDeg.get(e.source) ?? 0) + 1);
    inDeg.set(e.target, (inDeg.get(e.target) ?? 0) + 1);
  });
  return { inDeg, outDeg };
}

function namespaceClusters(nodes: Node[]): Map<string, Node[]> {
  const groups = new Map<string, Node[]>();
  nodes.forEach((n) => {
    const ns = (n.data as LayoutNodeData)?.namespace || 'unknown';
    if (!groups.has(ns)) groups.set(ns, []);
    groups.get(ns)!.push(n);
  });
  return groups;
}

function adaptiveSpacing(nodeCount: number): number {
  if (nodeCount <= 20) return NODE_W * 0.9 + PADDING;
  if (nodeCount <= 60) return NODE_W * 0.75 + PADDING * 0.8;
  if (nodeCount <= 150) return NODE_W * 0.65 + PADDING * 0.6;
  return NODE_W * 0.55 + PADDING * 0.4;
}

// --- Namespace Cluster ---
export function layoutNamespaceCluster(nodes: Node[], _edges: LayoutEdge[]): Node[] {
  const groups = namespaceClusters(nodes);
  const nsKeys = Array.from(groups.keys()).sort();
  const cols = Math.max(1, Math.ceil(Math.sqrt(nsKeys.length)));
  const maxPerGroup = Math.max(1, ...Array.from(groups.values()).map((g) => g.length));
  const innerCols = Math.max(1, Math.ceil(Math.sqrt(maxPerGroup)));
  const groupW = innerCols * (NODE_W + PADDING) + PADDING * 2;
  const innerRows = Math.ceil(maxPerGroup / innerCols);
  const groupH = innerRows * (NODE_H + PADDING) + PADDING * 2;
  const positioned = new Map<string, { x: number; y: number }>();

  nsKeys.forEach((ns, idx) => {
    const col = idx % cols;
    const row = Math.floor(idx / cols);
    const groupX = col * (groupW + PADDING * 2);
    const groupY = row * (groupH + PADDING * 2);
    const members = groups.get(ns)!;
    const mCols = Math.max(1, Math.ceil(Math.sqrt(members.length)));
    members.forEach((n, i) => {
      const ic = i % mCols;
      const ir = Math.floor(i / mCols);
      positioned.set(n.id, {
        x: groupX + PADDING + ic * (NODE_W + PADDING),
        y: groupY + PADDING + ir * (NODE_H + PADDING),
      });
    });
  });

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Concentric (by degree) ---
export function layoutConcentric(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const deg = getDegrees(nodes, edges);
  const sorted = [...nodes].sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0));
  const spacing = adaptiveSpacing(nodes.length);
  const centerX = Math.max(600, nodes.length * 8);
  const centerY = centerX;
  const positioned = new Map<string, { x: number; y: number }>();

  let ringIdx = 0;
  let placed = 0;
  while (placed < sorted.length) {
    const ringCapacity = ringIdx === 0 ? 1 : Math.max(4, Math.floor(ringIdx * 6));
    const ringRadius = ringIdx * spacing;
    const count = Math.min(ringCapacity, sorted.length - placed);
    for (let i = 0; i < count; i++) {
      const node = sorted[placed + i];
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      positioned.set(node.id, {
        x: centerX + ringRadius * Math.cos(angle) - NODE_W / 2,
        y: centerY + ringRadius * Math.sin(angle) - NODE_H / 2,
      });
    }
    placed += count;
    ringIdx++;
  }

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Organic / Spiral (golden angle phyllotaxis) ---
export function layoutOrganic(nodes: Node[]): Node[] {
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  const spacing = adaptiveSpacing(nodes.length) * 0.5;
  const centerX = Math.max(600, nodes.length * 6);
  const centerY = centerX;

  return nodes.map((n, i) => {
    const angle = i * goldenAngle;
    const radius = Math.sqrt(i + 1) * spacing;
    return {
      ...n,
      position: {
        x: centerX + radius * Math.cos(angle) - NODE_W / 2,
        y: centerY + radius * Math.sin(angle) - NODE_H / 2,
      },
    };
  });
}

// --- Error-Centric (highest error rate at center) ---
export function layoutErrorCentric(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const sorted = [...nodes].sort((a, b) => {
    const errA = (a.data as LayoutNodeData)?.errorRate ?? 0;
    const errB = (b.data as LayoutNodeData)?.errorRate ?? 0;
    return errB - errA;
  });

  const deg = getDegrees(sorted, edges);
  const spacing = adaptiveSpacing(nodes.length);
  const centerX = Math.max(600, nodes.length * 6);
  const centerY = centerX;
  const positioned = new Map<string, { x: number; y: number }>();

  let ringIdx = 0;
  let placed = 0;
  while (placed < sorted.length) {
    const ringCapacity = ringIdx === 0 ? 1 : Math.max(4, Math.floor(ringIdx * 6));
    const ringRadius = ringIdx * spacing;
    const count = Math.min(ringCapacity, sorted.length - placed);
    const ringNodes = sorted.slice(placed, placed + count);
    ringNodes.sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0));
    for (let i = 0; i < count; i++) {
      const node = ringNodes[i];
      const angle = (2 * Math.PI * i) / count - Math.PI / 2;
      positioned.set(node.id, {
        x: centerX + ringRadius * Math.cos(angle) - NODE_W / 2,
        y: centerY + ringRadius * Math.sin(angle) - NODE_H / 2,
      });
    }
    placed += count;
    ringIdx++;
  }

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Hub (most-connected nodes at center, decreasing outward) ---
export function layoutHub(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const deg = getDegrees(nodes, edges);
  const maxDeg = Math.max(1, ...Array.from(deg.values()));
  const spacing = adaptiveSpacing(nodes.length);
  const maxRadius = spacing * Math.ceil(Math.sqrt(nodes.length));
  const centerX = maxRadius + NODE_W;
  const centerY = maxRadius + NODE_H;
  const positioned = new Map<string, { x: number; y: number }>();

  const sorted = [...nodes].sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0));
  sorted.forEach((n, i) => {
    const d = deg.get(n.id) ?? 0;
    const normalizedDeg = d / maxDeg;
    const radius = maxRadius * (1 - normalizedDeg * 0.8);
    const goldenAngle = Math.PI * (3 - Math.sqrt(5));
    const angle = i * goldenAngle;
    positioned.set(n.id, {
      x: centerX + radius * Math.cos(angle) - NODE_W / 2,
      y: centerY + radius * Math.sin(angle) - NODE_H / 2,
    });
  });

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Force-Directed (spring simulation approximation) ---
export function layoutForce(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const spacing = adaptiveSpacing(nodes.length) * 0.6;
  const centerX = Math.max(800, nodes.length * 10);
  const centerY = centerX;

  const positions = new Map<string, { x: number; y: number }>();
  const goldenAngle = Math.PI * (3 - Math.sqrt(5));
  nodes.forEach((n, i) => {
    const angle = i * goldenAngle;
    const r = Math.sqrt(i + 1) * spacing;
    positions.set(n.id, { x: centerX + r * Math.cos(angle), y: centerY + r * Math.sin(angle) });
  });

  const adj = new Map<string, Set<string>>();
  nodes.forEach((n) => adj.set(n.id, new Set()));
  edges.forEach((e) => {
    adj.get(e.source)?.add(e.target);
    adj.get(e.target)?.add(e.source);
  });

  const iterations = Math.min(60, Math.max(20, 80 - nodes.length / 5));
  const idealDist = spacing * 1.5;

  for (let iter = 0; iter < iterations; iter++) {
    const temp = 0.3 * (1 - iter / iterations);
    const forces = new Map<string, { fx: number; fy: number }>();
    nodes.forEach((n) => forces.set(n.id, { fx: 0, fy: 0 }));

    // Repulsive forces (sample for large graphs)
    const sampleRate = nodes.length > 200 ? Math.ceil(nodes.length / 200) : 1;
    for (let i = 0; i < nodes.length; i++) {
      const pi = positions.get(nodes[i].id)!;
      for (let j = i + 1; j < nodes.length; j += sampleRate) {
        const pj = positions.get(nodes[j].id)!;
        const dx = pi.x - pj.x;
        const dy = pi.y - pj.y;
        const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
        const repForce = (idealDist * idealDist) / dist;
        const fx = (dx / dist) * repForce * 0.3;
        const fy = (dy / dist) * repForce * 0.3;
        forces.get(nodes[i].id)!.fx += fx;
        forces.get(nodes[i].id)!.fy += fy;
        forces.get(nodes[j].id)!.fx -= fx;
        forces.get(nodes[j].id)!.fy -= fy;
      }
    }

    // Attractive forces along edges
    edges.forEach((e) => {
      const ps = positions.get(e.source);
      const pt = positions.get(e.target);
      if (!ps || !pt) return;
      const dx = pt.x - ps.x;
      const dy = pt.y - ps.y;
      const dist = Math.max(1, Math.sqrt(dx * dx + dy * dy));
      const attForce = (dist - idealDist) * 0.05;
      const fx = (dx / dist) * attForce;
      const fy = (dy / dist) * attForce;
      forces.get(e.source)!.fx += fx;
      forces.get(e.source)!.fy += fy;
      forces.get(e.target)!.fx -= fx;
      forces.get(e.target)!.fy -= fy;
    });

    // Apply forces
    nodes.forEach((n) => {
      const f = forces.get(n.id)!;
      const p = positions.get(n.id)!;
      const mag = Math.sqrt(f.fx * f.fx + f.fy * f.fy);
      if (mag > 0) {
        const cap = idealDist * temp;
        const scale = Math.min(cap, mag) / mag;
        p.x += f.fx * scale;
        p.y += f.fy * scale;
      }
    });
  }

  return nodes.map((n) => {
    const p = positions.get(n.id) || { x: 0, y: 0 };
    return { ...n, position: { x: p.x - NODE_W / 2, y: p.y - NODE_H / 2 } };
  });
}

// --- Radial (expanding rings, 8 per ring) ---
export function layoutRadial(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const deg = getDegrees(nodes, edges);
  const sorted = [...nodes].sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0));
  const spacing = adaptiveSpacing(nodes.length);
  const nodesPerRing = Math.max(4, Math.min(12, Math.ceil(nodes.length / 8)));
  const centerX = Math.max(600, nodes.length * 6);
  const centerY = centerX;
  const positioned = new Map<string, { x: number; y: number }>();

  if (sorted.length > 0) {
    positioned.set(sorted[0].id, { x: centerX - NODE_W / 2, y: centerY - NODE_H / 2 });
  }
  let placed = 1;
  let ringIdx = 1;
  while (placed < sorted.length) {
    const capacity = Math.min(nodesPerRing, sorted.length - placed);
    const radius = ringIdx * spacing;
    for (let i = 0; i < capacity; i++) {
      const node = sorted[placed + i];
      const angle = (2 * Math.PI * i) / capacity - Math.PI / 2;
      positioned.set(node.id, {
        x: centerX + radius * Math.cos(angle) - NODE_W / 2,
        y: centerY + radius * Math.sin(angle) - NODE_H / 2,
      });
    }
    placed += capacity;
    ringIdx++;
  }

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Circle (even distribution) ---
export function layoutCircle(nodes: Node[]): Node[] {
  const radius = Math.max(200, nodes.length * (NODE_W * 0.22));
  const centerX = radius + NODE_W;
  const centerY = radius + NODE_H;

  return nodes.map((n, i) => {
    const angle = (2 * Math.PI * i) / nodes.length - Math.PI / 2;
    return {
      ...n,
      position: {
        x: centerX + radius * Math.cos(angle) - NODE_W / 2,
        y: centerY + radius * Math.sin(angle) - NODE_H / 2,
      },
    };
  });
}

// --- Grid (matrix layout) ---
export function layoutGrid(nodes: Node[]): Node[] {
  const cols = Math.max(1, Math.ceil(Math.sqrt(nodes.length)));
  const cellW = NODE_W + PADDING;
  const cellH = NODE_H + PADDING;

  return nodes.map((n, i) => {
    const col = i % cols;
    const row = Math.floor(i / cols);
    return {
      ...n,
      position: { x: col * cellW + PADDING, y: row * cellH + PADDING },
    };
  });
}

// --- Tree (hierarchical levels by BFS from roots) ---
export function layoutTree(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const { inDeg, outDeg } = getInOutDegrees(edges);
  const adj = new Map<string, string[]>();
  nodes.forEach((n) => adj.set(n.id, []));
  edges.forEach((e) => {
    adj.get(e.source)?.push(e.target);
  });

  const roots = nodes.filter((n) => (inDeg.get(n.id) ?? 0) === 0 || (outDeg.get(n.id) ?? 0) > (inDeg.get(n.id) ?? 0));
  if (!roots.length && nodes.length > 0) roots.push(nodes[0]);

  const level = new Map<string, number>();
  const queue: string[] = [];
  roots.forEach((r) => { level.set(r.id, 0); queue.push(r.id); });

  while (queue.length) {
    const id = queue.shift()!;
    const lev = level.get(id)!;
    for (const child of (adj.get(id) || [])) {
      if (!level.has(child)) {
        level.set(child, lev + 1);
        queue.push(child);
      }
    }
  }

  // Assign unvisited nodes
  nodes.forEach((n) => { if (!level.has(n.id)) level.set(n.id, 0); });

  const levGroups = new Map<number, Node[]>();
  nodes.forEach((n) => {
    const l = level.get(n.id)!;
    if (!levGroups.has(l)) levGroups.set(l, []);
    levGroups.get(l)!.push(n);
  });

  const cellW = NODE_W + PADDING;
  const cellH = NODE_H + PADDING * 1.5;

  return nodes.map((n) => {
    const l = level.get(n.id)!;
    const group = levGroups.get(l)!;
    const idx = group.indexOf(n);
    const offsetX = -(group.length * cellW) / 2;
    return {
      ...n,
      position: { x: offsetX + idx * cellW + PADDING, y: l * cellH + PADDING },
    };
  });
}

// --- Star (node 0 at center, others on arms) ---
export function layoutStar(nodes: Node[], edges: LayoutEdge[]): Node[] {
  if (!nodes.length) return [];
  const deg = getDegrees(nodes, edges);
  const sorted = [...nodes].sort((a, b) => (deg.get(b.id) ?? 0) - (deg.get(a.id) ?? 0));
  const spacing = adaptiveSpacing(nodes.length);
  const arms = Math.max(4, Math.min(8, Math.ceil(nodes.length / 6)));
  const centerX = Math.max(500, nodes.length * 5);
  const centerY = centerX;
  const positioned = new Map<string, { x: number; y: number }>();

  positioned.set(sorted[0].id, { x: centerX - NODE_W / 2, y: centerY - NODE_H / 2 });

  for (let i = 1; i < sorted.length; i++) {
    const arm = (i - 1) % arms;
    const layer = Math.floor((i - 1) / arms) + 1;
    const angle = (2 * Math.PI * arm) / arms - Math.PI / 2;
    const radius = layer * spacing;
    positioned.set(sorted[i].id, {
      x: centerX + radius * Math.cos(angle) - NODE_W / 2,
      y: centerY + radius * Math.sin(angle) - NODE_H / 2,
    });
  }

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Mesh (hexagonal grid) ---
export function layoutMesh(nodes: Node[]): Node[] {
  const cols = Math.max(3, Math.min(8, Math.ceil(Math.sqrt(nodes.length))));
  const cellW = NODE_W + PADDING;
  const cellH = (NODE_H + PADDING) * 0.9;

  return nodes.map((n, i) => {
    const row = Math.floor(i / cols);
    const col = i % cols;
    const xOffset = row % 2 === 1 ? cellW * 0.5 : 0;
    return {
      ...n,
      position: { x: col * cellW + xOffset + PADDING, y: row * cellH + PADDING },
    };
  });
}

// --- Layered (horizontal bands by namespace) ---
export function layoutLayered(nodes: Node[]): Node[] {
  const groups = namespaceClusters(nodes);
  const nsKeys = Array.from(groups.keys()).sort();
  const cellW = NODE_W + PADDING;
  const bandH = NODE_H + PADDING * 2;
  const positioned = new Map<string, { x: number; y: number }>();

  nsKeys.forEach((ns, bandIdx) => {
    const members = groups.get(ns)!;
    const yBase = bandIdx * (bandH + PADDING);
    members.forEach((n, i) => {
      positioned.set(n.id, {
        x: i * cellW + PADDING,
        y: yBase + PADDING,
      });
    });
  });

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Tier (Frontend → Backend → DB layers from name/kind heuristics) ---
function guessTier(n: Node): number {
  const data = n.data as LayoutNodeData;
  const name = ((data?.workloadName || '') + ' ' + (data?.kind || '')).toLowerCase();
  if (/gateway|ingress|frontend|ui|web|nginx|haproxy|envoy|istio/.test(name)) return 0;
  if (/api|backend|service|app|server|worker|consumer|processor/.test(name)) return 1;
  if (/db|database|postgres|mysql|mongo|redis|elastic|kafka|rabbitmq|clickhouse|neo4j|cassandra|minio|harbor/.test(name)) return 2;
  if (/monitor|prom|grafana|alert|log|jaeger|otel|tempo|loki/.test(name)) return 3;
  return 1; // default to middle tier
}

export function layoutTier(nodes: Node[], _edges: LayoutEdge[]): Node[] {
  const tierGroups = new Map<number, Node[]>();
  nodes.forEach((n) => {
    const t = guessTier(n);
    if (!tierGroups.has(t)) tierGroups.set(t, []);
    tierGroups.get(t)!.push(n);
  });

  const tiers = Array.from(tierGroups.keys()).sort();
  const cellW = NODE_W + PADDING;
  const bandH = NODE_H + PADDING * 2;
  const positioned = new Map<string, { x: number; y: number }>();

  tiers.forEach((tier, bandIdx) => {
    const members = tierGroups.get(tier)!;
    const cols = Math.max(1, Math.ceil(Math.sqrt(members.length)));
    members.forEach((n, i) => {
      const col = i % cols;
      const row = Math.floor(i / cols);
      positioned.set(n.id, {
        x: col * cellW + PADDING,
        y: bandIdx * (bandH * 2) + row * (NODE_H + PADDING) + PADDING,
      });
    });
  });

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

// --- Flow (source on left, target on right based on in/out degree ratio) ---
export function layoutFlow(nodes: Node[], edges: LayoutEdge[]): Node[] {
  const { inDeg, outDeg } = getInOutDegrees(edges);
  const colCount = 5;
  const cellW = NODE_W + PADDING * 1.5;
  const cellH = NODE_H + PADDING;

  const columns = new Map<number, Node[]>();
  nodes.forEach((n) => {
    const inD = inDeg.get(n.id) ?? 0;
    const outD = outDeg.get(n.id) ?? 0;
    const total = inD + outD;
    const ratio = total > 0 ? inD / total : 0.5;
    const col = Math.min(colCount - 1, Math.floor(ratio * colCount));
    if (!columns.has(col)) columns.set(col, []);
    columns.get(col)!.push(n);
  });

  const positioned = new Map<string, { x: number; y: number }>();
  for (let c = 0; c < colCount; c++) {
    const group = columns.get(c) || [];
    group.forEach((n, i) => {
      positioned.set(n.id, {
        x: c * cellW + PADDING,
        y: i * cellH + PADDING,
      });
    });
  }

  return nodes.map((n) => ({ ...n, position: positioned.get(n.id) || { x: 0, y: 0 } }));
}

export function applyLayout(
  layoutType: L7LayoutType,
  nodes: Node[],
  edges: LayoutEdge[],
): Node[] | null {
  switch (layoutType) {
    case 'namespace-cluster':
      return layoutNamespaceCluster(nodes, edges);
    case 'concentric':
      return layoutConcentric(nodes, edges);
    case 'organic':
      return layoutOrganic(nodes);
    case 'error-centric':
      return layoutErrorCentric(nodes, edges);
    case 'hub':
      return layoutHub(nodes, edges);
    case 'force':
      return layoutForce(nodes, edges);
    case 'radial':
      return layoutRadial(nodes, edges);
    case 'circle':
      return layoutCircle(nodes);
    case 'grid':
      return layoutGrid(nodes);
    case 'tree':
      return layoutTree(nodes, edges);
    case 'star':
      return layoutStar(nodes, edges);
    case 'mesh':
      return layoutMesh(nodes);
    case 'layered':
      return layoutLayered(nodes);
    case 'tier':
      return layoutTier(nodes, edges);
    case 'flow':
      return layoutFlow(nodes, edges);
    default:
      return null;
  }
}
