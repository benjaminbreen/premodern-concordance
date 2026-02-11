"use client";

import { useEffect, useState, useMemo, useCallback } from "react";
import Link from "next/link";
import { CATEGORY_COLORS } from "@/lib/colors";
import { BOOK_SHORT_NAMES } from "@/lib/books";

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


const BOOK_LANG_FLAGS: Record<string, string> = {
  English: "EN",
  Portuguese: "PT",
  Spanish: "ES",
  Latin: "LA",
  French: "FR",
  Italian: "IT",
};

function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

function clusterSlug(cluster: Cluster, allClusters: Cluster[]): string {
  if (cluster.stable_key) return cluster.stable_key;
  const base = slugify(cluster.canonical_name);
  const hasCollision = allClusters.some(
    (c) => c.id !== cluster.id && slugify(c.canonical_name) === base
  );
  return hasCollision ? `${base}-${cluster.id}` : base;
}

function displayName(cluster: Cluster): string {
  return cluster.ground_truth?.modern_name || cluster.canonical_name;
}

/** Capitalize first letter of identification text */
function cap(r: { text: string; italic: boolean }): { text: string; italic: boolean } {
  if (r.text.length > 0) {
    return { ...r, text: r.text.charAt(0).toUpperCase() + r.text.slice(1) };
  }
  return r;
}

/** Build a richer identification string for the list row */
function getIdentification(cluster: Cluster): { text: string; italic: boolean } | null {
  const gt = cluster.ground_truth;
  if (!gt || !gt.modern_name) return null;
  const cat = cluster.category;
  const labelLower = displayName(cluster).toLowerCase();

  if (cat === "PERSON") {
    // Always show modern_name with dates for persons
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

  // SUBSTANCE, CONCEPT, DISEASE, PLACE, OBJECT
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

/** Language-only source tags with hover tooltip */
function SourceLangs({ bookIds, books }: { bookIds: string[]; books: BookMeta[] }) {
  const seen = new Set<string>();
  const langs: string[] = [];
  bookIds.forEach((bid) => {
    const book = books.find((b) => b.id === bid);
    const lang = BOOK_LANG_FLAGS[book?.language || ""] || "?";
    if (!seen.has(lang)) {
      seen.add(lang);
      langs.push(lang);
    }
  });

  const bookDetails = bookIds
    .map((bid) => {
      const book = books.find((b) => b.id === bid);
      if (!book) return null;
      return {
        lang: BOOK_LANG_FLAGS[book.language] || "?",
        name: BOOK_SHORT_NAMES[bid] || book.title,
        year: book.year,
      };
    })
    .filter((b): b is NonNullable<typeof b> => b !== null);

  return (
    <div className="relative group/src flex gap-1 overflow-visible">
      {langs.map((lang) => (
        <span
          key={lang}
          className="px-1.5 py-0.5 text-xs font-mono rounded border border-[var(--border)] text-[var(--muted)]"
        >
          {lang}
        </span>
      ))}
      <div className="pointer-events-none absolute bottom-full left-0 mb-2 opacity-0 group-hover/src:opacity-100 transition-opacity duration-150 z-50">
        <div className="bg-[var(--foreground)] text-[var(--background)] rounded-lg px-3 py-2 text-xs shadow-lg whitespace-nowrap space-y-0.5">
          {bookDetails.map((b, i) => (
            <div key={i} className="flex items-center gap-2">
              <span className="font-mono opacity-60">{b.lang}</span>
              <span>{b.name}</span>
              <span className="opacity-40">{b.year}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
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
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 8000);
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) { clearTimeout(timeout); return; }

      fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`, { signal: controller.signal })
        .then((res) => res.json())
        .then((data) => {
          if (data.thumbnail?.source) {
            setThumb(data.thumbnail.source);
          }
        })
        .catch(() => {})
        .finally(() => clearTimeout(timeout));
    } catch {
      clearTimeout(timeout);
    }
    return () => { controller.abort(); clearTimeout(timeout); };
  }, [url]);

  if (!thumb) return null;

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={thumb}
      alt=""
      className="w-24 h-24 rounded object-cover shrink-0 border border-[var(--border)]"
    />
  );
}

/** Fetches and displays Wikipedia article extract with expandable reading */
function WikiExtract({ url }: { url: string }) {
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) { setLoading(false); clearTimeout(timeout); return; }

      fetch(
        `https://${lang}.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&prop=extracts&explaintext=true&exsectionformat=plain&format=json&origin=*`,
        { signal: controller.signal }
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
        .catch(() => setLoading(false))
        .finally(() => clearTimeout(timeout));
    } catch {
      setLoading(false);
      clearTimeout(timeout);
    }
    return () => { controller.abort(); clearTimeout(timeout); };
  }, [url]);

  if (loading || paragraphs.length === 0) return null;

  // Truncate first paragraph to ~500 chars at a sentence boundary
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
    <div className="mt-3">
      <p className="text-sm text-[var(--foreground)]/80 leading-relaxed">
        {preview}
      </p>
      {expanded && (
        <div className="max-h-[280px] overflow-y-auto space-y-3 text-sm text-[var(--foreground)]/80 leading-relaxed">
          {restOfFirst && <p>{restOfFirst}</p>}
          {paragraphs.slice(1).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
      {hasMore && (
        <button
          onClick={(e) => { e.stopPropagation(); setExpanded(!expanded); }}
          className="mt-2 text-xs text-[var(--accent)] hover:underline"
        >
          {expanded ? "Less" : "More"}
        </button>
      )}
    </div>
  );
}

export default function ConcordancePage() {
  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [search, setSearch] = useState("");
  const [fromSearch, setFromSearch] = useState<string | null>(null);
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [bookFilter, setBookFilter] = useState("ALL");
  const [expandedCluster, setExpandedCluster] = useState<number | null>(null);
  const [showCount, setShowCount] = useState(50);
  const [corpusExpanded, setCorpusExpanded] = useState(false);

  // Read all URL params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get("highlight");
    const searchQuery = params.get("from_search");
    const cat = params.get("category");
    const book = params.get("book");
    const q = params.get("q");
    if (highlight) setSearch(highlight);
    else if (q) setSearch(q);
    if (searchQuery) setFromSearch(searchQuery);
    if (cat) setCategoryFilter(cat);
    if (book) setBookFilter(book);
  }, []);

  // Sync filter state to URL
  useEffect(() => {
    const url = new URL(window.location.href);
    if (search && !url.searchParams.has("highlight")) {
      url.searchParams.set("q", search);
    } else if (!search) {
      url.searchParams.delete("q");
    }
    if (categoryFilter !== "ALL") {
      url.searchParams.set("category", categoryFilter);
    } else {
      url.searchParams.delete("category");
    }
    if (bookFilter !== "ALL") {
      url.searchParams.set("book", bookFilter);
    } else {
      url.searchParams.delete("book");
    }
    window.history.replaceState({}, "", url.toString());
  }, [search, categoryFilter, bookFilter]);

  // Auto-expand exact match when navigating from search
  useEffect(() => {
    if (!data || !search) return;
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get("highlight");
    if (!highlight) return;
    const match = data.clusters.find(
      (c) =>
        c.canonical_name.toLowerCase() === highlight.toLowerCase()
        || displayName(c).toLowerCase() === highlight.toLowerCase()
    );
    if (match) setExpandedCluster(match.id);
  }, [data, search]);

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
          displayName(c).toLowerCase().includes(q) ||
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

  // Keyboard navigation: Escape to close, Left/Right arrows to navigate
  const handleKeyDown = useCallback((e: KeyboardEvent) => {
    // Don't interfere with input fields
    if (e.target instanceof HTMLInputElement || e.target instanceof HTMLSelectElement || e.target instanceof HTMLTextAreaElement) return;

    if (e.key === "Escape") {
      setExpandedCluster(null);
      return;
    }

    if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
      e.preventDefault();
      const visible = filteredClusters.slice(0, showCount);
      if (visible.length === 0) return;

      if (expandedCluster === null) {
        const target = e.key === "ArrowRight" ? visible[0] : visible[visible.length - 1];
        setExpandedCluster(target.id);
        setTimeout(() => {
          document.getElementById(`cluster-${target.id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
        }, 50);
        return;
      }

      const currentIdx = visible.findIndex((c) => c.id === expandedCluster);
      if (currentIdx === -1) return;

      const nextIdx = e.key === "ArrowRight" ? currentIdx + 1 : currentIdx - 1;
      if (nextIdx < 0 || nextIdx >= visible.length) return;

      setExpandedCluster(visible[nextIdx].id);
      setTimeout(() => {
        document.getElementById(`cluster-${visible[nextIdx].id}`)?.scrollIntoView({ behavior: "smooth", block: "nearest" });
      }, 50);
    }
  }, [filteredClusters, expandedCluster, showCount]);

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

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
          className="flex items-center gap-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] px-3 py-1.5 -ml-3 rounded-lg hover:bg-[var(--border)]/40 transition-all"
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
          className="px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent cursor-pointer hover:border-[var(--muted)] transition-colors appearance-none bg-[length:1.25rem] bg-[position:right_0.5rem_center] bg-no-repeat"
          style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2378716c'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`, paddingRight: "2rem" }}
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
          className="px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent cursor-pointer hover:border-[var(--muted)] transition-colors appearance-none bg-[length:1.25rem] bg-[position:right_0.5rem_center] bg-no-repeat"
          style={{ backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' fill='none' viewBox='0 0 24 24' stroke='%2378716c'%3E%3Cpath stroke-linecap='round' stroke-linejoin='round' stroke-width='2' d='M19 9l-7 7-7-7'/%3E%3C/svg%3E")`, paddingRight: "2rem" }}
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

      <div className="flex items-baseline gap-2 mb-3 flex-wrap">
        <span className="text-sm font-medium">{filteredClusters.length.toLocaleString()} clusters</span>
        {(search || categoryFilter !== "ALL" || bookFilter !== "ALL") && (
          <span className="text-xs text-[var(--muted)]">
            of {data.clusters.length.toLocaleString()} total
            {search && <> matching &ldquo;{search}&rdquo;</>}
          </span>
        )}
        <span className="text-xs text-[var(--muted)] ml-auto">
          Looking for something specific? Try <a href="/search" className="text-[var(--accent)] hover:underline">semantic search</a>
        </span>
      </div>

      {/* Column header */}
      <div className="hidden md:grid grid-cols-[1.75rem_1fr_1fr_5.5rem_1fr_3rem_1.5rem] items-center gap-x-3 px-4 py-2.5 text-xs uppercase tracking-widest text-[var(--muted)] font-medium border-b border-[var(--border)] sticky top-16 bg-[var(--background)] z-20">
        <span />
        <span>Name</span>
        <span>Identification</span>
        <span>Type</span>
        <span>Sources</span>
        <span className="text-right">Refs</span>
        <span />
      </div>

      {/* Cluster rows */}
      {filteredClusters.length === 0 && (
        <div className="py-16 text-center">
          <p className="text-lg font-medium text-[var(--muted)] mb-1">No matching clusters</p>
          <p className="text-sm text-[var(--muted)] opacity-60">Try adjusting your filters or clearing the search.</p>
        </div>
      )}
      <div className="divide-y divide-[var(--border)] border-b border-[var(--border)]">
        {filteredClusters.slice(0, showCount).map((cluster) => {
          const isExpanded = expandedCluster === cluster.id;
          const catColor = CATEGORY_COLORS[cluster.category];
          const bookIds = [...new Set(cluster.members.map((m) => m.book_id))];
          const identification = getIdentification(cluster);

          return (
            <div
              key={cluster.id}
              id={`cluster-${cluster.id}`}
              className="relative bg-[var(--card)] group/row"
            >
              {/* Left accent bar — visible on hover or when expanded */}
              <span className={`absolute left-0 top-0 bottom-0 w-0.5 ${catColor?.dot || "bg-gray-400"} ${isExpanded ? "opacity-100" : "opacity-0 group-hover/row:opacity-100"} transition-opacity z-10`} />

              {/* Cluster row */}
              <button
                onClick={() => setExpandedCluster(isExpanded ? null : cluster.id)}
                className="w-full px-4 py-3 grid grid-cols-[auto_1fr_auto_auto] md:grid-cols-[1.75rem_1fr_1fr_5.5rem_1fr_3rem_1.5rem] items-center gap-x-3 hover:bg-[var(--border)]/30 transition-colors text-left"
              >

                {/* Indicator */}
                <div className="flex items-center justify-center">
                  {cluster.ground_truth?.portrait_url ? (
                    // eslint-disable-next-line @next/next/no-img-element
                    <img
                      src={cluster.ground_truth.portrait_url}
                      alt=""
                      className="w-7 h-7 rounded-full object-cover border border-[var(--border)] bg-[var(--border)]"
                    />
                  ) : (
                    <span className={`w-2.5 h-2.5 rounded-full ${catColor?.dot || "bg-gray-400"}`} />
                  )}
                </div>

                {/* Name + mobile description */}
                <div className="min-w-0">
                  <Link
                    href={`/concordance/${clusterSlug(cluster, data!.clusters)}`}
                    onClick={(e) => e.stopPropagation()}
                    className="font-semibold truncate block hover:text-[var(--accent)] transition-colors"
                  >
                    {displayName(cluster)}
                  </Link>
                  {displayName(cluster).toLowerCase() !== cluster.canonical_name.toLowerCase() && (
                    <span className="text-xs text-[var(--muted)] truncate block mt-0.5">
                      {cluster.canonical_name}
                    </span>
                  )}
                  {cluster.ground_truth?.wikidata_description && (
                    <span className="md:hidden text-xs text-[var(--muted)] truncate block mt-0.5">
                      {cluster.ground_truth.wikidata_description}
                    </span>
                  )}
                </div>

                {/* Identification + description — hidden on mobile */}
                <div className="hidden md:block min-w-0">
                  {identification ? (
                    <span className="text-sm text-[var(--muted)] truncate block">
                      {identification.italic ? <i>{identification.text}</i> : identification.text}
                    </span>
                  ) : null}
                  {cluster.ground_truth?.wikidata_description && (
                    <span className="text-xs text-[var(--muted)] opacity-60 truncate block">
                      {cluster.ground_truth.wikidata_description}
                    </span>
                  )}
                </div>

                {/* Category — hidden on mobile */}
                <span className={`hidden md:inline-flex ${catColor?.badge || "bg-[var(--border)]"} px-2 py-0.5 rounded text-xs font-medium border justify-center`}>
                  {cluster.category}
                </span>

                {/* Source language tags — hidden on mobile */}
                <div className="hidden md:block overflow-visible">
                  <SourceLangs bookIds={bookIds} books={data.books} />
                </div>

                {/* Mention count */}
                <span className="text-sm text-[var(--muted)] font-mono text-right tabular-nums">
                  {cluster.total_mentions.toLocaleString()}
                </span>

                {/* Chevron */}
                <svg
                  className={`w-4 h-4 text-[var(--muted)] transition-transform justify-self-end ${isExpanded ? "rotate-180" : ""}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Expanded detail */}
              {isExpanded && (
                <div className="px-4 pb-5 border-t border-[var(--border)] animate-expand">
                  <div className="md:flex md:gap-6 mt-4">
                    {/* Left panel: Identification */}
                    {cluster.ground_truth && (
                      <div className="md:w-2/5 md:shrink-0">
                        <div className="p-3 rounded-lg bg-[var(--background)] border border-[var(--border)]">
                          <div className="flex items-start gap-3">
                            {cluster.ground_truth.portrait_url ? (
                              <div className="shrink-0">
                                {/* eslint-disable-next-line @next/next/no-img-element */}
                                <img
                                  src={cluster.ground_truth.portrait_url}
                                  alt={cluster.ground_truth.modern_name}
                                  className="w-14 h-[4.5rem] rounded object-cover border border-[var(--border)] bg-[var(--border)]"
                                />
                              </div>
                            ) : cluster.ground_truth.wikipedia_url ? (
                              <WikiThumbnail url={cluster.ground_truth.wikipedia_url} />
                            ) : null}
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
                                <p className="text-xs text-[var(--muted)] mt-1.5 leading-relaxed">{cluster.ground_truth.description}</p>
                              )}
                              {cluster.ground_truth.wikidata_description && !cluster.ground_truth.description && (
                                <p className="text-xs text-[var(--muted)] mt-1.5 leading-relaxed">{cluster.ground_truth.wikidata_description}</p>
                              )}
                              <div className="flex flex-wrap gap-x-3 gap-y-0.5 mt-2 text-xs text-[var(--muted)]">
                                {cluster.ground_truth.family && <span>Family: {cluster.ground_truth.family}</span>}
                                {cluster.ground_truth.birth_year && (
                                  <span>{cluster.ground_truth.birth_year}&ndash;{cluster.ground_truth.death_year || "?"}</span>
                                )}
                                {cluster.ground_truth.country && <span>{cluster.ground_truth.country}</span>}
                                {cluster.ground_truth.modern_term && cluster.ground_truth.modern_term !== cluster.ground_truth.modern_name && (
                                  <span>Modern: {cluster.ground_truth.modern_term}</span>
                                )}
                              </div>
                              {cluster.ground_truth.note && (
                                <p className="text-xs text-[var(--muted)] mt-2 border-l-2 border-[var(--border)] pl-2 leading-relaxed">
                                  {cluster.ground_truth.note}
                                </p>
                              )}
                              <div className="flex items-center gap-2 mt-2 flex-wrap">
                                {cluster.ground_truth.wikipedia_url && (
                                  <a
                                    href={cluster.ground_truth.wikipedia_url}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-[var(--border)] hover:bg-[var(--border)] transition-colors"
                                  >
                                    <svg className="w-3 h-3" viewBox="0 0 24 24" fill="currentColor"><path d="M12.09 13.119c-.936 1.932-2.217 4.548-2.853 5.728-.616 1.074-1.127.931-1.532.029-1.406-3.321-4.293-9.144-5.651-12.409-.251-.601-.441-.987-.619-1.139-.181-.15-.554-.224-1.122-.224L.203 5.104c-.196 0-.302-.099-.302-.296S.035 4.5.231 4.5h4.717c.196 0 .294.099.294.296s-.098.312-.294.312c-.635 0-1.067.078-1.3.234-.238.155-.244.467-.06.931 1.283 3.223 3.944 8.502 5.283 11.727.477-1.054 2.067-4.287 2.772-5.821C10.791 10.485 9.25 7.35 8.187 5.104c-.196-.439-.36-.685-.535-.789-.173-.104-.583-.156-1.225-.156l-.022-.312c-.196 0-.302-.099-.302-.296S6.207 3.24 6.403 3.24h4.43c.196 0 .294.099.294.296s-.098.312-.294.312c-.523 0-.885.078-1.085.234-.205.155-.178.39.024.693 1.095 2.23 2.256 4.475 2.93 5.737.384-.747 1.665-3.324 2.466-4.957.354-.786.456-1.357.129-1.619-.191-.164-.616-.246-1.27-.246l-.022-.312c-.196 0-.302-.099-.302-.296s.106-.312.302-.312h4.068c.196 0 .294.099.294.296s-.098.312-.294.312c-.466 0-.86.078-1.181.234-.322.155-.662.5-1.019 1.035-.638.862-2.096 3.785-2.709 5.01.634 1.259 2.627 5.532 3.423 7.142.424-.811 2.464-5.014 3.241-6.661.344-.746.395-1.357.017-1.619-.227-.164-.662-.246-1.303-.246l-.022-.312c-.196 0-.302-.099-.302-.296s.106-.312.302-.312h3.686c.196 0 .294.099.294.296s-.098.312-.294.312c-.487 0-.89.078-1.211.234-.322.155-.705.5-1.15 1.035-.8 1.094-2.722 5.236-3.592 7.136-.453.987-1.024 2.145-1.49 3.124-.556 1.074-1.073.931-1.478.029L12.09 13.119z"/></svg>
                                    Wikipedia
                                  </a>
                                )}
                                {cluster.ground_truth.wikidata_id && (
                                  <a
                                    href={`https://www.wikidata.org/wiki/${cluster.ground_truth.wikidata_id}`}
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-[var(--border)] hover:bg-[var(--border)] transition-colors font-mono text-[var(--muted)]"
                                    title={cluster.ground_truth.wikidata_id}
                                  >
                                    {cluster.ground_truth.wikidata_id}
                                  </a>
                                )}
                              </div>
                            </div>
                          </div>
                        </div>
                        {/* Wikipedia extract */}
                        {cluster.ground_truth?.wikipedia_url && (
                          <WikiExtract url={cluster.ground_truth.wikipedia_url} />
                        )}
                      </div>
                    )}

                    {/* Right panel: Members by book */}
                    <div className={`flex-1 min-w-0 ${cluster.ground_truth ? "mt-4 md:mt-0" : ""}`}>
                      <h4 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-2">Source Evidence</h4>
                      <div className="space-y-3">
                        {data.books
                          .filter((b) => cluster.members.some((m) => m.book_id === b.id))
                          .map((book) => {
                            const bookMembers = cluster.members.filter((m) => m.book_id === book.id);
                            return (
                              <div key={book.id} className="pl-3 border-l-2 border-[var(--border)]">
                                <div className="flex items-baseline gap-2 mb-1">
                                  <span className="text-xs font-medium">{BOOK_SHORT_NAMES[book.id] || book.title}</span>
                                  <span className="text-xs text-[var(--muted)] font-mono">{BOOK_LANG_FLAGS[book.language] || ""}</span>
                                  <span className="text-xs text-[var(--muted)]">{book.year}</span>
                                </div>
                                {bookMembers.map((member) => (
                                  <div key={member.entity_id} className="mb-2.5 last:mb-0">
                                    <div className="flex items-baseline gap-2 flex-wrap">
                                      <Link
                                        href={`/books/${book.id}/entity/${member.entity_id}`}
                                        className="text-sm font-medium text-[var(--accent)] hover:underline"
                                      >
                                        {member.name}
                                      </Link>
                                      <span className="text-xs text-[var(--muted)] font-mono tabular-nums">
                                        {member.count}
                                      </span>
                                      {member.variants.length > 1 && (
                                        <span className="text-xs text-[var(--muted)]">
                                          {member.variants.slice(0, 5).join(", ")}
                                          {member.variants.length > 5 && ` +${member.variants.length - 5}`}
                                        </span>
                                      )}
                                    </div>
                                    {member.contexts.length > 0 && (
                                      <div className="mt-1.5 pl-3 border-l border-[var(--border)]">
                                        {member.contexts.slice(0, 2).map((ctx, i) => (
                                          <p key={i} className="text-sm text-[var(--muted)] italic leading-relaxed mb-1 last:mb-0">
                                            &ldquo;{ctx.length > 200 ? ctx.slice(0, 197) + "\u2026" : ctx}&rdquo;
                                          </p>
                                        ))}
                                      </div>
                                    )}
                                  </div>
                                ))}
                              </div>
                            );
                          })}
                      </div>
                    </div>
                  </div>

                  {/* Cross-book similarity — full width */}
                  {cluster.edges.length > 0 && (
                    <div className="mt-4 pt-3 border-t border-[var(--border)]">
                      <h4 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-2">Cross-book Connections</h4>
                      <div className="space-y-1">
                        {cluster.edges.slice(0, 6).map((edge, idx) => (
                          <div key={idx} className="flex items-center gap-2 text-xs">
                            <span className="text-[var(--muted)] shrink-0">
                              {BOOK_SHORT_NAMES[edge.source_book] || edge.source_book}:
                            </span>
                            <span className="shrink-0">{edge.source_name}</span>
                            <span className="text-[var(--muted)]">&harr;</span>
                            <span className="text-[var(--muted)] shrink-0">
                              {BOOK_SHORT_NAMES[edge.target_book] || edge.target_book}:
                            </span>
                            <span className="shrink-0">{edge.target_name}</span>
                            <span className="font-mono text-[var(--muted)] ml-auto tabular-nums">{Math.round(edge.similarity * 100)}%</span>
                          </div>
                        ))}
                        {cluster.edges.length > 6 && (
                          <p className="text-xs text-[var(--muted)] mt-1">
                            +{cluster.edges.length - 6} more connections
                          </p>
                        )}
                      </div>
                    </div>
                  )}

                  {/* View full details link */}
                  <div className="mt-4 pt-3 border-t border-[var(--border)]">
                    <Link
                      href={`/concordance/${clusterSlug(cluster, data!.clusters)}`}
                      className="inline-flex items-center gap-1.5 text-sm text-[var(--accent)] hover:underline"
                      onClick={(e) => e.stopPropagation()}
                    >
                      View full details &rarr;
                    </Link>
                  </div>
                </div>
              )}
            </div>
          );
        })}
      </div>

      {/* Load more */}
      {filteredClusters.length > showCount && (
        <div className="text-center mt-6 py-4 border-t border-[var(--border)]">
          <button
            onClick={() => setShowCount((c) => c + 50)}
            className="px-8 py-3 rounded-lg border border-[var(--border)] text-sm font-medium hover:bg-[var(--border)] hover:border-[var(--foreground)]/20 transition-colors"
          >
            Show more
          </button>
          <p className="text-xs text-[var(--muted)] mt-2">
            {(filteredClusters.length - showCount).toLocaleString()} more of {filteredClusters.length.toLocaleString()} total
          </p>
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
