"use client";

import React, { useEffect, useState, useMemo } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { LinkedExcerpt, buildPersonLinks, type PersonLinkInfo } from "@/components/LinkedExcerpt";
import { useBookContext } from "./BookContext";
import { CAT_BADGE as CATEGORY_COLORS } from "@/lib/colors";
import { BOOK_TEXTS } from "@/lib/books";

type SortKey = "name" | "count" | "category";
type SortDir = "asc" | "desc";


function CategoryBadge({ category, subcategory }: { category: string; subcategory?: string }) {
  const badgeClass = CATEGORY_COLORS[category] || "bg-[var(--border)]";

  return (
    <div className="flex flex-col gap-0.5">
      <span className={`${badgeClass} px-2 py-0.5 rounded text-xs font-medium border`}>
        {category}
      </span>
      {subcategory && subcategory !== `OTHER_${category}` && (
        <span className="text-[10px] text-[var(--muted)]">{subcategory.toLowerCase()}</span>
      )}
    </div>
  );
}

export default function BookDetailPage() {
  const params = useParams();
  const { bookData: data, concordanceData } = useBookContext();
  const [search, setSearch] = useState("");
  const [categoryFilter, setCategoryFilter] = useState<string>("ALL");
  const [sortKey, setSortKey] = useState<SortKey>("count");
  const [sortDir, setSortDir] = useState<SortDir>("desc");
  const [page, setPage] = useState(0);
  const [expandedEntity, setExpandedEntity] = useState<string | null>(null);
  const [personLinks, setPersonLinks] = useState<PersonLinkInfo[]>([]);
  const pageSize = 50;

  // Build person links for auto-linking names in excerpts
  useEffect(() => {
    const bookId = data.book.id;
    if (concordanceData) {
      setPersonLinks(buildPersonLinks(data.entities, bookId, concordanceData.clusters));
    } else {
      setPersonLinks(buildPersonLinks(data.entities, bookId));
    }
  }, [data, concordanceData]);

  const filteredEntities = useMemo(() => {
    let entities = data.entities;

    // Filter by search
    if (search) {
      const searchLower = search.toLowerCase();
      entities = entities.filter(
        (e) =>
          e.name.toLowerCase().includes(searchLower) ||
          e.contexts.some((c) => c.toLowerCase().includes(searchLower))
      );
    }

    // Filter by category
    if (categoryFilter !== "ALL") {
      entities = entities.filter((e) => e.category === categoryFilter);
    }

    // Sort
    entities = [...entities].sort((a, b) => {
      let cmp = 0;
      if (sortKey === "name") {
        cmp = a.name.localeCompare(b.name);
      } else if (sortKey === "count") {
        cmp = a.count - b.count;
      } else if (sortKey === "category") {
        cmp = a.category.localeCompare(b.category);
      }
      return sortDir === "desc" ? -cmp : cmp;
    });

    return entities;
  }, [data, search, categoryFilter, sortKey, sortDir]);

  const paginatedEntities = useMemo(() => {
    return filteredEntities.slice(page * pageSize, (page + 1) * pageSize);
  }, [filteredEntities, page]);

  const totalPages = Math.ceil(filteredEntities.length / pageSize);

  const handleSort = (key: SortKey) => {
    if (sortKey === key) {
      setSortDir(sortDir === "asc" ? "desc" : "asc");
    } else {
      setSortKey(key);
      setSortDir("desc");
    }
    setPage(0);
  };

  return (
    <>
      {/* Header */}
      <div className="mb-4">
        <div className="flex flex-col sm:flex-row sm:items-start sm:justify-between gap-3">
          <div>
            <h1 className="text-3xl font-bold mb-2">{data.book.title}</h1>
            <p className="text-[var(--muted)] text-lg">{data.book.author}, {data.book.year}</p>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            <span className="text-sm text-[var(--muted)] bg-[var(--border)] px-3 py-1 rounded">
              {data.book.language}
            </span>
            {BOOK_TEXTS[data.book.id] && (
              <a
                href={BOOK_TEXTS[data.book.id]}
                download
                className="px-3 py-1.5 border border-[var(--border)] rounded-lg text-sm text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--border)] transition-colors inline-flex items-center gap-1.5"
              >
                <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                </svg>
                Download .txt
              </a>
            )}
          </div>
        </div>
        <p className="mt-4 text-xs text-[var(--muted)] max-w-3xl">{data.book.description}</p>
      </div>

      {/* Stats */}
      <div className="flex flex-wrap items-baseline gap-x-8 gap-y-3 mb-8">
        <span className="text-[var(--foreground)] text-base">
          <strong className="text-2xl font-semibold tabular-nums">{data.stats.total_entities.toLocaleString()}</strong>
          <span className="ml-1.5 text-[var(--muted)]">entities</span>
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-purple-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.PERSON || 0).toLocaleString()}</span> persons
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-cyan-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.SUBSTANCE || 0).toLocaleString()}</span> substances
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-red-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.DISEASE || 0).toLocaleString()}</span> diseases
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-amber-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.CONCEPT || 0).toLocaleString()}</span> concepts
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-green-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.PLACE || 0).toLocaleString()}</span> places
        </span>
        <span className="text-[var(--muted)] text-[15px]">
          <span className="inline-block w-2 h-2 rounded-full bg-slate-500/60 mr-2 align-middle" />
          <span className="font-medium tabular-nums">{(data.stats.by_category.OBJECT || 0).toLocaleString()}</span> objects
        </span>
      </div>

      {/* Filters */}
      <div className="flex flex-col sm:flex-row gap-4 mb-6">
        <div className="flex-1">
          <input
            type="text"
            placeholder="Search entities..."
            value={search}
            onChange={(e) => {
              setSearch(e.target.value);
              setPage(0);
            }}
            className="w-full px-4 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent"
          />
        </div>
        <div className="flex flex-wrap gap-2">
          {["ALL", "PERSON", "SUBSTANCE", "DISEASE", "CONCEPT", "PLACE", "OBJECT"].map((cat) => (
            <button
              key={cat}
              onClick={() => {
                setCategoryFilter(cat);
                setPage(0);
              }}
              className={`px-3 py-1.5 rounded-lg text-sm font-medium transition-colors ${
                categoryFilter === cat
                  ? "bg-[var(--accent)] text-white"
                  : "border border-[var(--border)] hover:bg-[var(--border)]"
              }`}
            >
              {cat === "ALL" ? "All" : cat.charAt(0) + cat.slice(1).toLowerCase()}
            </button>
          ))}
        </div>
      </div>

      {/* Results count */}
      <div className="text-sm text-[var(--muted)] mb-4">
        Showing {paginatedEntities.length} of {filteredEntities.length} entities
        {search && ` matching "${search}"`}
      </div>

      {/* Table */}
      <div className="border border-[var(--border)] rounded-lg overflow-hidden">
        <table className="w-full">
          <thead className="bg-[var(--card)]">
            <tr className="border-b border-[var(--border)]">
              <th
                onClick={() => handleSort("name")}
                className="text-left px-4 py-3 text-sm font-medium cursor-pointer hover:bg-[var(--border)] transition-colors"
              >
                <span className="flex items-center gap-1">
                  Entity
                  {sortKey === "name" && (
                    <span className="text-[var(--accent)]">{sortDir === "asc" ? "↑" : "↓"}</span>
                  )}
                </span>
              </th>
              <th
                onClick={() => handleSort("category")}
                className="text-left px-4 py-3 text-sm font-medium cursor-pointer hover:bg-[var(--border)] transition-colors"
              >
                <span className="flex items-center gap-1">
                  Category
                  {sortKey === "category" && (
                    <span className="text-[var(--accent)]">{sortDir === "asc" ? "↑" : "↓"}</span>
                  )}
                </span>
              </th>
              <th
                onClick={() => handleSort("count")}
                className="text-right px-4 py-3 text-sm font-medium cursor-pointer hover:bg-[var(--border)] transition-colors"
              >
                <span className="flex items-center justify-end gap-1">
                  Count
                  {sortKey === "count" && (
                    <span className="text-[var(--accent)]">{sortDir === "asc" ? "↑" : "↓"}</span>
                  )}
                </span>
              </th>
              <th className="text-left px-4 py-3 text-sm font-medium">Context</th>
            </tr>
          </thead>
          <tbody>
            {paginatedEntities.map((entity, idx) => {
              const isExpanded = expandedEntity === entity.id;
              const hasMentions = entity.mentions && entity.mentions.length > 0;
              return (
                <React.Fragment key={entity.id}>
                  <tr
                    onClick={() => hasMentions && setExpandedEntity(isExpanded ? null : entity.id)}
                    className={`border-b border-[var(--border)] transition-colors ${
                      hasMentions ? "cursor-pointer hover:bg-[var(--card)]" : ""
                    } ${idx % 2 === 0 ? "bg-transparent" : "bg-[var(--card)]/50"}`}
                  >
                    <td className="px-4 py-3">
                      <div className="flex items-center gap-2">
                        {hasMentions && (
                          <span className={`text-xs text-[var(--muted)] transition-transform ${isExpanded ? "rotate-90" : ""}`}>
                            &#9654;
                          </span>
                        )}
                        <div>
                          <div className="font-medium">{entity.name}</div>
                          {entity.variants.length > 1 && (
                            <div className="text-xs text-[var(--muted)] mt-1">
                              {entity.variants.slice(0, 3).filter(v => v !== entity.name).join(", ")}
                              {entity.variants.length > 3 && " ..."}
                            </div>
                          )}
                        </div>
                      </div>
                    </td>
                    <td className="px-4 py-3">
                      <CategoryBadge category={entity.category} subcategory={entity.subcategory} />
                    </td>
                    <td className="px-4 py-3 text-right font-mono text-sm">{entity.count}</td>
                    <td className="px-4 py-3 text-sm text-[var(--muted)] max-w-xs truncate">
                      {entity.contexts[0] || "—"}
                    </td>
                  </tr>
                  {isExpanded && hasMentions && (
                    <tr className="bg-[var(--card)]">
                      <td colSpan={4} className="px-4 py-4">
                        <div className="ml-6 space-y-3">
                          <div className="text-xs font-medium text-[var(--muted)] mb-2">
                            {entity.mentions!.length} excerpt{entity.mentions!.length !== 1 ? "s" : ""} found in text
                          </div>
                          {entity.mentions!.slice(0, 5).map((mention, mIdx) => (
                            <div
                              key={mIdx}
                              className="text-sm border-l-2 border-[var(--accent)] pl-3 py-1"
                            >
                              <LinkedExcerpt
                                excerpt={mention.excerpt}
                                matchedTerm={mention.matched_term}
                                personLinks={personLinks}
                              />
                            </div>
                          ))}
                          <Link
                            href={`/books/${params.id}/entity/${entity.id}`}
                            className="inline-flex items-center gap-1.5 text-sm font-medium text-[var(--foreground)] border border-[var(--border)] rounded-md px-3 py-1.5 mt-3 hover:bg-[var(--border)] transition-colors"
                            onClick={(e) => e.stopPropagation()}
                          >
                            View all {entity.mentions!.length} excerpts
                            <span className="text-[var(--muted)]">&rarr;</span>
                          </Link>
                        </div>
                      </td>
                    </tr>
                  )}
                </React.Fragment>
              );
            })}
          </tbody>
        </table>
      </div>

      {/* Pagination */}
      {totalPages > 1 && (
        <div className="flex items-center justify-between mt-6">
          <button
            onClick={() => setPage(Math.max(0, page - 1))}
            disabled={page === 0}
            className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--border)] transition-colors"
          >
            Previous
          </button>
          <span className="text-sm text-[var(--muted)]">
            Page {page + 1} of {totalPages}
          </span>
          <button
            onClick={() => setPage(Math.min(totalPages - 1, page + 1))}
            disabled={page >= totalPages - 1}
            className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm disabled:opacity-50 disabled:cursor-not-allowed hover:bg-[var(--border)] transition-colors"
          >
            Next
          </button>
        </div>
      )}

      {/* Metadata */}
      <div className="mt-8 pt-8 border-t border-[var(--border)] text-sm text-[var(--muted)]">
        <p>
          Extracted using {data.stats.extraction_method} • {data.stats.chunks_processed} text chunks processed
        </p>
      </div>
    </>
  );
}
