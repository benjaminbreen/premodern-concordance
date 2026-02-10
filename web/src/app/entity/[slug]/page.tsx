"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { CAT_BADGE } from "@/lib/colors";
import { BOOK_SHORT_NAMES } from "@/lib/books";
import {
  buildEntityNameIndex,
  buildSlugMap,
  AutoLinkedText,
  type ClusterPreview,
} from "@/components/EntityHoverCard";

interface RegistryAttestation {
  book_id: string;
  book_title: string;
  book_author: string;
  book_year: number;
  book_language: string;
  local_entity_id: string;
  local_name: string;
  category: string;
  subcategory: string;
  count: number;
  variants: string[];
  contexts: string[];
  mention_count: number;
  excerpt_samples: string[];
  entity_page_path: string;
}

interface RegistryEntity {
  id: string;
  slug: string;
  canonical_name: string;
  category: string;
  subcategory: string;
  book_count: number;
  total_mentions: number;
  is_concordance: boolean;
  concordance_cluster_id: number | null;
  concordance_slug: string | null;
  ground_truth: Record<string, unknown>;
  books: string[];
  names: string[];
  attestations: RegistryAttestation[];
}

export default function CanonicalEntityPage() {
  const params = useParams();
  const slug = params.slug as string;
  const [entity, setEntity] = useState<RegistryEntity | null | undefined>(undefined);

  useEffect(() => {
    fetch(`/api/entity/${encodeURIComponent(slug)}`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        setEntity(data?.entity || null);
      })
      .catch(() => setEntity(null));
  }, [slug]);

  const overview = useMemo(() => {
    if (!entity) return "";
    const gt = entity.ground_truth || {};
    return (
      (gt["description"] as string) ||
      (gt["semantic_gloss"] as string) ||
      (gt["wikidata_description"] as string) ||
      ""
    );
  }, [entity]);

  // Load concordance clusters for entity hover cards
  const [concordanceClusters, setConcordanceClusters] = useState<
    { id: number; canonical_name: string; category: string; subcategory: string; book_count: number; total_mentions: number; members: { entity_id: string; book_id: string; name: string; category: string; subcategory: string; count: number; variants: string[]; contexts: string[] }[]; ground_truth?: { modern_name: string; confidence: "high" | "medium" | "low"; type: string; linnaean?: string; description?: string; wikidata_description?: string; semantic_gloss?: string } }[]
  >([]);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((r) => r.json())
      .then((d) => {
        if (d?.clusters) setConcordanceClusters(d.clusters);
      })
      .catch(() => {});
  }, []);

  const nameIndex = useMemo(() => {
    if (concordanceClusters.length === 0) return new Map<string, ClusterPreview>();
    const slugMap = buildSlugMap(concordanceClusters);
    return buildEntityNameIndex(concordanceClusters, slugMap);
  }, [concordanceClusters]);

  // Get the concordance cluster ID for this entity so we can exclude self-links
  const excludeClusterId = useMemo(() => {
    if (!entity) return undefined;
    return entity.concordance_cluster_id ?? undefined;
  }, [entity]);

  if (entity === undefined) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <div className="animate-pulse space-y-3">
          <div className="h-8 w-1/3 bg-[var(--border)] rounded" />
          <div className="h-4 w-2/3 bg-[var(--border)] rounded" />
          <div className="h-32 bg-[var(--border)] rounded" />
        </div>
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
        <p className="text-sm text-[var(--muted)]">Entity not found.</p>
        <Link href="/entities" className="text-sm text-[var(--accent)] hover:underline mt-3 inline-block">
          Back to entities
        </Link>
      </div>
    );
  }

  const gt = entity.ground_truth || {};
  const wikiUrl = gt["wikipedia_url"] as string | undefined;
  const portraitUrl = (gt["portrait_url"] as string) || "";

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      <nav className="mb-5 text-sm">
        <Link href="/entities" className="text-[var(--muted)] hover:text-[var(--foreground)]">Entities</Link>
        <span className="mx-2 text-[var(--muted)]">/</span>
        <span>{entity.canonical_name}</span>
      </nav>

      <section className="border border-[var(--border)] rounded-xl bg-[var(--card)] p-6 mb-6">
        <div className="flex items-start justify-between gap-4">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-2">
              <h1 className="text-3xl font-bold truncate">{entity.canonical_name}</h1>
              <span className={`px-2 py-0.5 rounded text-xs border ${CAT_BADGE[entity.category] || "bg-[var(--border)]"}`}>
                {entity.category}
              </span>
            </div>
            {entity.subcategory && (
              <p className="text-xs text-[var(--muted)] mb-3">{entity.subcategory.toLowerCase()}</p>
            )}
            <div className="flex flex-wrap gap-4 text-sm text-[var(--muted)]">
              <span><strong className="text-[var(--foreground)]">{entity.book_count}</strong> books</span>
              <span><strong className="text-[var(--foreground)]">{entity.total_mentions.toLocaleString()}</strong> mentions</span>
              <span><strong className="text-[var(--foreground)]">{entity.names.length}</strong> variants</span>
              <span>{entity.is_concordance ? "Cross-book entity" : "Single-book entity"}</span>
            </div>
          </div>
          {portraitUrl && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={portraitUrl} alt="" className="w-20 h-20 rounded object-cover border border-[var(--border)]" />
          )}
        </div>
        {overview && (
          <p className="mt-4 text-sm leading-relaxed text-[var(--muted)]">{overview}</p>
        )}
        <div className="mt-4 flex items-center gap-3 text-xs">
          {entity.is_concordance && entity.concordance_slug && (
            <Link href={`/concordance/${entity.concordance_slug}`} className="text-[var(--accent)] hover:underline">
              View concordance page
            </Link>
          )}
          {wikiUrl && (
            <a href={wikiUrl} target="_blank" rel="noopener noreferrer" className="text-[var(--accent)] hover:underline">
              Wikipedia
            </a>
          )}
        </div>
      </section>

      <section className="mb-8">
        <h2 className="text-lg font-semibold mb-3">Names and Variants</h2>
        <div className="flex flex-wrap gap-2">
          {entity.names.slice(0, 80).map((name) => (
            <span key={name} className="px-2 py-1 rounded border border-[var(--border)] bg-[var(--card)] text-sm">
              {name}
            </span>
          ))}
        </div>
      </section>

      <section>
        <h2 className="text-lg font-semibold mb-3">Attestations by Book</h2>
        <div className="space-y-4">
          {[...entity.attestations]
            .sort((a, b) => b.count - a.count || a.book_year - b.book_year)
            .map((a) => (
              <article key={`${a.book_id}-${a.local_entity_id}`} className="border border-[var(--border)] rounded-lg p-4 bg-[var(--card)]">
                <div className="flex items-start justify-between gap-4 mb-2">
                  <div>
                    <div className="text-sm font-medium">
                      <Link href={`/books/${a.book_id}`} className="hover:text-[var(--accent)]">
                        {BOOK_SHORT_NAMES[a.book_id] || a.book_title}
                      </Link>
                      <span className="text-[var(--muted)] ml-2">({a.book_year}, {a.book_language})</span>
                    </div>
                    <div className="text-xs text-[var(--muted)] mt-1">
                      Surface form: <strong className="text-[var(--foreground)]">{a.local_name}</strong>
                    </div>
                  </div>
                  <div className="text-xs text-[var(--muted)] font-mono">
                    {a.count}× · {a.mention_count} excerpts
                  </div>
                </div>

                {a.contexts.length > 0 && (
                  <p className="text-sm text-[var(--muted)] mb-3">
                    {nameIndex.size > 0 ? (
                      <AutoLinkedText text={a.contexts[0]} nameIndex={nameIndex} excludeClusterId={excludeClusterId} />
                    ) : a.contexts[0]}
                  </p>
                )}

                {a.excerpt_samples.length > 0 && (
                  <div className="space-y-2 mb-3">
                    {a.excerpt_samples.slice(0, 2).map((ex, idx) => (
                      <p key={idx} className="text-xs text-[var(--muted)] leading-relaxed border-l-2 border-[var(--border)] pl-3">
                        ...{nameIndex.size > 0 ? (
                          <AutoLinkedText text={ex} nameIndex={nameIndex} excludeClusterId={excludeClusterId} />
                        ) : ex}...
                      </p>
                    ))}
                  </div>
                )}

                <div className="flex items-center gap-3 text-xs">
                  <Link
                    href={a.entity_page_path}
                    className="text-[var(--accent)] hover:underline"
                  >
                    View local entity page
                  </Link>
                  <span className="text-[var(--muted)]">
                    {a.variants.length} variants
                  </span>
                </div>
              </article>
            ))}
        </div>
      </section>
    </div>
  );
}
