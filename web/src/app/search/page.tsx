"use client";

import Link from "next/link";
import { useState, useCallback, useRef, useEffect } from "react";
import { CATEGORY_COLORS as CAT_COLORS, CAT_HEX } from "@/lib/colors";
import { BOOK_SHORT_NAMES, BOOK_TITLES, BOOK_YEARS, BOOK_LANGS } from "@/lib/books";

// ── Types ──────────────────────────────────────────────────────────────

interface MemberDetail {
  book_id: string;
  entity_id: string;
  name: string;
  count: number;
  context: string;
}

interface ResultMetadata {
  id: string;
  stable_key?: string;
  display_name?: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  books: string[];
  modern_name: string;
  linnaean: string;
  wikidata_id: string;
  wikidata_description: string;
  wikipedia_url: string;
  confidence: string;
  note: string;
  family: string;
  semantic_gloss: string;
  portrait_url: string;
  names: string[];
  members?: MemberDetail[];
}

interface SearchResult {
  metadata: ResultMetadata;
  score: number;
  semantic_score: number;
  lexical_score: number;
}

interface SearchResponse {
  query: string;
  results: SearchResult[];
  total_candidates: number;
  mode: "hybrid" | "lexical";
  error?: string;
}

// ── Helpers ─────────────────────────────────────────────────────────────

function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

const TOTAL_BOOKS = Object.keys(BOOK_YEARS).length;

// ── Constants ──────────────────────────────────────────────────────────

const CATEGORIES = [
  "ALL",
  "PERSON",
  "PLANT",
  "ANIMAL",
  "SUBSTANCE",
  "PLACE",
  "DISEASE",
  "CONCEPT",
  "OBJECT",
];

// ── Component ──────────────────────────────────────────────────────────

export default function SearchPage() {
  const [query, setQuery] = useState("");
  const [results, setResults] = useState<SearchResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [searchMode, setSearchMode] = useState<"hybrid" | "lexical" | null>(
    null
  );
  const [totalCandidates, setTotalCandidates] = useState(0);
  const [categoryFilter, setCategoryFilter] = useState("ALL");
  const [hasSearched, setHasSearched] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expandedId, setExpandedId] = useState<string | null>(null);
  const [showAllMembers, setShowAllMembers] = useState<Set<string>>(new Set());
  const [hoveredNode, setHoveredNode] = useState<string | null>(null); // "clusterId-bookId"
  const debounceRef = useRef<NodeJS.Timeout | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  // Read URL params on mount and restore state
  useEffect(() => {
    const params = new URLSearchParams(window.location.search);
    const q = params.get("q");
    const cat = params.get("category") || "ALL";
    if (cat !== "ALL") setCategoryFilter(cat);
    if (q) {
      setQuery(q);
      doSearch(q, cat);
    } else {
      inputRef.current?.focus();
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Keep URL in sync with search state
  const syncUrl = useCallback((q: string, cat: string) => {
    const url = new URL(window.location.href);
    if (q.trim().length >= 2) {
      url.searchParams.set("q", q.trim());
    } else {
      url.searchParams.delete("q");
    }
    if (cat !== "ALL") {
      url.searchParams.set("category", cat);
    } else {
      url.searchParams.delete("category");
    }
    window.history.replaceState({}, "", url.toString());
  }, []);

  const doSearch = useCallback(async (q: string, cat: string) => {
    if (q.trim().length < 2) {
      setResults([]);
      setHasSearched(false);
      setError(null);
      syncUrl(q, cat);
      return;
    }

    setLoading(true);
    setError(null);
    setExpandedId(null);
    syncUrl(q, cat);

    try {
      const params = new URLSearchParams({ q: q.trim(), limit: "30" });
      if (cat !== "ALL") params.set("category", cat);

      const res = await fetch(`/api/search?${params}`);
      const data: SearchResponse = await res.json();

      if (data.error) {
        setError(data.error);
        setResults([]);
      } else {
        setResults(data.results);
        setSearchMode(data.mode);
        setTotalCandidates(data.total_candidates);
      }
      setHasSearched(true);
    } catch {
      setError("Search failed. Make sure the search index is built.");
      setResults([]);
      setHasSearched(true);
    } finally {
      setLoading(false);
    }
  }, [syncUrl]);

  const handleInputChange = (value: string) => {
    setQuery(value);
    if (debounceRef.current) clearTimeout(debounceRef.current);
    debounceRef.current = setTimeout(
      () => doSearch(value, categoryFilter),
      300
    );
  };

  const handleCategoryChange = (cat: string) => {
    setCategoryFilter(cat);
    if (query.trim().length >= 2) {
      doSearch(query, cat);
    }
  };

  function highlightMatch(text: string, q: string): React.ReactNode {
    if (!q || q.length < 2) return text;
    const idx = text.toLowerCase().indexOf(q.toLowerCase());
    if (idx === -1) return text;
    return (
      <>
        {text.slice(0, idx)}
        <mark className="bg-[var(--accent)]/15 text-[var(--foreground)] rounded-sm px-0.5">
          {text.slice(idx, idx + q.length)}
        </mark>
        {text.slice(idx + q.length)}
      </>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Hero — title + prominent search bar */}
      <div className="py-12 md:py-20 animate-fade-up delay-0">
        <h1 className="text-4xl md:text-5xl font-bold tracking-tight leading-[1.15] mb-8">
          Search
        </h1>

        {/* Search input — full width, large */}
        <div className="relative mb-8 rounded-xl has-[:focus]:ring-2 has-[:focus]:ring-[var(--accent)] has-[:focus]:shadow-md transition-shadow">
          <svg
            className="absolute left-4 md:left-5 top-1/2 -translate-y-1/2 w-5 h-5 text-[var(--muted)]"
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={1.5}
              d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z"
            />
          </svg>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => handleInputChange(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Escape") {
                handleInputChange("");
                inputRef.current?.blur();
              }
            }}
            placeholder="Entity, plant, person, place, concept..."
            className="w-full pl-12 md:pl-14 pr-12 py-4 md:py-5 rounded-xl border border-[var(--border)] bg-[var(--card)] text-xl md:text-2xl placeholder:text-[var(--muted)]/50 focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent transition-all shadow-sm"
          />
          <div className="absolute right-4 top-1/2 -translate-y-1/2 flex items-center gap-2">
            {loading && (
              <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            )}
            {!loading && query.length > 0 && (
              <button
                onClick={() => {
                  handleInputChange("");
                  inputRef.current?.focus();
                }}
                className="p-1 rounded-full hover:bg-[var(--border)] transition-colors text-[var(--muted)] hover:text-[var(--foreground)]"
                aria-label="Clear search"
              >
                <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            )}
          </div>
        </div>

        {/* Description grid below search */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6 animate-fade-in delay-2">
          <p className="text-[var(--muted)] text-sm leading-relaxed md:col-span-2">
            Semantic and lexical search across {totalCandidates > 0 ? totalCandidates.toLocaleString() : "1,300"} concordance
            clusters. Try a modern name, historical spelling, Linnaean binomial,
            or abstract concept &mdash; &ldquo;poisonous plants&rdquo; finds
            entries about toxic herbs even without an exact name match.
          </p>
          <div className="text-[var(--muted)] text-xs leading-relaxed md:text-right">
            {searchMode && hasSearched ? (
              <span className="font-mono">{searchMode === "hybrid" ? "semantic + lexical" : "lexical only"}</span>
            ) : (
              <span className="font-mono">hybrid search</span>
            )}
          </div>
        </div>
      </div>

      {/* Cross-link to concordance */}
      <div className="text-sm text-[var(--muted)] mb-2 animate-fade-in delay-2">
        Or <Link href="/concordance" className="text-[var(--accent)] hover:underline">browse the full concordance</Link> with category and book filters.
      </div>

      {/* Category filter strip */}
      <div className="animate-fade-up delay-3">
        <div className="border-t border-[var(--border)]" />
        <div className="flex flex-wrap gap-1.5 py-5">
          {CATEGORIES.map((cat) => {
            const active = categoryFilter === cat;
            const color = cat !== "ALL" ? CAT_COLORS[cat] : null;
            return (
              <button
                key={cat}
                onClick={() => handleCategoryChange(cat)}
                className={`inline-flex items-center gap-1.5 px-2 py-1 rounded text-xs transition-colors ${
                  active
                    ? color
                      ? `${color.badge} border border-current`
                      : "bg-[var(--foreground)] text-[var(--background)]"
                    : "border border-[var(--border)] text-[var(--muted)] hover:text-[var(--foreground)] hover:border-[var(--foreground)]/30"
                }`}
              >
                {color && (
                  <span
                    className={`w-1.5 h-1.5 rounded-full ${color.dot}`}
                  />
                )}
                {cat === "ALL" ? "All" : cat.charAt(0) + cat.slice(1).toLowerCase()}
              </button>
            );
          })}
        </div>
        <div className="border-t border-[var(--border)]" />
      </div>

      {/* Example searches */}
      {!hasSearched && !loading && (
        <div className="py-12 animate-fade-up delay-5">
          <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-5">
            Example queries
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
            {[
              { q: "cinnamon", desc: "Modern name finds Canela cluster" },
              { q: "Nicotiana", desc: "Linnaean binomial finds Tabaco" },
              { q: "fever remedy", desc: "Conceptual query via semantic search" },
              { q: "Galeno", desc: "Historical spelling resolves to Galen" },
              { q: "poisonous plants", desc: "Natural language finds toxic herbs" },
              { q: "exotic spice", desc: "Abstract concept across categories" },
            ].map(({ q, desc }) => (
              <button
                key={q}
                onClick={() => {
                  setQuery(q);
                  doSearch(q, categoryFilter);
                }}
                className="bg-[var(--card)] p-5 hover:bg-[var(--border)]/30 transition-colors text-left"
              >
                <span className="font-semibold block mb-1">{q}</span>
                <span className="text-sm text-[var(--muted)]">{desc}</span>
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-6 p-4 border border-red-300 dark:border-red-800 bg-red-50 dark:bg-red-900/20 text-red-800 dark:text-red-300 text-sm">
          {error}
        </div>
      )}

      {/* Results */}
      {hasSearched && !error && (
        <div className="py-8 animate-fade-up delay-1">
          {/* Results count */}
          <div className="flex items-baseline gap-2 mb-6">
            <span className="text-3xl font-bold tracking-tight">
              {results.length}
            </span>
            <span className="text-sm text-[var(--muted)]">
              result{results.length !== 1 ? "s" : ""}
              {totalCandidates > 0 &&
                ` of ${totalCandidates.toLocaleString()}`}
            </span>
          </div>

          {results.length > 0 ? (
            <div className="divide-y divide-[var(--border)]">
              {results.map((result) => {
                const m = result.metadata;
                const cat = CAT_COLORS[m.category];
                const catHex = CAT_HEX[m.category] || "#888";
                const description = m.semantic_gloss || m.wikidata_description || "";
                const displayName = m.display_name || m.modern_name || m.canonical_name;
                const showCanonical = displayName.toLowerCase() !== m.canonical_name.toLowerCase();
                const identification = m.linnaean || "";
                const members = m.members || [];
                const rid = String(m.id);
                const isExpanded = expandedId === rid;
                const clusterSlug = m.stable_key || slugify(m.canonical_name);

                return (
                  <div key={rid}>
                    {/* Collapsed row — clickable */}
                    <button
                      onClick={() => setExpandedId(isExpanded ? null : rid)}
                      className="w-full text-left py-6 md:py-8 hover:bg-[var(--card)]/50 transition-colors cursor-pointer group"
                    >
                      {/* Header with expand chevron at right */}
                      <div className="flex items-start justify-between gap-4 mb-1.5">
                        <div className="flex items-baseline gap-3 flex-wrap min-w-0">
                          <span className="font-bold text-2xl group-hover:text-[var(--accent)] transition-colors">
                            {highlightMatch(displayName, query)}
                          </span>
                          {showCanonical && (
                            <span className="text-sm text-[var(--muted)]">
                              {highlightMatch(m.canonical_name, query)}
                            </span>
                          )}
                          {identification && (
                            <span className="text-base text-[var(--muted)] italic">
                              {highlightMatch(identification, query)}
                            </span>
                          )}
                          <span
                            className={`px-2 py-1 rounded text-xs font-semibold uppercase tracking-wide border ${
                              cat?.badge || "bg-[var(--border)]"
                            }`}
                          >
                            {m.category}
                          </span>
                        </div>
                        <svg
                          className={`w-4 h-4 shrink-0 mt-2 text-[var(--muted)] transition-transform ${isExpanded ? "rotate-180" : ""}`}
                          fill="none"
                          stroke="currentColor"
                          viewBox="0 0 24 24"
                        >
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M19 9l-7 7-7-7" />
                        </svg>
                      </div>

                      {/* Description */}
                      {description && (
                        <p className="text-sm text-[var(--muted)] mb-5 leading-relaxed max-w-3xl">
                          {description}
                        </p>
                      )}

                      {/* Timeline strip */}
                      {members.length > 0 && (() => {
                        const MAX_VISIBLE = 7;
                        const allRevealed = showAllMembers.has(rid);
                        const hasOverflow = members.length > MAX_VISIBLE;
                        const visible = allRevealed ? members : members.slice(0, MAX_VISIBLE);
                        const isMobile = typeof window !== "undefined" && window.innerWidth < 640;
                        const nodeWidth = isMobile ? 120 : 180;
                        const lineWidth = (visible.length - 1) * nodeWidth;

                        return (
                          <div className="mb-2">
                            <div className="flex items-start">
                              <div className="relative">
                                {/* Connecting line behind dots */}
                                {visible.length > 1 && (
                                  <div
                                    className="absolute h-px top-[7px]"
                                    style={{
                                      backgroundColor: catHex,
                                      opacity: 0.25,
                                      left: `${nodeWidth / 2}px`,
                                      width: `${lineWidth}px`,
                                    }}
                                  />
                                )}
                                <div className="flex items-start gap-0">
                                  {visible.map((member) => {
                                    const year = BOOK_YEARS[member.book_id] || 0;
                                    const nodeKey = `${rid}-${member.book_id}`;
                                    const isNodeHovered = hoveredNode === nodeKey;
                                    const shortName = BOOK_SHORT_NAMES[member.book_id] || "";
                                    const title = BOOK_TITLES[member.book_id] || "";

                                    return (
                                      <div
                                        key={member.book_id}
                                        className="flex flex-col items-center text-center relative w-[120px] sm:w-[180px]"
                                        onMouseEnter={() => setHoveredNode(nodeKey)}
                                        onMouseLeave={() => setHoveredNode(null)}
                                      >
                                        {/* Tooltip — floats above-right of the dot */}
                                        <div
                                          className="absolute bottom-full mb-2 left-2 px-2.5 py-1.5 rounded bg-[var(--foreground)] text-[var(--background)] text-xs leading-tight whitespace-nowrap pointer-events-none z-20"
                                          style={{
                                            opacity: isNodeHovered ? 1 : 0,
                                            transform: isNodeHovered ? "translateY(0)" : "translateY(4px)",
                                            transition: "opacity 200ms ease, transform 200ms ease",
                                          }}
                                        >
                                          <span className="font-semibold">{shortName}</span>
                                          {title && <span className="opacity-70"> — {title}</span>}
                                        </div>
                                        {/* Dot */}
                                        <div
                                          className="w-[14px] h-[14px] rounded-full shrink-0 relative z-10"
                                          style={{
                                            backgroundColor: catHex,
                                            transform: isNodeHovered ? "scale(1.35)" : "scale(1)",
                                            transition: "transform 200ms ease",
                                          }}
                                        />
                                        {/* Year */}
                                        <span className="text-xs text-[var(--muted)] mt-2 font-mono">
                                          {year}
                                        </span>
                                        {/* Local name */}
                                        <span className="text-sm font-semibold mt-0.5 leading-tight">
                                          {member.name}
                                        </span>
                                        {/* Context snippet */}
                                        <span className="text-xs text-[var(--muted)] mt-0.5 leading-snug line-clamp-2 italic px-1">
                                          {member.context || "—"}
                                        </span>
                                      </div>
                                    );
                                  })}
                                </div>
                              </div>

                              {/* "See more" button for overflow */}
                              {hasOverflow && !allRevealed && (
                                <button
                                  onClick={(e) => {
                                    e.stopPropagation();
                                    setShowAllMembers((prev) => {
                                      const next = new Set(prev);
                                      next.add(rid);
                                      return next;
                                    });
                                  }}
                                  className="ml-2 shrink-0 flex items-center gap-1 text-xs text-[var(--accent)] hover:underline self-center"
                                >
                                  +{members.length - MAX_VISIBLE} more
                                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                                  </svg>
                                </button>
                              )}
                            </div>
                          </div>
                        );
                      })()}

                      {/* Stats — quiet footer line */}
                      <div className="text-xs text-[var(--muted)]/60 mt-1 text-right">
                        {m.total_mentions.toLocaleString()} mentions &middot; {m.book_count} of {TOTAL_BOOKS} books
                      </div>
                    </button>

                    {/* Expanded: comparative table */}
                    {isExpanded && members.length > 0 && (
                      <div className="pb-8 animate-fade-in">
                        <div className="border border-[var(--border)] rounded-lg bg-[var(--card)] overflow-hidden">
                          {/* Table header */}
                          <div className="px-5 py-3 border-b border-[var(--border)] bg-[var(--background)]">
                            <span className="text-xs uppercase tracking-widest text-[var(--muted)] font-semibold">
                              Attestations across the corpus
                            </span>
                          </div>

                          {/* Table */}
                          <div className="overflow-x-auto">
                            <table className="w-full text-sm">
                              <thead>
                                <tr className="border-b border-[var(--border)] text-xs uppercase tracking-wider text-[var(--muted)]">
                                  <th className="text-left px-5 py-2.5 font-medium">Book</th>
                                  <th className="text-left px-5 py-2.5 font-medium">Name</th>
                                  <th className="text-left px-5 py-2.5 font-medium">Lang</th>
                                  <th className="text-right px-5 py-2.5 font-medium">Refs</th>
                                  <th className="text-left px-5 py-2.5 font-medium hidden md:table-cell">Description</th>
                                </tr>
                              </thead>
                              <tbody className="divide-y divide-[var(--border)]">
                                {members.map((member) => {
                                  const year = BOOK_YEARS[member.book_id] || 0;
                                  const lang = BOOK_LANGS[member.book_id] || "??";
                                  const shortName = BOOK_SHORT_NAMES[member.book_id] || member.book_id;
                                  const entityUrl = `/books/${encodeURIComponent(member.book_id)}/entity/${encodeURIComponent(member.entity_id)}`;

                                  return (
                                    <tr key={member.book_id} className="group/row hover:bg-[var(--background)] border-l-2 border-l-transparent hover:border-l-[var(--accent)] transition-colors">
                                      <td className="px-5 py-3">
                                        <Link href={entityUrl} className="block group-hover/row:text-[var(--accent)] transition-colors">
                                          <div className="font-medium text-sm">{shortName}</div>
                                          <div className="text-xs text-[var(--muted)] font-mono">{year}</div>
                                        </Link>
                                      </td>
                                      <td className="px-5 py-3">
                                        <Link href={entityUrl} className="font-medium group-hover/row:text-[var(--accent)] transition-colors">
                                          {member.name}
                                        </Link>
                                      </td>
                                      <td className="px-5 py-3">
                                        <span className="px-1.5 py-0.5 rounded text-xs font-mono bg-[var(--border)]">
                                          {lang}
                                        </span>
                                      </td>
                                      <td className="px-5 py-3 text-right tabular-nums font-mono">{member.count}</td>
                                      <td className="px-5 py-3 text-[var(--muted)] italic text-xs max-w-[320px] hidden md:table-cell">
                                        <Link href={entityUrl} className="line-clamp-2 hover:text-[var(--foreground)] transition-colors">
                                          {member.context || "—"}
                                        </Link>
                                      </td>
                                    </tr>
                                  );
                                })}
                              </tbody>
                            </table>
                          </div>

                          {/* Link to cluster page */}
                          <div className="px-5 py-3 border-t border-[var(--border)]">
                            <Link
                              href={`/concordance/${clusterSlug}`}
                              className="text-sm text-[var(--accent)] hover:underline inline-flex items-center gap-1"
                            >
                              View full cluster page
                              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
                              </svg>
                            </Link>
                          </div>
                        </div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          ) : (
            /* No results */
            <div className="py-16 text-center">
              <p className="text-lg font-medium text-[var(--muted)] mb-1">
                No results found
              </p>
              <p className="text-sm text-[var(--muted)] opacity-60 mb-4">
                Try a different spelling, a modern equivalent, or a broader term.
              </p>
              <Link href="/concordance" className="text-sm text-[var(--accent)] hover:underline">
                Browse the full concordance &rarr;
              </Link>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
