"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import Link from "next/link";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceX,
  forceY,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { scaleSqrt } from "d3-scale";
import { BOOK_SHORT_NAMES, BOOK_COLORS } from "@/lib/books";

// ── Types ──────────────────────────────────────────────────────────────

interface BookMeta {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
}

interface GlobalNodeData {
  id: number;
  name: string;
  identity_id: string | null;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  books: string[];
  is_corpus_author: boolean;
  author_of: string[] | null;
}

interface GlobalEdgeData {
  s: number;
  t: number;
  w: number;
  b: number[]; // book indices
}

interface PersonIdentity {
  name: string;
  wikipedia_slug?: string;
  description?: string;
  thumbnail?: string;
  thumbnail_url?: string;
  confidence?: number;
}

interface NetworkData {
  book_index: string[];
  nodes: GlobalNodeData[];
  edges: GlobalEdgeData[];
  corpus_authors: Record<string, { cluster_id: number; name: string }>;
}

// Simulation types
interface SimNode extends SimulationNodeDatum {
  id: number;
  name: string;
  identity_id: string | null;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  books: string[];
  is_corpus_author: boolean;
  author_of: string[] | null;
  radius: number;
  portraitUrl?: string;
}

interface SimLink extends SimulationLinkDatum<SimNode> {
  weight: number;
  sharedBooks: string[];
}

// ── Subcategory colors ─────────────────────────────────────────────────

const SUB_COLORS: Record<string, string> = {
  AUTHORITY: "#a855f7",
  SCHOLAR: "#3b82f6",
  PRACTITIONER: "#10b981",
  PATRON: "#f59e0b",
  OTHER_PERSON: "#64748b",
};

// ── Component ──────────────────────────────────────────────────────────

export default function GlobalKnowledgeGraph({ books }: { books: BookMeta[] }) {
  const [network, setNetwork] = useState<NetworkData | null>(null);
  const [identities, setIdentities] = useState<Record<string, PersonIdentity>>({});
  const [loading, setLoading] = useState(true);

  const [minWeight, setMinWeight] = useState(4);
  const [focusedNode, setFocusedNode] = useState<number | null>(null);
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);
  const [, setTick] = useState(0);
  const [failedPortraits, setFailedPortraits] = useState<Set<string>>(new Set());

  // Zoom/pan
  const [vt, setVt] = useState({ scale: 1, panX: 0, panY: 0 });
  const dragRef = useRef<{ startX: number; startY: number; startPanX: number; startPanY: number } | null>(null);

  // Container sizing
  const containerRef = useRef<HTMLDivElement>(null);
  const [dims, setDims] = useState({ width: 900, height: 600 });

  const simRef = useRef<ReturnType<typeof forceSimulation<SimNode>> | null>(null);
  const nodesRef = useRef<SimNode[]>([]);
  const linksRef = useRef<SimLink[]>([]);

  // Load data
  useEffect(() => {
    Promise.all([
      fetch("/data/global_person_network.json").then((r) => r.json()),
      fetch("/data/person_identities.json").then((r) => r.json()).catch(() => ({})),
    ]).then(([net, idents]) => {
      setNetwork(net);
      setIdentities(idents);
      setLoading(false);
    });
  }, []);

  // Responsive sizing — use window.innerWidth directly for reliable full-width
  useEffect(() => {
    const update = () => {
      const w = Math.min(window.innerWidth - 64, 1600); // wider than max-w-7xl (1280) but capped
      const h = w < 500 ? Math.min(500, Math.max(350, w * 1.0)) : Math.min(700, Math.max(500, w * 0.45));
      setDims({ width: w, height: h });
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // Filter graph by minWeight
  const filteredGraph = useMemo(() => {
    if (!network) return { nodes: [], edges: [] };
    const bookIndex = network.book_index;

    const validEdges = network.edges.filter((e) => e.w >= minWeight);
    const nodeIds = new Set<number>();
    for (const e of validEdges) {
      nodeIds.add(e.s);
      nodeIds.add(e.t);
    }
    const validNodes = network.nodes.filter((n) => nodeIds.has(n.id));

    // Resolve book indices to IDs
    const resolvedEdges = validEdges.map((e) => ({
      ...e,
      bookIds: e.b.map((i) => bookIndex[i]),
    }));

    return { nodes: validNodes, edges: resolvedEdges };
  }, [network, minWeight]);

  // Ego-network filter
  const displayGraph = useMemo(() => {
    if (focusedNode === null) return filteredGraph;
    const connected = new Set<number>([focusedNode]);
    for (const e of filteredGraph.edges) {
      if (e.s === focusedNode) connected.add(e.t);
      if (e.t === focusedNode) connected.add(e.s);
    }
    return {
      nodes: filteredGraph.nodes.filter((n) => connected.has(n.id)),
      edges: filteredGraph.edges.filter(
        (e) => e.s === focusedNode || e.t === focusedNode
      ),
    };
  }, [filteredGraph, focusedNode]);

  // Connected IDs for hover highlighting
  const connectedIds = useMemo(() => {
    if (hoveredNode === null) return new Set<number>();
    const s = new Set<number>([hoveredNode]);
    for (const e of displayGraph.edges) {
      if (e.s === hoveredNode) s.add(e.t);
      if (e.t === hoveredNode) s.add(e.s);
    }
    return s;
  }, [hoveredNode, displayGraph]);

  // D3-force simulation
  useEffect(() => {
    if (displayGraph.nodes.length === 0) return;
    const { width, height } = dims;

    const maxCount = Math.max(...displayGraph.nodes.map((n) => n.book_count), 1);
    const rScale = scaleSqrt().domain([1, maxCount]).range([8, 34]);

    const nodes: SimNode[] = displayGraph.nodes.map((n, i) => {
      const angle = (i / displayGraph.nodes.length) * 2 * Math.PI;
      const r = rScale(n.book_count);

      // Portrait
      let portraitUrl: string | undefined;
      if (n.identity_id && identities[n.identity_id]) {
        const ident = identities[n.identity_id];
        if (ident.thumbnail && !failedPortraits.has(n.identity_id)) {
          portraitUrl = `/thumbnails/${ident.thumbnail}`;
        } else if (ident.thumbnail_url && !failedPortraits.has(n.identity_id)) {
          portraitUrl = ident.thumbnail_url;
        }
      }

      return {
        ...n,
        x: width / 2 + Math.cos(angle) * width * 0.42,
        y: height / 2 + Math.sin(angle) * height * 0.42,
        radius: r,
        portraitUrl,
        ...(focusedNode === n.id ? { fx: width / 2, fy: height / 2 } : {}),
      };
    });

    const nodeMap = new Map(nodes.map((n) => [n.id, n]));
    const maxWeight = Math.max(...displayGraph.edges.map((e) => e.w), 1);

    const links: SimLink[] = displayGraph.edges
      .map((e) => ({
        source: nodeMap.get(e.s)!,
        target: nodeMap.get(e.t)!,
        weight: e.w,
        sharedBooks: e.bookIds || [],
      }))
      .filter((l) => l.source && l.target);

    nodesRef.current = nodes;
    linksRef.current = links;

    // Scale force parameters to canvas size so nodes fill the space
    const wScale = width / 900; // 1.0 at 900px, ~1.5 at 1400px
    const linkDistBase = (focusedNode !== null ? 80 : 65) * wScale;
    const linkDistRange = (focusedNode !== null ? 180 : 240) * wScale;

    const sim = forceSimulation<SimNode>(nodes)
      .force(
        "link",
        forceLink<SimNode, SimLink>(links)
          .id((d) => d.id)
          .distance((d) => linkDistBase + (1 - d.weight / maxWeight) * linkDistRange)
          .strength((d) => 0.1 + (d.weight / maxWeight) * 0.3)
      )
      .force("charge", forceManyBody().strength(focusedNode ? -500 : -400).distanceMax(width * 0.6))
      .force("x", forceX<SimNode>(width / 2).strength(0.012))
      .force("y", forceY<SimNode>(height / 2).strength(0.012))
      .force("collide", forceCollide<SimNode>().radius((d) => d.radius + 6).strength(0.7))
      .alpha(1)
      .alphaDecay(0.02)
      .velocityDecay(0.45);

    // Pre-warm
    for (let i = 0; i < 180; i++) {
      sim.tick();
      for (const n of nodes) {
        const pad = 8;
        n.x = Math.max(n.radius + pad, Math.min(width - n.radius - pad, n.x!));
        n.y = Math.max(n.radius + pad, Math.min(height - n.radius - pad - 20, n.y!));
      }
    }
    setTick((t) => t + 1);

    // Gentle settling
    sim.alpha(0.1).alphaDecay(0.04).velocityDecay(0.55);
    sim.on("tick", () => {
      for (const n of nodes) {
        const pad = 8;
        n.x = Math.max(n.radius + pad, Math.min(width - n.radius - pad, n.x!));
        n.y = Math.max(n.radius + pad, Math.min(height - n.radius - pad - 20, n.y!));
      }
      setTick((t) => t + 1);
    });
    simRef.current = sim;

    return () => { sim.stop(); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [displayGraph, dims, focusedNode, identities]);

  // Reset zoom when focus changes
  useEffect(() => {
    setVt({ scale: 1, panX: 0, panY: 0 });
  }, [focusedNode, minWeight]);

  // Zoom handler
  const handleWheel = useCallback((e: React.WheelEvent) => {
    e.preventDefault();
    const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
    setVt((prev) => {
      const newScale = Math.max(0.3, Math.min(4, prev.scale * factor));
      return { ...prev, scale: newScale };
    });
  }, []);

  // Pan handlers
  const handlePointerDown = useCallback((e: React.PointerEvent) => {
    if ((e.target as SVGElement).tagName === "svg" || (e.target as SVGElement).tagName === "rect") {
      dragRef.current = { startX: e.clientX, startY: e.clientY, startPanX: vt.panX, startPanY: vt.panY };
      (e.target as SVGElement).setPointerCapture(e.pointerId);
    }
  }, [vt]);

  const handlePointerMove = useCallback((e: React.PointerEvent) => {
    if (!dragRef.current) return;
    const { startX, startY, startPanX, startPanY } = dragRef.current;
    const dx = e.clientX - startX;
    const dy = e.clientY - startY;
    setVt((prev) => ({ ...prev, panX: startPanX + dx, panY: startPanY + dy }));
  }, []);

  const handlePointerUp = useCallback(() => { dragRef.current = null; }, []);

  const nodes = nodesRef.current;
  const links = linksRef.current;
  const { width, height } = dims;
  const maxWeight = Math.max(...links.map((l) => l.weight), 1);

  if (loading) {
    return <div className="h-[500px] rounded-lg border border-[var(--border)] animate-pulse bg-[var(--card)]" />;
  }

  if (!network || filteredGraph.nodes.length < 2) {
    return (
      <div className="text-center py-16">
        <p className="text-[var(--muted)]">Not enough cross-book person data. Try lowering the minimum shared books.</p>
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {/* Description */}
      <p className="text-sm text-[var(--muted)] max-w-2xl">
        Persons cited across multiple books in the corpus. Edges connect figures who appear in the same books.
        {focusedNode !== null
          ? " Click background to show all."
          : " Click a node to focus its connections."}
      </p>

      {/* Controls */}
      <div className="flex flex-wrap items-center gap-4">
        <div className="flex items-center gap-2">
          <label className="text-xs text-[var(--muted)]">Min shared books:</label>
          <input
            type="range"
            min={2}
            max={6}
            value={minWeight}
            onChange={(e) => { setMinWeight(Number(e.target.value)); setFocusedNode(null); }}
            className="w-24 accent-[var(--accent)]"
          />
          <span className="text-xs font-mono text-[var(--muted)] w-4">{minWeight}</span>
        </div>
        <span className="text-xs text-[var(--muted)]">
          {displayGraph.nodes.length} persons &middot; {displayGraph.edges.length} connections
        </span>
        {focusedNode !== null && (
          <button
            onClick={() => setFocusedNode(null)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            Show all
          </button>
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-3 text-xs text-[var(--muted)]">
        {Object.entries(SUB_COLORS).map(([sub, color]) => (
          <div key={sub} className="flex items-center gap-1.5">
            <span className="w-2 h-2 rounded-full" style={{ backgroundColor: color }} />
            <span>{sub === "OTHER_PERSON" ? "Other" : sub.charAt(0) + sub.slice(1).toLowerCase()}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-2 pl-2 border-l border-[var(--border)]">
          <span className="w-3 h-3 rounded-full border-2 border-amber-500" />
          <span>Corpus author</span>
        </div>
        <div className="flex items-center gap-1.5">
          <span className="flex gap-0.5">
            {["#22c55e", "#f59e0b", "#3b82f6"].map((c) => (
              <span key={c} className="w-1.5 h-1.5 rounded-full" style={{ backgroundColor: c }} />
            ))}
          </span>
          <span>Book sources</span>
        </div>
      </div>

      {/* Graph — breaks out to near-full viewport width */}
      <div
        ref={containerRef}
        className="relative rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden"
        style={{ width: `${dims.width}px`, marginLeft: `calc(50% - ${dims.width / 2}px)` }}
      >
        <svg
          viewBox={`0 0 ${width} ${height}`}
          style={{ width: "100%", height: `${height}px`, maxHeight: 700 }}
          onWheel={handleWheel}
          onPointerDown={handlePointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          className="select-none"
        >
          <defs>
            <radialGradient id="gn-sheen" cx="35%" cy="35%" r="65%">
              <stop offset="0%" stopColor="white" stopOpacity={0.25} />
              <stop offset="100%" stopColor="white" stopOpacity={0} />
            </radialGradient>
            <filter id="gn-shadow" x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx={0} dy={1} stdDeviation={2} floodOpacity={0.15} />
            </filter>
            {/* Portrait patterns */}
            {nodes.filter((n) => n.portraitUrl).map((n) => (
              <pattern
                key={`portrait-${n.id}`}
                id={`gp-${n.id}`}
                patternUnits="objectBoundingBox"
                width={1}
                height={1}
              >
                <image
                  href={n.portraitUrl}
                  x={0}
                  y={0}
                  width={n.radius * 2}
                  height={n.radius * 2}
                  preserveAspectRatio="xMidYMid slice"
                  onError={() => setFailedPortraits((s) => new Set([...s, n.identity_id!]))}
                />
              </pattern>
            ))}
          </defs>
          <rect x={0} y={0} width={width} height={height} fill="transparent" onClick={() => setFocusedNode(null)} />
          <g transform={`translate(${vt.panX},${vt.panY}) scale(${vt.scale})`}>
            {/* Edges */}
            {links.map((link, i) => {
              const src = link.source as SimNode;
              const tgt = link.target as SimNode;
              if (!src.x || !tgt.x) return null;

              const isHighlighted = hoveredNode !== null &&
                ((src.id === hoveredNode || tgt.id === hoveredNode));
              const isDimmed = hoveredNode !== null && !isHighlighted;

              const dx = tgt.x! - src.x!;
              const dy = tgt.y! - src.y!;
              const len = Math.sqrt(dx * dx + dy * dy) || 1;
              const curve = Math.min(15, len * 0.08);
              const nx = -dy / len;
              const ny = dx / len;
              const cx = (src.x! + tgt.x!) / 2 + nx * curve;
              const cy = (src.y! + tgt.y!) / 2 + ny * curve;

              return (
                <path
                  key={i}
                  d={`M${src.x},${src.y} Q${cx},${cy} ${tgt.x},${tgt.y}`}
                  fill="none"
                  stroke={isHighlighted ? "var(--accent)" : "var(--foreground)"}
                  strokeWidth={0.5 + (link.weight / maxWeight) * 3}
                  strokeOpacity={isDimmed ? 0.04 : isHighlighted ? 0.5 : 0.08 + (link.weight / maxWeight) * 0.12}
                  style={{ pointerEvents: "none" }}
                />
              );
            })}

            {/* Nodes — sorted so active/hovered on top */}
            {[...nodes]
              .sort((a, b) => {
                const scoreA = a.id === hoveredNode ? 2 : connectedIds.has(a.id) ? 1 : 0;
                const scoreB = b.id === hoveredNode ? 2 : connectedIds.has(b.id) ? 1 : 0;
                return scoreA - scoreB;
              })
              .map((node) => {
                const isActive = node.id === hoveredNode || node.id === focusedNode;
                const isConnected = connectedIds.has(node.id);
                const isDimmed = hoveredNode !== null && !isActive && !isConnected;
                const color = SUB_COLORS[node.subcategory] || "#64748b";
                const hasPortrait = !!node.portraitUrl && !failedPortraits.has(node.identity_id || "");

                return (
                  <g
                    key={node.id}
                    style={{ cursor: "pointer" }}
                    onClick={(e) => {
                      e.stopPropagation();
                      setFocusedNode(focusedNode === node.id ? null : node.id);
                    }}
                    onPointerEnter={() => setHoveredNode(node.id)}
                    onPointerLeave={() => setHoveredNode(null)}
                    opacity={isDimmed ? 0.2 : 1}
                  >
                    {/* Corpus author ring */}
                    {node.is_corpus_author && (
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius + 5}
                        fill="none"
                        stroke="#f59e0b"
                        strokeWidth={2.5}
                        strokeDasharray="4 2"
                        opacity={isDimmed ? 0.2 : 0.8}
                      />
                    )}

                    {/* Book-colored arc segments */}
                    {!isDimmed && node.books.length > 1 && node.books.map((bid, bi) => {
                      const total = node.books.length;
                      const gap = 0.06; // small gap between arcs
                      const startAngle = (bi / total) * 2 * Math.PI - Math.PI / 2 + gap;
                      const endAngle = ((bi + 1) / total) * 2 * Math.PI - Math.PI / 2 - gap;
                      const arcR = node.radius + (node.is_corpus_author ? 9 : 4);
                      const x1 = node.x! + Math.cos(startAngle) * arcR;
                      const y1 = node.y! + Math.sin(startAngle) * arcR;
                      const x2 = node.x! + Math.cos(endAngle) * arcR;
                      const y2 = node.y! + Math.sin(endAngle) * arcR;
                      const largeArc = (endAngle - startAngle) > Math.PI ? 1 : 0;
                      return (
                        <path
                          key={`arc-${bid}`}
                          d={`M${x1},${y1} A${arcR},${arcR} 0 ${largeArc} 1 ${x2},${y2}`}
                          fill="none"
                          stroke={BOOK_COLORS[bid] || "#888"}
                          strokeWidth={2}
                          strokeLinecap="round"
                          opacity={0.7}
                          style={{ pointerEvents: "none" }}
                        />
                      );
                    })}

                    {/* Node circle */}
                    {hasPortrait ? (
                      <>
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.radius}
                          fill={`url(#gp-${node.id})`}
                          stroke={color}
                          strokeWidth={isActive ? 3 : 2}
                          filter="url(#gn-shadow)"
                        />
                      </>
                    ) : (
                      <>
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.radius}
                          fill={color}
                          stroke={isActive ? "var(--foreground)" : color}
                          strokeWidth={isActive ? 2 : 1}
                          filter="url(#gn-shadow)"
                        />
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.radius}
                          fill="url(#gn-sheen)"
                          style={{ pointerEvents: "none" }}
                        />
                      </>
                    )}

                    {/* Corpus author badge */}
                    {node.is_corpus_author && !isDimmed && (
                      <g transform={`translate(${node.x! + node.radius * 0.6},${node.y! - node.radius * 0.6})`}>
                        <circle r={7} fill="#f59e0b" stroke="var(--background)" strokeWidth={1.5} />
                        <text textAnchor="middle" dy="3.5" fontSize="9" fill="white" fontWeight="bold" style={{ pointerEvents: "none" }}>A</text>
                      </g>
                    )}

                    {/* Label */}
                    <text
                      x={node.x}
                      y={node.y! + node.radius + 12}
                      textAnchor="middle"
                      fontSize={isActive ? 11 : isConnected ? 10 : Math.max(7, Math.min(9, node.radius * 0.7))}
                      fontWeight={isActive ? 600 : 400}
                      fill="var(--foreground)"
                      stroke="var(--background)"
                      strokeWidth={3}
                      paintOrder="stroke"
                      opacity={isDimmed ? 0.3 : 1}
                      style={{ pointerEvents: "none" }}
                    >
                      {node.name.length > 18 ? node.name.slice(0, 16) + "\u2026" : node.name}
                    </text>
                  </g>
                );
              })}
          </g>
        </svg>

        {/* Tooltip */}
        {hoveredNode !== null && (() => {
          const node = nodes.find((n) => n.id === hoveredNode);
          if (!node || !node.x) return null;
          const ident = node.identity_id ? identities[node.identity_id] : null;
          const sx = node.x! * vt.scale + vt.panX;
          const sy = node.y! * vt.scale + vt.panY;
          const left = sx > width * 0.6;

          return (
            <div
              className="absolute z-30 pointer-events-none"
              style={{
                left: left ? undefined : `${sx + node.radius + 12}px`,
                right: left ? `${width - sx + node.radius + 12}px` : undefined,
                top: `${Math.max(8, sy - 20)}px`,
              }}
            >
              <div className="bg-[var(--foreground)] text-[var(--background)] rounded-lg px-3 py-2.5 text-xs shadow-xl max-w-[240px]">
                <div className="font-semibold text-sm mb-1">{node.name}</div>
                {ident?.description && (
                  <div className="opacity-70 mb-1.5 leading-snug">
                    {ident.description.length > 100
                      ? ident.description.slice(0, 97) + "\u2026"
                      : ident.description}
                  </div>
                )}
                <div className="opacity-50 mb-1">{node.book_count} books &middot; {node.total_mentions} mentions</div>
                {node.is_corpus_author && node.author_of && (
                  <div className="text-amber-400 mb-1">
                    Author of {node.author_of.map((bid) => BOOK_SHORT_NAMES[bid] || bid).join(", ")}
                  </div>
                )}
                <div className="border-t border-current/20 pt-1.5 mt-1 space-y-0.5">
                  {node.books.map((bid) => (
                    <div key={bid} className="flex items-center gap-1.5">
                      <span
                        className="w-1.5 h-1.5 rounded-full shrink-0"
                        style={{ backgroundColor: BOOK_COLORS[bid] || "#888" }}
                      />
                      <span className="opacity-70">{BOOK_SHORT_NAMES[bid] || bid}</span>
                    </div>
                  ))}
                </div>
                {/* Top connections */}
                {(() => {
                  const conns = links
                    .filter((l) => (l.source as SimNode).id === node.id || (l.target as SimNode).id === node.id)
                    .sort((a, b) => b.weight - a.weight)
                    .slice(0, 4);
                  if (conns.length === 0) return null;
                  return (
                    <div className="border-t border-current/20 pt-1.5 mt-1 space-y-0.5">
                      <div className="opacity-40 mb-0.5">Top connections:</div>
                      {conns.map((c, i) => {
                        const other = (c.source as SimNode).id === node.id
                          ? (c.target as SimNode)
                          : (c.source as SimNode);
                        return (
                          <div key={i} className="flex items-center justify-between gap-2">
                            <span className="opacity-80 truncate">{other.name}</span>
                            <span className="opacity-40 font-mono shrink-0">{c.weight} books</span>
                          </div>
                        );
                      })}
                    </div>
                  );
                })()}
              </div>
            </div>
          );
        })()}

        {/* Zoom controls */}
        <div className="absolute top-3 right-3 flex flex-col gap-1">
          <button
            onClick={() => setVt((p) => ({ ...p, scale: Math.min(4, p.scale * 1.3) }))}
            className="w-7 h-7 rounded border border-[var(--border)] bg-[var(--card)] text-sm flex items-center justify-center hover:bg-[var(--border)]"
          >+</button>
          <button
            onClick={() => setVt((p) => ({ ...p, scale: Math.max(0.3, p.scale / 1.3) }))}
            className="w-7 h-7 rounded border border-[var(--border)] bg-[var(--card)] text-sm flex items-center justify-center hover:bg-[var(--border)]"
          >&minus;</button>
          <button
            onClick={() => setVt({ scale: 1, panX: 0, panY: 0 })}
            className="w-7 h-7 rounded border border-[var(--border)] bg-[var(--card)] text-[10px] flex items-center justify-center hover:bg-[var(--border)]"
          >1:1</button>
        </div>
      </div>

      {/* Directory */}
      <div className="grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 gap-1.5 text-xs">
        {displayGraph.nodes
          .sort((a, b) => b.book_count - a.book_count || b.total_mentions - a.total_mentions)
          .slice(0, 40)
          .map((n) => {
            const color = SUB_COLORS[n.subcategory] || "#64748b";
            return (
              <button
                key={n.id}
                onClick={() => setFocusedNode(focusedNode === n.id ? null : n.id)}
                onPointerEnter={() => setHoveredNode(n.id)}
                onPointerLeave={() => setHoveredNode(null)}
                className={`flex items-center gap-1.5 px-2 py-1.5 rounded border transition-colors text-left ${
                  focusedNode === n.id
                    ? "border-[var(--accent)] bg-[var(--accent)]/10"
                    : "border-[var(--border)] hover:bg-[var(--border)]/40"
                }`}
              >
                <span className="w-2 h-2 rounded-full shrink-0" style={{ backgroundColor: color }} />
                <span className="truncate">{n.name}</span>
                <span className="text-[var(--muted)] font-mono ml-auto shrink-0">{n.book_count}</span>
              </button>
            );
          })}
      </div>
    </div>
  );
}
