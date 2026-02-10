"use client";

import { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { CAT_DOT } from "@/lib/colors";

/* ── Types ── */

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
  wikidata_id?: string;
  wikipedia_url?: string;
  linnaean?: string;
}

interface CrossReference {
  target_cluster_id: number | null;
  target_name: string;
  link_type: string;
  is_reverse?: boolean;
}

interface Cluster {
  id: number;
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

/* ── Constants ── */

const CATEGORY_COLORS: Record<string, { bar: string; dot: string }> =
  Object.fromEntries(
    Object.entries(CAT_DOT).map(([k, v]) => [k, { bar: v, dot: v }])
  );

const BOOK_LANG_FLAGS: Record<string, string> = {
  English: "EN",
  Portuguese: "PT",
  Spanish: "ES",
  Latin: "LA",
  French: "FR",
  Italian: "IT",
};

/* ── Derived Stats ── */

interface DerivedStats {
  totalClusters: number;
  entitiesMatched: number;
  totalMentions: number;
  crossBookClusters: number;
  bookCount: number;
  languages: number;
  timespan: string;
  categoryBreakdown: { category: string; count: number; pct: number }[];
  bookStats: {
    id: string;
    title: string;
    author: string;
    year: number;
    language: string;
    clusters: number;
    mentions: number;
    coverage: number;
  }[];
  clusterDistribution: { bookCount: number; clusters: number; pct: number }[];
  enrichment: {
    category: string;
    total: number;
    wikidata: number;
    wikipedia: number;
    linnaean: number;
  }[];
  crossRefs: {
    total: number;
    clustersWithRefs: number;
    reverseRefs: number;
    byType: { type: string; count: number; pct: number }[];
  };
  network: {
    totalEdges: number;
    avgSimilarity: number;
    buckets: { label: string; count: number; pct: number }[];
  };
  languageStats: {
    language: string;
    books: string[];
    totalEntities: number;
    totalMentions: number;
    categories: { category: string; count: number; pct: number }[];
  }[];
}

function computeStats(data: ConcordanceData): DerivedStats {
  const clusters = data.clusters;
  const totalClusters = clusters.length;
  const entitiesMatched = data.stats.entities_matched;
  const totalMentions = clusters.reduce((s, c) => s + c.total_mentions, 0);

  // Languages & timespan from books
  const langs = new Set(data.books.map((b) => b.language));
  const years = data.books.map((b) => b.year);

  // Cross-book = book_count >= data.books.length (all books)
  const allBookCount = data.books.length;
  const crossBookClusters = clusters.filter((c) => c.book_count >= allBookCount).length;

  // Category breakdown
  const catEntries = Object.entries(data.stats.by_category)
    .map(([category, count]) => ({ category, count, pct: (count / totalClusters) * 100 }))
    .sort((a, b) => b.count - a.count);

  // Book stats
  const bookMap = new Map<string, { clusters: number; mentions: number }>();
  for (const c of clusters) {
    const seenBooks = new Set<string>();
    for (const m of c.members) {
      if (!seenBooks.has(m.book_id)) {
        seenBooks.add(m.book_id);
        const entry = bookMap.get(m.book_id) || { clusters: 0, mentions: 0 };
        entry.clusters++;
        entry.mentions += m.count;
        bookMap.set(m.book_id, entry);
      } else {
        const entry = bookMap.get(m.book_id)!;
        entry.mentions += m.count;
      }
    }
  }
  const bookStats = data.books.map((b) => {
    const s = bookMap.get(b.id) || { clusters: 0, mentions: 0 };
    return {
      ...b,
      clusters: s.clusters,
      mentions: s.mentions,
      coverage: (s.clusters / totalClusters) * 100,
    };
  }).sort((a, b) => b.clusters - a.clusters);

  // Cluster distribution by book count
  const distMap = new Map<number, number>();
  for (const c of clusters) {
    distMap.set(c.book_count, (distMap.get(c.book_count) || 0) + 1);
  }
  const clusterDistribution = Array.from(distMap.entries())
    .sort((a, b) => a[0] - b[0])
    .map(([bookCount, count]) => ({
      bookCount,
      clusters: count,
      pct: (count / totalClusters) * 100,
    }));

  // Enrichment coverage by category
  const enrichMap = new Map<string, { total: number; wd: number; wp: number; ln: number }>();
  for (const c of clusters) {
    const cat = c.category;
    const e = enrichMap.get(cat) || { total: 0, wd: 0, wp: 0, ln: 0 };
    e.total++;
    if (c.ground_truth?.wikidata_id) e.wd++;
    if (c.ground_truth?.wikipedia_url) e.wp++;
    if (c.ground_truth?.linnaean) e.ln++;
    enrichMap.set(cat, e);
  }
  const enrichment = Array.from(enrichMap.entries())
    .sort((a, b) => b[1].total - a[1].total)
    .map(([category, e]) => ({
      category,
      total: e.total,
      wikidata: e.wd,
      wikipedia: e.wp,
      linnaean: e.ln,
    }));

  // Cross-references
  let totalRefs = 0;
  let reverseRefs = 0;
  let clustersWithRefs = 0;
  const typeMap = new Map<string, number>();
  for (const c of clusters) {
    const refs = c.cross_references || [];
    if (refs.length > 0) clustersWithRefs++;
    for (const r of refs) {
      totalRefs++;
      if (r.is_reverse) reverseRefs++;
      typeMap.set(r.link_type, (typeMap.get(r.link_type) || 0) + 1);
    }
  }
  const crossRefs = {
    total: totalRefs,
    clustersWithRefs,
    reverseRefs,
    byType: Array.from(typeMap.entries())
      .sort((a, b) => b[1] - a[1])
      .map(([type, count]) => ({ type, count, pct: totalRefs > 0 ? (count / totalRefs) * 100 : 0 })),
  };

  // Network stats
  let totalEdges = 0;
  let simSum = 0;
  const buckets = [
    { label: "0.80–0.85", min: 0.80, max: 0.85, count: 0 },
    { label: "0.85–0.90", min: 0.85, max: 0.90, count: 0 },
    { label: "0.90–0.95", min: 0.90, max: 0.95, count: 0 },
    { label: "0.95–1.00", min: 0.95, max: 1.01, count: 0 },
  ];
  for (const c of clusters) {
    for (const e of c.edges) {
      totalEdges++;
      simSum += e.similarity;
      for (const b of buckets) {
        if (e.similarity >= b.min && e.similarity < b.max) {
          b.count++;
          break;
        }
      }
    }
  }

  // Language stats
  const bookLangMap = new Map<string, string>();
  const langBooksMap = new Map<string, string[]>();
  for (const b of data.books) {
    bookLangMap.set(b.id, b.language);
    const arr = langBooksMap.get(b.language) || [];
    arr.push(b.title);
    langBooksMap.set(b.language, arr);
  }
  const langCatMap = new Map<string, Map<string, number>>();
  const langMentionMap = new Map<string, number>();
  const langEntityMap = new Map<string, number>();
  for (const c of clusters) {
    for (const m of c.members) {
      const lang = bookLangMap.get(m.book_id);
      if (!lang) continue;
      const cats = langCatMap.get(lang) || new Map<string, number>();
      cats.set(c.category, (cats.get(c.category) || 0) + 1);
      langCatMap.set(lang, cats);
      langMentionMap.set(lang, (langMentionMap.get(lang) || 0) + m.count);
      langEntityMap.set(lang, (langEntityMap.get(lang) || 0) + 1);
    }
  }
  const languageStats = Array.from(langCatMap.entries())
    .map(([language, cats]) => {
      const totalEntities = langEntityMap.get(language) || 0;
      const catArr = Array.from(cats.entries())
        .map(([category, count]) => ({ category, count, pct: totalEntities > 0 ? (count / totalEntities) * 100 : 0 }))
        .sort((a, b) => b.count - a.count);
      return {
        language,
        books: langBooksMap.get(language) || [],
        totalEntities,
        totalMentions: langMentionMap.get(language) || 0,
        categories: catArr,
      };
    })
    .sort((a, b) => b.totalEntities - a.totalEntities);

  return {
    totalClusters,
    entitiesMatched,
    totalMentions,
    crossBookClusters,
    bookCount: data.books.length,
    languages: langs.size,
    timespan: years.length > 0 ? `${Math.min(...years)}–${Math.max(...years)}` : "—",
    categoryBreakdown: catEntries,
    bookStats,
    clusterDistribution,
    enrichment,
    crossRefs,
    languageStats,
    network: {
      totalEdges,
      avgSimilarity: totalEdges > 0 ? simSum / totalEdges : 0,
      buckets: buckets.map((b) => ({
        label: b.label,
        count: b.count,
        pct: totalEdges > 0 ? (b.count / totalEdges) * 100 : 0,
      })),
    },
  };
}

/* ── CSV / TXT generators ── */

function generateCSV(data: ConcordanceData): string {
  const header = [
    "id",
    "name",
    "category",
    "subcategory",
    "book_count",
    "total_mentions",
    "modern_name",
    "wikidata_id",
  ].join("\t");
  const rows = data.clusters.map((c) =>
    [
      c.id,
      c.canonical_name,
      c.category,
      c.subcategory,
      c.book_count,
      c.total_mentions,
      c.ground_truth?.modern_name || "",
      c.ground_truth?.wikidata_id || "",
    ].join("\t")
  );
  return [header, ...rows].join("\n");
}

function generateReport(data: ConcordanceData, stats: DerivedStats): string {
  const lines: string[] = [];
  const hr = "─".repeat(60);
  lines.push("PREMODERN CONCORDANCE — DATA REPORT");
  lines.push(`Generated: ${new Date().toISOString().slice(0, 10)}`);
  lines.push(`Data built: ${data.metadata.created}`);
  lines.push(hr);
  lines.push("");
  lines.push("OVERVIEW");
  lines.push(`  Total clusters:       ${stats.totalClusters.toLocaleString()}`);
  lines.push(`  Entities matched:     ${stats.entitiesMatched.toLocaleString()}`);
  lines.push(`  Total mentions:       ${stats.totalMentions.toLocaleString()}`);
  lines.push(`  Cross-book clusters:  ${stats.crossBookClusters.toLocaleString()} (in all ${stats.bookCount} books)`);
  lines.push(`  Books in corpus:      ${stats.bookCount}`);
  lines.push(`  Languages:            ${stats.languages}`);
  lines.push(`  Timespan:             ${stats.timespan}`);
  lines.push("");
  lines.push(hr);
  lines.push("CATEGORIES");
  for (const cat of stats.categoryBreakdown) {
    lines.push(`  ${cat.category.padEnd(16)} ${String(cat.count).padStart(5)}  (${cat.pct.toFixed(1)}%)`);
  }
  lines.push("");
  lines.push(hr);
  lines.push("BOOKS");
  for (const b of stats.bookStats) {
    lines.push(`  ${b.title}`);
    lines.push(`    Author: ${b.author} (${b.year}, ${b.language})`);
    lines.push(`    Clusters: ${b.clusters}  |  Mentions: ${b.mentions.toLocaleString()}  |  Coverage: ${b.coverage.toFixed(1)}%`);
  }
  lines.push("");
  lines.push(hr);
  lines.push("CLUSTER DISTRIBUTION (by book count)");
  for (const d of stats.clusterDistribution) {
    lines.push(`  ${d.bookCount} books: ${String(d.clusters).padStart(5)} clusters (${d.pct.toFixed(1)}%)`);
  }
  lines.push("");
  lines.push(hr);
  lines.push("NETWORK");
  lines.push(`  Total edges:        ${stats.network.totalEdges.toLocaleString()}`);
  lines.push(`  Avg similarity:     ${stats.network.avgSimilarity.toFixed(4)}`);
  lines.push("  Similarity distribution:");
  for (const b of stats.network.buckets) {
    lines.push(`    ${b.label}: ${String(b.count).padStart(5)} edges (${b.pct.toFixed(1)}%)`);
  }
  if (stats.crossRefs.total > 0) {
    lines.push("");
    lines.push(hr);
    lines.push("CROSS-REFERENCES");
    lines.push(`  Total:               ${stats.crossRefs.total}`);
    lines.push(`  Clusters with refs:  ${stats.crossRefs.clustersWithRefs}`);
    lines.push(`  Reverse refs:        ${stats.crossRefs.reverseRefs}`);
    for (const t of stats.crossRefs.byType) {
      lines.push(`    ${t.type.padEnd(24)} ${String(t.count).padStart(5)} (${t.pct.toFixed(1)}%)`);
    }
  }
  if (stats.enrichment.some((e) => e.wikidata + e.wikipedia + e.linnaean > 0)) {
    lines.push("");
    lines.push(hr);
    lines.push("ENRICHMENT COVERAGE");
    for (const e of stats.enrichment) {
      lines.push(`  ${e.category.padEnd(16)} Wikidata: ${e.wikidata}/${e.total}  Wikipedia: ${e.wikipedia}/${e.total}  Linnaean: ${e.linnaean}/${e.total}`);
    }
  }
  lines.push("");
  lines.push(hr);
  lines.push("END OF REPORT");
  return lines.join("\n");
}

function downloadBlob(content: string, filename: string, mime: string) {
  const blob = new Blob([content], { type: mime });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  document.body.removeChild(a);
  URL.revokeObjectURL(url);
}

/* ── Components ── */

function StatCard({
  label,
  value,
  delay,
}: {
  label: string;
  value: string | number;
  delay: number;
}) {
  return (
    <div
      className={`bg-[var(--card)] border border-[var(--border)] rounded-lg p-6 animate-fade-up delay-${delay}`}
    >
      <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-2">
        {label}
      </div>
      <div className="text-3xl font-mono tabular-nums text-[var(--foreground)]">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </div>
  );
}

function Bar({
  pct,
  colorClass,
  height = "h-2",
}: {
  pct: number;
  colorClass: string;
  height?: string;
}) {
  const [mounted, setMounted] = useState(false);
  useEffect(() => {
    const id = requestAnimationFrame(() => setMounted(true));
    return () => cancelAnimationFrame(id);
  }, []);
  return (
    <div className={`${height} rounded-full bg-[var(--border)] overflow-hidden flex-1`}>
      <div
        className={`${height} rounded-full ${colorClass} transition-all duration-700 ease-out`}
        style={{ width: mounted ? `${Math.max(pct, 0.5)}%` : "0%" }}
      />
    </div>
  );
}

function SectionHeader({ children }: { children: React.ReactNode }) {
  return (
    <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-4">
      {children}
    </h2>
  );
}

/* ── Page ── */

export default function DataPage() {
  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((d: ConcordanceData) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const stats = useMemo(() => (data ? computeStats(data) : null), [data]);

  // Scroll to hash anchor after data loads (browser can't find the element during loading skeleton)
  useEffect(() => {
    if (!data) return;
    const hash = window.location.hash;
    if (hash) {
      requestAnimationFrame(() => {
        const el = document.querySelector(hash);
        if (el) el.scrollIntoView({ behavior: "smooth" });
      });
    }
  }, [data]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="space-y-4">
          <div className="h-8 w-48 bg-[var(--border)] rounded animate-pulse" />
          <div className="h-4 w-96 bg-[var(--border)] rounded animate-pulse" />
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mt-8">
            {Array.from({ length: 8 }).map((_, i) => (
              <div
                key={i}
                className="h-24 bg-[var(--border)] rounded-lg animate-pulse"
              />
            ))}
          </div>
        </div>
      </div>
    );
  }

  if (!data || !stats) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <p className="text-[var(--muted)]">Failed to load concordance data.</p>
      </div>
    );
  }

  const maxCat = Math.max(...stats.categoryBreakdown.map((c) => c.count));
  const maxBookCluster = Math.max(...stats.bookStats.map((b) => b.clusters));
  const maxDist = Math.max(...stats.clusterDistribution.map((d) => d.clusters));
  const maxBucket = Math.max(...stats.network.buckets.map((b) => b.count));

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* ── Header ── */}
      <div className="mb-12 animate-fade-up delay-0">
        <h1 className="text-3xl font-semibold tracking-tight mb-2">Data</h1>
        <p className="text-[var(--muted)] max-w-xl">
          Quantitative overview of the concordance corpus.
        </p>
        <p className="text-xs text-[var(--muted)] mt-2 font-mono">
          Last built: {data.metadata.created}
        </p>
      </div>

      {/* ── Overview Cards ── */}
      <section className="mb-16 animate-fade-up delay-1">
        <SectionHeader>Overview</SectionHeader>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <StatCard label="Total Clusters" value={stats.totalClusters} delay={0} />
          <StatCard label="Entities Matched" value={stats.entitiesMatched} delay={1} />
          <StatCard label="Total Mentions" value={stats.totalMentions} delay={2} />
          <StatCard
            label={`Cross-Book Clusters`}
            value={stats.crossBookClusters}
            delay={3}
          />
          <StatCard label="Books in Corpus" value={stats.bookCount} delay={4} />
          <StatCard label="Languages" value={stats.languages} delay={5} />
          <StatCard label="Timespan" value={stats.timespan} delay={6} />
          <StatCard label="Network Edges" value={stats.network.totalEdges} delay={7} />
        </div>
      </section>

      {/* ── Category Breakdown ── */}
      <section className="mb-16 animate-fade-up delay-2">
        <SectionHeader>Categories</SectionHeader>
        <div className="space-y-3">
          {stats.categoryBreakdown.map((cat) => {
            const colors = CATEGORY_COLORS[cat.category] || CATEGORY_COLORS.OBJECT;
            return (
              <div key={cat.category} className="flex items-center gap-3">
                <div className="w-28 flex items-center gap-2 shrink-0">
                  <span className={`w-2.5 h-2.5 rounded-full ${colors.dot}`} />
                  <span className="text-sm truncate">{cat.category}</span>
                </div>
                <div className="flex-1 h-3 rounded-full bg-[var(--border)] overflow-hidden">
                  <div
                    className={`h-3 rounded-full ${colors.bar} opacity-80 transition-all duration-700 ease-out`}
                    style={{ width: `${(cat.count / maxCat) * 100}%` }}
                  />
                </div>
                <span className="text-sm font-mono tabular-nums w-12 text-right">
                  {cat.count}
                </span>
                <span className="text-xs text-[var(--muted)] font-mono tabular-nums w-14 text-right">
                  {cat.pct.toFixed(1)}%
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ── Books ── */}
      <section className="mb-16 animate-fade-up delay-3">
        <SectionHeader>Books</SectionHeader>
        <div className="overflow-x-auto -mx-4 px-4">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)]">
                <th className="text-left py-3 pr-4 font-medium text-[var(--muted)]">
                  Title
                </th>
                <th className="text-left py-3 pr-4 font-medium text-[var(--muted)] hidden sm:table-cell">
                  Author
                </th>
                <th className="text-center py-3 px-2 font-medium text-[var(--muted)]">
                  Year
                </th>
                <th className="text-center py-3 px-2 font-medium text-[var(--muted)]">
                  Lang
                </th>
                <th className="text-right py-3 px-2 font-medium text-[var(--muted)]">
                  Clusters
                </th>
                <th className="text-right py-3 px-2 font-medium text-[var(--muted)] hidden md:table-cell">
                  Mentions
                </th>
                <th className="text-right py-3 pl-2 font-medium text-[var(--muted)]">
                  Coverage
                </th>
              </tr>
            </thead>
            <tbody>
              {stats.bookStats.map((b, i) => (
                <tr
                  key={b.id}
                  className={`border-b border-[var(--border)]/50 ${i % 2 === 1 ? "bg-[var(--card)]" : ""}`}
                >
                  <td className="py-3 pr-4">
                    <Link
                      href={`/books/${b.id}`}
                      className="hover:text-[var(--accent)] transition-colors"
                    >
                      {b.title}
                    </Link>
                  </td>
                  <td className="py-3 pr-4 text-[var(--muted)] hidden sm:table-cell">
                    {b.author}
                  </td>
                  <td className="py-3 px-2 text-center font-mono tabular-nums">
                    {b.year}
                  </td>
                  <td className="py-3 px-2 text-center text-xs text-[var(--muted)]">
                    {BOOK_LANG_FLAGS[b.language] || b.language}
                  </td>
                  <td className="py-3 px-2 text-right font-mono tabular-nums">
                    {b.clusters.toLocaleString()}
                  </td>
                  <td className="py-3 px-2 text-right font-mono tabular-nums hidden md:table-cell">
                    {b.mentions.toLocaleString()}
                  </td>
                  <td className="py-3 pl-2 text-right">
                    <div className="flex items-center justify-end gap-2">
                      <div className="w-16 h-1.5 rounded-full bg-[var(--border)] overflow-hidden hidden sm:block">
                        <div
                          className="h-1.5 rounded-full bg-[var(--accent)] transition-all duration-700"
                          style={{ width: `${(b.clusters / maxBookCluster) * 100}%` }}
                        />
                      </div>
                      <span className="font-mono tabular-nums text-xs">
                        {b.coverage.toFixed(1)}%
                      </span>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      {/* ── Cluster Distribution ── */}
      <section className="mb-16 animate-fade-up delay-4">
        <SectionHeader>Cluster Distribution by Book Count</SectionHeader>
        <div className="space-y-2.5">
          {stats.clusterDistribution.map((d) => (
            <div key={d.bookCount} className="flex items-center gap-3">
              <span className="text-sm font-mono tabular-nums w-20 shrink-0">
                {d.bookCount} {d.bookCount === 1 ? "book" : "books"}
              </span>
              <Bar
                pct={(d.clusters / maxDist) * 100}
                colorClass="bg-[var(--accent)]"
                height="h-2.5"
              />
              <span className="text-sm font-mono tabular-nums w-14 text-right">
                {d.clusters.toLocaleString()}
              </span>
              <span className="text-xs text-[var(--muted)] font-mono tabular-nums w-14 text-right">
                {d.pct.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Enrichment Coverage (only if data has enrichment) ── */}
      {stats.enrichment.some((e) => e.wikidata + e.wikipedia + e.linnaean > 0) && (
        <section className="mb-16 animate-fade-up delay-5">
          <SectionHeader>Enrichment Coverage</SectionHeader>
          <div className="overflow-x-auto -mx-4 px-4">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)]">
                  <th className="text-left py-3 pr-4 font-medium text-[var(--muted)]">
                    Category
                  </th>
                  <th className="text-right py-3 px-4 font-medium text-[var(--muted)]">
                    Wikidata
                  </th>
                  <th className="text-right py-3 px-4 font-medium text-[var(--muted)]">
                    Wikipedia
                  </th>
                  <th className="text-right py-3 pl-4 font-medium text-[var(--muted)]">
                    Linnaean
                  </th>
                </tr>
              </thead>
              <tbody>
                {stats.enrichment.map((e, i) => (
                  <tr
                    key={e.category}
                    className={`border-b border-[var(--border)]/50 ${i % 2 === 1 ? "bg-[var(--card)]" : ""}`}
                  >
                    <td className="py-2.5 pr-4 flex items-center gap-2">
                      <span
                        className={`w-2 h-2 rounded-full ${
                          CATEGORY_COLORS[e.category]?.dot || "bg-slate-500"
                        }`}
                      />
                      {e.category}
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums">
                      {e.wikidata}
                      <span className="text-[var(--muted)] text-xs ml-1">
                        / {e.total}
                      </span>
                    </td>
                    <td className="py-2.5 px-4 text-right font-mono tabular-nums">
                      {e.wikipedia}
                      <span className="text-[var(--muted)] text-xs ml-1">
                        / {e.total}
                      </span>
                    </td>
                    <td className="py-2.5 pl-4 text-right font-mono tabular-nums">
                      {e.linnaean}
                      <span className="text-[var(--muted)] text-xs ml-1">
                        / {e.total}
                      </span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}

      {/* ── Languages ── */}
      <section id="languages" className="mb-16 animate-fade-up delay-5 scroll-mt-24">
        <SectionHeader>Languages</SectionHeader>
        <p className="text-sm text-[var(--muted)] mb-6 max-w-2xl">
          How entity categories distribute across the five languages in the corpus reveals
          different epistemic priorities: Portuguese texts emphasize materia medica (plants, substances,
          diseases), Humboldt&rsquo;s French foregrounds geography, and the Italian <em>Ricettario</em> focuses
          on pharmacological substances and preparations.
        </p>

        {/* Stacked bar comparison */}
        <div className="space-y-5 mb-10">
          {stats.languageStats.map((lang) => {
            const allCats = ["PLANT", "SUBSTANCE", "PLACE", "CONCEPT", "DISEASE", "PERSON", "ANIMAL", "OBJECT", "ANATOMY", "ORGANIZATION"];
            return (
              <div key={lang.language}>
                <div className="flex items-baseline justify-between mb-1.5">
                  <div className="flex items-baseline gap-2">
                    <span className="text-sm font-medium">{lang.language}</span>
                    <span className="text-xs text-[var(--muted)]">
                      {lang.books.length} {lang.books.length === 1 ? "book" : "books"}
                    </span>
                  </div>
                  <span className="text-xs text-[var(--muted)] font-mono tabular-nums">
                    {lang.totalEntities.toLocaleString()} entities
                  </span>
                </div>
                {/* Stacked bar */}
                <div className="h-6 rounded flex overflow-hidden">
                  {allCats.map((cat) => {
                    const entry = lang.categories.find((c) => c.category === cat);
                    if (!entry || entry.pct < 1) return null;
                    const colors = CATEGORY_COLORS[cat] || CATEGORY_COLORS.OBJECT;
                    return (
                      <div
                        key={cat}
                        className={`${colors.bar} opacity-80 relative group`}
                        style={{ width: `${entry.pct}%` }}
                        title={`${cat}: ${entry.count} (${entry.pct.toFixed(1)}%)`}
                      >
                        {entry.pct >= 8 && (
                          <span className="absolute inset-0 flex items-center justify-center text-[10px] text-black font-bold">
                            {cat.slice(0, 4)}
                          </span>
                        )}
                      </div>
                    );
                  })}
                </div>
              </div>
            );
          })}
        </div>

        {/* Detailed per-language breakdowns */}
        <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
          {stats.languageStats.map((lang) => (
            <div key={lang.language} className="border border-[var(--border)] rounded-lg p-5 bg-[var(--card)]">
              <div className="flex items-baseline justify-between mb-1">
                <h3 className="font-semibold text-sm">{lang.language}</h3>
                <span className="text-xs text-[var(--muted)] font-mono tabular-nums">
                  {lang.totalMentions.toLocaleString()} mentions
                </span>
              </div>
              <p className="text-[10px] text-[var(--muted)] mb-3">
                {lang.books.join(" / ")}
              </p>
              <div className="space-y-1.5">
                {lang.categories.slice(0, 8).map((cat) => {
                  const colors = CATEGORY_COLORS[cat.category] || CATEGORY_COLORS.OBJECT;
                  const maxPct = lang.categories[0]?.pct || 1;
                  return (
                    <div key={cat.category} className="flex items-center gap-2">
                      <span className={`w-2 h-2 rounded-full shrink-0 ${colors.dot}`} />
                      <span className="text-xs w-20 truncate shrink-0">{cat.category}</span>
                      <div className="flex-1 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
                        <div
                          className={`h-1.5 rounded-full ${colors.bar} opacity-70`}
                          style={{ width: `${(cat.pct / maxPct) * 100}%` }}
                        />
                      </div>
                      <span className="text-[10px] font-mono tabular-nums text-[var(--muted)] w-10 text-right">
                        {cat.pct.toFixed(1)}%
                      </span>
                    </div>
                  );
                })}
              </div>
            </div>
          ))}
        </div>
      </section>

      {/* ── Cross-References (only if data has them) ── */}
      {stats.crossRefs.total > 0 && (
        <section className="mb-16 animate-fade-up delay-5">
          <SectionHeader>Cross-References</SectionHeader>
          <div className="grid grid-cols-3 gap-4 mb-6">
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">
                Total Refs
              </div>
              <div className="text-2xl font-mono tabular-nums">
                {stats.crossRefs.total.toLocaleString()}
              </div>
            </div>
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">
                Clusters w/ Refs
              </div>
              <div className="text-2xl font-mono tabular-nums">
                {stats.crossRefs.clustersWithRefs}
              </div>
            </div>
            <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
              <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">
                Reverse Refs
              </div>
              <div className="text-2xl font-mono tabular-nums">
                {stats.crossRefs.reverseRefs}
              </div>
            </div>
          </div>
          {stats.crossRefs.byType.length > 0 && (
            <div className="space-y-2.5">
              {stats.crossRefs.byType.map((t) => (
                <div key={t.type} className="flex items-center gap-3">
                  <span className="text-sm w-48 truncate shrink-0">
                    {t.type.replace(/_/g, " ")}
                  </span>
                  <Bar pct={t.pct} colorClass="bg-[var(--accent)]" />
                  <span className="text-sm font-mono tabular-nums w-12 text-right">
                    {t.count}
                  </span>
                  <span className="text-xs text-[var(--muted)] font-mono tabular-nums w-14 text-right">
                    {t.pct.toFixed(1)}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </section>
      )}

      {/* ── Network Stats ── */}
      <section className="mb-16 animate-fade-up delay-5">
        <SectionHeader>Network</SectionHeader>
        <div className="grid grid-cols-2 gap-4 mb-6">
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">
              Total Edges
            </div>
            <div className="text-2xl font-mono tabular-nums">
              {stats.network.totalEdges.toLocaleString()}
            </div>
          </div>
          <div className="bg-[var(--card)] border border-[var(--border)] rounded-lg p-4">
            <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-1">
              Avg Similarity
            </div>
            <div className="text-2xl font-mono tabular-nums">
              {stats.network.avgSimilarity.toFixed(4)}
            </div>
          </div>
        </div>
        <div className="space-y-2.5">
          {stats.network.buckets.map((b) => (
            <div key={b.label} className="flex items-center gap-3">
              <span className="text-sm font-mono tabular-nums w-24 shrink-0">
                {b.label}
              </span>
              <Bar
                pct={maxBucket > 0 ? (b.count / maxBucket) * 100 : 0}
                colorClass="bg-[var(--accent)]"
                height="h-2.5"
              />
              <span className="text-sm font-mono tabular-nums w-14 text-right">
                {b.count.toLocaleString()}
              </span>
              <span className="text-xs text-[var(--muted)] font-mono tabular-nums w-14 text-right">
                {b.pct.toFixed(1)}%
              </span>
            </div>
          ))}
        </div>
      </section>

      {/* ── Downloads ── */}
      <section className="mb-16 animate-fade-up delay-6">
        <SectionHeader>Downloads</SectionHeader>
        <div className="flex flex-wrap gap-3">
          <button
            onClick={() =>
              downloadBlob(generateCSV(data), "concordance_clusters.tsv", "text/tab-separated-values")
            }
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--card)] border border-[var(--border)] rounded-lg text-sm hover:bg-[var(--border)] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M12 10v6m0 0l-3-3m3 3l3-3m2 8H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Download CSV
          </button>
          <button
            onClick={() =>
              downloadBlob(generateReport(data, stats), "concordance_report.txt", "text/plain")
            }
            className="inline-flex items-center gap-2 px-5 py-2.5 bg-[var(--card)] border border-[var(--border)] rounded-lg text-sm hover:bg-[var(--border)] transition-colors"
          >
            <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
            </svg>
            Download Report (TXT)
          </button>
        </div>
      </section>
    </div>
  );
}
