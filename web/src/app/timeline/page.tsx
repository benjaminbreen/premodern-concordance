"use client";

import { useEffect, useState, useMemo, useRef, useCallback } from "react";
import Link from "next/link";
import { CAT_HEX, CATEGORY_COLORS, CATEGORY_ORDER_STREAM as CATEGORY_ORDER } from "@/lib/colors";
import { BOOK_SHORT_NAMES } from "@/lib/books";

// ── Types ──────────────────────────────────────────────────────────────

interface BookMeta {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
}

interface ClusterMember {
  entity_id: string;
  book_id: string;
  name: string;
  category: string;
  count: number;
  variants?: string[];
}

interface Cluster {
  id: number;
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  members: ClusterMember[];
}

// ── Constants ──────────────────────────────────────────────────────────


// SVG dimensions
const SVG_W = 900;
const SVG_H = 280;
const PAD_LEFT = 50;
const PAD_RIGHT = 50;
const PAD_TOP = 20;
const PAD_BOTTOM = 30;

// Frequency chart dimensions
const FREQ_H = 280;
const FREQ_PAD_TOP = 25;
const FREQ_PAD_BOTTOM = 30;
const FREQ_PAD_LEFT = 60;

// Unique trace colors (distinct from each other in both light/dark mode)
const TRACE_COLORS = [
  "#3b82f6", // blue
  "#ef4444", // red
  "#f59e0b", // amber
  "#8b5cf6", // violet
  "#14b8a6", // teal
];

// ── Helpers ────────────────────────────────────────────────────────────

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Compute category counts per book from clusters — single pass O(total_members) */
function computeBookClusters(
  books: BookMeta[],
  clusters: Cluster[]
): Map<string, Record<string, number>> {
  const map = new Map<string, Record<string, number>>();
  for (const b of books) map.set(b.id, {});
  for (const cluster of clusters) {
    const seenBooks = new Set<string>();
    for (const m of cluster.members) {
      if (seenBooks.has(m.book_id)) continue;
      seenBooks.add(m.book_id);
      const rec = map.get(m.book_id);
      if (rec) {
        rec[cluster.category] = (rec[cluster.category] || 0) + 1;
      }
    }
  }
  return map;
}

function xScale(
  year: number,
  minYear: number,
  maxYear: number
): number {
  return (
    PAD_LEFT +
    ((year - minYear) / (maxYear - minYear)) * (SVG_W - PAD_LEFT - PAD_RIGHT)
  );
}

/** Build a smooth area path using cubic bezier between top and bottom point arrays */
function buildAreaPath(
  topPoints: { x: number; y: number }[],
  bottomPoints: { x: number; y: number }[]
): string {
  if (topPoints.length < 2) return "";
  const n = topPoints.length;

  let d = `M ${topPoints[0].x},${topPoints[0].y}`;
  for (let i = 1; i < n; i++) {
    const prev = topPoints[i - 1];
    const curr = topPoints[i];
    const dx = curr.x - prev.x;
    const cp1x = prev.x + dx / 3;
    const cp2x = curr.x - dx / 3;
    d += ` C ${cp1x},${prev.y} ${cp2x},${curr.y} ${curr.x},${curr.y}`;
  }

  d += ` L ${bottomPoints[n - 1].x},${bottomPoints[n - 1].y}`;

  for (let i = n - 2; i >= 0; i--) {
    const prev = bottomPoints[i + 1];
    const curr = bottomPoints[i];
    const dx = curr.x - prev.x;
    const cp1x = prev.x + dx / 3;
    const cp2x = curr.x - dx / 3;
    d += ` C ${cp1x},${prev.y} ${cp2x},${curr.y} ${curr.x},${curr.y}`;
  }

  d += " Z";
  return d;
}

/** Build a line path with Catmull-Rom smoothing (0 = straight, 5 = very smooth) */
function buildSmoothPath(
  points: { x: number; y: number }[],
  smoothing: number
): string {
  if (points.length === 0) return "";
  if (points.length === 1) return `M ${points[0].x},${points[0].y}`;
  if (smoothing === 0 || points.length === 2) {
    return points.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`).join(" ");
  }

  const tension = smoothing / 5; // normalize 0–1
  let d = `M ${points[0].x},${points[0].y}`;

  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[Math.max(0, i - 1)];
    const p1 = points[i];
    const p2 = points[i + 1];
    const p3 = points[Math.min(points.length - 1, i + 2)];

    const cp1x = p1.x + ((p2.x - p0.x) * tension) / 3;
    const cp1y = p1.y + ((p2.y - p0.y) * tension) / 3;
    const cp2x = p2.x - ((p3.x - p1.x) * tension) / 3;
    const cp2y = p2.y - ((p3.y - p1.y) * tension) / 3;

    d += ` C ${cp1x},${cp1y} ${cp2x},${cp2y} ${p2.x},${p2.y}`;
  }

  return d;
}

// ── Main Component ─────────────────────────────────────────────────────

export default function TimelinePage() {
  const [books, setBooks] = useState<BookMeta[]>([]);
  const [clusters, setClusters] = useState<Cluster[]>([]);
  const [loading, setLoading] = useState(true);
  const [activeTab, setActiveTab] = useState<"overview" | "explore">(
    "overview"
  );

  // Overview state
  const [hoveredBookIdx, setHoveredBookIdx] = useState<number | null>(null);
  const [hoveredCategory, setHoveredCategory] = useState<string | null>(null);
  const [highlightedCategory, setHighlightedCategory] = useState<string | null>(null);
  const [selectedBookId, setSelectedBookId] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<"absolute" | "relative">("absolute");
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Explore state
  const [searchQuery, setSearchQuery] = useState("");
  const [traces, setTraces] = useState<Cluster[]>([]);
  const [showDropdown, setShowDropdown] = useState(false);
  const [hoveredDot, setHoveredDot] = useState<{ traceId: number; bookId: string } | null>(null);
  const [smoothing, setSmoothing] = useState(2);
  const [hiddenTraces, setHiddenTraces] = useState<Set<number>>(new Set());
  const [expandedTrace, setExpandedTrace] = useState<number | null>(null);
  const searchRef = useRef<HTMLDivElement>(null);
  const freqContainerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((r) => r.json())
      .then((data) => {
        setBooks(data.books);
        setClusters(data.clusters);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  // Click outside to close dropdown
  useEffect(() => {
    function handler(e: MouseEvent) {
      if (
        searchRef.current &&
        !searchRef.current.contains(e.target as Node)
      ) {
        setShowDropdown(false);
      }
    }
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, []);

  // ── Derived data ───────────────────────────────────────────────────

  const sortedBooks = useMemo(
    () => [...books].sort((a, b) => a.year - b.year),
    [books]
  );

  const bookClusters = useMemo(
    () => computeBookClusters(books, clusters),
    [books, clusters]
  );

  const { minYear, maxYear } = useMemo(() => {
    if (sortedBooks.length === 0) return { minYear: 1500, maxYear: 1900 };
    return {
      minYear: sortedBooks[0].year,
      maxYear: sortedBooks[sortedBooks.length - 1].year,
    };
  }, [sortedBooks]);

  const extMinYear = minYear - 15;
  const extMaxYear = maxYear + 15;

  const presentCategories = useMemo(() => {
    const cats = new Set<string>();
    for (const rec of bookClusters.values()) {
      for (const cat of Object.keys(rec)) cats.add(cat);
    }
    return CATEGORY_ORDER.filter((c) => cats.has(c));
  }, [bookClusters]);

  // ── Pre-computed top entities per (book, category) ─────────────────

  const bookCatTopEntities = useMemo(() => {
    const map = new Map<string, Map<string, string[]>>();
    // First pass: collect all clusters per (book, category)
    const bookCatClusters = new Map<string, Map<string, { name: string; count: number }[]>>();
    for (const cluster of clusters) {
      const seenBooks = new Set<string>();
      for (const m of cluster.members) {
        if (seenBooks.has(m.book_id)) continue;
        seenBooks.add(m.book_id);
        if (!bookCatClusters.has(m.book_id)) {
          bookCatClusters.set(m.book_id, new Map());
        }
        const catMap = bookCatClusters.get(m.book_id)!;
        if (!catMap.has(cluster.category)) {
          catMap.set(cluster.category, []);
        }
        catMap.get(cluster.category)!.push({
          name: cluster.canonical_name,
          count: cluster.total_mentions,
        });
      }
    }
    // Sort and take top 3
    for (const [bookId, catMap] of bookCatClusters) {
      const resultCatMap = new Map<string, string[]>();
      for (const [cat, items] of catMap) {
        items.sort((a, b) => b.count - a.count);
        resultCatMap.set(cat, items.slice(0, 3).map((i) => i.name));
      }
      map.set(bookId, resultCatMap);
    }
    return map;
  }, [clusters]);

  // ── Stream chart data ──────────────────────────────────────────────

  const streamData = useMemo(() => {
    if (sortedBooks.length === 0) return null;

    type DataPoint = { year: number; bookId: string | null; counts: Record<string, number> };
    const points: DataPoint[] = [];

    points.push({ year: extMinYear, bookId: null, counts: {} });
    for (const book of sortedBooks) {
      const rec = bookClusters.get(book.id) || {};
      points.push({ year: book.year, bookId: book.id, counts: rec });
    }
    points.push({ year: extMaxYear, bookId: null, counts: {} });

    const n = points.length;
    const numCats = presentCategories.length;

    // Compute totals per point
    const rawTotals = points.map((p) =>
      presentCategories.reduce(
        (sum, cat) => sum + (p.counts[cat] || 0),
        0
      )
    );

    // Normalize counts if in relative mode
    const NORM_TOTAL = 100;
    const effectiveCounts: Record<string, number>[] = points.map((p, j) => {
      if (viewMode === "relative" && rawTotals[j] > 0) {
        const result: Record<string, number> = {};
        for (const cat of presentCategories) {
          result[cat] = ((p.counts[cat] || 0) / rawTotals[j]) * NORM_TOTAL;
        }
        return result;
      }
      return p.counts;
    });

    const totals = effectiveCounts.map((ec) =>
      presentCategories.reduce((sum, cat) => sum + (ec[cat] || 0), 0)
    );
    const maxTotal = Math.max(...totals, 1);

    const chartH = SVG_H - PAD_TOP - PAD_BOTTOM;
    const scale = chartH / maxTotal;

    // Stack categories and center (silhouette)
    const stacked: { top: number; bottom: number }[][] = Array.from(
      { length: numCats },
      () => Array.from({ length: n }, () => ({ top: 0, bottom: 0 }))
    );

    for (let j = 0; j < n; j++) {
      const total = totals[j];
      const totalHeight = total * scale;
      const centerY = PAD_TOP + chartH / 2;
      let y = centerY + totalHeight / 2;

      for (let i = 0; i < numCats; i++) {
        const cat = presentCategories[i];
        const val = (effectiveCounts[j][cat] || 0) * scale;
        stacked[i][j] = { bottom: y, top: y - val };
        y -= val;
      }
    }

    // Build paths
    const paths = presentCategories.map((cat, i) => {
      const topPts = stacked[i].map((s, j) => ({
        x: xScale(points[j].year, extMinYear, extMaxYear),
        y: s.top,
      }));
      const bottomPts = stacked[i].map((s, j) => ({
        x: xScale(points[j].year, extMinYear, extMaxYear),
        y: s.bottom,
      }));
      return {
        category: cat,
        d: buildAreaPath(topPts, bottomPts),
        color: CAT_HEX[cat] || "#888",
      };
    });

    // Hover columns
    const bookPoints = points.slice(1, -1);
    const hoverCols = bookPoints.map((bp, idx) => {
      const bx = xScale(bp.year, extMinYear, extMaxYear);
      const prevX =
        idx === 0
          ? PAD_LEFT
          : xScale(bookPoints[idx - 1].year, extMinYear, extMaxYear);
      const nextX =
        idx === bookPoints.length - 1
          ? SVG_W - PAD_RIGHT
          : xScale(bookPoints[idx + 1].year, extMinYear, extMaxYear);
      const left = (prevX + bx) / 2;
      const right = (bx + nextX) / 2;
      return {
        bookId: bp.bookId!,
        x: bx,
        left,
        width: right - left,
        year: bp.year,
      };
    });

    // Stacked bounds for band-aware hover detection
    // stackedBounds[catIdx][pointIdx] = { top, bottom } in SVG coords
    const stackedBounds = stacked;

    return { paths, hoverCols, points, totals, rawTotals, stackedBounds };
  }, [sortedBooks, bookClusters, presentCategories, extMinYear, extMaxYear, viewMode]);

  // ── Grid lines ─────────────────────────────────────────────────────

  const gridLines = useMemo(() => {
    const lines: { x: number; year: number }[] = [];
    const startDecade = Math.ceil(extMinYear / 50) * 50;
    for (let y = startDecade; y <= extMaxYear; y += 50) {
      lines.push({ x: xScale(y, extMinYear, extMaxYear), year: y });
    }
    return lines;
  }, [extMinYear, extMaxYear]);

  // ── SVG mouse handler for band-aware hover ─────────────────────────

  const handleSvgMouseMove = useCallback(
    (e: React.MouseEvent<SVGSVGElement>) => {
      if (!streamData || !svgRef.current) return;
      const svg = svgRef.current;
      const rect = svg.getBoundingClientRect();
      // Convert client coords to SVG coords
      const svgX = ((e.clientX - rect.left) / rect.width) * SVG_W;
      const svgY = ((e.clientY - rect.top) / rect.height) * SVG_H;

      // Find which book column we're in
      let bookIdx: number | null = null;
      for (let i = 0; i < streamData.hoverCols.length; i++) {
        const col = streamData.hoverCols[i];
        if (svgX >= col.left && svgX < col.left + col.width) {
          bookIdx = i;
          break;
        }
      }

      if (bookIdx !== null) {
        // pointIdx in stacked array = bookIdx + 1 (skip taper start)
        const pointIdx = bookIdx + 1;
        let foundCat: string | null = null;

        // Scan bands to find which one contains svgY
        for (let catIdx = 0; catIdx < presentCategories.length; catIdx++) {
          const bounds = streamData.stackedBounds[catIdx][pointIdx];
          if (svgY >= bounds.top && svgY <= bounds.bottom) {
            foundCat = presentCategories[catIdx];
            break;
          }
        }

        setHoveredBookIdx(bookIdx);
        setHoveredCategory(foundCat);
      } else {
        setHoveredBookIdx(null);
        setHoveredCategory(null);
      }
    },
    [streamData, presentCategories]
  );

  const handleSvgMouseLeave = useCallback(() => {
    setHoveredBookIdx(null);
    setHoveredCategory(null);
  }, []);

  // ── Explore: search results ────────────────────────────────────────

  const searchResults = useMemo(() => {
    if (!searchQuery.trim()) return [];
    const q = searchQuery.toLowerCase();
    const matched = clusters.filter((c) =>
      c.canonical_name.toLowerCase().includes(q)
    );
    matched.sort((a, b) => {
      const aPrefix = a.canonical_name.toLowerCase().startsWith(q) ? 0 : 1;
      const bPrefix = b.canonical_name.toLowerCase().startsWith(q) ? 0 : 1;
      if (aPrefix !== bPrefix) return aPrefix - bPrefix;
      return b.book_count - a.book_count;
    });
    return matched.slice(0, 8);
  }, [searchQuery, clusters]);

  const popularClusters = useMemo(
    () =>
      clusters
        .filter((c) => c.book_count >= 2)
        .sort((a, b) => b.book_count - a.book_count)
        .slice(0, 12),
    [clusters]
  );

  // ── Frequency chart data (ngram-style) ────────────────────────────

  const frequencyData = useMemo(() => {
    if (traces.length === 0) return null;

    // For each book, compute total mentions across all entities
    const bookTotalMentions = new Map<string, number>();
    for (const cluster of clusters) {
      for (const m of cluster.members) {
        bookTotalMentions.set(
          m.book_id,
          (bookTotalMentions.get(m.book_id) || 0) + m.count
        );
      }
    }

    const traceLines = traces.map((cluster, traceIdx) => {
      const dataPoints: { bookId: string; year: number; density: number; count: number; name: string }[] = [];
      const membersByBook = new Map<string, ClusterMember>();
      for (const m of cluster.members) {
        // Take the member with highest count per book
        const existing = membersByBook.get(m.book_id);
        if (!existing || m.count > existing.count) {
          membersByBook.set(m.book_id, m);
        }
      }

      for (const [bookId, member] of membersByBook) {
        const book = books.find((b) => b.id === bookId);
        if (!book) continue;
        const totalInBook = bookTotalMentions.get(bookId) || 1;
        const density = (member.count / totalInBook) * 1000;
        dataPoints.push({
          bookId,
          year: book.year,
          density,
          count: member.count,
          name: member.name,
        });
      }
      dataPoints.sort((a, b) => a.year - b.year);

      return {
        clusterId: cluster.id,
        clusterName: cluster.canonical_name,
        category: cluster.category,
        color: TRACE_COLORS[traceIdx % TRACE_COLORS.length],
        points: dataPoints,
      };
    });

    // Compute max density across all traces
    let maxDensity = 0;
    for (const line of traceLines) {
      for (const p of line.points) {
        if (p.density > maxDensity) maxDensity = p.density;
      }
    }
    maxDensity = Math.max(maxDensity, 0.1);

    // All book IDs in order
    const allBookIds = new Set<string>();
    for (const line of traceLines) {
      for (const p of line.points) allBookIds.add(p.bookId);
    }

    return { traceLines, maxDensity, allBookIds };
  }, [traces, clusters, books]);

  // ── Selected book detail ───────────────────────────────────────────

  const selectedBook = useMemo(
    () => books.find((b) => b.id === selectedBookId) || null,
    [books, selectedBookId]
  );

  const selectedBookCats = useMemo(() => {
    if (!selectedBookId) return [];
    const rec = bookClusters.get(selectedBookId) || {};
    return Object.entries(rec)
      .sort(([, a], [, b]) => b - a);
  }, [selectedBookId, bookClusters]);

  const selectedBookTopEntities = useMemo(() => {
    if (!selectedBookId) return [];
    return clusters
      .filter((c) => c.members.some((m) => m.book_id === selectedBookId))
      .sort((a, b) => b.book_count - a.book_count)
      .slice(0, 12);
  }, [selectedBookId, clusters]);

  // ── Handlers ───────────────────────────────────────────────────────

  const addTrace = useCallback(
    (cluster: Cluster) => {
      if (traces.length >= 5) return;
      if (traces.some((t) => t.id === cluster.id)) return;
      setTraces((prev) => [...prev, cluster]);
      setSearchQuery("");
      setShowDropdown(false);
    },
    [traces]
  );

  const removeTrace = useCallback((id: number) => {
    setTraces((prev) => prev.filter((t) => t.id !== id));
    setHiddenTraces((prev) => {
      const next = new Set(prev);
      next.delete(id);
      return next;
    });
    setExpandedTrace((prev) => (prev === id ? null : prev));
  }, []);

  const toggleTraceVisibility = useCallback((id: number) => {
    setHiddenTraces((prev) => {
      const next = new Set(prev);
      if (next.has(id)) next.delete(id);
      else next.add(id);
      return next;
    });
  }, []);

  // ── Compute band opacity ──────────────────────────────────────────

  const activeCat = hoveredCategory || highlightedCategory;

  function bandOpacity(cat: string): number {
    if (!activeCat) return 0.75;
    return cat === activeCat ? 0.9 : 0.15;
  }

  // ── Render ─────────────────────────────────────────────────────────

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-[var(--border)] rounded w-1/4" />
          <div className="h-4 bg-[var(--border)] rounded w-1/2" />
          <div className="h-64 bg-[var(--border)] rounded" />
        </div>
      </div>
    );
  }

  const maxCatCount = selectedBookCats.length > 0 ? selectedBookCats[0][1] : 1;

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8 animate-fade-up delay-0">
        <h1 className="text-3xl font-bold mb-2">Timeline</h1>
        <p className="text-[var(--muted)] max-w-2xl">
          {sortedBooks.length} texts across{" "}
          {maxYear - minYear > 0
            ? `${maxYear - minYear} years`
            : "the corpus"}
          {" "}&mdash; visualizing the distribution and trajectories of{" "}
          {clusters.length.toLocaleString()} entity clusters.
        </p>
      </div>

      {/* Tab switcher */}
      <div className="flex items-center gap-1 p-1 rounded-lg bg-[var(--border)]/50 w-fit mb-8 animate-fade-up delay-1">
        {(["overview", "explore"] as const).map((tab) => (
          <button
            key={tab}
            onClick={() => setActiveTab(tab)}
            className={`px-4 py-1.5 rounded-md text-sm font-medium transition-colors ${
              activeTab === tab
                ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            {tab === "overview" ? "Overview" : "Explore"}
          </button>
        ))}
      </div>

      {/* ═══════════════ TAB 1: OVERVIEW ═══════════════ */}
      {activeTab === "overview" && (
        <div className="animate-fade-up delay-2">
          {/* Legend + view mode toggle */}
          <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mb-4">
            {/* Interactive legend */}
            <div className="flex flex-wrap gap-x-3 gap-y-1.5 flex-1">
              {presentCategories.map((cat) => {
                const isActive = highlightedCategory === cat;
                return (
                  <button
                    key={cat}
                    onClick={() =>
                      setHighlightedCategory(isActive ? null : cat)
                    }
                    className={`flex items-center gap-1.5 px-1.5 py-0.5 rounded transition-all cursor-pointer ${
                      isActive
                        ? "ring-1 ring-[var(--foreground)]/30 bg-[var(--border)]/30"
                        : "hover:bg-[var(--border)]/20"
                    } ${
                      highlightedCategory && !isActive
                        ? "opacity-40"
                        : "opacity-100"
                    }`}
                  >
                    <span
                      className="w-2.5 h-2.5 rounded-full"
                      style={{ backgroundColor: CAT_HEX[cat] }}
                    />
                    <span className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)]">
                      {cat}
                    </span>
                  </button>
                );
              })}
            </div>

            {/* Absolute / Relative toggle */}
            <div className="flex items-center gap-0.5 p-0.5 rounded-md bg-[var(--border)]/50 text-[10px] uppercase tracking-[0.1em]">
              {(["absolute", "relative"] as const).map((mode) => (
                <button
                  key={mode}
                  onClick={() => setViewMode(mode)}
                  className={`px-2.5 py-1 rounded transition-colors ${
                    viewMode === mode
                      ? "bg-[var(--card)] text-[var(--foreground)] shadow-sm font-medium"
                      : "text-[var(--muted)] hover:text-[var(--foreground)]"
                  }`}
                >
                  {mode}
                </button>
              ))}
            </div>
          </div>

          {/* Stream chart */}
          {streamData && (
            <div className="relative">
              <svg
                ref={svgRef}
                viewBox={`0 0 ${SVG_W} ${SVG_H}`}
                className="w-full h-auto cursor-crosshair"
                style={{ maxHeight: 340 }}
                onMouseMove={handleSvgMouseMove}
                onMouseLeave={handleSvgMouseLeave}
                onClick={() => {
                  if (hoveredBookIdx !== null) {
                    const col = streamData.hoverCols[hoveredBookIdx];
                    setSelectedBookId(
                      selectedBookId === col.bookId ? null : col.bookId
                    );
                  }
                }}
              >
                {/* Grid lines */}
                {gridLines.map((gl) => (
                  <g key={gl.year}>
                    <line
                      x1={gl.x}
                      y1={PAD_TOP}
                      x2={gl.x}
                      y2={SVG_H - PAD_BOTTOM}
                      stroke="var(--border)"
                      strokeWidth={0.5}
                    />
                    <text
                      x={gl.x}
                      y={SVG_H - 10}
                      textAnchor="middle"
                      className="fill-[var(--muted)]"
                      style={{
                        fontSize: "10px",
                        fontFamily: "monospace",
                      }}
                    >
                      {gl.year}
                    </text>
                  </g>
                ))}

                {/* Relative mode: Y-axis percentage ticks */}
                {viewMode === "relative" && (() => {
                  const chartH = SVG_H - PAD_TOP - PAD_BOTTOM;
                  const centerY = PAD_TOP + chartH / 2;
                  // In relative mode, total is always NORM_TOTAL=100, scale = chartH/100
                  const scale = chartH / 100;
                  const halfHeight = (100 * scale) / 2;
                  const ticks = [0, 25, 50, 75, 100];
                  return ticks.map((pct) => {
                    const y = centerY + halfHeight - (pct / 100) * (2 * halfHeight);
                    return (
                      <g key={`pct-${pct}`}>
                        <line
                          x1={PAD_LEFT}
                          y1={y}
                          x2={SVG_W - PAD_RIGHT}
                          y2={y}
                          stroke="var(--border)"
                          strokeWidth={0.3}
                          strokeDasharray="2 4"
                        />
                        <text
                          x={PAD_LEFT - 6}
                          y={y + 3}
                          textAnchor="end"
                          className="fill-[var(--muted)]"
                          style={{ fontSize: "8px", fontFamily: "monospace" }}
                        >
                          {pct}%
                        </text>
                      </g>
                    );
                  });
                })()}

                {/* Stream paths with dynamic opacity */}
                {streamData.paths.map((p) => (
                  <path
                    key={p.category}
                    d={p.d}
                    fill={p.color}
                    fillOpacity={bandOpacity(p.category)}
                    stroke={p.color}
                    strokeWidth={0.5}
                    strokeOpacity={0.3}
                    style={{ transition: "fill-opacity 150ms ease" }}
                    pointerEvents="none"
                  />
                ))}

                {/* Hovered indicator line */}
                {hoveredBookIdx !== null &&
                  streamData.hoverCols[hoveredBookIdx] && (
                    <line
                      x1={streamData.hoverCols[hoveredBookIdx].x}
                      y1={PAD_TOP}
                      x2={streamData.hoverCols[hoveredBookIdx].x}
                      y2={SVG_H - PAD_BOTTOM}
                      stroke="var(--foreground)"
                      strokeWidth={1}
                      strokeDasharray="4 3"
                      pointerEvents="none"
                      opacity={0.5}
                    />
                  )}

                {/* Book year dots */}
                {streamData.hoverCols.map((col, idx) => (
                  <circle
                    key={`dot-${col.bookId}`}
                    cx={col.x}
                    cy={SVG_H - PAD_BOTTOM}
                    r={selectedBookId === col.bookId ? 4 : 2.5}
                    fill={
                      selectedBookId === col.bookId
                        ? "var(--accent)"
                        : "var(--foreground)"
                    }
                    opacity={
                      hoveredBookIdx === idx ||
                      selectedBookId === col.bookId
                        ? 1
                        : 0.4
                    }
                    pointerEvents="none"
                  />
                ))}
              </svg>

              {/* Tooltip */}
              {hoveredBookIdx !== null &&
                streamData.hoverCols[hoveredBookIdx] && (() => {
                  const col = streamData.hoverCols[hoveredBookIdx];
                  const book = books.find((b) => b.id === col.bookId);
                  if (!book) return null;
                  const pct = ((col.x - PAD_LEFT) / (SVG_W - PAD_LEFT - PAD_RIGHT)) * 100;
                  const rec = bookClusters.get(book.id) || {};
                  const total = Object.values(rec).reduce((s, v) => s + v, 0);

                  if (hoveredCategory) {
                    // Band-specific tooltip
                    const catCount = rec[hoveredCategory] || 0;
                    const topEntities = bookCatTopEntities.get(book.id)?.get(hoveredCategory) || [];
                    const rawTotal = streamData.rawTotals[hoveredBookIdx + 1];
                    const percentage = rawTotal > 0
                      ? ((catCount / total) * 100).toFixed(1)
                      : "0";

                    return (
                      <div
                        className="absolute pointer-events-none z-10 bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 shadow-lg text-xs"
                        style={{
                          left: `${Math.min(Math.max(pct, 10), 90)}%`,
                          top: 8,
                          transform: "translateX(-50%)",
                        }}
                      >
                        <div className="font-semibold text-sm mb-0.5">
                          {BOOK_SHORT_NAMES[book.id] || book.title}
                          <span className="font-normal text-[var(--muted)] ml-1.5">
                            {book.year}
                          </span>
                        </div>
                        <div className="flex items-center gap-1.5 mt-1">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: CAT_HEX[hoveredCategory] }}
                          />
                          <span className="font-medium">{hoveredCategory}</span>
                          <span className="text-[var(--muted)]">
                            &mdash; {catCount} clusters
                            {viewMode === "relative" && (
                              <span className="ml-1">({percentage}%)</span>
                            )}
                          </span>
                        </div>
                        {topEntities.length > 0 && (
                          <div className="mt-1 text-[var(--muted)]">
                            {topEntities.map((name, i) => (
                              <span key={name}>
                                {i > 0 && ", "}
                                <span className="text-[var(--foreground)]">{name}</span>
                              </span>
                            ))}
                          </div>
                        )}
                      </div>
                    );
                  }

                  // General book tooltip (no specific band hovered)
                  const topCats = Object.entries(rec)
                    .sort(([, a], [, b]) => b - a)
                    .slice(0, 3);
                  const topCatMax = topCats.length > 0 ? topCats[0][1] : 1;

                  return (
                    <div
                      className="absolute pointer-events-none z-10 bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 shadow-lg text-xs"
                      style={{
                        left: `${Math.min(Math.max(pct, 10), 90)}%`,
                        top: 8,
                        transform: "translateX(-50%)",
                      }}
                    >
                      <div className="font-semibold text-sm mb-0.5">
                        {BOOK_SHORT_NAMES[book.id] || book.title}
                      </div>
                      <div className="text-[var(--muted)]">
                        {book.author}, {book.year} &middot; {book.language}
                      </div>
                      <div className="text-[var(--muted)] mt-1">
                        {total} clusters
                      </div>
                      {topCats.length > 0 && (
                        <div className="mt-1.5 space-y-0.5">
                          {topCats.map(([cat, count]) => (
                            <div key={cat} className="flex items-center gap-1.5">
                              <span
                                className="w-1.5 h-1.5 rounded-full shrink-0"
                                style={{ backgroundColor: CAT_HEX[cat] }}
                              />
                              <span className="text-[var(--muted)] w-16 truncate text-[10px] uppercase">{cat}</span>
                              <div className="w-16 h-1.5 bg-[var(--border)]/50 rounded-full overflow-hidden">
                                <div
                                  className="h-full rounded-full"
                                  style={{
                                    width: `${(count / topCatMax) * 100}%`,
                                    backgroundColor: CAT_HEX[cat] || "#888",
                                  }}
                                />
                              </div>
                              <span className="font-mono tabular-nums text-[var(--muted)]">{count}</span>
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })()}
            </div>
          )}

          {/* Selected book detail panel */}
          {selectedBook && (
            <div className="mt-6 p-5 rounded-lg border border-[var(--border)] bg-[var(--card)] animate-expand">
              <div className="flex items-start justify-between mb-4">
                <div>
                  <Link
                    href={`/books/${selectedBook.id}`}
                    className="text-lg font-semibold hover:text-[var(--accent)] transition-colors"
                  >
                    {selectedBook.title}
                  </Link>
                  <p className="text-sm text-[var(--muted)]">
                    {selectedBook.author}, {selectedBook.year} &middot;{" "}
                    {selectedBook.language}
                  </p>
                </div>
                <button
                  onClick={() => setSelectedBookId(null)}
                  className="p-1 rounded hover:bg-[var(--border)] transition-colors text-[var(--muted)]"
                >
                  <svg
                    className="w-4 h-4"
                    fill="none"
                    stroke="currentColor"
                    viewBox="0 0 24 24"
                  >
                    <path
                      strokeLinecap="round"
                      strokeLinejoin="round"
                      strokeWidth={2}
                      d="M6 18L18 6M6 6l12 12"
                    />
                  </svg>
                </button>
              </div>

              {/* Category bars */}
              <div className="space-y-1.5 mb-5">
                {selectedBookCats.map(([cat, count]) => (
                  <div key={cat} className="flex items-center gap-2">
                    <span className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] w-24 text-right shrink-0">
                      {cat}
                    </span>
                    <div className="flex-1 h-3 bg-[var(--border)]/50 rounded-full overflow-hidden">
                      <div
                        className="h-full rounded-full transition-all"
                        style={{
                          width: `${(count / maxCatCount) * 100}%`,
                          backgroundColor: CAT_HEX[cat] || "#888",
                          opacity: 0.8,
                        }}
                      />
                    </div>
                    <span className="text-xs font-mono tabular-nums text-[var(--muted)] w-8 text-right">
                      {count}
                    </span>
                  </div>
                ))}
              </div>

              {/* Top entities */}
              <h4 className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium mb-2">
                Top entities
              </h4>
              <div className="flex flex-wrap gap-1.5">
                {selectedBookTopEntities.map((cluster) => (
                  <Link
                    key={cluster.id}
                    href={`/concordance/${slugify(cluster.canonical_name)}`}
                    className="inline-flex items-center gap-1.5 px-2 py-1 rounded-full border border-[var(--border)] text-xs hover:bg-[var(--border)]/50 transition-colors"
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        backgroundColor: CAT_HEX[cluster.category] || "#888",
                      }}
                    />
                    {cluster.canonical_name}
                    <span className="font-mono text-[var(--muted)] tabular-nums">
                      {cluster.book_count}
                    </span>
                  </Link>
                ))}
              </div>
            </div>
          )}
        </div>
      )}

      {/* ═══════════════ TAB 2: EXPLORE ═══════════════ */}
      {activeTab === "explore" && (
        <div className="animate-fade-up delay-2">
          {/* Search + autocomplete */}
          <div className="relative mb-4" ref={searchRef}>
            <div className="relative">
              <svg
                className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)]"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
                />
              </svg>
              <input
                type="text"
                value={searchQuery}
                onChange={(e) => {
                  setSearchQuery(e.target.value);
                  setShowDropdown(true);
                }}
                onFocus={() => searchQuery.trim() && setShowDropdown(true)}
                placeholder="Search for an entity to trace across books..."
                className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm placeholder:text-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent transition-all"
              />
            </div>

            {/* Dropdown */}
            {showDropdown && searchResults.length > 0 && (
              <div className="absolute z-20 top-full mt-1 w-full bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-lg overflow-hidden">
                {searchResults.map((cluster) => {
                  const already = traces.some((t) => t.id === cluster.id);
                  return (
                    <button
                      key={cluster.id}
                      disabled={already || traces.length >= 5}
                      onClick={() => addTrace(cluster)}
                      className={`w-full px-3 py-2 text-left text-sm flex items-center gap-2 transition-colors ${
                        already
                          ? "opacity-40 cursor-not-allowed"
                          : "hover:bg-[var(--border)]/50"
                      }`}
                    >
                      <span
                        className="w-2 h-2 rounded-full shrink-0"
                        style={{
                          backgroundColor:
                            CAT_HEX[cluster.category] || "#888",
                        }}
                      />
                      <span className="font-medium">
                        {cluster.canonical_name}
                      </span>
                      <span className="text-[var(--muted)] text-xs">
                        {cluster.category}
                      </span>
                      <span className="ml-auto text-xs font-mono text-[var(--muted)] tabular-nums">
                        {cluster.book_count} books
                      </span>
                    </button>
                  );
                })}
              </div>
            )}
          </div>

          {/* Active trace chips (removable, shown inline below search) */}
          {traces.length > 0 && (
            <div className="flex flex-wrap items-center gap-2 mb-4">
              {traces.map((t, idx) => (
                <span
                  key={t.id}
                  className="inline-flex items-center gap-1.5 pl-2 pr-1 py-1 rounded-full text-xs font-medium border border-[var(--border)] bg-[var(--card)]"
                >
                  <span
                    className="w-2.5 h-2.5 rounded-full"
                    style={{ backgroundColor: TRACE_COLORS[idx % TRACE_COLORS.length] }}
                  />
                  {t.canonical_name}
                  <button
                    onClick={() => removeTrace(t.id)}
                    className="ml-0.5 p-0.5 rounded-full hover:bg-[var(--border)] transition-colors text-[var(--muted)]"
                  >
                    <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </span>
              ))}
              {traces.length < 5 && (
                <span className="text-[10px] text-[var(--muted)]">
                  {5 - traces.length} more available
                </span>
              )}
            </div>
          )}

          {/* Popular chips (always visible) */}
          <div className="mb-6">
            <h3 className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium mb-2">
              {traces.length > 0 ? "Suggestions" : "Popular entities"}
            </h3>
            <div className="flex flex-wrap gap-1.5">
              {popularClusters
                .filter((c) => !traces.some((t) => t.id === c.id))
                .slice(0, traces.length > 0 ? 8 : 12)
                .map((cluster) => (
                  <button
                    key={cluster.id}
                    onClick={() => addTrace(cluster)}
                    disabled={traces.length >= 5}
                    className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full border border-[var(--border)] text-xs hover:bg-[var(--border)]/50 transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
                  >
                    <span
                      className="w-1.5 h-1.5 rounded-full"
                      style={{
                        backgroundColor: CAT_HEX[cluster.category] || "#888",
                      }}
                    />
                    {cluster.canonical_name}
                    <span className="font-mono text-[var(--muted)] tabular-nums">
                      {cluster.book_count}
                    </span>
                  </button>
                ))}
            </div>
          </div>

          {/* ── Hero frequency chart (ngram-style) ── */}
          {traces.length > 0 && frequencyData && (
            <div className="mb-6 p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]" ref={freqContainerRef}>
              {/* Chart header + controls */}
              <div className="flex flex-wrap items-center justify-between gap-3 mb-3">
                <h3 className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium">
                  Mention density
                  <span className="normal-case tracking-normal ml-2 font-normal">
                    (per 1,000 mentions in each book)
                  </span>
                </h3>
                <div className="flex items-center gap-3">
                  {/* Smoothing slider */}
                  <div className="flex items-center gap-2">
                    <label className="text-[10px] text-[var(--muted)] uppercase tracking-[0.1em]">
                      Smoothing
                    </label>
                    <input
                      type="range"
                      min={0}
                      max={5}
                      step={1}
                      value={smoothing}
                      onChange={(e) => setSmoothing(Number(e.target.value))}
                      className="w-20 h-1 accent-[var(--accent)]"
                    />
                    <span className="text-[10px] font-mono text-[var(--muted)] w-3 text-right tabular-nums">
                      {smoothing}
                    </span>
                  </div>
                </div>
              </div>

              <div className="relative">
                <svg
                  viewBox={`0 0 ${SVG_W} ${FREQ_H}`}
                  className="w-full h-auto"
                  style={{ maxHeight: 340 }}
                >
                  {/* Y-axis ticks */}
                  {(() => {
                    const chartH = FREQ_H - FREQ_PAD_TOP - FREQ_PAD_BOTTOM;
                    const nTicks = 5;
                    const ticks: number[] = [];
                    for (let i = 0; i < nTicks; i++) {
                      ticks.push((frequencyData.maxDensity / (nTicks - 1)) * i);
                    }
                    return ticks.map((val) => {
                      const y = FREQ_PAD_TOP + chartH - (val / frequencyData.maxDensity) * chartH;
                      return (
                        <g key={`ytick-${val}`}>
                          <line
                            x1={FREQ_PAD_LEFT}
                            y1={y}
                            x2={SVG_W - PAD_RIGHT}
                            y2={y}
                            stroke="var(--border)"
                            strokeWidth={0.3}
                            strokeDasharray="2 4"
                          />
                          <text
                            x={FREQ_PAD_LEFT - 6}
                            y={y + 3}
                            textAnchor="end"
                            className="fill-[var(--muted)]"
                            style={{ fontSize: "9px", fontFamily: "monospace" }}
                          >
                            {val < 1 ? val.toFixed(1) : Math.round(val)}
                          </text>
                        </g>
                      );
                    });
                  })()}

                  {/* Vertical grid lines */}
                  {gridLines.map((gl) => (
                    <line
                      key={gl.year}
                      x1={gl.x}
                      y1={FREQ_PAD_TOP}
                      x2={gl.x}
                      y2={FREQ_H - FREQ_PAD_BOTTOM}
                      stroke="var(--border)"
                      strokeWidth={0.3}
                    />
                  ))}

                  {/* Book year tick marks on X-axis */}
                  {sortedBooks.map((b) => {
                    const cx = xScale(b.year, extMinYear, extMaxYear);
                    return (
                      <g key={`xtick-${b.id}`}>
                        <line
                          x1={cx}
                          y1={FREQ_H - FREQ_PAD_BOTTOM}
                          x2={cx}
                          y2={FREQ_H - FREQ_PAD_BOTTOM + 4}
                          stroke="var(--muted)"
                          strokeWidth={0.5}
                          strokeOpacity={0.5}
                        />
                        <text
                          x={cx}
                          y={FREQ_H - 8}
                          textAnchor="middle"
                          className="fill-[var(--muted)]"
                          style={{ fontSize: "9px", fontFamily: "monospace" }}
                        >
                          {b.year}
                        </text>
                      </g>
                    );
                  })}

                  {/* Absent book markers */}
                  {frequencyData.traceLines.map((line) => {
                    if (hiddenTraces.has(line.clusterId)) return null;
                    const presentBooks = new Set(line.points.map((p) => p.bookId));
                    return sortedBooks
                      .filter((b) => !presentBooks.has(b.id))
                      .map((b) => {
                        const cx = xScale(b.year, extMinYear, extMaxYear);
                        const chartH = FREQ_H - FREQ_PAD_TOP - FREQ_PAD_BOTTOM;
                        return (
                          <line
                            key={`absent-${line.clusterId}-${b.id}`}
                            x1={cx}
                            y1={FREQ_PAD_TOP + chartH - 4}
                            x2={cx}
                            y2={FREQ_PAD_TOP + chartH + 4}
                            stroke={line.color}
                            strokeWidth={1}
                            strokeOpacity={0.2}
                          />
                        );
                      });
                  })}

                  {/* Trace lines (smoothed) */}
                  {frequencyData.traceLines.map((line) => {
                    if (hiddenTraces.has(line.clusterId)) return null;
                    if (line.points.length < 2) return null;
                    const chartH = FREQ_H - FREQ_PAD_TOP - FREQ_PAD_BOTTOM;
                    const svgPoints = line.points.map((p) => ({
                      x: xScale(p.year, extMinYear, extMaxYear),
                      y: FREQ_PAD_TOP + chartH - (p.density / frequencyData.maxDensity) * chartH,
                    }));
                    const pathD = buildSmoothPath(svgPoints, smoothing);
                    return (
                      <path
                        key={`line-${line.clusterId}`}
                        d={pathD}
                        fill="none"
                        stroke={line.color}
                        strokeWidth={2.5}
                        strokeOpacity={0.85}
                        strokeLinejoin="round"
                        strokeLinecap="round"
                      />
                    );
                  })}

                  {/* Trace dots */}
                  {frequencyData.traceLines.map((line) => {
                    if (hiddenTraces.has(line.clusterId)) return null;
                    const chartH = FREQ_H - FREQ_PAD_TOP - FREQ_PAD_BOTTOM;
                    return line.points.map((p) => {
                      const cx = xScale(p.year, extMinYear, extMaxYear);
                      const cy = FREQ_PAD_TOP + chartH - (p.density / frequencyData.maxDensity) * chartH;
                      const isHovered =
                        hoveredDot?.traceId === line.clusterId &&
                        hoveredDot?.bookId === p.bookId;
                      return (
                        <g key={`freqdot-${line.clusterId}-${p.bookId}`}>
                          {isHovered && (
                            <circle
                              cx={cx}
                              cy={cy}
                              r={12}
                              fill={line.color}
                              fillOpacity={0.12}
                            />
                          )}
                          <circle
                            cx={cx}
                            cy={cy}
                            r={isHovered ? 5.5 : 4}
                            fill={line.color}
                            stroke="var(--card)"
                            strokeWidth={2}
                            className="cursor-pointer"
                            onMouseEnter={() =>
                              setHoveredDot({
                                traceId: line.clusterId,
                                bookId: p.bookId,
                              })
                            }
                            onMouseLeave={() => setHoveredDot(null)}
                          />
                        </g>
                      );
                    });
                  })}

                  {/* Inline endpoint labels */}
                  {frequencyData.traceLines.map((line) => {
                    if (hiddenTraces.has(line.clusterId)) return null;
                    if (line.points.length === 0) return null;
                    const chartH = FREQ_H - FREQ_PAD_TOP - FREQ_PAD_BOTTOM;
                    const lastPt = line.points[line.points.length - 1];
                    const cx = xScale(lastPt.year, extMinYear, extMaxYear);
                    const cy = FREQ_PAD_TOP + chartH - (lastPt.density / frequencyData.maxDensity) * chartH;
                    return (
                      <text
                        key={`label-${line.clusterId}`}
                        x={cx + 8}
                        y={cy + 3}
                        className="fill-current"
                        style={{
                          fontSize: "9px",
                          fontWeight: 600,
                          fill: line.color,
                        }}
                      >
                        {line.clusterName}
                      </text>
                    );
                  })}
                </svg>

                {/* Frequency dot tooltip */}
                {hoveredDot && (() => {
                  const line = frequencyData.traceLines.find(
                    (l) => l.clusterId === hoveredDot.traceId
                  );
                  const point = line?.points.find(
                    (p) => p.bookId === hoveredDot.bookId
                  );
                  if (!line || !point) return null;
                  const book = books.find((b) => b.id === point.bookId);
                  if (!book) return null;
                  const pct =
                    ((xScale(point.year, extMinYear, extMaxYear) - PAD_LEFT) /
                      (SVG_W - PAD_LEFT - PAD_RIGHT)) *
                    100;

                  return (
                    <div
                      className="absolute pointer-events-none z-10 bg-[var(--card)] border border-[var(--border)] rounded-lg px-3 py-2 shadow-lg text-xs"
                      style={{
                        left: `${Math.min(Math.max(pct, 10), 90)}%`,
                        top: 4,
                        transform: "translateX(-50%)",
                      }}
                    >
                      <div className="flex items-center gap-1.5">
                        <span
                          className="w-2 h-2 rounded-full"
                          style={{ backgroundColor: line.color }}
                        />
                        <span className="font-semibold text-sm">
                          {point.name}
                        </span>
                      </div>
                      <div className="text-[var(--muted)] mt-0.5">
                        {BOOK_SHORT_NAMES[book.id] || book.title}, {book.year}
                      </div>
                      <div className="mt-1">
                        <span className="font-mono tabular-nums">{point.count}</span>{" "}
                        <span className="text-[var(--muted)]">mentions</span>
                        <span className="text-[var(--muted)]"> &middot; </span>
                        <span className="font-mono tabular-nums">{point.density.toFixed(1)}</span>
                        <span className="text-[var(--muted)]"> per 1k</span>
                      </div>
                    </div>
                  );
                })()}
              </div>

              {/* Interactive legend (clickable to toggle visibility) */}
              <div className="flex flex-wrap items-center gap-x-4 gap-y-1.5 mt-3 pt-3 border-t border-[var(--border)]/50">
                {frequencyData.traceLines.map((line) => {
                  const isHidden = hiddenTraces.has(line.clusterId);
                  return (
                    <button
                      key={line.clusterId}
                      onClick={() => toggleTraceVisibility(line.clusterId)}
                      className={`flex items-center gap-1.5 text-xs transition-opacity ${
                        isHidden ? "opacity-30" : "opacity-100"
                      } hover:opacity-80`}
                    >
                      <span
                        className="w-3 h-0.5 rounded-full"
                        style={{
                          backgroundColor: line.color,
                          opacity: isHidden ? 0.3 : 1,
                        }}
                      />
                      <span className={isHidden ? "line-through text-[var(--muted)]" : ""}>
                        {line.clusterName}
                      </span>
                    </button>
                  );
                })}
              </div>
            </div>
          )}

          {/* Compact trace detail rows (expandable) */}
          {traces.length > 0 && (
            <div className="space-y-1.5 mb-8">
              {traces.map((cluster, traceIdx) => {
                const traceColor = TRACE_COLORS[traceIdx % TRACE_COLORS.length];
                const totalMentions = cluster.members.reduce(
                  (s, m) => s + m.count,
                  0
                );
                const catColor = CATEGORY_COLORS[cluster.category];
                const isExpanded = expandedTrace === cluster.id;

                // Build appearances for expanded view
                const membersByBook = new Map<string, ClusterMember>();
                for (const m of cluster.members) {
                  const existing = membersByBook.get(m.book_id);
                  if (!existing || m.count > existing.count) {
                    membersByBook.set(m.book_id, m);
                  }
                }
                const appearances = [...membersByBook.entries()]
                  .map(([bid, member]) => {
                    const book = books.find((b) => b.id === bid);
                    if (!book) return null;
                    return {
                      bookId: bid,
                      year: book.year,
                      surname: BOOK_SHORT_NAMES[bid] || book.author.split(" ").pop() || "",
                      language: book.language,
                      memberName: member.name,
                      count: member.count,
                      variants: member.variants,
                    };
                  })
                  .filter((a): a is NonNullable<typeof a> => a !== null)
                  .sort((a, b) => a.year - b.year);

                return (
                  <div
                    key={cluster.id}
                    className="rounded-lg border border-[var(--border)] bg-[var(--card)] overflow-hidden"
                  >
                    {/* Compact row */}
                    <button
                      onClick={() =>
                        setExpandedTrace(isExpanded ? null : cluster.id)
                      }
                      className="w-full px-4 py-2.5 flex items-center gap-3 text-left hover:bg-[var(--border)]/20 transition-colors"
                    >
                      <span
                        className="w-3 h-3 rounded-full shrink-0"
                        style={{ backgroundColor: traceColor }}
                      />
                      <Link
                        href={`/concordance/${slugify(cluster.canonical_name)}`}
                        onClick={(e) => e.stopPropagation()}
                        className="font-semibold text-sm hover:text-[var(--accent)] transition-colors"
                      >
                        {cluster.canonical_name}
                      </Link>
                      <span
                        className={`px-1.5 py-0.5 rounded text-[10px] font-medium border ${
                          catColor?.badge || "bg-[var(--border)]"
                        }`}
                      >
                        {cluster.category}
                      </span>
                      <span className="text-xs text-[var(--muted)] font-mono tabular-nums">
                        {cluster.book_count} books
                      </span>
                      <span className="text-xs text-[var(--muted)] font-mono tabular-nums">
                        {totalMentions}&times;
                      </span>
                      <svg
                        className={`w-3.5 h-3.5 ml-auto text-[var(--muted)] transition-transform ${
                          isExpanded ? "rotate-180" : ""
                        }`}
                        fill="none"
                        stroke="currentColor"
                        viewBox="0 0 24 24"
                      >
                        <path
                          strokeLinecap="round"
                          strokeLinejoin="round"
                          strokeWidth={2}
                          d="M19 9l-7 7-7-7"
                        />
                      </svg>
                    </button>

                    {/* Expanded detail panel */}
                    {isExpanded && (
                      <div className="px-4 pb-4 pt-1 border-t border-[var(--border)]/50">
                        {/* Book-by-book breakdown */}
                        <div className="space-y-1.5">
                          {appearances.map((a) => (
                            <div
                              key={a.bookId}
                              className="flex items-center gap-3 text-xs"
                            >
                              <span className="font-mono tabular-nums text-[var(--muted)] w-10 text-right shrink-0">
                                {a.year}
                              </span>
                              <span className="font-medium w-20 shrink-0">
                                {a.surname}
                              </span>
                              <span className="text-[var(--foreground)]">
                                {a.memberName}
                              </span>
                              <span className="font-mono tabular-nums text-[var(--muted)]">
                                {a.count}&times;
                              </span>
                              {a.variants && a.variants.length > 0 && (
                                <span className="text-[var(--muted)] italic truncate">
                                  {a.variants.slice(0, 3).join(", ")}
                                </span>
                              )}
                              <span className="text-[var(--muted)] ml-auto text-[10px]">
                                {a.language}
                              </span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}

          {/* Comparison table */}
          {traces.length >= 2 && (
            <div className="overflow-x-auto mb-8">
              <h3 className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium mb-3">
                Comparison
              </h3>
              <table className="w-full text-sm border-collapse">
                <thead>
                  <tr className="border-b border-[var(--border)]">
                    <th className="py-2 pr-4 text-left text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] font-medium" />
                    {traces.map((t, idx) => (
                      <th
                        key={t.id}
                        className="py-2 px-3 text-left font-semibold"
                      >
                        <div className="flex items-center gap-1.5">
                          <span
                            className="w-2 h-2 rounded-full"
                            style={{
                              backgroundColor:
                                TRACE_COLORS[idx % TRACE_COLORS.length],
                            }}
                          />
                          {t.canonical_name}
                        </div>
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  <tr className="border-b border-[var(--border)]/50">
                    <td className="py-1.5 pr-4 text-[var(--muted)]">
                      Books
                    </td>
                    {traces.map((t) => (
                      <td
                        key={t.id}
                        className="py-1.5 px-3 font-mono tabular-nums"
                      >
                        {t.book_count}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-[var(--border)]/50">
                    <td className="py-1.5 pr-4 text-[var(--muted)]">
                      Mentions
                    </td>
                    {traces.map((t) => (
                      <td
                        key={t.id}
                        className="py-1.5 px-3 font-mono tabular-nums"
                      >
                        {t.total_mentions}
                      </td>
                    ))}
                  </tr>
                  <tr className="border-b border-[var(--border)]/50">
                    <td className="py-1.5 pr-4 text-[var(--muted)]">
                      First year
                    </td>
                    {traces.map((t) => {
                      const years = t.members
                        .map((m) => books.find((b) => b.id === m.book_id)?.year)
                        .filter((y): y is number => y !== undefined);
                      return (
                        <td
                          key={t.id}
                          className="py-1.5 px-3 font-mono tabular-nums"
                        >
                          {years.length > 0 ? Math.min(...years) : "\u2014"}
                        </td>
                      );
                    })}
                  </tr>
                  <tr className="border-b border-[var(--border)]/50">
                    <td className="py-1.5 pr-4 text-[var(--muted)]">
                      Last year
                    </td>
                    {traces.map((t) => {
                      const years = t.members
                        .map((m) => books.find((b) => b.id === m.book_id)?.year)
                        .filter((y): y is number => y !== undefined);
                      return (
                        <td
                          key={t.id}
                          className="py-1.5 px-3 font-mono tabular-nums"
                        >
                          {years.length > 0 ? Math.max(...years) : "\u2014"}
                        </td>
                      );
                    })}
                  </tr>
                  <tr className="border-b border-[var(--border)]/50">
                    <td className="py-1.5 pr-4 text-[var(--muted)]">
                      Languages
                    </td>
                    {traces.map((t) => {
                      const langs = [
                        ...new Set(
                          t.members
                            .map(
                              (m) =>
                                books.find((b) => b.id === m.book_id)
                                  ?.language
                            )
                            .filter(Boolean)
                        ),
                      ];
                      return (
                        <td
                          key={t.id}
                          className="py-1.5 px-3 text-[var(--muted)]"
                        >
                          {langs.join(", ")}
                        </td>
                      );
                    })}
                  </tr>
                  {traces.length === 2 && (() => {
                    const booksA = new Set(
                      traces[0].members.map((m) => m.book_id)
                    );
                    const shared = traces[1].members.filter((m) =>
                      booksA.has(m.book_id)
                    );
                    const sharedBooks = new Set(
                      shared.map((m) => m.book_id)
                    );
                    return (
                      <tr>
                        <td className="py-1.5 pr-4 text-[var(--muted)]">
                          Co-occurrence
                        </td>
                        <td
                          colSpan={2}
                          className="py-1.5 px-3 font-mono tabular-nums"
                        >
                          {sharedBooks.size} shared{" "}
                          {sharedBooks.size === 1 ? "book" : "books"}
                        </td>
                      </tr>
                    );
                  })()}
                </tbody>
              </table>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
