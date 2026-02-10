"use client";

import React, { useMemo, useRef, useState, useEffect, useCallback } from "react";
import Link from "next/link";
import { CAT_DOT, CAT_HEX } from "@/lib/colors";

/* ───── types ───── */

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

interface GroundTruth {
  modern_name: string;
  confidence: "high" | "medium" | "low";
  type: string;
  linnaean?: string;
  description?: string;
  wikidata_description?: string;
  semantic_gloss?: string;
}

interface Cluster {
  id: number;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  members: ClusterMember[];
  ground_truth?: GroundTruth;
}

/* ───── ClusterPreview: lightweight shape stored in the index ───── */

export interface ClusterPreview {
  id: number;
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  slug: string;
  identification: string | null; // modern_name / linnaean
  description: string | null; // brief text for hover
}

/* ───── buildEntityNameIndex ───── */

/**
 * Build a Map<lowercase name, ClusterPreview> from concordance clusters.
 * Indexes canonical_name, ground_truth.modern_name, member names, and member variants.
 * Only names >= 4 chars. Skips ambiguous names that map to multiple cluster IDs.
 */
export function buildEntityNameIndex(
  clusters: Cluster[],
  slugMap: Map<number, string>
): Map<string, ClusterPreview> {
  // First pass: collect all name → cluster id mappings
  const nameToIds = new Map<string, Set<number>>();

  function addName(name: string, clusterId: number) {
    const key = name.toLowerCase().trim();
    if (key.length < 4) return;
    let set = nameToIds.get(key);
    if (!set) {
      set = new Set();
      nameToIds.set(key, set);
    }
    set.add(clusterId);
  }

  const clusterMap = new Map<number, Cluster>();
  for (const c of clusters) {
    clusterMap.set(c.id, c);
    addName(c.canonical_name, c.id);
    if (c.ground_truth?.modern_name) addName(c.ground_truth.modern_name, c.id);
    for (const m of c.members) {
      addName(m.name, c.id);
      for (const v of m.variants) addName(v, c.id);
    }
  }

  // Second pass: build index, skipping ambiguous names
  const index = new Map<string, ClusterPreview>();

  for (const [key, ids] of nameToIds) {
    if (ids.size !== 1) continue; // ambiguous — skip
    const clusterId = ids.values().next().value!;
    if (index.has(key)) continue;
    const c = clusterMap.get(clusterId)!;
    const gt = c.ground_truth;

    let identification: string | null = null;
    if (gt) {
      if ((c.category === "PLANT" || c.category === "ANIMAL") && gt.linnaean) {
        identification = gt.linnaean;
      } else if (gt.modern_name && gt.modern_name.toLowerCase() !== c.canonical_name.toLowerCase()) {
        identification = gt.modern_name;
      }
    }

    let description: string | null = null;
    if (gt?.description) {
      description = gt.description.length > 120 ? gt.description.slice(0, 117) + "\u2026" : gt.description;
    } else if (gt?.semantic_gloss) {
      const first = gt.semantic_gloss.match(/^.+?[.!?](?:\s|$)/);
      description = first ? first[0].trim() : (gt.semantic_gloss.length > 120 ? gt.semantic_gloss.slice(0, 117) + "\u2026" : gt.semantic_gloss);
    } else if (gt?.wikidata_description) {
      description = gt.wikidata_description.length > 120 ? gt.wikidata_description.slice(0, 117) + "\u2026" : gt.wikidata_description;
    } else {
      // Use first member context
      const ctx = c.members.find((m) => m.contexts.length > 0)?.contexts[0];
      if (ctx) {
        description = ctx.length > 100 ? ctx.slice(0, 97) + "\u2026" : ctx;
      }
    }

    index.set(key, {
      id: c.id,
      canonical_name: c.canonical_name,
      category: c.category,
      book_count: c.book_count,
      total_mentions: c.total_mentions,
      slug: slugMap.get(c.id) || "",
      identification,
      description,
    });
  }

  return index;
}

/* ───── slug helpers ───── */

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

// eslint-disable-next-line @typescript-eslint/no-explicit-any
function clusterSlugLocal(cluster: { id: number; canonical_name: string }, allClusters: { id: number; canonical_name: string }[]): string {
  const base = slugify(cluster.canonical_name);
  const hasCollision = allClusters.some(
    (c) => c.id !== cluster.id && slugify(c.canonical_name) === base
  );
  return hasCollision ? `${base}-${cluster.id}` : base;
}

/**
 * Build a Map<cluster id, slug string> from clusters array.
 * Exported so consumers don't need to duplicate slug logic.
 */
export function buildSlugMap(clusters: { id: number; canonical_name: string }[]): Map<number, string> {
  return new Map(clusters.map((c) => [c.id, clusterSlugLocal(c, clusters)]));
}

/* ───── linkifyChildren — for ReactMarkdown integration ───── */

/**
 * Recursively process React children, replacing string nodes with AutoLinkedText.
 * Use in ReactMarkdown component overrides to entity-link LLM output.
 */
export function linkifyChildren(
  children: React.ReactNode,
  nameIndex: Map<string, ClusterPreview>,
  excludeClusterId?: number
): React.ReactNode {
  return React.Children.map(children, (child) => {
    if (typeof child === "string") {
      return <AutoLinkedText text={child} nameIndex={nameIndex} excludeClusterId={excludeClusterId} />;
    }
    if (React.isValidElement(child) && child.props && typeof child.props === "object" && "children" in child.props) {
      return React.cloneElement(
        child,
        {},
        linkifyChildren((child.props as { children?: React.ReactNode }).children, nameIndex, excludeClusterId)
      );
    }
    return child;
  });
}

/* ───── EntityHoverCard ───── */

function EntityHoverCard({ preview }: { preview: ClusterPreview }) {
  const dotClass = CAT_DOT[preview.category] || "bg-slate-500";

  return (
    <div className="w-64 bg-[var(--foreground)] text-[var(--background)] rounded-lg px-4 py-3 shadow-xl">
      {/* Header */}
      <div className="flex items-center gap-2 mb-1">
        <span className={`w-2 h-2 rounded-full shrink-0 ${dotClass}`} />
        <span className="font-semibold text-sm leading-tight truncate">
          {preview.canonical_name}
        </span>
      </div>
      {/* Identification */}
      {preview.identification && (
        <p className="text-[11px] opacity-70 mb-1 truncate">{preview.identification}</p>
      )}
      {/* Stats */}
      <div className="flex items-center gap-2 text-[10px] opacity-50 mb-1.5">
        <span>{preview.category}</span>
        <span>&middot;</span>
        <span>{preview.book_count} book{preview.book_count !== 1 ? "s" : ""}</span>
        <span>&middot;</span>
        <span>{preview.total_mentions} mention{preview.total_mentions !== 1 ? "s" : ""}</span>
      </div>
      {/* Description */}
      {preview.description && (
        <p className="text-[11px] leading-relaxed opacity-75 line-clamp-3">
          {preview.description}
        </p>
      )}
      {/* Click hint */}
      <p className="text-[10px] opacity-40 mt-2 pt-1.5 border-t border-current/10">
        Click to view
      </p>
    </div>
  );
}

/* ───── AutoLinkedText ───── */

export function AutoLinkedText({
  text,
  nameIndex,
  excludeClusterId,
}: {
  text: string;
  nameIndex: Map<string, ClusterPreview>;
  excludeClusterId?: number;
}) {
  const triggerRef = useRef<HTMLSpanElement>(null);
  const [activeMatch, setActiveMatch] = useState<{ preview: ClusterPreview; rect: DOMRect } | null>(null);
  const [cardPosition, setCardPosition] = useState<"above" | "below">("above");
  const hideTimeout = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Build regex from index keys, longest first, word-boundary
  const regex = useMemo(() => {
    const keys = [...nameIndex.keys()]
      .filter((k) => {
        if (excludeClusterId == null) return true;
        const preview = nameIndex.get(k);
        return preview ? preview.id !== excludeClusterId : true;
      })
      .sort((a, b) => b.length - a.length);
    if (keys.length === 0) return null;
    // Escape special regex chars
    const escaped = keys.map((k) => k.replace(/[.*+?^${}()|[\]\\]/g, "\\$&"));
    return new RegExp(`\\b(${escaped.join("|")})\\b`, "gi");
  }, [nameIndex, excludeClusterId]);

  const handleMouseEnter = useCallback((e: React.MouseEvent, preview: ClusterPreview) => {
    if (hideTimeout.current) {
      clearTimeout(hideTimeout.current);
      hideTimeout.current = null;
    }
    const rect = (e.target as HTMLElement).getBoundingClientRect();
    // If near top of viewport, show below
    setCardPosition(rect.top < 200 ? "below" : "above");
    setActiveMatch({ preview, rect });
  }, []);

  const handleMouseLeave = useCallback(() => {
    hideTimeout.current = setTimeout(() => setActiveMatch(null), 150);
  }, []);

  // Clear on unmount
  useEffect(() => {
    return () => {
      if (hideTimeout.current) clearTimeout(hideTimeout.current);
    };
  }, []);

  if (!regex) return <span>{text}</span>;

  // Split text on matches
  const parts: { text: string; preview: ClusterPreview | null }[] = [];
  let lastIndex = 0;
  let match: RegExpExecArray | null;

  // Reset regex
  regex.lastIndex = 0;
  while ((match = regex.exec(text)) !== null) {
    if (match.index > lastIndex) {
      parts.push({ text: text.slice(lastIndex, match.index), preview: null });
    }
    const preview = nameIndex.get(match[0].toLowerCase());
    if (preview && preview.id !== excludeClusterId) {
      parts.push({ text: match[0], preview });
    } else {
      parts.push({ text: match[0], preview: null });
    }
    lastIndex = regex.lastIndex;
  }
  if (lastIndex < text.length) {
    parts.push({ text: text.slice(lastIndex), preview: null });
  }

  return (
    <span ref={triggerRef} className="relative">
      {parts.map((part, i) => {
        if (!part.preview) return <span key={i}>{part.text}</span>;
        const preview = part.preview;
        const hexColor = CAT_HEX[preview.category] || "#64748b";
        return (
          <span
            key={i}
            className="relative inline"
          >
            <Link
              href={`/concordance/${preview.slug}`}
              className="font-semibold border-b border-dotted hover:border-solid transition-colors"
              style={{ borderColor: hexColor, color: "inherit" }}
              onMouseEnter={(e) => handleMouseEnter(e, preview)}
              onMouseLeave={handleMouseLeave}
            >
              {part.text}
            </Link>
          </span>
        );
      })}
      {/* Floating hover card — rendered once, positioned via fixed */}
      {activeMatch && (
        <div
          className="fixed z-[100] pointer-events-auto"
          style={{
            left: `${activeMatch.rect.left}px`,
            ...(cardPosition === "above"
              ? { bottom: `${window.innerHeight - activeMatch.rect.top + 6}px` }
              : { top: `${activeMatch.rect.bottom + 6}px` }),
          }}
          onMouseEnter={() => {
            if (hideTimeout.current) {
              clearTimeout(hideTimeout.current);
              hideTimeout.current = null;
            }
          }}
          onMouseLeave={handleMouseLeave}
        >
          <EntityHoverCard preview={activeMatch.preview} />
        </div>
      )}
    </span>
  );
}
