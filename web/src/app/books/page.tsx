"use client";

import Link from "next/link";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CAT_HEX as CATEGORY_COLORS, CATEGORY_ORDER } from "@/lib/colors";
import { BOOK_COVERS, BOOK_TEXTS } from "@/lib/books";

interface BookData {
  book: {
    id: string;
    title: string;
    author: string;
    year: number;
    language: string;
    description: string;
  };
  stats: {
    total_entities: number;
    by_category: Record<string, number>;
  };
}

type SortKey = "title" | "author" | "year" | "language" | "entities";
type SortDir = "asc" | "desc";
type ViewMode = "cards" | "list" | "rings";


function CategoryTooltip({ byCategory, total, anchorRef }: { byCategory: Record<string, number>; total: number; anchorRef: React.RefObject<HTMLElement | null> }) {
  const sorted = CATEGORY_ORDER
    .filter((c) => byCategory[c] && byCategory[c] > 0)
    .map((c) => ({ category: c, count: byCategory[c] }));

  Object.entries(byCategory).forEach(([c, count]) => {
    if (count > 0 && !CATEGORY_ORDER.includes(c)) {
      sorted.push({ category: c, count });
    }
  });

  sorted.sort((a, b) => b.count - a.count);

  const rect = anchorRef.current?.getBoundingClientRect();
  if (!rect) return null;

  const tooltipWidth = 224; // w-56 = 14rem = 224px
  let left = rect.left + rect.width / 2 - tooltipWidth / 2;
  // Clamp to viewport
  left = Math.max(8, Math.min(left, window.innerWidth - tooltipWidth - 8));

  return createPortal(
    <div
      className="fixed z-[9999] w-56 p-3 rounded-lg border border-[var(--border)] bg-[var(--card)] shadow-xl text-xs pointer-events-none"
      style={{ top: rect.top - 8, left, transform: "translateY(-100%)" }}
    >
      {/* Stacked bar */}
      <div className="flex h-2 rounded-full overflow-hidden mb-2.5">
        {sorted.map(({ category, count }) => (
          <div
            key={category}
            style={{
              width: `${(count / total) * 100}%`,
              backgroundColor: CATEGORY_COLORS[category] || "#888",
            }}
          />
        ))}
      </div>
      {/* Labels */}
      <div className="space-y-1">
        {sorted.slice(0, 6).map(({ category, count }) => (
          <div key={category} className="flex items-center justify-between gap-2">
            <span className="flex items-center gap-1.5 text-[var(--muted)]">
              <span
                className="inline-block w-2 h-2 rounded-sm shrink-0"
                style={{ backgroundColor: CATEGORY_COLORS[category] || "#888" }}
              />
              {category.charAt(0) + category.slice(1).toLowerCase()}
            </span>
            <span className="font-mono text-[var(--foreground)]">{count.toLocaleString()}</span>
          </div>
        ))}
        {sorted.length > 6 && (
          <div className="text-[var(--muted)] opacity-60 text-center pt-0.5">
            +{sorted.length - 6} more
          </div>
        )}
      </div>
      {/* Arrow */}
      <div
        className="fixed w-0 h-0 border-l-[6px] border-l-transparent border-r-[6px] border-r-transparent border-t-[6px] border-t-[var(--border)]"
        style={{ top: rect.top - 8, left: rect.left + rect.width / 2 - 6 }}
      />
    </div>,
    document.body
  );
}

function EntityCountWithTooltip({ bookId, byCategory, total, label }: { bookId: string; byCategory: Record<string, number>; total: number; label?: string }) {
  const [hovered, setHovered] = useState(false);
  const ref = useRef<HTMLSpanElement>(null);
  return (
    <span
      ref={ref}
      className="relative font-mono cursor-default"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {total.toLocaleString()}{label ? ` ${label}` : ""}
      {hovered && (
        <CategoryTooltip
          byCategory={byCategory}
          total={total}
          anchorRef={ref}
        />
      )}
    </span>
  );
}

// Muted, archival tones — not app-bright, more like ink or dye colors
const LANG_COLORS: Record<string, string> = {
  Portuguese: "#9a6b4c",  // warm sienna
  English:    "#6b7f99",  // cool slate
  Spanish:    "#9a8a3c",  // dry ochre
  French:     "#7b6b99",  // muted lavender
  Italian:    "#8b6b6b",  // dusty rose
};


function getGlobalCategoryOrder(books: BookData[]): string[] {
  const sums: Record<string, number> = {};
  for (const b of books) {
    for (const [cat, count] of Object.entries(b.stats.by_category)) {
      sums[cat] = (sums[cat] || 0) + count;
    }
  }
  return Object.entries(sums)
    .sort((a, b) => b[1] - a[1])
    .map(([cat]) => cat);
}

function getCategorySorted(byCategory: Record<string, number>) {
  const sorted = CATEGORY_ORDER
    .filter((c) => byCategory[c] && byCategory[c] > 0)
    .map((c) => ({ category: c, count: byCategory[c] }));
  Object.entries(byCategory).forEach(([c, count]) => {
    if (count > 0 && !CATEGORY_ORDER.includes(c)) sorted.push({ category: c, count });
  });
  sorted.sort((a, b) => b.count - a.count);
  return sorted;
}

function CategoryRing({ byCategory, total, size = 120, order }: { byCategory: Record<string, number>; total: number; size?: number; order?: string[] }) {
  const r = size / 2;
  const strokeWidth = size * 0.1;
  const innerR = r - strokeWidth / 2 - 1;
  const circumference = 2 * Math.PI * innerR;
  const catOrder = order || CATEGORY_ORDER;

  let offset = 0;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {catOrder.map((category) => {
        const count = byCategory[category] || 0;
        if (count === 0) return null;
        const pct = count / total;
        const dash = pct * circumference;
        const gap = circumference - dash;
        const currentOffset = offset;
        offset += dash;
        return (
          <circle
            key={category}
            cx={r}
            cy={r}
            r={innerR}
            fill="none"
            stroke={CATEGORY_COLORS[category] || "#888"}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={-currentOffset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${r} ${r})`}
          />
        );
      })}
    </svg>
  );
}

function RingWithLabels({ byCategory, total, size, order, hovered }: { byCategory: Record<string, number>; total: number; size: number; order: string[]; hovered: boolean }) {
  const [hoveredSegment, setHoveredSegment] = useState<string | null>(null);
  const r = size / 2;
  const strokeWidth = size * 0.1;
  const innerR = r - strokeWidth / 2 - 1;
  const labelR = r + 26;

  // Build segments in fixed order
  const segments: { category: string; count: number; startAngle: number; endAngle: number }[] = [];
  let angleSoFar = -90; // start at 12 o'clock
  for (const cat of order) {
    const count = byCategory[cat] || 0;
    if (count === 0) continue;
    const sweep = (count / total) * 360;
    segments.push({ category: cat, count, startAngle: angleSoFar, endAngle: angleSoFar + sweep });
    angleSoFar += sweep;
  }

  // Labels for segments >4%, plus any directly-hovered small segment
  const largeSegments = segments.filter(s => s.count / total > 0.04);
  const pad = 44;
  return (
    <div className="relative" style={{ width: size + pad * 2, height: size + pad * 2 }}>
      {/* Ring with glow effect */}
      <div
        className="absolute"
        style={{
          left: pad, top: pad,
          filter: hovered
            ? 'saturate(1.45) brightness(1.1) drop-shadow(0 0 10px rgba(180,160,220,0.35)) drop-shadow(0 0 4px rgba(120,100,200,0.2))'
            : 'saturate(1) brightness(1) drop-shadow(0 0 0px rgba(180,160,220,0))',
          transform: hovered ? 'scale(1.04)' : 'scale(1)',
          transition: 'filter 600ms ease, transform 500ms ease',
        }}
      >
        <CategoryRing byCategory={byCategory} total={total} size={size} order={order} />
      </div>
      {/* Invisible arc hit targets for segment hover */}
      <svg
        className="absolute"
        style={{ left: pad, top: pad }}
        width={size}
        height={size}
        viewBox={`0 0 ${size} ${size}`}
      >
        {segments.map((seg) => {
          const startRad = (seg.startAngle * Math.PI) / 180;
          const endRad = (seg.endAngle * Math.PI) / 180;
          const x1 = r + innerR * Math.cos(startRad);
          const y1 = r + innerR * Math.sin(startRad);
          const x2 = r + innerR * Math.cos(endRad);
          const y2 = r + innerR * Math.sin(endRad);
          const largeArc = seg.endAngle - seg.startAngle > 180 ? 1 : 0;
          return (
            <path
              key={seg.category}
              d={`M ${x1} ${y1} A ${innerR} ${innerR} 0 ${largeArc} 1 ${x2} ${y2}`}
              fill="none"
              stroke="transparent"
              strokeWidth={strokeWidth + 6}
              pointerEvents="stroke"
              onMouseEnter={() => setHoveredSegment(seg.category)}
              onMouseLeave={() => setHoveredSegment(null)}
              style={{ cursor: 'pointer' }}
            />
          );
        })}
      </svg>
      {/* Clock labels — staggered fade in/out, highlight on segment hover */}
      {segments.map((seg) => {
        const isLarge = seg.count / total > 0.04;
        const isActive = hoveredSegment === seg.category;
        const shouldShow = hovered && (isLarge || isActive);
        const staggerIdx = largeSegments.indexOf(seg);
        const midAngle = ((seg.startAngle + seg.endAngle) / 2) * (Math.PI / 180);
        const cx = (size / 2) + pad;
        const cy = (size / 2) + pad;
        const x = cx + labelR * Math.cos(midAngle);
        const y = cy + labelR * Math.sin(midAngle);
        const label = seg.category.charAt(0) + seg.category.slice(1).toLowerCase();
        return (
          <span
            key={seg.category}
            className={`absolute flex flex-col items-center text-[9px] tracking-wide pointer-events-none ${
              isActive
                ? 'font-bold text-[var(--foreground)]'
                : 'font-medium text-[var(--muted)]'
            }`}
            style={{
              left: x,
              top: y,
              transform: `translate(-50%, -50%) ${shouldShow ? 'translateY(0)' : 'translateY(2px)'}`,
              opacity: shouldShow ? 1 : 0,
              transition: 'opacity 350ms ease, transform 350ms ease, color 200ms ease',
              transitionDelay: (hovered && staggerIdx >= 0) ? `${380 + staggerIdx * 100}ms` : '0ms',
            }}
          >
            <span className="whitespace-nowrap">{label}</span>
            {isActive && (
              <span className="text-[8px] font-mono font-normal text-[var(--muted)] leading-tight">{seg.count}</span>
            )}
          </span>
        );
      })}
    </div>
  );
}

function RingCard({ bookData, globalCatOrder }: { bookData: BookData; globalCatOrder: string[] }) {
  const [hovered, setHovered] = useState(false);

  return (
    <Link
      href={`/books/${bookData.book.id}`}
      className="flex flex-col items-center py-3 px-3 rounded-lg"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      <RingWithLabels
        byCategory={bookData.stats.by_category}
        total={bookData.stats.total_entities}
        size={130}
        order={globalCatOrder}
        hovered={hovered}
      />
      <div className="text-center mt-1 max-w-[200px]">
        <p
          className="text-[14px] font-bold leading-snug text-[var(--foreground)] line-clamp-2"
          style={{
            opacity: hovered ? 1 : 0,
            transform: hovered ? 'translateY(0)' : 'translateY(4px)',
            transition: 'opacity 400ms ease, transform 400ms ease',
            transitionDelay: hovered ? '60ms' : '0ms',
          }}
        >
          {bookData.book.title}
        </p>
        <p
          className="text-[12px] text-[var(--muted)] mt-0.5"
          style={{
            opacity: hovered ? 1 : 0,
            transform: hovered ? 'translateY(0)' : 'translateY(4px)',
            transition: 'opacity 400ms ease, transform 400ms ease',
            transitionDelay: hovered ? '160ms' : '0ms',
          }}
        >
          {bookData.book.author} <span className="font-mono">{bookData.book.year}</span>
        </p>
      </div>
    </Link>
  );
}

function LangDot({ language }: { language: string }) {
  const color = LANG_COLORS[language] || "var(--muted)";
  return (
    <span
      className="inline-block w-1.5 h-1.5 rounded-full shrink-0"
      style={{ backgroundColor: color }}
    />
  );
}

function CoverModal({ src, title, onClose }: { src: string; title: string; onClose: () => void }) {
  useEffect(() => {
    const handler = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [onClose]);

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-sm"
      onClick={onClose}
    >
      <div className="relative max-w-lg max-h-[85vh] mx-4" onClick={(e) => e.stopPropagation()}>
        <img src={src} alt={title} className="max-h-[80vh] w-auto rounded-lg shadow-2xl border border-white/10" />
        <p className="text-center text-white/70 text-sm mt-3">{title}</p>
        <button
          onClick={onClose}
          className="absolute -top-3 -right-3 w-8 h-8 rounded-full bg-black/80 text-white/80 hover:text-white flex items-center justify-center text-lg"
        >
          &times;
        </button>
      </div>
    </div>
  );
}

export default function BooksPage() {
  const [books, setBooks] = useState<BookData[]>([]);
  const [loading, setLoading] = useState(true);
  const [sortBy, setSortBy] = useState<SortKey>("year");
  const [sortDir, setSortDir] = useState<SortDir>("asc");
  const [viewMode, setViewMode] = useState<ViewMode>("cards");
  const [modalImage, setModalImage] = useState<{ src: string; title: string } | null>(null);

  useEffect(() => {
    const saved = localStorage.getItem("books-view-mode");
    if (saved === "cards" || saved === "list" || saved === "rings") setViewMode(saved);
  }, []);

  useEffect(() => {
    localStorage.setItem("books-view-mode", viewMode);
  }, [viewMode]);

  useEffect(() => {
    const bookFiles = [
      "/data/semedo_entities.json",
      "/data/culpeper_entities.json",
      "/data/orta_entities.json",
      "/data/monardes_entities.json",
      "/data/humboldt_entities.json",
      "/data/ricettario_entities.json",
      "/data/james_psychology_entities.json",
      "/data/darwin_origin_entities.json",
    ];
    Promise.all(
      bookFiles.map((f) => fetch(f).then((res) => res.json()).catch(() => null))
    ).then((results) => {
      setBooks(results.filter(Boolean));
      setLoading(false);
    });
  }, []);

  function toggleSort(key: SortKey) {
    if (sortBy === key) {
      setSortDir(d => d === "asc" ? "desc" : "asc");
    } else {
      setSortBy(key);
      setSortDir(key === "entities" ? "desc" : "asc");
    }
  }

  const sorted = [...books].sort((a, b) => {
    let cmp = 0;
    if (sortBy === "title") cmp = a.book.title.localeCompare(b.book.title);
    else if (sortBy === "author") cmp = a.book.author.localeCompare(b.book.author);
    else if (sortBy === "year") cmp = a.book.year - b.book.year;
    else if (sortBy === "language") cmp = a.book.language.localeCompare(b.book.language);
    else cmp = a.stats.total_entities - b.stats.total_entities;
    return sortDir === "asc" ? cmp : -cmp;
  });

  const totalEntities = books.reduce((sum, b) => sum + b.stats.total_entities, 0);
  const globalCatOrder = useMemo(() => getGlobalCategoryOrder(books), [books]);

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-[var(--border)] rounded w-1/4"></div>
          <div className="h-4 bg-[var(--border)] rounded w-1/2"></div>
        </div>
      </div>
    );
  }

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Header */}
      <div className="mb-8">
        <h1 className="text-3xl font-bold mb-2">Corpus</h1>
        <p className="text-[var(--muted)] max-w-2xl">
          {books.length} texts &middot; <span className="font-mono text-sm">{totalEntities.toLocaleString()}</span> extracted entities across {[...new Set(books.map(b => b.book.language))].length} languages.
        </p>
      </div>

      {/* Controls */}
      <div className="flex items-center justify-between mb-6 text-sm">
        <div className={`flex items-center gap-1 text-[var(--muted)] ${viewMode === "rings" ? "invisible" : ""}`}>
          <span className="mr-1">Sort</span>
          {(["year", "title", "entities"] as SortKey[]).map((key) => (
            <button
              key={key}
              onClick={() => toggleSort(key)}
              className={`px-2 py-0.5 rounded transition-colors inline-flex items-center gap-1 ${
                sortBy === key
                  ? "text-[var(--foreground)] bg-[var(--border)]"
                  : "hover:text-[var(--foreground)]"
              }`}
            >
              {key === "entities" ? "count" : key}
              {sortBy === key && (
                <svg width="10" height="10" viewBox="0 0 10 10" fill="currentColor" className={sortDir === "desc" ? "rotate-180" : ""}>
                  <path d="M5 3L8 7H2L5 3Z" />
                </svg>
              )}
            </button>
          ))}
        </div>
        <div className="flex items-center gap-0.5 border border-[var(--border)] rounded-md p-0.5">
          <button
            onClick={() => setViewMode("list")}
            className={`p-1 rounded transition-colors ${
              viewMode === "list" ? "bg-[var(--border)] text-[var(--foreground)]" : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
            aria-label="List view"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <line x1="3" y1="4" x2="13" y2="4" />
              <line x1="3" y1="8" x2="13" y2="8" />
              <line x1="3" y1="12" x2="13" y2="12" />
            </svg>
          </button>
          <button
            onClick={() => setViewMode("cards")}
            className={`p-1 rounded transition-colors ${
              viewMode === "cards" ? "bg-[var(--border)] text-[var(--foreground)]" : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
            aria-label="Card view"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <rect x="2" y="2" width="5" height="5" rx="1" />
              <rect x="9" y="2" width="5" height="5" rx="1" />
              <rect x="2" y="9" width="5" height="5" rx="1" />
              <rect x="9" y="9" width="5" height="5" rx="1" />
            </svg>
          </button>
          <button
            onClick={() => setViewMode("rings")}
            className={`p-1 rounded transition-colors ${
              viewMode === "rings" ? "bg-[var(--border)] text-[var(--foreground)]" : "text-[var(--muted)] hover:text-[var(--foreground)]"
            }`}
            aria-label="Rings view"
          >
            <svg width="16" height="16" viewBox="0 0 16 16" fill="none" stroke="currentColor" strokeWidth="1.5">
              <circle cx="8" cy="8" r="5.5" />
            </svg>
          </button>
        </div>
      </div>

      {/* List View */}
      {viewMode === "list" && (
        <div className="border border-[var(--border)] rounded-lg overflow-hidden">
          <table className="w-full text-sm">
            <thead>
              <tr className="border-b border-[var(--border)] text-[var(--muted)] text-xs uppercase tracking-wider">
                {([
                  { key: "title" as SortKey, label: "Title", align: "left", classes: "" },
                  { key: "author" as SortKey, label: "Author", align: "left", classes: "hidden sm:table-cell" },
                  { key: "year" as SortKey, label: "Year", align: "right", classes: "font-mono" },
                  { key: "language" as SortKey, label: "Language", align: "left", classes: "hidden md:table-cell" },
                  { key: "entities" as SortKey, label: "Entities", align: "right", classes: "font-mono" },
                  { key: "" as SortKey, label: "", align: "right", classes: "w-10" },
                ]).map((col) => (
                  <th
                    key={col.key}
                    className={`font-medium px-4 py-2.5 ${col.classes} text-${col.align} cursor-pointer select-none hover:text-[var(--foreground)] transition-colors`}
                    onClick={() => toggleSort(col.key)}
                  >
                    <span className={`inline-flex items-center gap-1 ${col.align === "right" ? "justify-end" : ""}`}>
                      {col.label}
                      {sortBy === col.key && (
                        <svg width="8" height="8" viewBox="0 0 10 10" fill="currentColor" className={sortDir === "desc" ? "rotate-180" : ""}>
                          <path d="M5 3L8 7H2L5 3Z" />
                        </svg>
                      )}
                    </span>
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {sorted.map((bookData, i) => (
                <tr
                  key={bookData.book.id}
                  className={`border-b border-[var(--border)] last:border-b-0 hover:bg-[var(--border)]/40 transition-colors ${
                    i % 2 === 0 ? "" : "bg-[var(--card)]"
                  }`}
                >
                  <td className="px-4 py-3">
                    <Link
                      href={`/books/${bookData.book.id}`}
                      className="font-medium hover:text-[var(--accent)] transition-colors"
                    >
                      {bookData.book.title}
                    </Link>
                  </td>
                  <td className="px-4 py-3 text-[var(--muted)] hidden sm:table-cell">
                    {bookData.book.author}
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-[var(--muted)]">
                    {bookData.book.year}
                  </td>
                  <td className="px-4 py-3 text-[var(--muted)] hidden md:table-cell">
                    <span className="inline-flex items-center gap-1.5">
                      <LangDot language={bookData.book.language} />
                      {bookData.book.language}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-right font-mono text-xs text-[var(--muted)]">
                    <EntityCountWithTooltip
                      bookId={bookData.book.id}
                      byCategory={bookData.stats.by_category}
                      total={bookData.stats.total_entities}
                    />
                  </td>
                  <td className="px-4 py-3 text-right">
                    {BOOK_TEXTS[bookData.book.id] && (
                      <a
                        href={BOOK_TEXTS[bookData.book.id]}
                        download
                        className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                        title="Download full text"
                      >
                        <svg className="w-4 h-4 inline" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                        </svg>
                      </a>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {/* Card View */}
      {viewMode === "cards" && (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
          {sorted.map((bookData) => {
            const coverSrc = BOOK_COVERS[bookData.book.id];
            return (
              <div
                key={bookData.book.id}
                className="flex rounded-lg border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--border)]/30 transition-colors overflow-hidden"
              >
                {coverSrc && (
                  <button
                    onClick={() => setModalImage({ src: coverSrc, title: `${bookData.book.title} (${bookData.book.year})` })}
                    className="shrink-0 w-20 bg-[var(--border)]/30 flex items-start justify-center p-2 cursor-zoom-in hover:opacity-80 transition-opacity"
                  >
                    <img
                      src={coverSrc}
                      alt={`Title page of ${bookData.book.title}`}
                      className="w-full h-auto rounded shadow-sm border border-[var(--border)]"
                    />
                  </button>
                )}
                <Link
                  href={`/books/${bookData.book.id}`}
                  className="flex-1 p-4 block min-w-0"
                >
                  <div className="flex items-baseline justify-between gap-4 mb-2">
                    <h2 className="font-semibold leading-snug">
                      {bookData.book.title}
                    </h2>
                    <span className="text-sm font-mono text-[var(--muted)] shrink-0">
                      {bookData.book.year}
                    </span>
                  </div>
                  <p className="text-sm text-[var(--muted)] mb-3">
                    {bookData.book.author}
                  </p>
                  <div className="flex items-center gap-3 text-xs text-[var(--muted)]">
                    <EntityCountWithTooltip
                      bookId={bookData.book.id}
                      byCategory={bookData.stats.by_category}
                      total={bookData.stats.total_entities}
                      label="entities"
                    />
                    <span className="opacity-40">&middot;</span>
                    <span className="inline-flex items-center gap-1.5">
                      <LangDot language={bookData.book.language} />
                      {bookData.book.language}
                    </span>
                  </div>
                </Link>
                {BOOK_TEXTS[bookData.book.id] && (
                  <a
                    href={BOOK_TEXTS[bookData.book.id]}
                    download
                    onClick={(e) => e.stopPropagation()}
                    className="shrink-0 self-end m-3 ml-0 px-3 py-1.5 border border-[var(--border)] rounded-lg text-xs text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--border)] transition-colors inline-flex items-center gap-1.5"
                    title="Download full text"
                  >
                    <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                    </svg>
                    .txt
                  </a>
                )}
              </div>
            );
          })}
        </div>
      )}

      {/* Rings View */}
      {viewMode === "rings" && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
          {sorted.map((bookData) => (
            <RingCard
              key={bookData.book.id}
              bookData={bookData}
              globalCatOrder={globalCatOrder}
            />
          ))}
        </div>
      )}

      {/* Cover image modal */}
      {modalImage && (
        <CoverModal
          src={modalImage.src}
          title={modalImage.title}
          onClose={() => setModalImage(null)}
        />
      )}

      {/* Footer note */}
      <p className="mt-8 text-xs text-[var(--muted)] opacity-60">
        More texts will be added to the corpus.
      </p>
    </div>
  );
}
