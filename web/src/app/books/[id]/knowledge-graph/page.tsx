"use client";

import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import { useRouter } from "next/navigation";
import { useBookContext } from "../BookContext";
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

// ── Types ────────────────────────────────────────────────────────────────────

interface PersonNode {
  id: string;
  name: string;
  aliases: string[];
  count: number;
  subcategory: string;
  contexts: string[];
}

interface PersonEdge {
  source: string;
  target: string;
  weight: number;
  excerpts: string[];
}

interface PersonGraph {
  book_id: string;
  book_title: string;
  book_author: string;
  book_year: number;
  nodes: PersonNode[];
  edges: PersonEdge[];
}

interface GraphNode extends SimulationNodeDatum {
  id: string;
  name: string;
  aliases: string[];
  count: number;
  subcategory: string;
  contexts: string[];
  radius: number;
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  weight: number;
  excerpts: string[];
}

interface PersonIdentity {
  name: string;
  wikipedia_slug?: string;
  description?: string;
  thumbnail?: string | null;
  thumbnail_url?: string;
  confidence?: number;
  alias_of?: string;
}

type IdentityMap = Record<string, PersonIdentity>;

interface ConcordanceClusterRef {
  id: number;
  stable_key?: string;
  canonical_name: string;
  members: { entity_id: string; book_id: string }[];
}

function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function resolveNodeUrl(
  nodeId: string,
  bookId: string,
  clusters: ConcordanceClusterRef[],
  identities: IdentityMap,
): string | null {
  const findCluster = (id: string): ConcordanceClusterRef | null => {
    // 1. Match by member entity_id in same book
    for (const c of clusters) {
      if (c.members.some(m => m.entity_id === id && m.book_id === bookId)) return c;
    }
    // 2. Match by member entity_id in any book
    for (const c of clusters) {
      if (c.members.some(m => m.entity_id === id)) return c;
    }
    // 3. Match by canonical_name slug
    for (const c of clusters) {
      if (slugify(c.canonical_name) === id) return c;
    }
    return null;
  };

  // Try direct ID
  let cluster = findCluster(nodeId);

  // Try alias resolution via person_identities
  if (!cluster) {
    const alias = identities[nodeId]?.alias_of;
    if (alias) cluster = findCluster(alias);
  }

  if (cluster) {
    if (cluster.stable_key) {
      return `/concordance/${cluster.stable_key}`;
    }
    const base = slugify(cluster.canonical_name);
    const hasCollision = clusters.some(
      c => c.id !== cluster!.id && slugify(c.canonical_name) === base
    );
    return `/concordance/${hasCollision ? `${base}-${cluster.id}` : base}`;
  }

  // Fallback to book entity page
  return `/books/${bookId}/entity/${nodeId}`;
}

// ── Constants ────────────────────────────────────────────────────────────────

const SUBCATEGORY_COLORS: Record<string, string> = {
  AUTHORITY: "#a855f7",
  SCHOLAR: "#3b82f6",
  PRACTITIONER: "#10b981",
  PATRON: "#f59e0b",
  OTHER_PERSON: "#64748b",
};

const SUBCATEGORY_LABELS: Record<string, string> = {
  AUTHORITY: "Classical Authority",
  SCHOLAR: "Scholar / Naturalist",
  PRACTITIONER: "Practitioner",
  PATRON: "Patron / Noble",
  OTHER_PERSON: "Other",
};

// ── Component ────────────────────────────────────────────────────────────────

export default function KnowledgeGraphPage() {
  const { bookData } = useBookContext();
  const bookId = bookData.book.id;

  const router = useRouter();
  const [graphData, setGraphData] = useState<PersonGraph | null>(null);
  const [identities, setIdentities] = useState<IdentityMap>({});
  const [clusters, setClusters] = useState<ConcordanceClusterRef[]>([]);
  const [loading, setLoading] = useState(true);
  const [focusedNode, setFocusedNode] = useState<string | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [hoveredDirectoryNode, setHoveredDirectoryNode] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      fetch("/data/person_graphs.json").then((r) => r.json()),
      fetch("/data/person_identities.json").then((r) => r.json()).catch(() => ({})),
      fetch("/data/concordance.json").then((r) => r.json()).catch(() => ({ clusters: [] })),
    ])
      .then(([allGraphs, allIdentities, concordance]: [Record<string, PersonGraph>, IdentityMap, { clusters: ConcordanceClusterRef[] }]) => {
        setGraphData(allGraphs[bookId] || null);
        setIdentities(allIdentities);
        setClusters(concordance.clusters.map(c => ({
          id: c.id,
          canonical_name: c.canonical_name,
          members: c.members.map(m => ({ entity_id: m.entity_id, book_id: m.book_id })),
        })));
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [bookId]);

  const handleNavigateNode = useCallback(
    (nodeId: string) => {
      const url = resolveNodeUrl(nodeId, bookId, clusters, identities);
      if (url) router.push(url);
    },
    [bookId, clusters, identities, router]
  );

  // Clear focus when graph data changes
  useEffect(() => {
    setFocusedNode(null);
    setSearchQuery("");
  }, [bookId]);

  if (loading) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted)] mb-1">
            Knowledge Graph
          </h2>
          <p className="text-sm text-[var(--muted)]">Loading person network...</p>
        </div>
        <div className="h-[460px] rounded-lg border border-[var(--border)] animate-pulse bg-[var(--card)]" />
      </div>
    );
  }

  if (!graphData || graphData.nodes.length < 2) {
    return (
      <div className="space-y-6">
        <div>
          <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted)] mb-1">
            Knowledge Graph
          </h2>
          <p className="text-sm text-[var(--muted)]">
            Not enough person data to build a knowledge graph for this book.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted)] mb-1">
          Knowledge Graph
        </h2>
        <p className="text-sm text-[var(--muted)]">
          Co-citation network of people referenced in{" "}
          <span className="text-[var(--foreground)]">{bookData.book.title}</span>.
          Lines connect people who appear together in the same passage. Thicker lines
          indicate more co-occurrences.{" "}
          <span className="opacity-70">Click a node to see its ego-network. Click the center node again to visit its page.</span>
        </p>
      </div>

      <PersonNetwork
        graph={graphData}
        identities={identities}
        focusedNode={focusedNode}
        onFocusNode={setFocusedNode}
        onNavigateNode={handleNavigateNode}
        hoveredDirectoryNode={hoveredDirectoryNode}
      />

      <PersonDirectory
        graph={graphData}
        identities={identities}
        focusedNode={focusedNode}
        searchQuery={searchQuery}
        onSearchChange={setSearchQuery}
        onFocusNode={setFocusedNode}
        onHoverNode={setHoveredDirectoryNode}
      />

      {/* Stats row */}
      <div className="grid grid-cols-3 gap-4">
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="text-2xl font-semibold">{graphData.nodes.length}</div>
          <div className="text-xs text-[var(--muted)] mt-1">People</div>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="text-2xl font-semibold">{graphData.edges.length}</div>
          <div className="text-xs text-[var(--muted)] mt-1">Co-citations</div>
        </div>
        <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] p-4">
          <div className="text-2xl font-semibold">
            {graphData.edges.length > 0
              ? Math.max(...graphData.edges.map((e) => e.weight))
              : 0}
          </div>
          <div className="text-xs text-[var(--muted)] mt-1">Strongest link</div>
        </div>
      </div>

      {/* Top co-citations table */}
      <TopCoCitations graph={graphData} />
    </div>
  );
}

// ── Force-directed network ───────────────────────────────────────────────────

function PersonNetwork({
  graph,
  identities,
  focusedNode,
  onFocusNode,
  onNavigateNode,
  hoveredDirectoryNode,
}: {
  graph: PersonGraph;
  identities: IdentityMap;
  focusedNode: string | null;
  onFocusNode: (id: string | null) => void;
  onNavigateNode: (id: string) => void;
  hoveredDirectoryNode: string | null;
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<ReturnType<typeof forceSimulation<GraphNode>> | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphLink[]>([]);

  const [, setTick] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [selectedNode, setSelectedNode] = useState<GraphNode | null>(null);
  const [dragNode, setDragNode] = useState<GraphNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 900, height: 700 });
  const wasDraggedRef = useRef(false);
  const [failedPortraits, setFailedPortraits] = useState<Set<string>>(new Set());

  // Zoom & pan — single atomic state to avoid cross-setter race conditions
  const [vt, setVt] = useState({ scale: 1, panX: 0, panY: 0 });
  const isPanningRef = useRef(false);
  const panStartRef = useRef({ x: 0, y: 0, panX: 0, panY: 0 });

  // Get portrait image URL for a node: local file > remote URL > null
  const getPortraitUrl = useCallback(
    (nodeId: string): string | null => {
      if (failedPortraits.has(nodeId)) return null;
      const ident = identities[nodeId];
      if (!ident) return null;
      if (ident.thumbnail) return `/thumbnails/${ident.thumbnail}`;
      if (ident.thumbnail_url) return ident.thumbnail_url;
      return null;
    },
    [identities, failedPortraits]
  );

  const handlePortraitError = useCallback((nodeId: string) => {
    setFailedPortraits((prev) => new Set(prev).add(nodeId));
  }, []);

  // Responsive sizing — bigger graph
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width;
      setDimensions({
        width: w,
        height: w < 500
          ? Math.min(500, Math.max(320, w * 0.9))   // mobile: taller ratio
          : Math.min(725, Math.max(475, w * 0.78)),  // desktop
      });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Compute filtered graph for ego-network mode
  const filteredGraph = useMemo(() => {
    if (!focusedNode) return { nodes: graph.nodes, edges: graph.edges };

    const connectedIds = new Set<string>();
    connectedIds.add(focusedNode);
    for (const e of graph.edges) {
      if (e.source === focusedNode) connectedIds.add(e.target);
      if (e.target === focusedNode) connectedIds.add(e.source);
    }

    const nodes = graph.nodes.filter((n) => connectedIds.has(n.id));
    const edges = graph.edges.filter(
      (e) => e.source === focusedNode || e.target === focusedNode
    );

    return { nodes, edges };
  }, [graph, focusedNode]);

  // Reset zoom/pan when focus changes
  useEffect(() => {
    setVt({ scale: 1, panX: 0, panY: 0 });
  }, [focusedNode]);

  // Convert screen coordinates to graph coordinates (accounting for zoom/pan)
  const screenToGraph = useCallback(
    (clientX: number, clientY: number) => {
      const svg = svgRef.current;
      if (!svg) return { x: 0, y: 0 };
      const rect = svg.getBoundingClientRect();
      const svgX = (clientX - rect.left) * (dimensions.width / rect.width);
      const svgY = (clientY - rect.top) * (dimensions.height / rect.height);
      return {
        x: (svgX - vt.panX) / vt.scale,
        y: (svgY - vt.panY) / vt.scale,
      };
    },
    [dimensions, vt]
  );

  // Build graph + start simulation (pre-warmed for smooth appearance)
  useEffect(() => {
    const { width, height } = dimensions;
    const { nodes: activeNodes, edges: activeEdges } = filteredGraph;

    const maxCount = Math.max(...activeNodes.map((n) => n.count), 1);
    const radiusScale = scaleSqrt().domain([1, maxCount]).range([6, 32]);
    const maxWeight = Math.max(...activeEdges.map((e) => e.weight), 1);

    // Spread initial positions across an ellipse that uses the full space
    const graphNodes: GraphNode[] = activeNodes.map((n, i) => {
      const angle = (i / activeNodes.length) * 2 * Math.PI;
      const isFocused = focusedNode && n.id === focusedNode;
      return {
        ...n,
        radius: radiusScale(n.count),
        x: isFocused ? width / 2 : width / 2 + Math.cos(angle) * width * 0.42,
        y: isFocused ? height / 2 : height / 2 + Math.sin(angle) * height * 0.38,
        fx: isFocused ? width / 2 : undefined,
        fy: isFocused ? height / 2 : undefined,
      };
    });

    const nodeIdSet = new Set(graphNodes.map((n) => n.id));
    const graphLinks: GraphLink[] = activeEdges
      .filter((e) => nodeIdSet.has(e.source) && nodeIdSet.has(e.target))
      .map((e) => ({
        source: e.source,
        target: e.target,
        weight: e.weight,
        excerpts: e.excerpts,
      }));

    nodesRef.current = graphNodes;
    linksRef.current = graphLinks;

    simRef.current?.stop();

    const chargeStrength = focusedNode ? -450 : -350;
    const linkDistBase = focusedNode ? 80 : 55;
    const linkDistRange = focusedNode ? 150 : 130;

    const sim = forceSimulation<GraphNode>(graphNodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(graphLinks)
          .id((d) => d.id)
          .distance((d) => linkDistBase + (1 - d.weight / maxWeight) * linkDistRange)
          .strength((d) => 0.15 + (d.weight / maxWeight) * 0.35)
      )
      .force("charge", forceManyBody().strength(chargeStrength).distanceMax(500))
      .force("x", forceX<GraphNode>(width / 2).strength(width > height ? 0.018 : 0.04))
      .force("y", forceY<GraphNode>(height / 2).strength(width > height ? 0.045 : 0.02))
      .force(
        "collide",
        forceCollide<GraphNode>()
          .radius((d) => d.radius + 6)
          .strength(0.8)
      )
      .alpha(1)
      .alphaDecay(0.02)
      .velocityDecay(0.45);

    // Pre-warm: run 180 ticks silently so layout arrives pre-settled
    const pad = 8;
    const padBottom = 28; // extra space for label text below nodes
    sim.stop();
    for (let i = 0; i < 180; i++) {
      sim.tick();
      for (const n of graphNodes) {
        const p = n.radius + pad;
        if (n.fx == null) n.x = Math.max(p, Math.min(width - p, n.x!));
        if (n.fy == null) n.y = Math.max(p, Math.min(height - n.radius - padBottom, n.y!));
      }
    }

    // Show the pre-warmed layout immediately
    setTick((t) => t + 1);

    // Continue with gentle fine-tuning (barely perceptible motion)
    sim.alpha(0.12).alphaDecay(0.04).velocityDecay(0.55);
    sim.on("tick", () => {
      for (const n of graphNodes) {
        const p = n.radius + pad;
        if (n.fx == null) n.x = Math.max(p, Math.min(width - p, n.x!));
        if (n.fy == null) n.y = Math.max(p, Math.min(height - n.radius - padBottom, n.y!));
      }
      setTick((t) => t + 1);
    });
    sim.restart();

    simRef.current = sim;
    return () => {
      sim.stop();
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [graph, dimensions.width, focusedNode]);

  // Drag handlers (zoom/pan-aware)
  const handlePointerDown = useCallback((e: React.PointerEvent, node: GraphNode) => {
    e.preventDefault();
    e.stopPropagation();
    (e.target as Element).setPointerCapture(e.pointerId);
    node.fx = node.x;
    node.fy = node.y;
    wasDraggedRef.current = false;
    setDragNode(node);
    setHoveredNode(null);
    simRef.current?.alphaTarget(0.3).restart();
  }, []);

  const handlePointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (dragNode && svgRef.current) {
        wasDraggedRef.current = true;
        const { x, y } = screenToGraph(e.clientX, e.clientY);
        dragNode.fx = x;
        dragNode.fy = y;
      } else if (isPanningRef.current && svgRef.current) {
        const svg = svgRef.current;
        const rect = svg.getBoundingClientRect();
        const dx = (e.clientX - panStartRef.current.x) * (dimensions.width / rect.width);
        const dy = (e.clientY - panStartRef.current.y) * (dimensions.height / rect.height);
        setVt((prev) => ({
          ...prev,
          panX: panStartRef.current.panX + dx,
          panY: panStartRef.current.panY + dy,
        }));
      }
    },
    [dragNode, dimensions, screenToGraph]
  );

  const handlePointerUp = useCallback(() => {
    if (dragNode) {
      if (focusedNode && dragNode.id === focusedNode) {
        dragNode.fx = dimensions.width / 2;
        dragNode.fy = dimensions.height / 2;
      } else {
        dragNode.fx = null;
        dragNode.fy = null;
      }
      setDragNode(null);
      simRef.current?.alphaTarget(0);
    }
    isPanningRef.current = false;
  }, [dragNode, focusedNode, dimensions]);

  const handleBackgroundPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      isPanningRef.current = true;
      panStartRef.current = {
        x: e.clientX,
        y: e.clientY,
        panX: vt.panX,
        panY: vt.panY,
      };
    },
    [vt.panX, vt.panY]
  );

  const handleWheel = useCallback(
    (e: WheelEvent) => {
      e.preventDefault();
      const factor = e.deltaY < 0 ? 1.08 : 1 / 1.08;
      const { width: w, height: h } = dimensions;
      setVt((prev) => {
        const nextScale = Math.min(4, Math.max(0.25, prev.scale * factor));
        const ratio = nextScale / prev.scale;
        return {
          scale: nextScale,
          panX: w / 2 - (w / 2 - prev.panX) * ratio,
          panY: h / 2 - (h / 2 - prev.panY) * ratio,
        };
      });
    },
    [dimensions]
  );

  // Attach wheel listener with { passive: false } to allow preventDefault
  useEffect(() => {
    const svg = svgRef.current;
    if (!svg) return;
    svg.addEventListener("wheel", handleWheel, { passive: false });
    return () => svg.removeEventListener("wheel", handleWheel);
  }, [handleWheel]);

  const handleNodeClick = useCallback(
    (node: GraphNode) => {
      if (wasDraggedRef.current) return;
      if (focusedNode === node.id) {
        // Clicking the focused center node navigates to the person's page
        onNavigateNode(node.id);
      } else {
        onFocusNode(node.id);
      }
    },
    [focusedNode, onFocusNode, onNavigateNode]
  );

  const nodes = nodesRef.current;
  const links = linksRef.current;
  const { width, height } = dimensions;

  // Find the directory-hovered node in the current graph
  const directoryHoveredGraphNode = useMemo(() => {
    if (!hoveredDirectoryNode) return null;
    return nodes.find((n) => n.id === hoveredDirectoryNode) || null;
  }, [hoveredDirectoryNode, nodes]);

  const activeNode = hoveredNode || directoryHoveredGraphNode || selectedNode;

  // Connected nodes for highlighting
  const connectedIds = useMemo(() => {
    if (!activeNode) return new Set<string>();
    const ids = new Set<string>();
    for (const l of links) {
      const s = typeof l.source === "object" ? (l.source as GraphNode).id : String(l.source);
      const t = typeof l.target === "object" ? (l.target as GraphNode).id : String(l.target);
      if (s === activeNode.id) ids.add(t);
      if (t === activeNode.id) ids.add(s);
    }
    return ids;
  }, [activeNode, links]);

  // Subcategories present in this graph
  const subcategories = useMemo(() => {
    const cats = new Set(nodes.map((n) => n.subcategory));
    return Array.from(cats).sort(
      (a, b) =>
        (Object.keys(SUBCATEGORY_COLORS).indexOf(a) + 1 || 99) -
        (Object.keys(SUBCATEGORY_COLORS).indexOf(b) + 1 || 99)
    );
  }, [nodes]);

  if (nodes.length === 0) return null;

  const maxWeight = Math.max(...links.map((l) => l.weight), 1);

  // Find focused node name for the back button
  const focusedNodeName = focusedNode
    ? graph.nodes.find((n) => n.id === focusedNode)?.name || focusedNode
    : null;

  return (
    <div className="space-y-3">
      {/* Toolbar row */}
      {focusedNode && (
        <div className="flex items-center gap-3">
          <button
            onClick={() => onFocusNode(null)}
            className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium rounded-md border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--accent)] hover:text-white transition-colors"
          >
            <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M19 12H5M12 19l-7-7 7-7" />
            </svg>
            Show all
          </button>
          <span className="text-sm text-[var(--muted)]">
            Showing connections of <span className="text-[var(--foreground)] font-medium">{focusedNodeName}</span>
          </span>
        </div>
      )}

      <div ref={containerRef} className="w-full relative">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full rounded-lg border border-[var(--border)] select-none"
          style={{
            height: `${height}px`,
            maxHeight: "725px",
            touchAction: "none",
            background:
              "radial-gradient(ellipse at center, var(--card) 0%, var(--background) 100%)",
          }}
          onPointerDown={handleBackgroundPointerDown}
          onPointerMove={handlePointerMove}
          onPointerUp={handlePointerUp}
          onPointerLeave={handlePointerUp}
          onClick={() => {
            if (!wasDraggedRef.current) setSelectedNode(null);
          }}
          role="img"
          aria-label={`Co-citation network showing ${nodes.length} people and ${links.length} connections`}
        >
          {/* Defs: gradients, filters, portrait patterns */}
          <defs>
            {/* Sheen overlay for non-portrait nodes */}
            <radialGradient id="node-sheen" cx="38%" cy="32%" r="65%">
              <stop offset="0%" stopColor="white" stopOpacity="0.3"/>
              <stop offset="100%" stopColor="white" stopOpacity="0"/>
            </radialGradient>
            {/* Subtle shadow for portrait nodes */}
            <filter id="node-shadow" x="-25%" y="-25%" width="150%" height="150%">
              <feDropShadow dx="0" dy="1" stdDeviation="2" floodOpacity="0.15"/>
            </filter>
            {/* Portrait image patterns for nodes with thumbnails */}
            {nodes.map((node) => {
              const url = getPortraitUrl(node.id);
              if (!url) return null;
              const d = node.radius * 2;
              return (
                <pattern
                  key={`portrait-${node.id}`}
                  id={`portrait-${node.id}`}
                  patternUnits="objectBoundingBox"
                  width="1"
                  height="1"
                >
                  <image
                    href={url}
                    width={d}
                    height={d}
                    preserveAspectRatio="xMidYMid slice"
                    onError={() => handlePortraitError(node.id)}
                  />
                </pattern>
              );
            })}
          </defs>
          <rect width={width} height={height} fill="transparent" />

          <g transform={`translate(${vt.panX},${vt.panY}) scale(${vt.scale})`}>
          {/* Edges */}
          {links.map((link, i) => {
            const source = link.source as GraphNode;
            const target = link.target as GraphNode;
            if (source.x == null || target.x == null) return null;

            const sid = typeof source === "object" ? source.id : String(source);
            const tid = typeof target === "object" ? target.id : String(target);
            const isHighlighted =
              activeNode &&
              ((sid === activeNode.id && connectedIds.has(tid)) ||
                (tid === activeNode.id && connectedIds.has(sid)));
            const isDimmed = activeNode && !isHighlighted;
            const sw = 0.5 + (link.weight / maxWeight) * 4;

            // Curved edges for better visibility
            const mx = (source.x! + target.x!) / 2;
            const my = (source.y! + target.y!) / 2;
            const dx = target.x! - source.x!;
            const dy = target.y! - source.y!;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            const curve = Math.min(20, len * 0.1);
            const cx = mx - (dy / len) * curve;
            const cy = my + (dx / len) * curve;

            const baseOpacity = focusedNode
              ? 0.18 + (link.weight / maxWeight) * 0.3
              : 0.1 + (link.weight / maxWeight) * 0.22;

            return (
              <path
                key={i}
                d={`M${source.x},${source.y} Q${cx},${cy} ${target.x},${target.y}`}
                fill="none"
                stroke={isHighlighted ? "var(--accent)" : "#8b95a5"}
                strokeOpacity={isDimmed ? 0.05 : isHighlighted ? 0.6 : baseOpacity}
                strokeWidth={isHighlighted ? Math.max(sw, 1.5) : sw}
                strokeLinecap="round"
                style={{ transition: "stroke-opacity 0.2s, stroke-width 0.15s" }}
              />
            );
          })}

          {/* Nodes — sorted so hovered/selected renders on top */}
          {nodes
            .slice()
            .sort((a, b) => {
              if (activeNode?.id === a.id) return 1;
              if (activeNode?.id === b.id) return -1;
              if (connectedIds.has(a.id)) return 1;
              if (connectedIds.has(b.id)) return -1;
              return 0;
            })
            .map((node) => {
              if (node.x == null || node.y == null) return null;
              const color = SUBCATEGORY_COLORS[node.subcategory] || "#64748b";
              const isActive = activeNode?.id === node.id;
              const isConnected = activeNode ? connectedIds.has(node.id) : false;
              const isDimmed = activeNode && !isActive && !isConnected;
              const isFocusedCenter = focusedNode === node.id;
              const hasPortrait = !!getPortraitUrl(node.id);

              return (
                <g
                  key={node.id}
                  style={{ cursor: dragNode ? "grabbing" : "pointer" }}
                  onPointerDown={(e) => handlePointerDown(e, node)}
                  onMouseEnter={() => {
                    if (!dragNode) setHoveredNode(node);
                  }}
                  onMouseLeave={() => {
                    if (!dragNode) setHoveredNode(null);
                  }}
                  onClick={(e) => {
                    e.stopPropagation();
                    handleNodeClick(node);
                  }}
                >
                  {/* Glow for active node */}
                  {(isActive || isFocusedCenter) && (
                    <circle
                      cx={node.x}
                      cy={node.y}
                      r={node.radius * 2.5}
                      fill={color}
                      fillOpacity={isFocusedCenter ? 0.15 : 0.12}
                      style={{ pointerEvents: "none" }}
                    />
                  )}
                  {hasPortrait ? (
                    <g filter={!isDimmed ? "url(#node-shadow)" : undefined}>
                      {/* Colored ring behind portrait */}
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius + 2.5}
                        fill="none"
                        stroke={color}
                        strokeWidth={isActive || isFocusedCenter ? 3.5 : 2.5}
                        strokeOpacity={isDimmed ? 0.2 : 0.9}
                        style={{ transition: "stroke-opacity 0.2s" }}
                      />
                      {/* Portrait circle */}
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius}
                        fill={`url(#portrait-${node.id})`}
                        opacity={isDimmed ? 0.25 : 1}
                        stroke={isActive || isFocusedCenter ? "var(--foreground)" : "none"}
                        strokeWidth={isFocusedCenter ? 2.5 : isActive ? 2 : 0}
                        style={{ transition: "opacity 0.2s" }}
                      />
                    </g>
                  ) : (
                    /* Colored circle with sheen (no portrait) */
                    <>
                      <circle
                        cx={node.x}
                        cy={node.y}
                        r={node.radius}
                        fill={color}
                        fillOpacity={isDimmed ? 0.15 : isActive || isFocusedCenter ? 0.9 : 0.65}
                        stroke={isActive || isFocusedCenter ? "var(--foreground)" : "rgba(255,255,255,0.15)"}
                        strokeWidth={isFocusedCenter ? 2.5 : isActive ? 2 : 0.75}
                        style={{ transition: "fill-opacity 0.2s, stroke-width 0.15s" }}
                      />
                      {!isDimmed && node.radius > 6 && (
                        <circle
                          cx={node.x}
                          cy={node.y}
                          r={node.radius}
                          fill="url(#node-sheen)"
                          style={{ pointerEvents: "none" }}
                        />
                      )}
                    </>
                  )}
                  {/* Label with readability halo */}
                  <text
                    x={node.x}
                    y={node.y! + node.radius + 12}
                    textAnchor="middle"
                    className="fill-[var(--foreground)]"
                    fontSize={isActive || isFocusedCenter ? 11 : isConnected ? 9.5 : node.radius > 10 ? 9 : 7.5}
                    fontWeight={isActive || isFocusedCenter ? 600 : 400}
                    opacity={isDimmed ? 0.15 : node.radius <= 10 && !isActive && !isConnected && !focusedNode ? 0.55 : 1}
                    stroke="var(--background)"
                    strokeWidth={3}
                    paintOrder="stroke"
                    strokeLinejoin="round"
                    style={{ pointerEvents: "none", transition: "opacity 0.2s" }}
                  >
                    {node.name.length > 15
                      ? node.name.slice(0, 13) + "\u2026"
                      : node.name}
                  </text>
                </g>
              );
            })}
          </g>
        </svg>

        {/* Zoom controls — min 44px tap target for mobile */}
        <div className="absolute top-2 right-2 sm:top-3 sm:right-3 flex flex-col gap-1 z-10">
          <button
            onClick={() => {
              setVt((prev) => {
                const nextScale = Math.min(4, prev.scale * 1.3);
                const ratio = nextScale / prev.scale;
                return {
                  scale: nextScale,
                  panX: width / 2 - (width / 2 - prev.panX) * ratio,
                  panY: height / 2 - (height / 2 - prev.panY) * ratio,
                };
              });
            }}
            className="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--background)] text-sm font-bold transition-colors"
            title="Zoom in"
          >
            +
          </button>
          <button
            onClick={() => {
              setVt((prev) => {
                const nextScale = Math.max(0.25, prev.scale / 1.3);
                const ratio = nextScale / prev.scale;
                return {
                  scale: nextScale,
                  panX: width / 2 - (width / 2 - prev.panX) * ratio,
                  panY: height / 2 - (height / 2 - prev.panY) * ratio,
                };
              });
            }}
            className="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--background)] text-sm font-bold transition-colors"
            title="Zoom out"
          >
            &minus;
          </button>
          <button
            onClick={() => setVt({ scale: 1, panX: 0, panY: 0 })}
            className="w-9 h-9 sm:w-8 sm:h-8 flex items-center justify-center rounded-md border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--background)] text-xs font-medium transition-colors"
            title="Reset zoom"
          >
            1:1
          </button>
        </div>

        {/* Zoom level indicator */}
        {vt.scale !== 1 && (
          <div className="absolute bottom-3 left-3 text-xs text-[var(--muted)] bg-[var(--card)]/80 px-2 py-1 rounded border border-[var(--border)]">
            {Math.round(vt.scale * 100)}%
          </div>
        )}

        {/* Floating tooltip */}
        {activeNode && !dragNode && activeNode.x != null && activeNode.y != null && (
          <NodeTooltip
            node={activeNode}
            links={links}
            nodes={nodes}
            identity={identities[activeNode.id]}
            svgWidth={width}
            svgHeight={height}
            zoomScale={vt.scale}
            panOffset={{ x: vt.panX, y: vt.panY }}
          />
        )}
      </div>

      {/* Legend */}
      <div className="flex flex-wrap gap-x-5 gap-y-1.5 text-xs text-[var(--muted)]">
        {subcategories.map((sc) => (
          <div key={sc} className="flex items-center gap-1.5">
            <span
              className="w-2.5 h-2.5 rounded-full"
              style={{ backgroundColor: SUBCATEGORY_COLORS[sc] || "#64748b" }}
            />
            <span>{SUBCATEGORY_LABELS[sc] || sc}</span>
          </div>
        ))}
        <div className="flex items-center gap-1.5 ml-auto opacity-60">
          <span className="text-xs">Click node to focus &middot; Drag to rearrange &middot; Scroll to zoom &middot; Drag background to pan</span>
        </div>
      </div>
    </div>
  );
}

// ── Person Directory ─────────────────────────────────────────────────────────

function PersonDirectory({
  graph,
  identities,
  focusedNode,
  searchQuery,
  onSearchChange,
  onFocusNode,
  onHoverNode,
}: {
  graph: PersonGraph;
  identities: IdentityMap;
  focusedNode: string | null;
  searchQuery: string;
  onSearchChange: (q: string) => void;
  onFocusNode: (id: string | null) => void;
  onHoverNode: (id: string | null) => void;
}) {
  const [expanded, setExpanded] = useState(false);

  // Connection counts per node
  const connectionCounts = useMemo(() => {
    const counts: Record<string, number> = {};
    for (const e of graph.edges) {
      counts[e.source] = (counts[e.source] || 0) + 1;
      counts[e.target] = (counts[e.target] || 0) + 1;
    }
    return counts;
  }, [graph.edges]);

  // Sorted by mention count, filtered by search
  const people = useMemo(() => {
    const sorted = graph.nodes.slice().sort((a, b) => b.count - a.count);
    if (!searchQuery.trim()) return sorted;
    const q = searchQuery.toLowerCase();
    return sorted.filter(
      (n) =>
        n.name.toLowerCase().includes(q) ||
        n.aliases.some((a) => a.toLowerCase().includes(q))
    );
  }, [graph.nodes, searchQuery]);

  const INITIAL_SHOW = 20;
  const visiblePeople = expanded ? people : people.slice(0, INITIAL_SHOW);
  const hasMore = people.length > INITIAL_SHOW;

  return (
    <div className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden">
      {/* Search header */}
      <div className="px-4 py-3 border-b border-[var(--border)]">
        <div className="relative">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 text-[var(--muted)]"
            width="14"
            height="14"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
          >
            <circle cx="11" cy="11" r="8" />
            <path d="m21 21-4.3-4.3" />
          </svg>
          <input
            type="text"
            placeholder="Search people..."
            value={searchQuery}
            onChange={(e) => onSearchChange(e.target.value)}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-[var(--border)] bg-[var(--background)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent"
          />
        </div>
      </div>

      {/* Person list */}
      <div className="divide-y divide-[var(--border)]">
        {visiblePeople.length === 0 && (
          <div className="px-4 py-6 text-center text-sm text-[var(--muted)]">
            No people matching &ldquo;{searchQuery}&rdquo;
          </div>
        )}
        {visiblePeople.map((person) => {
          const color = SUBCATEGORY_COLORS[person.subcategory] || "#64748b";
          const conns = connectionCounts[person.id] || 0;
          const isFocused = focusedNode === person.id;
          const ident = identities[person.id];
          const thumbSrc = ident?.thumbnail
            ? `/thumbnails/${ident.thumbnail}`
            : ident?.thumbnail_url || null;

          return (
            <button
              key={person.id}
              className={`w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-[var(--background)] ${
                isFocused ? "bg-[var(--accent)]/10" : ""
              }`}
              onClick={() => onFocusNode(isFocused ? null : person.id)}
              onMouseEnter={() => onHoverNode(person.id)}
              onMouseLeave={() => onHoverNode(null)}
            >
              {thumbSrc ? (
                <span
                  className="w-6 h-6 rounded-full shrink-0 bg-cover bg-center"
                  style={{
                    backgroundImage: `url(${thumbSrc})`,
                    border: `2px solid ${color}`,
                  }}
                />
              ) : (
                <span
                  className="w-2.5 h-2.5 rounded-full shrink-0"
                  style={{ backgroundColor: color }}
                />
              )}
              <span className="flex-1 min-w-0">
                <span className={`block truncate ${isFocused ? "font-medium" : ""}`}>
                  {person.name}
                </span>
                {ident?.description && (
                  <span className="block text-xs text-[var(--muted)] truncate leading-tight">
                    {ident.description}
                  </span>
                )}
              </span>
              <span className="text-xs text-[var(--muted)] tabular-nums shrink-0">
                {person.count}
              </span>
              <span className="text-xs text-[var(--muted)] tabular-nums shrink-0 w-14 text-right">
                {conns} {conns === 1 ? "link" : "links"}
              </span>
            </button>
          );
        })}
      </div>

      {/* Show more / less */}
      {hasMore && !searchQuery && (
        <div className="border-t border-[var(--border)] px-4 py-2.5">
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            {expanded ? "Show fewer" : `Show all ${people.length} people`}
          </button>
        </div>
      )}
    </div>
  );
}

// ── Tooltip ──────────────────────────────────────────────────────────────────

function NodeTooltip({
  node,
  links,
  nodes,
  identity,
  svgWidth,
  svgHeight,
  zoomScale = 1,
  panOffset = { x: 0, y: 0 },
}: {
  node: GraphNode;
  links: GraphLink[];
  nodes: GraphNode[];
  identity?: PersonIdentity;
  svgWidth: number;
  svgHeight: number;
  zoomScale?: number;
  panOffset?: { x: number; y: number };
}) {
  const nodeMap = useMemo(() => new Map(nodes.map((n) => [n.id, n])), [nodes]);

  const connections = useMemo(() => {
    const conns: { id: string; name: string; weight: number; excerpt: string }[] = [];
    for (const l of links) {
      const s = typeof l.source === "object" ? (l.source as GraphNode).id : String(l.source);
      const t = typeof l.target === "object" ? (l.target as GraphNode).id : String(l.target);
      if (s === node.id) {
        const other = nodeMap.get(t);
        if (other)
          conns.push({
            id: t,
            name: other.name,
            weight: l.weight,
            excerpt: l.excerpts?.[0] || "",
          });
      } else if (t === node.id) {
        const other = nodeMap.get(s);
        if (other)
          conns.push({
            id: s,
            name: other.name,
            weight: l.weight,
            excerpt: l.excerpts?.[0] || "",
          });
      }
    }
    conns.sort((a, b) => b.weight - a.weight);
    return conns.slice(0, 5);
  }, [node.id, links, nodeMap]);

  const adjustedX = node.x! * zoomScale + panOffset.x;
  const adjustedY = node.y! * zoomScale + panOffset.y;
  const nodeYPct = Math.max(5, Math.min(95, (adjustedY / svgHeight) * 100));
  const onLeft = adjustedX < svgWidth / 2;

  return (
    <div
      className="absolute z-50 pointer-events-none"
      style={{
        top: `${nodeYPct}%`,
        ...(onLeft
          ? { right: 0, transform: "translateY(-50%)" }
          : { left: 0, transform: "translateY(-50%)" }),
      }}
    >
      <div className="bg-[var(--foreground)] text-[var(--background)] rounded-lg px-4 py-3 shadow-xl max-w-[280px]">
        {/* Header */}
        <div className="flex items-center gap-2 mb-1">
          <span
            className="w-2.5 h-2.5 rounded-full shrink-0"
            style={{
              backgroundColor: SUBCATEGORY_COLORS[node.subcategory] || "#64748b",
            }}
          />
          <span className="font-semibold text-sm leading-tight">{node.name}</span>
        </div>
        {/* Subcategory + mentions */}
        <div className="flex items-center gap-2 text-xs opacity-60 mb-2">
          <span>{identity?.description || SUBCATEGORY_LABELS[node.subcategory] || node.subcategory}</span>
          <span>&middot;</span>
          <span>{node.count} mentions</span>
        </div>
        {/* Context */}
        {node.contexts[0] && (
          <p className="text-xs leading-relaxed opacity-80 mb-2 italic">
            {node.contexts[0]}
          </p>
        )}
        {/* Aliases */}
        {node.aliases.length > 1 && (
          <p className="text-xs opacity-50 mb-2">
            Also: {node.aliases.filter((a) => a !== node.name).slice(0, 3).join(", ")}
          </p>
        )}
        {/* Top connections */}
        {connections.length > 0 && (
          <div className="border-t border-current/10 pt-2 mt-1">
            <div className="text-xs opacity-50 mb-1">Top connections:</div>
            {connections.map((c) => (
              <div key={c.id} className="text-xs leading-snug mb-0.5">
                <span className="opacity-80">{c.name}</span>
                <span className="opacity-40 ml-1">({c.weight}x)</span>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

// ── Top Co-Citations Table ───────────────────────────────────────────────────

function TopCoCitations({ graph }: { graph: PersonGraph }) {
  const nodeMap = useMemo(
    () => new Map(graph.nodes.map((n) => [n.id, n])),
    [graph.nodes]
  );

  const topEdges = useMemo(
    () => graph.edges.slice().sort((a, b) => b.weight - a.weight).slice(0, 15),
    [graph.edges]
  );

  if (topEdges.length === 0) return null;

  return (
    <div>
      <h3 className="text-sm font-semibold uppercase tracking-wider text-[var(--muted)] mb-3">
        Strongest Co-Citations
      </h3>
      <div className="rounded-lg border border-[var(--border)] overflow-hidden">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-[var(--card)] border-b border-[var(--border)]">
              <th className="text-left px-4 py-2.5 font-medium text-[var(--muted)]">
                Person A
              </th>
              <th className="text-left px-4 py-2.5 font-medium text-[var(--muted)]">
                Person B
              </th>
              <th className="text-right px-4 py-2.5 font-medium text-[var(--muted)]">
                Co-citations
              </th>
            </tr>
          </thead>
          <tbody>
            {topEdges.map((edge, i) => {
              const a = nodeMap.get(edge.source);
              const b = nodeMap.get(edge.target);
              return (
                <tr
                  key={i}
                  className="border-b border-[var(--border)] last:border-0 hover:bg-[var(--card)]/50"
                >
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{
                          backgroundColor:
                            SUBCATEGORY_COLORS[a?.subcategory || ""] || "#64748b",
                        }}
                      />
                      {a?.name || edge.source}
                    </div>
                  </td>
                  <td className="px-4 py-2.5">
                    <div className="flex items-center gap-2">
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{
                          backgroundColor:
                            SUBCATEGORY_COLORS[b?.subcategory || ""] || "#64748b",
                        }}
                      />
                      {b?.name || edge.target}
                    </div>
                  </td>
                  <td className="px-4 py-2.5 text-right tabular-nums font-medium">
                    {edge.weight}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </div>
  );
}
