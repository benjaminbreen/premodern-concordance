"use client";

import { useEffect, useState, useCallback, useMemo, useRef } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";
import { CATEGORY_COLORS, CAT_DOT as CATEGORY_BAR_COLORS, CAT_TINT as CATEGORY_TINT, CAT_HEX } from "@/lib/colors";
import { BOOK_SHORT_NAMES } from "@/lib/books";
import { buildEntityNameIndex, AutoLinkedText } from "@/components/EntityHoverCard";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { scaleSqrt } from "d3-scale";

/* ───── shared types (duplicated from concordance/page.tsx) ───── */

interface ClusterMember {
  entity_id: string;
  book_id: string;
  name: string;
  category: string;
  subcategory: string;
  count: number;
  variants: string[];
  contexts: string[];
}

interface ClusterEdge {
  source_book: string;
  source_name: string;
  target_book: string;
  target_name: string;
  similarity: number;
}

interface GroundTruth {
  modern_name: string;
  confidence: "high" | "medium" | "low";
  type: string;
  wikidata_id?: string;
  wikidata_description?: string;
  wikipedia_url?: string;
  linnaean?: string;
  family?: string;
  birth_year?: number;
  death_year?: number;
  description?: string;
  country?: string;
  modern_term?: string;
  note?: string;
  portrait_url?: string;
  semantic_gloss?: string;
}

interface CrossReference {
  found_name: string;
  link_type: string;
  link_strength: number;
  target_cluster_id: number | null;
  target_cluster_name: string | null;
  source_book: string;
  evidence_snippet: string;
  confidence: number;
  auto_label: string;
  found_relationship: string;
  is_reverse?: boolean;
}

interface Cluster {
  id: number;
  stable_key?: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  members: ClusterMember[];
  edges: ClusterEdge[];
  ground_truth?: GroundTruth;
  cross_references?: CrossReference[];
}

interface BookMeta {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
}

interface ConcordanceData {
  metadata: {
    created: string;
    threshold: number;
    enriched?: boolean;
    enrichment_model?: string;
  };
  books: BookMeta[];
  stats: {
    total_clusters: number;
    entities_matched: number;
    clusters_all_books: number;
    by_category: Record<string, number>;
    enriched_clusters?: number;
    with_wikidata?: number;
    with_wikipedia?: number;
    with_linnaean?: number;
  };
  clusters: Cluster[];
}

/* ───── constants ───── */

const BOOK_LANG_FLAGS: Record<string, string> = {
  English: "EN",
  Portuguese: "PT",
  Spanish: "ES",
  Latin: "LA",
  French: "FR",
  Italian: "IT",
};

/* ───── slug helpers ───── */

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Build a slug for a cluster, appending ID if the base slug collides */
function clusterSlug(cluster: Cluster, allClusters: Cluster[]): string {
  if (cluster.stable_key) return cluster.stable_key;
  const base = slugify(cluster.canonical_name);
  const hasCollision = allClusters.some(
    (c) => c.id !== cluster.id && slugify(c.canonical_name) === base
  );
  return hasCollision ? `${base}-${cluster.id}` : base;
}

/** Find a cluster by its slug (try base match first, then id-suffixed) */
function findClusterBySlug(slug: string, clusters: Cluster[]): Cluster | null {
  // First try stable_key exact match.
  const stable = clusters.find((c) => c.stable_key === slug);
  if (stable) return stable;

  // First try exact base-slug match (unique names)
  const baseMatches = clusters.filter((c) => slugify(c.canonical_name) === slug);
  if (baseMatches.length === 1) return baseMatches[0];

  // Try id-suffixed match (e.g. "verde-113")
  const idMatch = slug.match(/-(\d+)$/);
  if (idMatch) {
    const id = Number(idMatch[1]);
    const found = clusters.find((c) => c.id === id);
    if (found) return found;
  }

  return null;
}

/* ───── helpers ───── */

function displayName(cluster: Cluster): string {
  return cluster.ground_truth?.modern_name || cluster.canonical_name;
}

function cap(r: { text: string; italic: boolean }): { text: string; italic: boolean } {
  if (r.text.length > 0) {
    return { ...r, text: r.text.charAt(0).toUpperCase() + r.text.slice(1) };
  }
  return r;
}

function getIdentification(cluster: Cluster): { text: string; italic: boolean } | null {
  const gt = cluster.ground_truth;
  if (!gt) return null;
  const cat = cluster.category;
  const labelLower = displayName(cluster).toLowerCase();

  if (cat === "PERSON") {
    if (gt.birth_year) {
      const dates = `(${gt.birth_year}\u2013${gt.death_year || "?"})`;
      return cap({ text: `${gt.modern_name} ${dates}`, italic: false });
    }
    const nameDiffers = gt.modern_name.toLowerCase() !== labelLower;
    if (nameDiffers) return cap({ text: gt.modern_name, italic: false });
    if (gt.description) {
      const d = gt.description;
      return cap({ text: d.length > 60 ? d.slice(0, 57) + "\u2026" : d, italic: false });
    }
    if (gt.wikidata_description) {
      const d = gt.wikidata_description;
      return cap({ text: d.length > 60 ? d.slice(0, 57) + "\u2026" : d, italic: false });
    }
    return null;
  }

  if (cat === "PLANT" || cat === "ANIMAL") {
    if (gt.linnaean) return cap({ text: gt.linnaean, italic: true });
    if (gt.modern_name.toLowerCase() !== labelLower) return cap({ text: gt.modern_name, italic: false });
    if (gt.family) return cap({ text: `Fam. ${gt.family}`, italic: true });
    return null;
  }

  if (gt.modern_name.toLowerCase() !== labelLower) return cap({ text: gt.modern_name, italic: false });
  if (gt.modern_term && gt.modern_term.toLowerCase() !== labelLower && gt.modern_term.toLowerCase() !== gt.modern_name.toLowerCase()) {
    return cap({ text: gt.modern_term, italic: false });
  }
  if (gt.description) {
    const d = gt.description;
    return cap({ text: d.length > 60 ? d.slice(0, 57) + "\u2026" : d, italic: false });
  }
  if (gt.wikidata_description) {
    const d = gt.wikidata_description;
    return cap({ text: d.length > 60 ? d.slice(0, 57) + "\u2026" : d, italic: false });
  }
  return null;
}

/** Group all member variants by book language */
function getVariantsByLanguage(
  members: ClusterMember[],
  books: BookMeta[]
): Record<string, string[]> {
  const byLang: Record<string, Set<string>> = {};
  for (const m of members) {
    const book = books.find((b) => b.id === m.book_id);
    const lang = book?.language || "Unknown";
    if (!byLang[lang]) byLang[lang] = new Set();
    for (const v of m.variants) byLang[lang].add(v);
  }
  const result: Record<string, string[]> = {};
  for (const [lang, set] of Object.entries(byLang)) {
    result[lang] = [...set].sort((a, b) => a.localeCompare(b));
  }
  return result;
}

/** Aggregate mention counts per book_id */
function getMentionsByBook(members: ClusterMember[]): { book_id: string; count: number }[] {
  const counts: Record<string, number> = {};
  for (const m of members) {
    counts[m.book_id] = (counts[m.book_id] || 0) + m.count;
  }
  return Object.entries(counts)
    .map(([book_id, count]) => ({ book_id, count }))
    .sort((a, b) => b.count - a.count);
}

/* ───── sub-components ───── */

function WikiThumbnail({ url, size = "sm" }: { url: string; size?: "sm" | "lg" }) {
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) return;

      fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.thumbnail?.source) setThumb(data.thumbnail.source);
        })
        .catch(() => {});
    } catch {
      // invalid URL
    }
  }, [url]);

  if (!thumb) return null;

  const sizeClass = size === "lg" ? "w-32 h-32" : "w-24 h-24";

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={thumb}
      alt=""
      className={`${sizeClass} rounded object-cover shrink-0 border border-[var(--border)]`}
    />
  );
}

function WikiExtract({ url, wikiUrl }: { url: string; wikiUrl?: string }) {
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) { setLoading(false); return; }

      fetch(
        `https://${lang}.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&prop=extracts&explaintext=true&exsectionformat=plain&format=json&origin=*`
      )
        .then((res) => res.json())
        .then((data) => {
          const pages = data.query?.pages;
          if (!pages) { setLoading(false); return; }
          const pageId = Object.keys(pages)[0];
          const extract = pages[pageId]?.extract || "";
          const paras = extract.split("\n\n").filter((p: string) => p.length > 40);
          setParagraphs(paras.slice(0, 6));
          setLoading(false);
        })
        .catch(() => setLoading(false));
    } catch {
      setLoading(false);
    }
  }, [url]);

  if (loading || paragraphs.length === 0) return null;

  const PREVIEW_MAX = 500;
  const firstPara = paragraphs[0];
  let preview: string;
  let restOfFirst: string | null = null;

  if (firstPara.length <= PREVIEW_MAX) {
    preview = firstPara;
  } else {
    const cut = firstPara.slice(0, PREVIEW_MAX);
    const sentenceEnd = cut.lastIndexOf(". ");
    if (sentenceEnd > 200) {
      preview = cut.slice(0, sentenceEnd + 1);
      restOfFirst = firstPara.slice(sentenceEnd + 2);
    } else {
      const wordEnd = cut.lastIndexOf(" ");
      preview = cut.slice(0, wordEnd > 0 ? wordEnd : PREVIEW_MAX) + "\u2026";
      restOfFirst = firstPara.slice(wordEnd > 0 ? wordEnd + 1 : PREVIEW_MAX);
    }
  }

  const hasMore = restOfFirst !== null || paragraphs.length > 1;

  return (
    <div>
      <p className="text-sm text-[var(--foreground)]/80 leading-relaxed">{preview}</p>
      {expanded && (
        <div className="max-h-[280px] overflow-y-auto space-y-3 text-sm text-[var(--foreground)]/80 leading-relaxed">
          {restOfFirst && <p>{restOfFirst}</p>}
          {paragraphs.slice(1).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3 mt-2">
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            {expanded ? "Less" : "More"}
          </button>
        )}
        {expanded && wikiUrl && (
          <a
            href={wikiUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[var(--accent)] hover:underline"
          >
            Read on Wikipedia &rarr;
          </a>
        )}
      </div>
    </div>
  );
}

/** Wikipedia card — receives resolved URL from parent */
function WikiCard({ url, searching }: { url: string | null; searching: boolean }) {
  if (searching) {
    return (
      <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
        <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Wikipedia
        </h3>
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
          <div className="w-3 h-3 border border-[var(--muted)] border-t-transparent rounded-full animate-spin" />
          Looking up article...
        </div>
      </div>
    );
  }

  if (!url) {
    return (
      <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
        <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Wikipedia
        </h3>
        <p className="text-xs text-[var(--muted)]">No Wikipedia article found.</p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
      <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
        Wikipedia
      </h3>
      <WikiExtract url={url} wikiUrl={url} />
    </div>
  );
}

/* ───── neighborhood graph ───── */

interface NeighborData {
  k: number;
  count: number;
  neighbors: Record<string, { id: number; sim: number }[]>;
}

interface GraphNode extends SimulationNodeDatum {
  id: number;
  name: string;
  category: string;
  mentions: number;
  isCurrent: boolean;
  slug: string;
  similarity: number; // similarity to the current cluster (1.0 for current)
  topBooks: { name: string; year: number }[];
  gloss: string; // first sentence of semantic_gloss, description, or wikidata_description
}

interface GraphLink extends SimulationLinkDatum<GraphNode> {
  similarity: number;
}

const CATEGORY_NODE_COLORS: Record<string, string> = {
  PERSON: "#a855f7",
  PLANT: "#10b981",
  ANIMAL: "#84cc16",
  SUBSTANCE: "#06b6d4",
  CONCEPT: "#f59e0b",
  DISEASE: "#ef4444",
  PLACE: "#22c55e",
  OBJECT: "#64748b",
  ANATOMY: "#f43f5e",
};

/** Extract first sentence from a text string */
function firstSentence(text: string): string {
  if (!text) return "";
  const m = text.match(/^.+?[.!?](?:\s|$)/);
  return m ? m[0].trim() : (text.length > 120 ? text.slice(0, 117) + "\u2026" : text);
}

function NeighborhoodGraph({
  clusterId,
  clusters,
  books,
}: {
  clusterId: number;
  clusters: Cluster[];
  books: BookMeta[];
}) {
  const svgRef = useRef<SVGSVGElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const simRef = useRef<ReturnType<typeof forceSimulation<GraphNode>> | null>(null);
  const nodesRef = useRef<GraphNode[]>([]);
  const linksRef = useRef<GraphLink[]>([]);

  const [neighborData, setNeighborData] = useState<NeighborData | null>(null);
  const [, setTick] = useState(0); // force re-render on sim tick
  const [hoveredNode, setHoveredNode] = useState<GraphNode | null>(null);
  const [dragNode, setDragNode] = useState<GraphNode | null>(null);
  const [dimensions, setDimensions] = useState({ width: 700, height: 460 });
  const wasDraggedRef = useRef(false);

  const router = useRouter();
  const bookMap = useMemo(() => new Map(books.map((b) => [b.id, b])), [books]);

  // Responsive width
  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;
    const ro = new ResizeObserver((entries) => {
      const w = entries[0].contentRect.width;
      setDimensions({ width: w, height: Math.min(460, Math.max(320, w * 0.55)) });
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, []);

  // Load neighbor data
  useEffect(() => {
    fetch("/data/cluster_neighbors.json")
      .then((r) => r.json())
      .then((d: NeighborData) => setNeighborData(d))
      .catch(() => {});
  }, []);

  // Build graph + start simulation
  useEffect(() => {
    if (!neighborData) return;
    const clusterMap = new Map(clusters.map((c) => [c.id, c]));
    const rawNeighborList = neighborData.neighbors[String(clusterId)];
    if (!rawNeighborList) return;
    // Filter out neighbors whose clusters were removed from the dataset
    const neighborList = rawNeighborList.filter((n) => clusterMap.has(n.id));
    const current = clusterMap.get(clusterId);
    if (!current) return;
    const { width, height } = dimensions;

    function buildNodeData(c: Cluster, isCurrent: boolean, sim: number): GraphNode {
      const memberBooks = [...new Set(c.members.map((m) => m.book_id))];
      const topBooks = memberBooks
        .map((bid) => bookMap.get(bid))
        .filter((b): b is BookMeta => !!b)
        .sort((a, b) => a.year - b.year)
        .slice(0, 3)
        .map((b) => ({ name: BOOK_SHORT_NAMES[b.id] || b.title, year: b.year }));
      const gt = c.ground_truth;
      const gloss = firstSentence(
        gt?.semantic_gloss || gt?.description || gt?.wikidata_description || ""
      );
      return {
        id: c.id,
        name: displayName(c),
        category: c.category,
        mentions: c.total_mentions,
        isCurrent,
        slug: clusterSlug(c, clusters),
        similarity: sim,
        topBooks,
        gloss,
      };
    }

    const nodeIds = new Set<number>([clusterId]);
    const graphNodes: GraphNode[] = [buildNodeData(current, true, 1)];
    // Pin the current node to center
    graphNodes[0].fx = width / 2;
    graphNodes[0].fy = height / 2;

    const simToId: Record<number, number> = {};
    for (const n of neighborList) {
      const c = clusterMap.get(n.id);
      if (!c) continue;
      nodeIds.add(n.id);
      simToId[n.id] = graphNodes.length;
      const nd = buildNodeData(c, false, n.sim);
      // Spread around in a circle initially
      const angle = (graphNodes.length / (neighborList.length + 1)) * 2 * Math.PI;
      nd.x = width / 2 + Math.cos(angle) * 150;
      nd.y = height / 2 + Math.sin(angle) * 150;
      graphNodes.push(nd);
    }

    const graphLinks: GraphLink[] = neighborList
      .filter((n) => nodeIds.has(n.id))
      .map((n) => ({ source: clusterId, target: n.id, similarity: n.sim }));

    // Neighbor-neighbor links
    const linkSet = new Set(graphLinks.map((l) => `${l.source}-${l.target}`));
    for (const n of neighborList) {
      const their = neighborData.neighbors[String(n.id)];
      if (!their) continue;
      for (const nn of their) {
        if (nn.id === clusterId || !nodeIds.has(nn.id) || nn.sim <= 0.5) continue;
        const key1 = `${n.id}-${nn.id}`;
        const key2 = `${nn.id}-${n.id}`;
        if (!linkSet.has(key1) && !linkSet.has(key2)) {
          graphLinks.push({ source: n.id, target: nn.id, similarity: nn.sim });
          linkSet.add(key1);
        }
      }
    }

    nodesRef.current = graphNodes;
    linksRef.current = graphLinks;

    const radiusScale = scaleSqrt()
      .domain([1, Math.max(...graphNodes.map((n) => n.mentions), 1)])
      .range([7, 30]);

    // Stop any prior simulation
    simRef.current?.stop();

    const sim = forceSimulation<GraphNode>(graphNodes)
      .force(
        "link",
        forceLink<GraphNode, GraphLink>(graphLinks)
          .id((d) => d.id)
          .distance((d) => 60 + (1 - d.similarity) * 140)
          .strength((d) => d.similarity * 0.5)
      )
      .force("charge", forceManyBody().strength(-250).distanceMax(350))
      .force("center", forceCenter(width / 2, height / 2).strength(0.05))
      .force("collide", forceCollide<GraphNode>().radius((d) => radiusScale(d.mentions) + 6).strength(0.7))
      .alpha(1)
      .alphaDecay(0.015)
      .velocityDecay(0.35);

    sim.on("tick", () => {
      for (const n of graphNodes) {
        const r = radiusScale(n.mentions);
        if (n.fx == null) n.x = Math.max(r + 50, Math.min(width - r - 50, n.x!));
        if (n.fy == null) n.y = Math.max(r + 20, Math.min(height - r - 20, n.y!));
      }
      setTick((t) => t + 1);
    });

    simRef.current = sim;
    return () => { sim.stop(); };
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [neighborData, clusterId, dimensions.width]);

  // Drag handlers
  const handlePointerDown = useCallback((e: React.PointerEvent, node: GraphNode) => {
    if (node.isCurrent) return;
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
      if (!dragNode || !svgRef.current) return;
      wasDraggedRef.current = true;
      const svg = svgRef.current;
      const rect = svg.getBoundingClientRect();
      const scaleX = dimensions.width / rect.width;
      const scaleY = dimensions.height / rect.height;
      dragNode.fx = (e.clientX - rect.left) * scaleX;
      dragNode.fy = (e.clientY - rect.top) * scaleY;
    },
    [dragNode, dimensions]
  );

  const handlePointerUp = useCallback(() => {
    if (!dragNode) return;
    dragNode.fx = null;
    dragNode.fy = null;
    setDragNode(null);
    simRef.current?.alphaTarget(0);
  }, [dragNode]);

  const nodes = nodesRef.current;
  const links = linksRef.current;

  if (!neighborData || nodes.length === 0) return null;

  const { width, height } = dimensions;
  const maxMentions = Math.max(...nodes.map((n) => n.mentions), 1);
  const radiusScale = scaleSqrt().domain([1, maxMentions]).range([7, 30]);

  return (
    <div ref={containerRef} className="w-full relative">
      <svg
        ref={svgRef}
        viewBox={`0 0 ${width} ${height}`}
        className="w-full rounded-lg border border-[var(--border)] select-none"
        style={{
          height: `${height}px`,
          maxHeight: "460px",
          background: "radial-gradient(ellipse at center, var(--card) 0%, var(--background) 100%)",
        }}
        onPointerMove={handlePointerMove}
        onPointerUp={handlePointerUp}
        onPointerLeave={handlePointerUp}
      >
        <defs>
          {/* Radial gradient for node glow */}
          {Object.entries(CATEGORY_NODE_COLORS).map(([cat, color]) => (
            <radialGradient key={cat} id={`glow-${cat}`}>
              <stop offset="0%" stopColor={color} stopOpacity={0.4} />
              <stop offset="100%" stopColor={color} stopOpacity={0} />
            </radialGradient>
          ))}
        </defs>

        {/* Subtle grid dots */}
        <pattern id="grid-dots" x="0" y="0" width="30" height="30" patternUnits="userSpaceOnUse">
          <circle cx="15" cy="15" r="0.5" fill="var(--muted)" opacity="0.15" />
        </pattern>
        <rect width={width} height={height} fill="url(#grid-dots)" />

        {/* Links */}
        {links.map((link, i) => {
          const source = link.source as GraphNode;
          const target = link.target as GraphNode;
          if (source.x == null || target.x == null) return null;
          const isHighlighted =
            hoveredNode && (source.id === hoveredNode.id || target.id === hoveredNode.id);
          const opacity = isHighlighted ? 0.5 : 0.06 + link.similarity * 0.2;
          const sw = isHighlighted ? 2 : link.similarity > 0.6 ? 1 : 0.5;
          return (
            <line
              key={i}
              x1={source.x}
              y1={source.y}
              x2={target.x}
              y2={target.y}
              stroke={isHighlighted ? "var(--foreground)" : "var(--muted)"}
              strokeOpacity={opacity}
              strokeWidth={sw}
              style={{ transition: "stroke-opacity 0.2s, stroke-width 0.2s" }}
            />
          );
        })}

        {/* Nodes — render in two passes: back (non-hovered) then front (hovered/current) */}
        {nodes
          .slice()
          .sort((a, b) => {
            if (a.isCurrent) return 1;
            if (b.isCurrent) return -1;
            if (hoveredNode?.id === a.id) return 1;
            if (hoveredNode?.id === b.id) return -1;
            return 0;
          })
          .map((node) => {
            if (node.x == null || node.y == null) return null;
            const r = radiusScale(node.mentions);
            const color = CATEGORY_NODE_COLORS[node.category] || "#64748b";
            const isHovered = hoveredNode?.id === node.id;
            const isDimmed = hoveredNode && !isHovered && !node.isCurrent;

            return (
              <g
                key={node.id}
                style={{ cursor: node.isCurrent ? "default" : dragNode ? "grabbing" : "grab" }}
                onPointerDown={(e) => handlePointerDown(e, node)}
                onMouseEnter={() => { if (!dragNode) setHoveredNode(node); }}
                onMouseLeave={() => { if (!dragNode) setHoveredNode(null); }}
                onClick={() => {
                  if (wasDraggedRef.current) return;
                  if (!node.isCurrent) router.push(`/concordance/${node.slug}`);
                }}
              >
                {/* Ambient glow */}
                {(node.isCurrent || isHovered) && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r * 2.5}
                    fill={`url(#glow-${node.category})`}
                    style={{ pointerEvents: "none" }}
                  />
                )}
                {/* Ring for current node */}
                {node.isCurrent && (
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r + 3}
                    fill="none"
                    stroke={color}
                    strokeWidth={1.5}
                    strokeOpacity={0.5}
                    strokeDasharray="3 3"
                  />
                )}
                {/* Main circle */}
                <circle
                  cx={node.x}
                  cy={node.y}
                  r={r}
                  fill={color}
                  fillOpacity={isDimmed ? 0.25 : node.isCurrent ? 0.95 : isHovered ? 0.85 : 0.6}
                  stroke={isHovered ? "var(--foreground)" : "rgba(255,255,255,0.15)"}
                  strokeWidth={isHovered ? 2 : 0.5}
                  style={{ transition: "fill-opacity 0.2s, stroke-width 0.15s" }}
                />
                {/* Label */}
                {(node.isCurrent || isHovered || r > 12) && (
                  <text
                    x={node.x}
                    y={node.y! + r + 13}
                    textAnchor="middle"
                    className="fill-[var(--foreground)]"
                    fontSize={node.isCurrent ? 12 : 10}
                    fontWeight={node.isCurrent ? 600 : 400}
                    opacity={isDimmed ? 0.3 : 1}
                    style={{ pointerEvents: "none", transition: "opacity 0.2s" }}
                  >
                    {node.name.length > 22 ? node.name.slice(0, 20) + "\u2026" : node.name}
                  </text>
                )}
              </g>
            );
          })}
      </svg>

      {/* Floating tooltip — anchored to node position, pushed to graph edge */}
      {hoveredNode && !dragNode && hoveredNode.x != null && hoveredNode.y != null && (() => {
        // Convert node SVG coords to percentage-based positioning
        const nodeYPct = (hoveredNode.y! / height) * 100;
        const onLeft = hoveredNode.x! < width / 2;
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
          <div className="bg-[var(--foreground)] text-[var(--background)] rounded-lg px-4 py-3 shadow-xl max-w-[260px]">
            {/* Header */}
            <div className="flex items-center gap-2 mb-1.5">
              <span
                className="w-2.5 h-2.5 rounded-full shrink-0"
                style={{ backgroundColor: CATEGORY_NODE_COLORS[hoveredNode.category] || "#64748b" }}
              />
              <span className="font-semibold text-sm leading-tight">{hoveredNode.name}</span>
            </div>
            {/* Category + mentions */}
            <div className="flex items-center gap-2 text-xs opacity-60 mb-2">
              <span>{hoveredNode.category}</span>
              <span>&middot;</span>
              <span>{hoveredNode.mentions} mentions</span>
              {!hoveredNode.isCurrent && (
                <>
                  <span>&middot;</span>
                  <span>{Math.round(hoveredNode.similarity * 100)}% similar</span>
                </>
              )}
            </div>
            {/* Gloss */}
            {hoveredNode.gloss && (
              <p className="text-xs leading-relaxed opacity-80 mb-2">
                {hoveredNode.gloss}
              </p>
            )}
            {/* Top books */}
            {hoveredNode.topBooks.length > 0 && (
              <div className="flex flex-wrap gap-x-2 gap-y-0.5 text-xs opacity-50">
                {hoveredNode.topBooks.map((b, i) => (
                  <span key={i}>
                    {b.name} ({b.year})
                  </span>
                ))}
              </div>
            )}
            {/* Click hint */}
            {!hoveredNode.isCurrent && (
              <p className="text-xs opacity-40 mt-2 pt-1.5 border-t border-current/10">
                Click to view &middot; Drag to rearrange
              </p>
            )}
          </div>
        </div>
        );
      })()}

      {/* Legend */}
      <div className="flex flex-wrap gap-x-3 gap-y-1 mt-3 text-xs text-[var(--muted)]">
        {Object.entries(
          nodes.reduce<Record<string, number>>((acc, n) => {
            acc[n.category] = (acc[n.category] || 0) + 1;
            return acc;
          }, {})
        )
          .sort(([, a], [, b]) => b - a)
          .map(([cat, count]) => (
            <span key={cat} className="flex items-center gap-1">
              <span
                className="w-2 h-2 rounded-full"
                style={{ backgroundColor: CATEGORY_NODE_COLORS[cat] || "#64748b" }}
              />
              {cat} ({count})
            </span>
          ))}
        <span className="opacity-40 ml-auto">
          Size = mentions &middot; Proximity = semantic similarity &middot; Drag to rearrange
        </span>
      </div>
    </div>
  );
}

/* ───── main page component ───── */

export default function ClusterDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const slug = params.slug as string;
  const fromSlug = searchParams.get("from");

  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [wikiUrl, setWikiUrl] = useState<string | null>(null);
  const [wikiImage, setWikiImage] = useState<string | null>(null);
  const [wikiSearching, setWikiSearching] = useState(false);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const cluster = useMemo(
    () => (data ? findClusterBySlug(slug, data.clusters) : null),
    [data, slug]
  );

  // Prev/next cluster slugs (by sorted order in data)
  const { prevSlug, nextSlug } = useMemo(() => {
    if (!data || !cluster) return { prevSlug: null, nextSlug: null };
    const idx = data.clusters.findIndex((c) => c.id === cluster.id);
    return {
      prevSlug: idx > 0 ? clusterSlug(data.clusters[idx - 1], data.clusters) : null,
      nextSlug: idx >= 0 && idx < data.clusters.length - 1 ? clusterSlug(data.clusters[idx + 1], data.clusters) : null,
    };
  }, [data, cluster]);

  // Build slug map + entity name index for hover cards
  const slugMap = useMemo(() => {
    if (!data) return new Map<number, string>();
    return new Map(data.clusters.map((c) => [c.id, clusterSlug(c, data.clusters)]));
  }, [data]);

  const nameIndex = useMemo(() => {
    if (!data) return new Map();
    return buildEntityNameIndex(data.clusters, slugMap);
  }, [data, slugMap]);

  // Fetch neighbor data at page level for "Also appears with"
  const [neighborData, setNeighborData] = useState<{
    k: number;
    count: number;
    neighbors: Record<string, { id: number; sim: number }[]>;
  } | null>(null);

  useEffect(() => {
    fetch("/data/cluster_neighbors.json")
      .then((r) => r.json())
      .then((d) => setNeighborData(d))
      .catch(() => {});
  }, []);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;

      if (e.key === "Escape") {
        router.push("/concordance");
        return;
      }
      if (e.key === "ArrowLeft" && prevSlug !== null) {
        router.push(`/concordance/${prevSlug}`);
        return;
      }
      if (e.key === "ArrowRight" && nextSlug !== null) {
        router.push(`/concordance/${nextSlug}`);
        return;
      }
    },
    [router, prevSlug, nextSlug]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Resolve Wikipedia URL + image from ground_truth or by searching
  useEffect(() => {
    setWikiUrl(null);
    setWikiImage(null);
    setWikiSearching(false);
    if (!cluster) return;
    const gt = cluster.ground_truth;
    if (!gt) return;

    let cancelled = false;

    async function resolve() {
      // If we have an explicit wikipedia_url, use it directly
      if (gt!.wikipedia_url) {
        setWikiUrl(gt!.wikipedia_url);
        // Fetch image from the page summary API
        try {
          const urlObj = new URL(gt!.wikipedia_url);
          const lang = urlObj.hostname.split(".")[0];
          const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
          if (title) {
            const res = await fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`);
            if (res.ok) {
              const d = await res.json();
              if (d.originalimage?.source && !cancelled) setWikiImage(d.originalimage.source);
              else if (d.thumbnail?.source && !cancelled) setWikiImage(d.thumbnail.source.replace(/\/\d+px-/, "/800px-"));
            }
          }
        } catch { /* ok */ }
        return;
      }

      // Try to find article from linnaean/modern_name
      const searchTerms = [gt!.linnaean, gt!.modern_name].filter(Boolean) as string[];
      if (searchTerms.length === 0) return;

      setWikiSearching(true);
      for (const term of searchTerms) {
        try {
          const res = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`);
          if (!res.ok) continue;
          const d = await res.json();
          if (d.type === "disambiguation") continue;
          if (d.content_urls?.desktop?.page && !cancelled) {
            setWikiUrl(d.content_urls.desktop.page);
            if (d.originalimage?.source) setWikiImage(d.originalimage.source);
            else if (d.thumbnail?.source) setWikiImage(d.thumbnail.source.replace(/\/\d+px-/, "/800px-"));
            setWikiSearching(false);
            return;
          }
        } catch { /* try next */ }
      }
      if (!cancelled) setWikiSearching(false);
    }

    resolve();
    return () => { cancelled = true; };
  }, [cluster]);

  /* ── loading / error states ── */

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-[var(--border)] rounded w-1/4" />
          <div className="h-8 bg-[var(--border)] rounded w-1/3" />
          <div className="h-64 bg-[var(--border)] rounded" />
        </div>
      </div>
    );
  }

  if (!data || !cluster) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <p className="text-[var(--muted)] mb-4">Cluster not found.</p>
        <Link
          href="/concordance"
          className="text-sm text-[var(--accent)] hover:underline"
        >
          &larr; Back to Concordance
        </Link>
      </div>
    );
  }

  /* ── derived data ── */

  const gt = cluster.ground_truth;
  const catColor = CATEGORY_COLORS[cluster.category];
  const tintColor = CATEGORY_TINT[cluster.category] || "rgba(100, 116, 139, 0.25)";
  const identification = getIdentification(cluster);
  const bookIds = [...new Set(cluster.members.map((m) => m.book_id))];
  const langCount = new Set(
    bookIds.map((bid) => data.books.find((b) => b.id === bid)?.language).filter(Boolean)
  ).size;
  const mentionsByBook = getMentionsByBook(cluster.members);
  const maxMentions = Math.max(...mentionsByBook.map((b) => b.count), 1);
  const variantsByLang = getVariantsByLanguage(cluster.members, data.books);
  const clusterDisplayName = displayName(cluster);

  // Subtitle line
  let subtitle: string | null = null;
  if (gt) {
    if ((cluster.category === "PLANT" || cluster.category === "ANIMAL") && gt.linnaean) {
      subtitle = gt.linnaean;
    } else if (cluster.category === "PERSON" && gt.birth_year) {
      subtitle = `${gt.birth_year}\u2013${gt.death_year || "?"}`;
    } else if (clusterDisplayName.toLowerCase() !== cluster.canonical_name.toLowerCase()) {
      subtitle = cluster.canonical_name;
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* ─── 1. Breadcrumb ─── */}
      <nav className="flex items-center gap-2 text-sm text-[var(--muted)] mb-6">
        <Link href="/concordance" className="hover:text-[var(--foreground)] transition-colors">
          Concordance
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">{clusterDisplayName}</span>
        {fromSlug && (() => {
          const fromCluster = findClusterBySlug(fromSlug, data.clusters);
          if (!fromCluster) return null;
          return (
            <span className="ml-auto text-xs">
              <Link
                href={`/concordance/${fromSlug}`}
                className="text-[var(--accent)] hover:underline transition-colors"
              >
                &larr; Back to {displayName(fromCluster)}
              </Link>
            </span>
          );
        })()}
      </nav>

      {/* ─── 2. Hero Header with Wikipedia Image ─── */}
      <div className="relative mb-8 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--background)]">
        {/* Image layer — fades from invisible on left to visible on right */}
        {wikiImage && (
          <div className="absolute inset-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={wikiImage}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
              style={{
                WebkitMaskImage: "linear-gradient(to right, transparent 35%, rgba(0,0,0,0.1) 55%, rgba(0,0,0,0.5) 80%, black 100%)",
                maskImage: "linear-gradient(to right, transparent 35%, rgba(0,0,0,0.1) 55%, rgba(0,0,0,0.5) 80%, black 100%)",
              }}
            />
            {/* Category tint on upper-right corner */}
            <div
              className="absolute inset-0"
              style={{
                background: `radial-gradient(ellipse at top right, ${tintColor} 0%, transparent 60%)`,
              }}
            />
            {/* Subtle bottom fade */}
            <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-[var(--background)] to-transparent" />
            {wikiUrl && (
              <a
                href={wikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="absolute bottom-2 right-3 z-20 text-xs text-[var(--muted)] opacity-50 hover:opacity-100 hover:text-[var(--accent)] transition-all cursor-pointer"
              >
                Image: Wikipedia
              </a>
            )}
          </div>
        )}

        {/* Content layer */}
        <div className="relative z-10 px-8 py-10" style={{ minHeight: wikiImage ? "200px" : undefined }}>
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <h1 className="text-3xl font-bold">{clusterDisplayName}</h1>
            <span
              className={`${catColor?.badge || "bg-[var(--border)]"} px-2.5 py-0.5 rounded text-xs font-medium border`}
            >
              {cluster.category}
            </span>
            {cluster.subcategory && cluster.subcategory !== cluster.category && (
              <span className="text-xs text-[var(--muted)]">{cluster.subcategory}</span>
            )}
          </div>
          {subtitle && (
            <p className="text-lg text-[var(--muted)] mt-1">
              {(cluster.category === "PLANT" || cluster.category === "ANIMAL") && gt?.linnaean ? (
                <i>{subtitle}</i>
              ) : (
                subtitle
              )}
            </p>
          )}
          {gt?.note && (
            <blockquote className="text-sm text-[var(--muted)] mt-3 border-l-2 border-[var(--border)] pl-3 leading-relaxed max-w-2xl">
              {gt.note}
            </blockquote>
          )}
          {/* Stats row */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-[var(--muted)]">
            <span>
              <strong className="text-[var(--foreground)]">{cluster.book_count}</strong> book{cluster.book_count !== 1 ? "s" : ""}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{cluster.total_mentions}</strong> mention{cluster.total_mentions !== 1 ? "s" : ""}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{cluster.members.length}</strong> entr{cluster.members.length !== 1 ? "ies" : "y"}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{langCount}</strong> language{langCount !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      </div>

      {/* ─── 3. Three-Column Info Strip ─── */}
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {/* Card 1: Identification */}
        <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
            Identification
          </h3>
          {gt ? (
            <div className="space-y-2">
              <div className="flex items-start gap-3">
                {gt.portrait_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={gt.portrait_url}
                    alt=""
                    className="w-12 h-14 rounded object-cover border border-[var(--border)] shrink-0"
                  />
                ) : gt.wikipedia_url && !gt.portrait_url ? (
                  <WikiThumbnail url={gt.wikipedia_url} size="sm" />
                ) : null}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">{gt.modern_name}</p>
                  {gt.linnaean && (
                    <p className="text-xs italic text-[var(--muted)]">{gt.linnaean}</p>
                  )}
                  {gt.family && (
                    <p className="text-xs text-[var(--muted)]">
                      Family: <i>{gt.family}</i>
                    </p>
                  )}
                  {gt.birth_year && (
                    <p className="text-xs text-[var(--muted)]">
                      {gt.birth_year}&ndash;{gt.death_year || "?"}
                    </p>
                  )}
                </div>
              </div>
              {gt.description && (
                <p className="text-xs text-[var(--muted)] leading-relaxed">{gt.description}</p>
              )}
              {gt.wikidata_description && !gt.description && (
                <p className="text-xs text-[var(--muted)] leading-relaxed">
                  {gt.wikidata_description}
                </p>
              )}
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                    gt.confidence === "high"
                      ? "bg-green-500/20 text-green-600 dark:text-green-400"
                      : gt.confidence === "medium"
                      ? "bg-yellow-500/20 text-yellow-600 dark:text-yellow-400"
                      : "bg-red-500/20 text-red-600 dark:text-red-400"
                  }`}
                >
                  {gt.confidence} confidence
                </span>
                {gt.wikidata_id && (
                  <a
                    href={`https://www.wikidata.org/wiki/${gt.wikidata_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-xs font-mono text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                  >
                    {gt.wikidata_id}
                  </a>
                )}
              </div>
              {gt.semantic_gloss && (
                <p className="text-xs text-[var(--foreground)]/70 leading-relaxed mt-3 pt-3 border-t border-[var(--border)]">
                  {gt.semantic_gloss}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-[var(--muted)]">No identification available.</p>
          )}
        </div>

        {/* Card 2: Wikipedia */}
        <WikiCard url={wikiUrl} searching={wikiSearching} />

        {/* Card 3: Variants by Language */}
        <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <h3 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
            Variants by Language
          </h3>
          <div className="space-y-2.5">
            {Object.entries(variantsByLang).map(([lang, variants]) => (
              <div key={lang}>
                <p className="text-xs font-medium text-[var(--muted)] mb-1">
                  {BOOK_LANG_FLAGS[lang] || "?"}{" "}
                  <span className="opacity-70">{lang}</span>
                </p>
                <div className="flex flex-wrap gap-1">
                  {variants.slice(0, 10).map((v) => (
                    <span
                      key={v}
                      className="px-1.5 py-0.5 text-xs rounded bg-[var(--border)]/50 text-[var(--foreground)]"
                    >
                      {v}
                    </span>
                  ))}
                  {variants.length > 10 && (
                    <span className="px-1.5 py-0.5 text-xs text-[var(--muted)]">
                      +{variants.length - 10} more
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── 3b. Cross-References Panel (full-width) ─── */}
      {cluster.cross_references && cluster.cross_references.filter(r => r.target_cluster_id !== null).length > 0 && (() => {
        const refs = cluster.cross_references!.filter(r => r.target_cluster_id !== null);
        // Only show forward (non-reverse) refs as synonyms — reverse refs are co-occurrence noise
        const synonyms = refs.filter(r => !r.is_reverse && (r.link_type === "same_referent" || r.link_type === "cross_linguistic" || r.link_type === "orthographic_variant"));
        const contested = refs.filter(r => !r.is_reverse && r.link_type === "contested_identity");
        // Related column includes forward conceptual + all reverse refs (looser relationship)
        const related = refs.filter(r =>
          (!r.is_reverse && (r.link_type === "conceptual_overlap" || r.link_type === "derivation")) ||
          r.is_reverse
        );

        const LINK_TYPE_LABELS: Record<string, { label: string; color: string }> = {
          same_referent: { label: "synonym", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
          cross_linguistic: { label: "translation", color: "bg-blue-500/15 text-blue-700 dark:text-blue-400" },
          orthographic_variant: { label: "variant", color: "bg-slate-500/15 text-slate-700 dark:text-slate-400" },
          contested_identity: { label: "contested", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
          conceptual_overlap: { label: "related", color: "bg-purple-500/15 text-purple-700 dark:text-purple-400" },
          derivation: { label: "derived", color: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400" },
        };

        const RefItem = ({ xref: r }: { xref: CrossReference }) => {
          const [translation, setTranslation] = useState<string | null>(null);
          const [showTranslation, setShowTranslation] = useState(false);
          const [translating, setTranslating] = useState(false);
          const [fadeState, setFadeState] = useState<"visible" | "fading-out" | "fading-in">("visible");

          const typeInfo = r.is_reverse
            ? { label: "co-occurs", color: "bg-slate-500/15 text-slate-600 dark:text-slate-400" }
            : (LINK_TYPE_LABELS[r.link_type] || { label: r.link_type, color: "bg-gray-500/15 text-gray-600" });
          const targetSlug = r.target_cluster_id !== null
            ? (() => {
                const targetCluster = data.clusters.find(c => c.id === r.target_cluster_id);
                return targetCluster ? clusterSlug(targetCluster, data.clusters) : null;
              })()
            : null;

          const bookLang = data.books.find(b => b.id === r.source_book)?.language || "";
          const isNonEnglish = bookLang && bookLang !== "English";

          const handleSnippetClick = async () => {
            if (!isNonEnglish || !r.evidence_snippet) return;

            if (translation) {
              // Toggle: crossfade between original and translation
              setFadeState("fading-out");
              setTimeout(() => {
                setShowTranslation(prev => !prev);
                setFadeState("fading-in");
                setTimeout(() => setFadeState("visible"), 50);
              }, 250);
              return;
            }

            // First click: fetch translation
            setTranslating(true);
            try {
              const res = await fetch("/api/translate", {
                method: "POST",
                headers: { "Content-Type": "application/json" },
                body: JSON.stringify({ text: r.evidence_snippet, language: bookLang }),
              });
              const result = await res.json();
              if (result.translation) {
                setTranslation(result.translation);
                // Crossfade to translation
                setFadeState("fading-out");
                setTimeout(() => {
                  setShowTranslation(true);
                  setFadeState("fading-in");
                  setTimeout(() => setFadeState("visible"), 50);
                }, 250);
              }
            } catch {
              // silently fail
            } finally {
              setTranslating(false);
            }
          };

          const snippetText = showTranslation && translation
            ? translation.slice(0, 200)
            : r.evidence_snippet?.slice(0, 150) || "";
          const isTruncated = showTranslation
            ? (translation?.length || 0) > 200
            : (r.evidence_snippet?.length || 0) > 150;

          return (
            <div className="flex items-start gap-2 py-1.5 group">
              <span className={`shrink-0 px-1.5 py-0.5 rounded text-xs font-medium mt-0.5 ${typeInfo.color}`}>
                {typeInfo.label}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  {targetSlug ? (
                    <Link
                      href={`/concordance/${targetSlug}?from=${encodeURIComponent(slug)}`}
                      className="text-sm font-medium hover:text-[var(--accent)] transition-colors"
                    >
                      {r.found_name}
                    </Link>
                  ) : (
                    <span className="text-sm font-medium">{r.found_name}</span>
                  )}
                  {r.target_cluster_name && r.target_cluster_name !== r.found_name && (
                    <span className="text-xs text-[var(--muted)]">
                      ({r.target_cluster_name})
                    </span>
                  )}
                  <Link
                    href={`/books/${encodeURIComponent(r.source_book)}`}
                    className="text-xs text-[var(--muted)] font-mono hover:text-[var(--accent)] transition-colors"
                  >
                    {BOOK_SHORT_NAMES[r.source_book] || r.source_book}
                  </Link>
                </div>
                {r.evidence_snippet && (
                  <p
                    className={`text-xs leading-relaxed mt-0.5 line-clamp-2 transition-opacity duration-250 ease-in-out ${
                      isNonEnglish ? "cursor-pointer hover:text-[var(--foreground)]" : ""
                    } ${showTranslation ? "text-[var(--foreground)]/80 italic" : "text-[var(--muted)]"} ${
                      fadeState === "fading-out" ? "opacity-0" : fadeState === "fading-in" ? "opacity-0" : "opacity-100"
                    }`}
                    onClick={handleSnippetClick}
                    title={isNonEnglish ? (showTranslation ? "Click to show original" : "Click to translate") : undefined}
                    style={{ transition: "opacity 250ms ease" }}
                  >
                    {translating ? (
                      <span className="inline-flex items-center gap-1.5 text-[var(--muted)] not-italic">
                        <span className="w-2.5 h-2.5 border border-[var(--accent)] border-t-transparent rounded-full animate-spin inline-block" />
                        Translating...
                      </span>
                    ) : (
                      <>
                        &ldquo;{snippetText}{isTruncated ? "\u2026" : ""}&rdquo;
                        {showTranslation && (
                          <span className="text-xs text-[var(--accent)] ml-1 not-italic font-medium">EN</span>
                        )}
                      </>
                    )}
                  </p>
                )}
              </div>
            </div>
          );
        };

        // Check if we have content for at least one column
        const hasContent = synonyms.length > 0 || contested.length > 0 || related.length > 0;
        if (!hasContent) return null;

        return (
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)] mb-8">
            <div className="grid md:grid-cols-3 gap-6">
              {/* Column 1: Synonyms & Translations */}
              <div>
                <h4 className="text-xs uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Synonyms &amp; Translations
                  {synonyms.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{synonyms.length}</span>
                  )}
                </h4>
                {synonyms.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {synonyms.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {synonyms.length > 8 && (
                      <p className="text-xs text-[var(--muted)] pt-2">
                        +{synonyms.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>

              {/* Column 2: Contested Identities */}
              <div>
                <h4 className="text-xs uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Contested Identities
                  {contested.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{contested.length}</span>
                  )}
                </h4>
                {contested.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {contested.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {contested.length > 8 && (
                      <p className="text-xs text-[var(--muted)] pt-2">
                        +{contested.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>

              {/* Column 3: Related & Co-occurring */}
              <div>
                <h4 className="text-xs uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Related &amp; Co-occurring
                  {related.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{related.length}</span>
                  )}
                </h4>
                {related.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {related.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {related.length > 8 && (
                      <p className="text-xs text-[var(--muted)] pt-2">
                        +{related.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* ─── 4. Mention Distribution Chart ─── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Mention Distribution
        </h2>
        <div className="space-y-2">
          {mentionsByBook.map(({ book_id, count }) => {
            const book = data.books.find((b) => b.id === book_id);
            const pct = (count / maxMentions) * 100;
            return (
              <div key={book_id} className="flex items-center gap-3">
                <div className="w-24 shrink-0 flex items-center gap-1.5 text-xs">
                  <span className="font-mono text-[var(--muted)]">
                    {BOOK_LANG_FLAGS[book?.language || ""] || "?"}
                  </span>
                  <Link
                    href={`/books/${encodeURIComponent(book_id)}`}
                    className="truncate hover:text-[var(--accent)] transition-colors"
                  >
                    {BOOK_SHORT_NAMES[book_id] || book?.title || book_id}
                  </Link>
                </div>
                <div className="flex-1 h-5 bg-[var(--border)]/30 rounded overflow-hidden">
                  <div
                    className={`h-full rounded ${CATEGORY_BAR_COLORS[cluster.category] || "bg-gray-500"} transition-all`}
                    style={{ width: `${Math.max(pct, 2)}%` }}
                  />
                </div>
                <span className="w-10 text-right text-xs font-mono text-[var(--muted)] tabular-nums">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── 5. Names Across Texts Mosaic ─── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Names Across Texts
        </h2>
        <div className="space-y-4">
          {data.books
            .filter((b) => cluster.members.some((m) => m.book_id === b.id))
            .map((book) => {
              const bookMembers = cluster.members.filter((m) => m.book_id === book.id);
              return (
                <div key={book.id}>
                  <h3 className="text-xs font-medium mb-2 flex items-center gap-2">
                    <Link
                      href={`/books/${encodeURIComponent(book.id)}`}
                      className="hover:text-[var(--accent)] transition-colors"
                    >
                      {BOOK_SHORT_NAMES[book.id] || book.title}
                    </Link>
                    <span className="text-[var(--muted)]">{book.year}</span>
                    <span className="font-mono text-[var(--muted)] text-xs">
                      {BOOK_LANG_FLAGS[book.language] || "?"}
                    </span>
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {bookMembers.map((member) => (
                      <Link
                        key={member.entity_id}
                        href={`/books/${encodeURIComponent(book.id)}/entity/${encodeURIComponent(member.entity_id)}`}
                        className="group/tile px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--border)]/40 transition-colors"
                      >
                        <span className="text-sm font-medium group-hover/tile:text-[var(--accent)] transition-colors">
                          {member.name}
                        </span>
                        <span className="text-xs text-[var(--muted)] ml-2 font-mono tabular-nums">
                          {member.count}
                        </span>
                        {member.variants.length > 1 && (
                          <span className="text-xs text-[var(--muted)] ml-1.5">
                            ({member.variants.length} variants)
                          </span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              );
            })}
        </div>
      </section>

      {/* ─── 6. Comparison Table ─── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          All Entries
        </h2>
        <div className="border border-[var(--border)] rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="text-left px-3 py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium w-10">
                    Lang
                  </th>
                  <th className="text-left px-3 py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium">
                    Book
                  </th>
                  <th className="text-left px-3 py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium">
                    Name
                  </th>
                  <th className="text-left px-3 py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium hidden md:table-cell">
                    Context
                  </th>
                  <th className="text-right px-3 py-2 text-xs uppercase tracking-widest text-[var(--muted)] font-medium w-14">
                    Count
                  </th>
                  <th className="px-3 py-2 w-16" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {[...cluster.members]
                  .sort((a, b) => b.count - a.count)
                  .map((member) => {
                    const book = data.books.find((b) => b.id === member.book_id);
                    return (
                      <tr
                        key={`${member.book_id}-${member.entity_id}`}
                        className="hover:bg-[var(--border)]/20 transition-colors"
                      >
                        <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                          {BOOK_LANG_FLAGS[book?.language || ""] || "?"}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          <Link
                            href={`/books/${encodeURIComponent(member.book_id)}`}
                            className="hover:text-[var(--accent)] transition-colors"
                          >
                            {BOOK_SHORT_NAMES[member.book_id] || book?.title || member.book_id}
                          </Link>
                        </td>
                        <td className="px-3 py-2">
                          <span className="font-medium">{member.name}</span>
                          {member.variants.length > 1 && (
                            <span className="text-xs text-[var(--muted)] ml-1.5">
                              +{member.variants.length - 1} variant{member.variants.length - 1 !== 1 ? "s" : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-[var(--muted)] hidden md:table-cell max-w-xs">
                          {member.contexts[0] ? (
                            <span className="line-clamp-2">
                              &ldquo;
                              <AutoLinkedText
                                text={member.contexts[0].length > 100 ? member.contexts[0].slice(0, 97) + "\u2026" : member.contexts[0]}
                                nameIndex={nameIndex}
                                excludeClusterId={cluster.id}
                              />
                              &rdquo;
                            </span>
                          ) : ""}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                          {member.count}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Link
                            href={`/books/${encodeURIComponent(member.book_id)}/entity/${encodeURIComponent(member.entity_id)}`}
                            className="text-xs text-[var(--accent)] hover:underline whitespace-nowrap"
                          >
                            View &rarr;
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ─── 7. Semantic Neighborhood ─── */}
      <section className="mb-8">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Semantic Neighborhood
        </h2>
        <p className="text-xs text-[var(--muted)] mb-3">
          Entities closest to {clusterDisplayName} in cross-lingual embedding space. Click a node to navigate.
        </p>
        <NeighborhoodGraph clusterId={cluster.id} clusters={data.clusters} books={data.books} />
      </section>

      {/* ─── 7b. Also Appears With ─── */}
      {neighborData && (() => {
        const neighbors = neighborData.neighbors[String(cluster.id)];
        if (!neighbors || neighbors.length === 0) return null;
        const top8 = neighbors.slice(0, 8);
        const maxSim = top8[0]?.sim || 1;
        const clusterMap = new Map(data.clusters.map((c) => [c.id, c]));

        return (
          <section className="mb-8">
            <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
              Also Appears With
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
              {top8.map((n) => {
                const nc = clusterMap.get(n.id);
                if (!nc) return null;
                const nSlug = slugMap.get(n.id) || "";
                const gt = nc.ground_truth;
                const name = displayName(nc);
                const subtitle = name.toLowerCase() !== nc.canonical_name.toLowerCase()
                  ? nc.canonical_name
                  : nc.members[0]?.contexts[0]
                    ? (nc.members[0].contexts[0].length > 60 ? nc.members[0].contexts[0].slice(0, 57) + "\u2026" : nc.members[0].contexts[0])
                    : null;
                const dotClass = CATEGORY_BAR_COLORS[nc.category] || "bg-slate-500";
                const barPct = (n.sim / maxSim) * 100;
                const hexColor = CAT_HEX[nc.category] || "#64748b";

                return (
                  <Link
                    key={n.id}
                    href={`/concordance/${nSlug}?from=${encodeURIComponent(slug)}`}
                    className="flex items-center gap-3 px-3 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--border)]/40 transition-colors group/neighbor"
                  >
                    <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${dotClass}`} />
                    <div className="flex-1 min-w-0">
                      <p className="text-sm font-medium truncate group-hover/neighbor:text-[var(--accent)] transition-colors">
                        {name}
                      </p>
                      {subtitle && (
                        <p className="text-xs text-[var(--muted)] truncate">{subtitle}</p>
                      )}
                    </div>
                    <div className="w-16 shrink-0 flex items-center gap-1.5">
                      <div className="flex-1 h-1 bg-[var(--border)]/50 rounded-full overflow-hidden">
                        <div
                          className="h-full rounded-full"
                          style={{ width: `${barPct}%`, backgroundColor: hexColor }}
                        />
                      </div>
                      <span className="text-xs font-mono text-[var(--muted)] tabular-nums w-7 text-right">
                        {Math.round(n.sim * 100)}
                      </span>
                    </div>
                  </Link>
                );
              })}
            </div>
          </section>
        );
      })()}

      {/* ─── 8. Navigation ─── */}
      <nav className="flex items-center justify-between pt-6 border-t border-[var(--border)]">
        {prevSlug !== null ? (
          <Link
            href={`/concordance/${prevSlug}`}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--border)]/30 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Previous
          </Link>
        ) : (
          <span />
        )}
        <Link
          href="/concordance"
          className="px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
        >
          Back to Concordance
        </Link>
        {nextSlug !== null ? (
          <Link
            href={`/concordance/${nextSlug}`}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--border)]/30 transition-colors"
          >
            Next
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ) : (
          <span />
        )}
      </nav>

      {/* Keyboard hint */}
      <p className="text-xs text-[var(--muted)] mt-4 text-center opacity-40">
        Use arrow keys to navigate between clusters &middot; Escape to return to list
      </p>
    </div>
  );
}
