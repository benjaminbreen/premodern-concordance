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

interface PersonIdentity {
  name: string;
  thumbnail?: string;
  thumbnail_url?: string;
  wikipedia_slug?: string;
  description?: string;
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
  const [personIdentities, setPersonIdentities] = useState<Record<string, PersonIdentity>>({});
  const [showAll, setShowAll] = useState(false);
  const [corpusExpanded, setCorpusExpanded] = useState(false);
  const [xrefFilter, setXrefFilter] = useState<string>(""); // "" = off, "any", "same_referent", "cross_linguistic", "contested_identity"

  // Read all URL params on mount
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const highlight = params.get("highlight");
    const searchQuery = params.get("from_search");
    const cat = params.get("category");
    const book = params.get("book");
    const q = params.get("q");
    const all = params.get("all");
    if (highlight) setSearch(highlight);
    else if (q) setSearch(q);
    if (searchQuery) setFromSearch(searchQuery);
    if (cat) setCategoryFilter(cat);
    if (book) setBookFilter(book);
    if (all === "1") setShowAll(true);
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
    if (showAll) {
      url.searchParams.set("all", "1");
    } else {
      url.searchParams.delete("all");
    }
    window.history.replaceState({}, "", url.toString());
  }, [search, categoryFilter, bookFilter, showAll]);

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
    fetch("/data/person_identities.json")
      .then((res) => res.json())
      .then((d) => setPersonIdentities(d))
      .catch(() => {});
  }, []);

  // Precompute cluster ID → local thumbnail path
  const clusterThumbnails = useMemo(() => {
    const identKeys = Object.keys(personIdentities);
    if (!data || identKeys.length === 0) return new Map<number, string>();
    // Pre-index: lowercase name → thumbnail path
    const thumbByName = new Map<string, string>();
    for (const key of identKeys) {
      const ident = personIdentities[key];
      if (ident?.thumbnail) thumbByName.set(key.toLowerCase().trim(), `/thumbnails/${ident.thumbnail}`);
    }
    const map = new Map<number, string>();
    for (const cluster of data.clusters) {
      const cn = (cluster.canonical_name || "").toLowerCase().trim();
      let found = thumbByName.get(cn);
      if (!found) {
        const mn = cluster.ground_truth?.modern_name;
        if (mn) found = thumbByName.get(mn.toLowerCase().trim());
      }
      if (!found) {
        for (const m of cluster.members) {
          found = thumbByName.get(m.name.toLowerCase().trim());
          if (found) break;
        }
      }
      if (found) map.set(cluster.id, found);
    }
    return map;
  }, [data, personIdentities]);

  const getClusterThumbnail = useCallback((cluster: Cluster): string | null => {
    return clusterThumbnails.get(cluster.id) || null;
  }, [clusterThumbnails]);

  const filteredClusters = useMemo(() => {
    if (!data) return [];
    let clusters = data.clusters;

    // Apply browse threshold when not searching (users can always find anything via search)
    if (!search && !showAll) {
      clusters = clusters.filter(
        (c) => c.book_count >= 3 && c.total_mentions >= 5
      );
    }

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

    if (xrefFilter) {
      clusters = clusters.filter((c) => {
        const refs = (c.cross_references || []).filter((r) => r.target_cluster_id != null && !r.is_reverse);
        if (xrefFilter === "any") return refs.length > 0;
        return refs.some((r) => r.link_type === xrefFilter);
      });
    }

    // Sort by salience: cross-book coverage weighted by mention frequency
    clusters = [...clusters].sort((a, b) => {
      const sa = a.book_count * a.total_mentions;
      const sb = b.book_count * b.total_mentions;
      return sb - sa;
    });

    return clusters;
  }, [data, search, categoryFilter, bookFilter, showAll, xrefFilter]);

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
          {/* Title + subtitle */}
          <div className="h-8 bg-[var(--border)] rounded w-1/4" />
          <div className="h-4 bg-[var(--border)] rounded w-1/2" />
          {/* Search bar + filter row */}
          <div className="flex gap-2">
            <div className="h-10 bg-[var(--border)] rounded-lg flex-1" />
            <div className="h-10 bg-[var(--border)] rounded-lg w-40" />
          </div>
          <div className="flex gap-1.5">
            {Array.from({ length: 7 }).map((_, i) => (
              <div key={i} className="h-7 bg-[var(--border)] rounded w-20" />
            ))}
          </div>
          {/* Table header */}
          <div className="hidden md:grid grid-cols-[1.75rem_1fr_1fr_5.5rem_1fr_3rem_1.5rem] gap-x-3 px-4 py-2.5">
            <div /><div className="h-3 bg-[var(--border)] rounded w-12" /><div className="h-3 bg-[var(--border)] rounded w-20" /><div className="h-3 bg-[var(--border)] rounded w-10" /><div className="h-3 bg-[var(--border)] rounded w-16" /><div className="h-3 bg-[var(--border)] rounded w-8" /><div />
          </div>
          {/* Rows */}
          {Array.from({ length: 8 }).map((_, i) => (
            <div key={i} className="grid grid-cols-[1.75rem_1fr_1fr_5.5rem_1fr_3rem_1.5rem] gap-x-3 px-4 py-3 items-center">
              <div className="w-2.5 h-2.5 bg-[var(--border)] rounded-full" />
              <div className="h-4 bg-[var(--border)] rounded w-3/4" />
              <div className="hidden md:block h-3 bg-[var(--border)] rounded w-2/3" />
              <div className="hidden md:block h-5 bg-[var(--border)] rounded w-14" />
              <div className="hidden md:flex gap-1"><div className="h-5 bg-[var(--border)] rounded w-8" /><div className="h-5 bg-[var(--border)] rounded w-8" /></div>
              <div className="hidden md:block h-3 bg-[var(--border)] rounded w-6 ml-auto" />
              <div className="hidden md:block w-4 h-4 bg-[var(--border)] rounded ml-auto" />
            </div>
          ))}
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

      {/* Search + book filter */}
      <div className="flex flex-col sm:flex-row gap-2 mb-3">
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
      <div className="relative mb-4">
        <div className="flex gap-1.5 overflow-x-auto pb-1 scrollbar-thin" style={{ WebkitOverflowScrolling: "touch" }}>
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
                  className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors whitespace-nowrap shrink-0 ${
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
      </div>

      {/* Cross-reference filter chips */}
      <div className="flex items-center gap-1.5 mb-3">
        <span className="text-xs text-[var(--muted)] mr-1 shrink-0">Links:</span>
        {([
          { key: "any", label: "Has cross-refs" },
          { key: "same_referent", label: "Synonyms" },
          { key: "cross_linguistic", label: "Translations" },
          { key: "contested_identity", label: "Contested" },
        ] as const).map(({ key, label }) => {
          const active = xrefFilter === key;
          return (
            <button
              key={key}
              onClick={() => { setXrefFilter(active ? "" : key); setShowCount(50); }}
              className={`px-2 py-0.5 rounded text-xs transition-colors whitespace-nowrap ${
                active
                  ? "bg-[var(--foreground)] text-[var(--background)]"
                  : "border border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)]"
              }`}
            >
              {label}
            </button>
          );
        })}
        {xrefFilter && (
          <button
            onClick={() => setXrefFilter("")}
            className="text-xs text-[var(--muted)] hover:text-[var(--foreground)] ml-1"
          >
            clear
          </button>
        )}
      </div>

      <div className="flex items-baseline gap-2 mb-3 flex-wrap">
        <span className="text-sm font-medium">{filteredClusters.length.toLocaleString()} clusters</span>
        {!search && !showAll && (
          <span className="text-xs text-[var(--muted)]">
            of {data.clusters.length.toLocaleString()} total &middot; showing notable clusters
          </span>
        )}
        {(search || categoryFilter !== "ALL" || bookFilter !== "ALL") && (showAll || search) && (
          <span className="text-xs text-[var(--muted)]">
            of {data.clusters.length.toLocaleString()} total
            {search && <> matching &ldquo;{search}&rdquo;</>}
          </span>
        )}
        {!search && (
          <button
            onClick={() => { setShowAll(!showAll); setShowCount(50); }}
            className="text-xs text-[var(--accent)] hover:underline ml-1"
          >
            {showAll ? "Show notable only" : "Show all"}
          </button>
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
              style={{ contentVisibility: "auto", containIntrinsicSize: "auto 56px" }}
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
                  <span className={`w-2.5 h-2.5 rounded-full ${catColor?.dot || "bg-gray-400"}`} />
                </div>

                {/* Name + mobile description */}
                <div className="min-w-0">
                  <Link
                    href={`/concordance/${clusterSlug(cluster, data!.clusters)}`}
                    onClick={(e) => e.stopPropagation()}
                    className="font-semibold truncate block hover:text-[var(--accent)] transition-colors"
                    title={displayName(cluster)}
                  >
                    {displayName(cluster)}
                  </Link>
                  {displayName(cluster).toLowerCase() !== cluster.canonical_name.toLowerCase() && (
                    <span className="text-xs text-[var(--muted)] truncate block mt-0.5" title={cluster.canonical_name}>
                      {cluster.canonical_name}
                    </span>
                  )}
                  {cluster.ground_truth?.wikidata_description && (
                    <span className="md:hidden text-xs text-[var(--muted)] truncate block mt-0.5" title={cluster.ground_truth.wikidata_description}>
                      {cluster.ground_truth.wikidata_description}
                    </span>
                  )}
                </div>

                {/* Identification + description — hidden on mobile */}
                <div className="hidden md:block min-w-0">
                  {identification ? (
                    <span className="text-sm text-[var(--muted)] truncate block" title={identification.text}>
                      {identification.italic ? <i>{identification.text}</i> : identification.text}
                    </span>
                  ) : null}
                  {cluster.ground_truth?.wikidata_description && (
                    <span className="text-xs text-[var(--muted)] opacity-60 truncate block" title={cluster.ground_truth.wikidata_description}>
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

                {/* Mention count + cross-ref indicator */}
                <div className="text-right">
                  <span className="text-sm text-[var(--muted)] font-mono tabular-nums">
                    {cluster.total_mentions.toLocaleString()}
                  </span>
                  {(() => {
                    const linkedRefs = (cluster.cross_references || []).filter((r) => r.target_cluster_id != null && !r.is_reverse);
                    if (linkedRefs.length === 0) return null;
                    return (
                      <span className="block text-[10px] text-[var(--accent)] font-mono tabular-nums mt-0.5" title={`${linkedRefs.length} cross-references`}>
                        {linkedRefs.length} links
                      </span>
                    );
                  })()}
                </div>

                {/* Chevron */}
                <svg
                  className={`w-4 h-4 text-[var(--muted)] transition-transform justify-self-end ${isExpanded ? "rotate-180" : ""}`}
                  fill="none" stroke="currentColor" viewBox="0 0 24 24"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                </svg>
              </button>

              {/* Expanded preview card */}
              {isExpanded && (
                <div className="px-4 pb-4 border-t border-[var(--border)] animate-expand">
                  <div className="mt-3 flex items-start gap-3">
                    {/* Optional thumbnail */}
                    {(() => {
                      const localThumb = getClusterThumbnail(cluster);
                      if (localThumb) return (
                        <div className="shrink-0">
                          {/* eslint-disable-next-line @next/next/no-img-element */}
                          <img
                            src={localThumb}
                            alt={cluster.ground_truth?.modern_name || ""}
                            className="w-12 h-14 rounded object-cover border border-[var(--border)] bg-[var(--border)]"
                          />
                        </div>
                      );
                      return null;
                    })()}
                    <div className="flex-1 min-w-0">
                      {/* One-line identification */}
                      {cluster.ground_truth && (
                        <div className="flex items-center gap-2 flex-wrap mb-1">
                          <span className="text-sm font-semibold">{cluster.ground_truth.modern_name}</span>
                          {cluster.ground_truth.linnaean && (
                            <span className="text-sm italic text-[var(--muted)]">{cluster.ground_truth.linnaean}</span>
                          )}
                        </div>
                      )}
                      {/* 2-3 line description */}
                      {(cluster.ground_truth?.description || cluster.ground_truth?.wikidata_description) && (
                        <p className="text-xs text-[var(--muted)] leading-relaxed line-clamp-3">
                          {cluster.ground_truth.description || cluster.ground_truth.wikidata_description}
                        </p>
                      )}
                    </div>
                  </div>

                  {/* Compact source book list with mention counts */}
                  <div className="mt-3">
                    <div className="flex flex-wrap gap-1.5">
                      {data.books
                        .filter((b) => cluster.members.some((m) => m.book_id === b.id))
                        .sort((a, b) => a.year - b.year)
                        .map((book) => {
                          const count = cluster.members.filter((m) => m.book_id === book.id).reduce((s, m) => s + m.count, 0);
                          return (
                            <span
                              key={book.id}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-[var(--border)] text-[var(--muted)]"
                            >
                              <span className="font-mono">{BOOK_LANG_FLAGS[book.language] || "?"}</span>
                              {BOOK_SHORT_NAMES[book.id] || book.title}
                              <span className="font-mono tabular-nums opacity-60">{count}</span>
                            </span>
                          );
                        })}
                    </div>
                  </div>

                  {/* Cross-reference highlights */}
                  {(() => {
                    const refs = (cluster.cross_references || []).filter((r) => r.target_cluster_id != null && !r.is_reverse);
                    if (refs.length === 0) return null;
                    const synonyms = refs.filter((r) => r.link_type === "same_referent" || r.link_type === "cross_linguistic");
                    const contested = refs.filter((r) => r.link_type === "contested_identity");
                    const shown = [...synonyms.slice(0, 3), ...contested.slice(0, 2)];
                    if (shown.length === 0 && refs.length > 0) {
                      // Show a few conceptual_overlap if nothing else
                      shown.push(...refs.slice(0, 3));
                    }
                    const typeLabel: Record<string, string> = {
                      same_referent: "synonym",
                      cross_linguistic: "translation",
                      contested_identity: "contested",
                      conceptual_overlap: "related",
                      derivation: "derived",
                    };
                    const typeColor: Record<string, string> = {
                      same_referent: "text-emerald-600 dark:text-emerald-400 bg-emerald-500/10",
                      cross_linguistic: "text-blue-600 dark:text-blue-400 bg-blue-500/10",
                      contested_identity: "text-amber-600 dark:text-amber-400 bg-amber-500/10",
                      conceptual_overlap: "text-purple-600 dark:text-purple-400 bg-purple-500/10",
                      derivation: "text-cyan-600 dark:text-cyan-400 bg-cyan-500/10",
                    };
                    return (
                      <div className="mt-3">
                        <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-1.5">
                          Cross-references
                          <span className="normal-case tracking-normal font-mono ml-1 opacity-60">({refs.length})</span>
                        </div>
                        <div className="flex flex-wrap gap-1.5">
                          {shown.map((r, i) => (
                            <span
                              key={i}
                              className="inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border border-[var(--border)]"
                            >
                              <span className={`px-1 py-px rounded text-[10px] font-medium ${typeColor[r.link_type] || "text-[var(--muted)] bg-[var(--border)]"}`}>
                                {typeLabel[r.link_type] || r.link_type}
                              </span>
                              <span className="text-[var(--muted)]">{r.target_cluster_name || r.found_name}</span>
                            </span>
                          ))}
                          {refs.length > shown.length && (
                            <span className="text-xs text-[var(--muted)] self-center">
                              +{refs.length - shown.length} more
                            </span>
                          )}
                        </div>
                      </div>
                    );
                  })()}

                  {/* Prominent full details button */}
                  <Link
                    href={`/concordance/${clusterSlug(cluster, data!.clusters)}`}
                    className="mt-3 w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 text-sm font-medium text-white bg-[var(--accent)] rounded-lg hover:opacity-90 transition-opacity"
                    onClick={(e) => e.stopPropagation()}
                  >
                    View full details
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                    </svg>
                  </Link>
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
