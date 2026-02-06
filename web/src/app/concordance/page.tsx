"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";

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

const CATEGORY_COLORS: Record<string, { badge: string; dot: string }> = {
  PERSON: {
    badge: "bg-purple-500/20 text-purple-600 dark:text-purple-400 border-purple-500/30",
    dot: "bg-purple-500",
  },
  PLANT: {
    badge: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
    dot: "bg-emerald-500",
  },
  ANIMAL: {
    badge: "bg-lime-500/20 text-lime-600 dark:text-lime-400 border-lime-500/30",
    dot: "bg-lime-500",
  },
  SUBSTANCE: {
    badge: "bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 border-cyan-500/30",
    dot: "bg-cyan-500",
  },
  CONCEPT: {
    badge: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
    dot: "bg-amber-500",
  },
  DISEASE: {
    badge: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
    dot: "bg-red-500",
  },
  PLACE: {
    badge: "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
    dot: "bg-green-500",
  },
  OBJECT: {
    badge: "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30",
    dot: "bg-slate-500",
  },
};

const BOOK_SHORT_NAMES: Record<string, string> = {
  "english_physician_1652": "Culpeper",
  "semedo-polyanthea-1741": "Semedo",
  "coloquios_da_orta_1563": "Da Orta",
  "historia_medicinal_monardes_1574": "Monardes",
  "relation_historique_humboldt_vol3_1825": "Humboldt",
};

const BOOK_LANG_FLAGS: Record<string, string> = {
  English: "EN",
  Portuguese: "PT",
  Spanish: "ES",
  Latin: "LA",
  French: "FR",
};

function BookPill({ bookId, books }: { bookId: string; books: BookMeta[] }) {
  const book = books.find((b) => b.id === bookId);
  const shortName = BOOK_SHORT_NAMES[bookId] || bookId;
  const lang = BOOK_LANG_FLAGS[book?.language || ""] || "";
  return (
    <span className="inline-flex items-center gap-1 px-2 py-0.5 text-xs rounded border border-[var(--border)] bg-[var(--card)]">
      {lang && <span className="text-[var(--muted)] font-mono">{lang}</span>}
      <span>{shortName}</span>
    </span>
  );
}

function SimilarityBar({ value }: { value: number }) {
  const pct = Math.round(value * 100);
  const color = pct >= 95 ? "bg-green-500" : pct >= 88 ? "bg-emerald-400" : pct >= 82 ? "bg-yellow-400" : "bg-orange-400";
  return (
    <div className="flex items-center gap-2">
      <div className="w-16 h-1.5 rounded-full bg-[var(--border)] overflow-hidden">
        <div className={`h-full rounded-full ${color}`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-[var(--muted)] font-mono">{pct}%</span>
    </div>
  );
}

function WikiThumbnail({ url }: { url: string }) {
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
          if (data.thumbnail?.source) {
            setThumb(data.thumbnail.source);
          }
        })
        .catch(() => {});
    } catch {
      // invalid URL
    }
  }, [url]);

  if (!thumb) return null;

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={thumb}
      alt=""
      className="w-16 h-16 rounded object-cover shrink-0 border border-[var(--border)]"
    />
  );
}

export default function ConcordancePage() {
  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fromSearch, setFromSearch] = useState<string | null>(null);

  // Read highlight param from URL on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get("highlight");
    const searchQuery = params.get("from_search");
    if (highlight) setSearch(highlight);
    if (searchQuery) setFromSearch(searchQuery);
  }, []);

  // Auto-expand exact match when navigating from search
  useEffect(() => {
    if (!data || !search) return;
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get("highlight");
    if (!highlight) return;
    const match = data.clusters.find(
      (c) => c.canonical_name.toLowerCase() === highlight.toLowerCase()
    );
    if (match) setExpandedCluster(match.id);
  }, [data, search]);
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [bookFilter, setBookFilter] = useState("ALL");
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null);
  const [showCount, setShowCount] = useState(50);
  const [corpusExpanded, setCorpusExpanded] = useState(false);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((d) => {
        setData(d);
        setLoading(false);
      })
      .catch(() => setLoading(false));
  }, []);

  const categories = useMemo(() => {
    if (!data) return [];
    return Object.keys(data.stats.by_category).sort();
  }, [data]);

  const filteredClusters = useMemo(() => {
    if (!data) return [];
    let clusters = data.clusters;

    if (search) {
      const q = search.toLowerCase();
      clusters = clusters.filter(
        (c) =>
          c.canonical_name.toLowerCase().includes(q) ||
          c.ground_truth?.modern_name?.toLowerCase().includes(q) ||
          c.ground_truth?.linnaean?.toLowerCase().includes(q) ||
          c.ground_truth?.wikidata_id?.toLowerCase().includes(q) ||
          c.members.some(
            (m) =>
              m.name.toLowerCase().includes(q) ||
              m.variants.some((v) => v.toLowerCase().includes(q))
          )
      );
    }

    if (categoryFilter !== "ALL") {
      clusters = clusters.filter((c) => c.category === categoryFilter);
    }

    if (bookFilter !== "ALL") {
      clusters = clusters.filter((c) =>
        c.members.some((m) => m.book_id === bookFilter)
      );
    }

    return clusters;
  }, [data, search, categoryFilter, bookFilter]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-[var(--border)] rounded w-1/4"></div>
          <div className="h-4 bg-[var(--border)] rounded w-1/2"></div>
          <div className="h-64 bg-[var(--border)] rounded"></div>
        </div>
      </div>
    );
  }

  if (!data) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <p className="text-[var(--muted)]">No concordance data found. Run build_concordance.py first.</p>
      </div>
    );
  }

  const languages = data.books.map((b) => b.language).filter((v, i, a) => a.indexOf(v) === i);

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Back to search */}
      {fromSearch && (
        <Link
          href={`/search?q=${encodeURIComponent(fromSearch)}`}
          className="inline-flex items-center gap-2 mb-6 px-3 py-1.5 text-sm text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:border-[var(--foreground)]/30 transition-colors"
        >
          <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 19l-7-7m0 0l7-7m-7 7h18" />
          </svg>
          Back to results for &ldquo;{fromSearch}&rdquo;
        </Link>
      )}

      {/* Header */}
      <div className="mb-6">
        <h1 className="text-3xl font-bold mb-2">Concordance</h1>
        <p className="text-[var(--muted)] max-w-2xl">
          {data.stats.total_clusters.toLocaleString()} clusters &middot;{" "}
          {data.stats.entities_matched.toLocaleString()} entities matched across{" "}
          {data.books.length} books in {languages.length} languages
        </p>
      </div>

      {/* Corpus summary — collapsed by default */}
      <div className="mb-6">
        <button
          onClick={() => setCorpusExpanded(!corpusExpanded)}
          className="flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
        >
          <svg
            className={`w-3.5 h-3.5 transition-transform ${corpusExpanded ? "rotate-90" : ""}`}
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
          </svg>
          <span>
            {data.books.length} books in {languages.length} languages
          </span>
        </button>
        {corpusExpanded && (
          <div className="mt-3 ml-6 flex flex-wrap gap-2">
            {data.books.map((book) => (
              <Link
                key={book.id}
                href={`/books/${book.id}`}
                className="flex items-center gap-2 px-2.5 py-1.5 rounded border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--border)]/50 transition-colors text-xs"
              >
                <span className="font-mono text-[var(--muted)]">
                  {BOOK_LANG_FLAGS[book.language] || "?"}
                </span>
                <span className="font-medium">{book.title}</span>
                <span className="text-[var(--muted)]">{book.year}</span>
              </Link>
            ))}
            {data.stats.enriched_clusters && (
              <div className="w-full mt-1 flex flex-wrap gap-3 text-xs text-[var(--muted)]">
                <span>{data.stats.enriched_clusters} identified</span>
                {data.stats.with_wikidata ? <span>&middot; {data.stats.with_wikidata} Wikidata</span> : null}
                {data.stats.with_wikipedia ? <span>&middot; {data.stats.with_wikipedia} Wikipedia</span> : null}
                {data.stats.with_linnaean ? <span>&middot; {data.stats.with_linnaean} Linnaean</span> : null}
              </div>
            )}
          </div>
        )}
      </div>

      {/* Search + filters */}
      <div className="flex flex-col sm:flex-row gap-2 mb-4">
        <div className="relative flex-1">
          <svg
            className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)]"
            fill="none" stroke="currentColor" viewBox="0 0 24 24"
          >
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
          </svg>
          <input
            type="text"
            placeholder="Search clusters..."
            value={search}
            onChange={(e) => { setSearch(e.target.value); setShowCount(50); }}
            className="w-full pl-9 pr-4 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent"
          />
        </div>
        <select
          value={categoryFilter}
          onChange={(e) => { setCategoryFilter(e.target.value); setShowCount(50); }}
          className="px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none"
        >
          <option value="ALL">All categories</option>
          {categories.map((cat) => (
            <option key={cat} value={cat}>
              {cat} ({data.stats.by_category[cat]})
            </option>
          ))}
        </select>
        <select
          value={bookFilter}
          onChange={(e) => { setBookFilter(e.target.value); setShowCount(50); }}
          className="px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none"
        >
          <option value="ALL">All books</option>
          {data.books.map((book) => (
            <option key={book.id} value={book.id}>
              {BOOK_SHORT_NAMES[book.id] || book.title}
            </option>
          ))}
        </select>
      </div>

      {/* Category chips */}
      <div className="flex flex-wrap gap-1.5 mb-4">
        {Object.entries(data.stats.by_category)
          .sort(([, a], [, b]) => b - a)
          .map(([cat, count]) => {
            const color = CATEGORY_COLORS[cat];
            const active = categoryFilter === cat;
            return (
              <button
                key={cat}
                onClick={() => {
                  setCategoryFilter(active ? "ALL" : cat);
                  setShowCount(50);
                }}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
                  active
                    ? `${color?.badge || "bg-[var(--border)]"} border border-current`
                    : "border border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)]"
                }`}
              >
                <span className={`w-1.5 h-1.5 rounded-full ${color?.dot || "bg-gray-400"}`} />
                {cat}
                <span className="font-mono opacity-60">{count}</span>
              </button>
            );
          })}
      </div>

      <div className="text-xs text-[var(--muted)] mb-3">
        {filteredClusters.length} clusters
        {search && ` matching "${search}"`}
      </div>

      {/* Cluster cards */}
      <div className="space-y-3">
        {filteredClusters.slice(0, showCount).map((cluster) => {
          const isExpanded = expandedCluster === cluster.id;
          const catColor = CATEGORY_COLORS[cluster.category];
          const bookIds = [...new Set(cluster.members.map((m) => m.book_id))];

          return (
            <div
              key={cluster.id}
              className="border border-[var(--border)] rounded-lg bg-[var(--card)] overflow-hidden"
            >
              {/* Cluster header */}
              <button
                onClick={() => setExpandedCluster(isExpanded ? null : cluster.id)}
                className="w-full px-4 py-3 flex items-center justify-between hover:bg-[var(--border)]/30 transition-colors text-left"
              >
                <div className="flex items-center gap-3 flex-1 min-w-0">
                  <span className={`w-2.5 h-2.5 rounded-full shrink-0 ${catColor?.dot || "bg-gray-400"}`} />
                  <span className="font-semibold truncate">{cluster.canonical_name}</span>
                  {cluster.ground_truth && cluster.ground_truth.modern_name.toLowerCase() !== cluster.canonical_name.toLowerCase() && (
                    <span className="text-sm text-[var(--muted)] truncate">
                      {cluster.ground_truth.linnaean ? (
                        <i>{cluster.ground_truth.linnaean}</i>
                      ) : (
                        cluster.ground_truth.modern_name
                      )}
                    </span>
                  )}
                  <span className={`${catColor?.badge || "bg-[var(--border)]"} px-2 py-0.5 rounded text-xs font-medium border shrink-0`}>
                    {cluster.category}
                  </span>
                  <div className="flex gap-1 shrink-0">
                    {bookIds.map((bid) => (
                      <BookPill key={bid} bookId={bid} books={data.books} />
                    ))}
                  </div>
                </div>
                <div className="flex items-center gap-4 shrink-0 ml-3">
                  <span className="text-sm text-[var(--muted)] font-mono">
                    {cluster.total_mentions}x
                  </span>
                  <svg
                    className={`w-4 h-4 text-[var(--muted)] transition-transform ${isExpanded ? "rotate-180" : ""}`}
                    fill="none" stroke="currentColor" viewBox="0 0 24 24"
                  >
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </div>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-[var(--border)]">
                  {/* Ground truth identification */}
                  {cluster.ground_truth && (
                    <div className="mt-4 p-3 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                      <div className="flex items-start gap-3">
                        {cluster.ground_truth.wikipedia_url && (
                          <WikiThumbnail url={cluster.ground_truth.wikipedia_url} />
                        )}
                        <div className="flex-1 min-w-0">
                          <div className="flex items-center gap-2 flex-wrap">
                            <span className="text-sm font-semibold">{cluster.ground_truth.modern_name}</span>
                            {cluster.ground_truth.linnaean && (
                              <span className="text-sm italic text-[var(--muted)]">{cluster.ground_truth.linnaean}</span>
                            )}
                            <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${
                              cluster.ground_truth.confidence === "high" ? "bg-green-500/20 text-green-600 dark:text-green-400" :
                              cluster.ground_truth.confidence === "medium" ? "bg-yellow-500/20 text-yellow-600 dark:text-yellow-400" :
                              "bg-red-500/20 text-red-600 dark:text-red-400"
                            }`}>
                              {cluster.ground_truth.confidence}
                            </span>
                          </div>
                          {cluster.ground_truth.description && (
                            <p className="text-xs text-[var(--muted)] mt-1">{cluster.ground_truth.description}</p>
                          )}
                          {cluster.ground_truth.wikidata_description && !cluster.ground_truth.description && (
                            <p className="text-xs text-[var(--muted)] mt-1">{cluster.ground_truth.wikidata_description}</p>
                          )}
                          {cluster.ground_truth.family && (
                            <p className="text-xs text-[var(--muted)] mt-0.5">Family: {cluster.ground_truth.family}</p>
                          )}
                          {cluster.ground_truth.birth_year && (
                            <p className="text-xs text-[var(--muted)] mt-0.5">
                              {cluster.ground_truth.birth_year}–{cluster.ground_truth.death_year || "?"}
                            </p>
                          )}
                          {cluster.ground_truth.country && (
                            <p className="text-xs text-[var(--muted)] mt-0.5">{cluster.ground_truth.country}</p>
                          )}
                          {cluster.ground_truth.modern_term && cluster.ground_truth.modern_term !== cluster.ground_truth.modern_name && (
                            <p className="text-xs text-[var(--muted)] mt-0.5">Modern: {cluster.ground_truth.modern_term}</p>
                          )}
                          {cluster.ground_truth.note && (
                            <p className="text-xs text-yellow-600 dark:text-yellow-400 mt-1">{cluster.ground_truth.note}</p>
                          )}
                          <div className="flex items-center gap-2 mt-2">
                            {cluster.ground_truth.wikipedia_url && (
                              <a
                                href={cluster.ground_truth.wikipedia_url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-[var(--border)] hover:bg-[var(--border)] transition-colors"
                              >
                                <svg className="w-3.5 h-3.5" viewBox="0 0 24 24" fill="currentColor"><path d="M12.09 13.119c-.936 1.932-2.217 4.548-2.853 5.728-.616 1.074-1.127.931-1.532.029-1.406-3.321-4.293-9.144-5.651-12.409-.251-.601-.441-.987-.619-1.139-.181-.15-.554-.224-1.122-.224L.203 5.104c-.196 0-.302-.099-.302-.296S.035 4.5.231 4.5h4.717c.196 0 .294.099.294.296s-.098.312-.294.312c-.635 0-1.067.078-1.3.234-.238.155-.244.467-.06.931 1.283 3.223 3.944 8.502 5.283 11.727.477-1.054 2.067-4.287 2.772-5.821C10.791 10.485 9.25 7.35 8.187 5.104c-.196-.439-.36-.685-.535-.789-.173-.104-.583-.156-1.225-.156l-.022-.312c-.196 0-.302-.099-.302-.296S6.207 3.24 6.403 3.24h4.43c.196 0 .294.099.294.296s-.098.312-.294.312c-.523 0-.885.078-1.085.234-.205.155-.178.39.024.693 1.095 2.23 2.256 4.475 2.93 5.737.384-.747 1.665-3.324 2.466-4.957.354-.786.456-1.357.129-1.619-.191-.164-.616-.246-1.27-.246l-.022-.312c-.196 0-.302-.099-.302-.296s.106-.312.302-.312h4.068c.196 0 .294.099.294.296s-.098.312-.294.312c-.466 0-.86.078-1.181.234-.322.155-.662.5-1.019 1.035-.638.862-2.096 3.785-2.709 5.01.634 1.259 2.627 5.532 3.423 7.142.424-.811 2.464-5.014 3.241-6.661.344-.746.395-1.357.017-1.619-.227-.164-.662-.246-1.303-.246l-.022-.312c-.196 0-.302-.099-.302-.296s.106-.312.302-.312h3.686c.196 0 .294.099.294.296s-.098.312-.294.312c-.487 0-.89.078-1.211.234-.322.155-.705.5-1.15 1.035-.8 1.094-2.722 5.236-3.592 7.136-.453.987-1.024 2.145-1.49 3.124-.556 1.074-1.073.931-1.478.029L12.09 13.119z"/></svg>
                                Wikipedia
                              </a>
                            )}
                            {cluster.ground_truth.wikidata_id && (
                              <a
                                href={`https://www.wikidata.org/wiki/${cluster.ground_truth.wikidata_id}`}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="inline-flex items-center gap-1 px-2 py-1 rounded text-xs border border-[var(--border)] hover:bg-[var(--border)] transition-colors font-mono"
                                title={cluster.ground_truth.wikidata_id}
                              >
                                {cluster.ground_truth.wikidata_id}
                              </a>
                            )}
                          </div>
                        </div>
                      </div>
                    </div>
                  )}

                  {/* Members by book */}
                  <div className="mt-4 space-y-4">
                    {data.books
                      .filter((b) => cluster.members.some((m) => m.book_id === b.id))
                      .map((book) => {
                        const bookMembers = cluster.members.filter((m) => m.book_id === book.id);
                        return (
                          <div key={book.id} className="pl-3 border-l-2 border-[var(--border)]">
                            <div className="flex items-center gap-2 mb-2">
                              <span className="text-sm font-medium">{book.title}</span>
                              <span className="text-xs text-[var(--muted)]">({book.language}, {book.year})</span>
                            </div>
                            {bookMembers.map((member) => (
                              <div key={member.entity_id} className="ml-2 mb-2">
                                <div className="flex items-center gap-2">
                                  <Link
                                    href={`/books/${book.id}/entity/${member.entity_id}`}
                                    className="text-sm font-medium text-[var(--accent)] hover:underline"
                                  >
                                    {member.name}
                                  </Link>
                                  <span className="text-xs text-[var(--muted)] font-mono">
                                    {member.count}x
                                  </span>
                                </div>
                                {member.variants.length > 1 && (
                                  <div className="flex flex-wrap gap-1 mt-1">
                                    {member.variants.slice(0, 8).map((v, i) => (
                                      <span key={i} className="text-xs px-1.5 py-0.5 rounded bg-[var(--border)]">
                                        {v}
                                      </span>
                                    ))}
                                    {member.variants.length > 8 && (
                                      <span className="text-xs text-[var(--muted)]">
                                        +{member.variants.length - 8} more
                                      </span>
                                    )}
                                  </div>
                                )}
                                {member.contexts.length > 0 && (
                                  <p className="text-xs text-[var(--muted)] mt-1 italic">
                                    {member.contexts[0]}
                                  </p>
                                )}
                              </div>
                            ))}
                          </div>
                        );
                      })}
                  </div>

                  {/* Cross-book similarity edges */}
                  {cluster.edges.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-[var(--border)]">
                      <h4 className="text-xs font-medium text-[var(--muted)] mb-2">Cross-book Similarity</h4>
                      <div className="space-y-1.5">
                        {cluster.edges.slice(0, 6).map((edge, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-xs">
                            <span className="text-[var(--muted)]">
                              {BOOK_SHORT_NAMES[edge.source_book] || edge.source_book}:
                            </span>
                            <span>{edge.source_name}</span>
                            <span className="text-[var(--muted)]">&harr;</span>
                            <span className="text-[var(--muted)]">
                              {BOOK_SHORT_NAMES[edge.target_book] || edge.target_book}:
                            </span>
                            <span>{edge.target_name}</span>
                            <SimilarityBar value={edge.similarity} />
                          </div>
                        ))}
                        {cluster.edges.length > 6 && (
                          <p className="text-xs text-[var(--muted)]">
                            +{cluster.edges.length - 6} more connections
                          </p>
                        )}
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Load more */}
      {filteredClusters.length > showCount && (
        <div className="text-center mt-6">
          <button
            onClick={() => setShowCount((c) => c + 50)}
            className="px-6 py-2 rounded-lg border border-[var(--border)] text-sm hover:bg-[var(--border)] transition-colors"
          >
            Show more ({filteredClusters.length - showCount} remaining)
          </button>
        </div>
      )}

      {/* Footer */}
      <p className="text-xs text-[var(--muted)] mt-8 opacity-60">
        Cross-lingual BGE-M3 embeddings · threshold {data.metadata.threshold}
        {data.metadata.enriched && ` · enriched via ${data.metadata.enrichment_model || "Gemini"} + Wikidata`}
      </p>
    </div>
  );
}
