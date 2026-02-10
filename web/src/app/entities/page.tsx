"use client";

import Link from "next/link";
import { useEffect, useMemo, useState, type FocusEvent, type MouseEvent } from "react";
import { CAT_BADGE } from "@/lib/colors";
import { BOOK_SHORT_NAMES } from "@/lib/books";

interface BookFacet {
  id: string;
  title: string;
  year: number;
  language: string;
}

interface EntityResult {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  books: string[];
  names: string[];
  ground_truth: Record<string, unknown>;
  score?: number;
}

interface EntityCompactResult {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  books: string[];
}

interface EntitySearchResponse {
  query: string;
  page: number;
  limit: number;
  total: number;
  total_pages: number;
  results: EntityResult[] | EntityCompactResult[];
  facets: {
    categories: Record<string, number>;
    books: BookFacet[];
    counts: {
      entities_total: number;
      entities_concordance: number;
      entities_singleton: number;
    };
  };
}

const INITIAL_NAV = [
  "ALL",
  ..."ABCDEFGHIJKLMNOPQRSTUVWXYZ".split(""),
];

function initialLetter(name: string): string {
  const first = name
    .trim()
    .replace(/^Æ/i, "A")
    .replace(/^æ/i, "a")
    .replace(/^Œ/i, "O")
    .replace(/^œ/i, "o")
    .charAt(0);
  const normalized = first
    .normalize("NFKD")
    .replace(/[\u0300-\u036f]/g, "")
    .toUpperCase();
  return /[A-Z]/.test(normalized) ? normalized : "#";
}

export default function EntitiesPage() {
  const [query, setQuery] = useState("");
  const [category, setCategory] = useState("ALL");
  const [book, setBook] = useState("ALL");
  const [mode, setMode] = useState<"grid" | "list">("grid");
  const [selectedInitial, setSelectedInitial] = useState("ALL");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<EntitySearchResponse | null>(null);
  const [hovered, setHovered] = useState<EntityCompactResult | null>(null);
  const [hoveredInitial, setHoveredInitial] = useState<string | null>(null);
  const [tooltipPos, setTooltipPos] = useState({ x: 0, y: 0 });
  const [placeholderNames, setPlaceholderNames] = useState<string[]>([]);

  const categories = useMemo(() => {
    if (!data) return [];
    return ["ALL", ...Object.keys(data.facets.categories).sort()];
  }, [data]);

  useEffect(() => {
    const ac = new AbortController();
    const params = new URLSearchParams();

    if (mode === "grid") {
      params.set("page", String(page));
      params.set("limit", "1200");
      params.set("compact", "1");
      params.set("sort", "alpha");
    } else {
      params.set("page", String(page));
      params.set("limit", "200");
      params.set("sort", "mentions");
    }

    if (query.trim()) params.set("q", query.trim());
    if (category !== "ALL") params.set("category", category);
    if (book !== "ALL") params.set("book", book);
    if (selectedInitial !== "ALL") params.set("initial", selectedInitial);

    fetch(`/api/entities?${params.toString()}`, { signal: ac.signal })
      .then((res) => res.json())
      .then((payload: EntitySearchResponse) => {
        setData(payload);
      })
      .catch(() => {
        setData((prev) => prev);
      });

    return () => ac.abort();
  }, [query, category, book, mode, page, selectedInitial]);

  useEffect(() => {
    const ac = new AbortController();
    fetch("/api/entities?compact=1&sort=mentions&limit=500&page=1", {
      signal: ac.signal,
    })
      .then((res) => res.json())
      .then((payload: EntitySearchResponse) => {
        const names = ((payload.results || []) as EntityCompactResult[])
          .map((e) => e.canonical_name)
          .filter((name, idx, arr) => name && arr.indexOf(name) === idx)
          .slice(0, 300);

        const picked: string[] = [];
        const used = new Set<number>();
        const target = Math.min(3, names.length);
        while (picked.length < target) {
          const idx = Math.floor(Math.random() * names.length);
          if (used.has(idx)) continue;
          used.add(idx);
          picked.push(names[idx]);
        }
        setPlaceholderNames(picked);
      })
      .catch(() => {});

    return () => ac.abort();
  }, []);

  const compactResults = useMemo(
    () => ((data?.results || []) as EntityCompactResult[]),
    [data]
  );

  const fullResults = useMemo(
    () => ((data?.results || []) as EntityResult[]),
    [data]
  );

  const groupedCompactResults = useMemo(() => {
    const grouped = new Map<string, EntityCompactResult[]>();
    const order: string[] = [];
    for (const entity of compactResults) {
      const letter = initialLetter(entity.canonical_name);
      if (!grouped.has(letter)) {
        grouped.set(letter, []);
        order.push(letter);
      }
      grouped.get(letter)?.push(entity);
    }
    return order
      .filter((initial) => initial !== "#")
      .map((initial) => ({
        initial,
        items: grouped.get(initial) || [],
      }));
  }, [compactResults]);

  const hoveredBookLabel = useMemo(() => {
    if (!hovered) return "";
    const names = (hovered.books || []).map((bookId) => BOOK_SHORT_NAMES[bookId] || bookId);
    if (hovered.book_count <= 5) {
      return names.join(", ");
    }
    const shown = names.slice(0, 5);
    const remaining = Math.max(0, hovered.book_count - shown.length);
    return remaining > 0 ? `${shown.join(", ")} and ${remaining} more` : shown.join(", ");
  }, [hovered]);

  const randomPlaceholder =
    placeholderNames.length === 3
      ? `Type to filter (${placeholderNames.join(", ")})...`
      : "Type to filter...";

  const updateTooltipPosition = (clientX: number, clientY: number) => {
    if (typeof window === "undefined") return;
    const panelWidth = 320;
    const panelHeight = 170;
    const margin = 12;
    let x = clientX + 16;
    let y = clientY - 14;
    if (x + panelWidth > window.innerWidth - margin) x = clientX - panelWidth - 16;
    if (y + panelHeight > window.innerHeight - margin) y = window.innerHeight - panelHeight - margin;
    if (x < margin) x = margin;
    if (y < margin) y = margin;
    setTooltipPos({ x, y });
  };

  const handleWordHover = (
    event: MouseEvent<HTMLAnchorElement>,
    entity: EntityCompactResult
  ) => {
    setHovered(entity);
    updateTooltipPosition(event.clientX, event.clientY);
  };

  const handleWordFocus = (
    event: FocusEvent<HTMLAnchorElement>,
    entity: EntityCompactResult
  ) => {
    const rect = event.currentTarget.getBoundingClientRect();
    setHovered(entity);
    updateTooltipPosition(rect.right, rect.top + rect.height / 2);
  };

  return (
    <div className="max-w-[96rem] mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <div className="py-8">
        <h1 className="text-4xl font-bold tracking-tight mb-2">Entities</h1>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-3 mb-4">
        <input
          type="text"
          value={query}
          onChange={(e) => {
            setData(null);
            setHovered(null);
            setQuery(e.target.value);
            setPage(1);
          }}
          placeholder={randomPlaceholder}
          className="lg:col-span-2 px-4 py-2.5 rounded border border-[var(--border)] bg-[var(--card)] text-sm"
        />
        <select
          value={category}
          onChange={(e) => {
            setData(null);
            setHovered(null);
            setCategory(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2.5 rounded border border-[var(--border)] bg-[var(--card)] text-sm"
        >
          {categories.map((c) => (
            <option key={c} value={c}>
              {c === "ALL" ? "All categories" : c}
            </option>
          ))}
        </select>
        <select
          value={book}
          onChange={(e) => {
            setData(null);
            setHovered(null);
            setBook(e.target.value);
            setPage(1);
          }}
          className="px-3 py-2.5 rounded border border-[var(--border)] bg-[var(--card)] text-sm"
        >
          <option value="ALL">All books</option>
          {(data?.facets.books || []).map((b) => (
            <option key={b.id} value={b.id}>
              {BOOK_SHORT_NAMES[b.id] || b.title}
            </option>
          ))}
        </select>
        <div className="flex gap-1.5 items-center border border-[var(--border)] rounded bg-[var(--card)] p-1">
          <button
            onClick={() => {
              setData(null);
              setHovered(null);
              setMode("grid");
              setSelectedInitial("ALL");
              setPage(1);
            }}
            className={`flex-1 text-xs px-2.5 py-1.5 rounded ${
              mode === "grid"
                ? "bg-[var(--foreground)] text-[var(--background)]"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            Word Grid
          </button>
          <button
            onClick={() => {
              setData(null);
              setHovered(null);
              setMode("list");
              setSelectedInitial("ALL");
              setPage(1);
            }}
            className={`flex-1 text-xs px-2.5 py-1.5 rounded ${
              mode === "list"
                ? "bg-[var(--foreground)] text-[var(--background)]"
                : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
          >
            List
          </button>
        </div>
      </div>

      <div className="text-xs uppercase tracking-widest text-[var(--muted)] mb-3">
        {!data ? "Loading..." : `${data.total.toLocaleString()} entities`}
      </div>

      {!data && (
        <div className="text-sm text-[var(--muted)] py-8">Loading entities...</div>
      )}

      {data && data.results.length === 0 && (
        <div className="text-sm text-[var(--muted)] py-8">No matching entities.</div>
      )}

      {data && mode === "grid" && compactResults.length > 0 && (
        <>
          <div className="grid grid-cols-1 lg:grid-cols-[6.5rem_minmax(0,1fr)] gap-x-10">
            <aside className="hidden lg:block">
              <nav className="sticky top-24 h-[calc(100vh-8rem)] pr-4 border-r border-[var(--border)] flex flex-col items-center gap-0.5 text-[11px] uppercase tracking-[0.08em]">
                {INITIAL_NAV.map((letter) => (
                  <button
                    key={`jump-${letter}`}
                    onClick={() => {
                      setData(null);
                      setHovered(null);
                      setSelectedInitial(letter);
                      setPage(1);
                    }}
                    className={`w-full text-center py-0.5 transition-colors ${
                      selectedInitial === letter
                        ? "text-[var(--foreground)] font-semibold"
                        : "text-[var(--muted)] hover:text-[var(--foreground)]"
                    }`}
                  >
                    {letter}
                  </button>
                ))}
              </nav>
            </aside>
            <div className="space-y-10 min-w-0 pr-2 lg:pr-6">
              {groupedCompactResults.map((group) => (
                <section key={group.initial}>
                  <h2 className="text-6xl sm:text-7xl font-bold tracking-tight leading-none mb-5">
                    <span className="sr-only">{group.initial}</span>
                    <span
                      className="relative inline-block cursor-default align-top"
                      aria-hidden="true"
                      onMouseEnter={() => setHoveredInitial(group.initial)}
                      onMouseLeave={() => setHoveredInitial((current) =>
                        current === group.initial ? null : current
                      )}
                    >
                      <span
                        className="block"
                        style={{
                          fontFamily: "'Space Grotesk', sans-serif",
                          opacity: hoveredInitial === group.initial ? 0 : 1,
                          transition: "opacity 500ms ease",
                        }}
                      >
                        {group.initial}
                      </span>
                      <span
                        className="absolute inset-0 block font-normal"
                        style={{
                          fontFamily: "'UnifrakturMaguntia', cursive",
                          opacity: hoveredInitial === group.initial ? 1 : 0,
                          transition: "opacity 500ms ease",
                        }}
                      >
                        {group.initial}
                      </span>
                    </span>
                  </h2>
                  <div className="columns-2 sm:columns-3 md:columns-3 lg:columns-4 xl:columns-5 [column-gap:1.4rem]">
                    {group.items.map((e) => {
                      const isHovered = hovered?.id === e.id;
                      return (
                        <Link
                          key={e.id}
                          href={`/entity/${encodeURIComponent(e.slug)}`}
                          onMouseEnter={(event) => handleWordHover(event, e)}
                          onMouseMove={(event) =>
                            updateTooltipPosition(event.clientX, event.clientY)
                          }
                          onFocus={(event) => handleWordFocus(event, e)}
                          onMouseLeave={() => setHovered(null)}
                          onBlur={() => setHovered(null)}
                          className={`block break-inside-avoid break-words mb-2 text-[17px] leading-[1.15] tracking-tight transition-all duration-300 ease-out ${
                            isHovered
                              ? "font-bold text-[var(--foreground)]"
                              : "font-medium text-[var(--foreground)]/72 hover:text-[var(--foreground)]"
                          }`}
                        >
                          {e.canonical_name}
                        </Link>
                      );
                    })}
                  </div>
                </section>
              ))}
            </div>
          </div>
          <div
            className={`fixed z-40 w-[min(20rem,calc(100vw-2rem))] rounded border border-[var(--border)] bg-[var(--card)] p-3 text-xs shadow-lg pointer-events-none transition-all duration-200 ${
              hovered ? "opacity-100 translate-y-0" : "opacity-0 translate-y-1"
            }`}
            style={{ left: tooltipPos.x, top: tooltipPos.y }}
          >
            {hovered && (
              <div className="space-y-2">
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] mb-1">
                    Entity
                  </div>
                  <div className="font-medium text-sm leading-tight">{hovered.canonical_name}</div>
                </div>
                <div className="flex items-center gap-2">
                  <span
                    className={`px-1.5 py-0.5 rounded border text-[10px] ${
                      CAT_BADGE[hovered.category] || "bg-[var(--border)]"
                    }`}
                  >
                    {hovered.category}
                  </span>
                  <span className="text-[var(--muted)]">
                    {hovered.is_concordance ? "Cross-book" : "Single-book"}
                  </span>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] mb-1">
                    Books
                  </div>
                  <div className="leading-snug">{hoveredBookLabel || `${hovered.book_count} books`}</div>
                </div>
                <div>
                  <div className="text-[10px] uppercase tracking-widest text-[var(--muted)] mb-1">
                    Mentions
                  </div>
                  <div className="font-mono">{hovered.total_mentions.toLocaleString()}</div>
                </div>
              </div>
            )}
          </div>
        </>
      )}

      {data && mode === "list" && fullResults.length > 0 && (
        <div className="border border-[var(--border)] rounded overflow-hidden">
          <div className="hidden md:grid grid-cols-[2fr_3.5rem_5rem_5rem_1fr_6rem] gap-x-3 px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] border-b border-[var(--border)] bg-[var(--card)]">
            <span>Name</span>
            <span>Cat</span>
            <span className="text-right">Books</span>
            <span className="text-right">Ment</span>
            <span>Top books</span>
            <span>Type</span>
          </div>
          <div className="divide-y divide-[var(--border)]">
            {fullResults.map((e) => (
              <Link
                key={e.id}
                href={`/entity/${encodeURIComponent(e.slug)}`}
                className="grid grid-cols-[1fr_auto] md:grid-cols-[2fr_3.5rem_5rem_5rem_1fr_6rem] gap-x-3 px-3 py-2.5 text-sm hover:bg-[var(--card)]"
              >
                <span className="truncate">{e.canonical_name}</span>
                <span className={`md:text-[10px] text-[10px] px-1.5 py-0.5 rounded border self-start ${CAT_BADGE[e.category] || "bg-[var(--border)]"}`}>
                  {e.category}
                </span>
                <span className="hidden md:block text-right font-mono text-xs">{e.book_count}</span>
                <span className="hidden md:block text-right font-mono text-xs">{e.total_mentions.toLocaleString()}</span>
                <span className="hidden md:block text-xs text-[var(--muted)] truncate">
                  {e.books.slice(0, 4).map((b) => BOOK_SHORT_NAMES[b] || b).join(" ")}
                </span>
                <span className="hidden md:block text-xs text-[var(--muted)]">
                  {e.is_concordance ? "concord." : "single"}
                </span>
              </Link>
            ))}
          </div>
        </div>
      )}

      {data && data.total_pages > 1 && (
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={() => {
              setData(null);
              setHovered(null);
              setPage((p) => Math.max(1, p - 1));
            }}
            disabled={page <= 1}
            className="px-4 py-2 rounded border border-[var(--border)] text-sm disabled:opacity-40"
          >
            Previous
          </button>
          <span className="text-sm text-[var(--muted)]">
            Page {page} of {data.total_pages}
          </span>
          <button
            onClick={() => {
              setData(null);
              setHovered(null);
              setPage((p) => Math.min(data.total_pages, p + 1));
            }}
            disabled={page >= data.total_pages}
            className="px-4 py-2 rounded border border-[var(--border)] text-sm disabled:opacity-40"
          >
            Next
          </button>
        </div>
      )}
    </div>
  );
}
