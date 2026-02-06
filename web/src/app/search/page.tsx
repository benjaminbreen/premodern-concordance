"use client";

import Link from "next/link";
import { useState, useCallback, useRef, useEffect } from "react";

// ── Types ──────────────────────────────────────────────────────────────

interface ResultMetadata {
  id: string;
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

// ── Constants ──────────────────────────────────────────────────────────

const CAT_COLORS: Record<string, { badge: string; dot: string }> = {
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
  PLACE: {
    badge: "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
    dot: "bg-green-500",
  },
  DISEASE: {
    badge: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
    dot: "bg-red-500",
  },
  CONCEPT: {
    badge: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
    dot: "bg-amber-500",
  },
  OBJECT: {
    badge: "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30",
    dot: "bg-slate-500",
  },
};

const BOOK_SHORT_NAMES: Record<string, string> = {
  "semedo-polyanthea-1741": "Semedo",
  "english_physician_1652": "Culpeper",
  "coloquios_da_orta_1563": "Da Orta",
  "historia_medicinal_monardes_1574": "Monardes",
  "relation_historique_humboldt_vol3_1825": "Humboldt",
};

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
        <div className="relative mb-8">
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
            placeholder="Entity, plant, person, place, concept..."
            className="w-full pl-12 md:pl-14 pr-12 py-4 md:py-5 rounded-xl border border-[var(--border)] bg-[var(--card)] text-xl md:text-2xl placeholder:text-[var(--muted)]/50 focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent transition-all shadow-sm"
          />
          {loading && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <div className="w-5 h-5 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
            </div>
          )}
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

      {/* Example searches — gap-px grid like home page clusters */}
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
            <>
              {/* Top results — full-width rows */}
              <div className="border border-[var(--border)] rounded-lg overflow-hidden mb-8">
                {results.slice(0, 3).map((result, idx) => {
                  const m = result.metadata;
                  const cat = CAT_COLORS[m.category];
                  const pct = Math.round(result.score * 100);
                  const description =
                    m.semantic_gloss || m.wikidata_description || "";

                  const q = query.toLowerCase();
                  const matchedVariants =
                    query.length >= 2
                      ? m.names
                          .filter(
                            (n) =>
                              n.toLowerCase().includes(q) &&
                              n.toLowerCase() !== m.canonical_name.toLowerCase() &&
                              n.toLowerCase() !== m.modern_name.toLowerCase()
                          )
                          .slice(0, 3)
                      : [];

                  // Book pills for top results
                  const bookPills = m.books.slice(0, 5);

                  return (
                    <Link
                      key={m.id}
                      href={`/concordance?highlight=${encodeURIComponent(m.canonical_name)}&from_search=${encodeURIComponent(query)}`}
                      className={`block bg-[var(--card)] hover:bg-[var(--border)]/30 transition-colors group relative ${
                        idx > 0 ? "border-t border-[var(--border)]" : ""
                      }`}
                    >
                      {/* Score bar — thin line at top */}
                      <div className="absolute top-0 left-0 right-0 h-[2px] bg-[var(--border)]">
                        <div
                          className="h-full bg-[var(--accent)] transition-all"
                          style={{ width: `${pct}%` }}
                        />
                      </div>

                      <div className="grid grid-cols-1 md:grid-cols-[1fr_2fr_auto] gap-4 md:gap-8 p-5 md:px-6 md:py-5 items-start">
                        {/* Left: name + identification */}
                        <div className="min-w-0">
                          <div className="flex items-center gap-2 mb-1">
                            {m.portrait_url ? (
                              // eslint-disable-next-line @next/next/no-img-element
                              <img
                                src={m.portrait_url}
                                alt=""
                                className="w-8 h-8 rounded-full object-cover shrink-0 border border-[var(--border)] bg-[var(--border)]"
                              />
                            ) : cat ? (
                              <span
                                className={`w-2.5 h-2.5 rounded-full shrink-0 ${cat.dot}`}
                              />
                            ) : null}
                            <span className="font-semibold text-lg group-hover:text-[var(--accent)] transition-colors truncate">
                              {highlightMatch(m.canonical_name, query)}
                            </span>
                          </div>
                          {(m.modern_name || m.linnaean) && (
                            <div className="text-sm text-[var(--muted)] truncate">
                              {m.modern_name &&
                                m.modern_name.toLowerCase() !==
                                  m.canonical_name.toLowerCase() && (
                                  <span>
                                    {highlightMatch(m.modern_name, query)}
                                  </span>
                                )}
                              {m.linnaean && (
                                <span className="italic ml-1">
                                  {highlightMatch(m.linnaean, query)}
                                </span>
                              )}
                            </div>
                          )}
                        </div>

                        {/* Center: description + metadata */}
                        <div className="min-w-0">
                          {description && (
                            <p className="text-sm text-[var(--muted)] mb-2 line-clamp-2 leading-relaxed">
                              {description}
                            </p>
                          )}
                          <div className="flex items-center flex-wrap gap-2 text-[10px] text-[var(--muted)]">
                            <span
                              className={`px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide ${
                                cat?.badge || "bg-[var(--border)]"
                              }`}
                            >
                              {m.category}
                            </span>
                            <span className="font-mono">
                              {m.book_count}b &middot; {m.total_mentions.toLocaleString()}&times;
                            </span>
                            {bookPills.map((b) => (
                              <span
                                key={b}
                                className="px-1.5 py-0.5 rounded bg-[var(--border)]"
                              >
                                {BOOK_SHORT_NAMES[b] || b}
                              </span>
                            ))}
                            {matchedVariants.length > 0 && (
                              <>
                                <span className="opacity-40">|</span>
                                {matchedVariants.map((v) => (
                                  <span
                                    key={v}
                                    className="px-1.5 py-0.5 rounded bg-[var(--background)]"
                                  >
                                    {highlightMatch(v, query)}
                                  </span>
                                ))}
                              </>
                            )}
                          </div>
                        </div>

                        {/* Right: score */}
                        <div className="hidden md:flex items-center gap-3 shrink-0 self-center">
                          <span className="text-2xl font-bold tracking-tight tabular-nums">
                            {pct}
                          </span>
                          <span className="text-xs text-[var(--muted)]">%</span>
                        </div>
                      </div>
                    </Link>
                  );
                })}
              </div>

              {/* More results */}
              {results.length > 3 && (
                <>
                  <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-5">
                    More results
                  </h2>
                  <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
                    {results.slice(3).map((result) => {
                      const m = result.metadata;
                      const cat = CAT_COLORS[m.category];
                      const pct = Math.round(result.score * 100);
                      const description =
                        m.semantic_gloss || m.wikidata_description || "";

                      const q = query.toLowerCase();
                      const matchedVariants =
                        query.length >= 2
                          ? m.names
                              .filter(
                                (n) =>
                                  n.toLowerCase().includes(q) &&
                                  n.toLowerCase() !== m.canonical_name.toLowerCase() &&
                                  n.toLowerCase() !== m.modern_name.toLowerCase()
                              )
                              .slice(0, 2)
                          : [];

                      return (
                        <Link
                          key={m.id}
                          href={`/concordance?highlight=${encodeURIComponent(m.canonical_name)}&from_search=${encodeURIComponent(query)}`}
                          className="bg-[var(--card)] p-5 hover:bg-[var(--border)]/30 transition-colors block group relative"
                        >
                          <div className="absolute top-0 left-0 right-0 h-[2px] bg-[var(--border)]">
                            <div
                              className="h-full bg-[var(--accent)] transition-all"
                              style={{ width: `${pct}%` }}
                            />
                          </div>

                          <div className="flex items-center gap-2 mb-1.5">
                            {cat && (
                              <span
                                className={`w-2 h-2 rounded-full shrink-0 ${cat.dot}`}
                              />
                            )}
                            <span className="font-semibold group-hover:text-[var(--accent)] transition-colors truncate">
                              {highlightMatch(m.canonical_name, query)}
                            </span>
                          </div>

                          {(m.modern_name || m.linnaean) && (
                            <div className="text-sm text-[var(--muted)] mb-1 truncate">
                              {m.modern_name &&
                                m.modern_name.toLowerCase() !==
                                  m.canonical_name.toLowerCase() && (
                                  <span>
                                    {highlightMatch(m.modern_name, query)}
                                  </span>
                                )}
                              {m.linnaean && (
                                <span className="italic ml-1">
                                  {highlightMatch(m.linnaean, query)}
                                </span>
                              )}
                            </div>
                          )}

                          {description && (
                            <p className="text-xs text-[var(--muted)] mb-3 line-clamp-2 leading-relaxed">
                              {description}
                            </p>
                          )}

                          <div className="flex items-center gap-2 text-[10px] text-[var(--muted)]">
                            <span
                              className={`px-1.5 py-0.5 rounded font-semibold uppercase tracking-wide ${
                                cat?.badge || "bg-[var(--border)]"
                              }`}
                            >
                              {m.category}
                            </span>
                            <span className="font-mono">
                              {m.book_count}b &middot; {m.total_mentions.toLocaleString()}&times;
                            </span>
                            <span className="ml-auto font-mono opacity-60">
                              {pct}%
                            </span>
                          </div>

                          {matchedVariants.length > 0 && (
                            <div className="mt-2 flex flex-wrap gap-1">
                              {matchedVariants.map((v) => (
                                <span
                                  key={v}
                                  className="text-[10px] px-1.5 py-0.5 rounded bg-[var(--background)] text-[var(--muted)]"
                                >
                                  {highlightMatch(v, query)}
                                </span>
                              ))}
                            </div>
                          )}
                        </Link>
                      );
                    })}
                  </div>
                </>
              )}
            </>
          ) : (
            /* No results */
            <div className="py-16 text-center">
              <p className="text-lg font-medium text-[var(--muted)] mb-1">
                No results found
              </p>
              <p className="text-sm text-[var(--muted)] opacity-60">
                Try a different spelling, a modern equivalent, or a broader
                term.
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
