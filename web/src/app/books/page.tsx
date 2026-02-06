"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
type ViewMode = "cards" | "list";

// Muted, archival tones — not app-bright, more like ink or dye colors
const LANG_COLORS: Record<string, string> = {
  Portuguese: "#9a6b4c",  // warm sienna
  English:    "#6b7f99",  // cool slate
  Spanish:    "#9a8a3c",  // dry ochre
  French:     "#7b6b99",  // muted lavender
  Italian:    "#8b6b6b",  // dusty rose
};

const BOOK_COVERS: Record<string, string> = {
  "polyanthea_medicinal": "/images/covers/semedo.png",
  "english_physician_1652": "/images/covers/culpeper.png",
  "coloquios_da_orta_1563": "/images/covers/orta.png",
  "historia_medicinal_monardes_1574": "/images/covers/monardes.png",
  "relation_historique_humboldt_vol3_1825": "/images/covers/humboldt.png",
  "ricettario_fiorentino_1597": "/images/covers/ricettario.png",
};

const BOOK_TEXTS: Record<string, string> = {
  "polyanthea_medicinal": "/texts/polyanthea_medicinal.txt",
  "english_physician_1652": "/texts/english_physician_1652.txt",
  "coloquios_da_orta_1563": "/texts/coloquios_da_orta_1563.txt",
  "historia_medicinal_monardes_1574": "/texts/historia_medicinal_monardes_1574.txt",
  "relation_historique_humboldt_vol3_1825": "/texts/relation_historique_humboldt_vol3_1825.txt",
  "ricettario_fiorentino_1597": "/texts/ricettario_fiorentino_1597.txt",
};

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
    if (saved === "cards" || saved === "list") setViewMode(saved);
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
        <div className="flex items-center gap-1 text-[var(--muted)]">
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
                    {bookData.stats.total_entities.toLocaleString()}
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
                    <span className="font-mono">
                      {bookData.stats.total_entities.toLocaleString()} entities
                    </span>
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
