"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter, useSearchParams } from "next/navigation";

/* ───── shared types (duplicated from concordance/page.tsx) ───── */

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
  semantic_gloss?: string;
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

/* ───── constants ───── */

const CATEGORY_COLORS: Record<string, { badge: string; dot: string }> = {
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
  CONCEPT: {
    badge: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
    dot: "bg-amber-500",
  },
  DISEASE: {
    badge: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
    dot: "bg-red-500",
  },
  PLACE: {
    badge: "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
    dot: "bg-green-500",
  },
  OBJECT: {
    badge: "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30",
    dot: "bg-slate-500",
  },
  ANATOMY: {
    badge: "bg-rose-500/20 text-rose-600 dark:text-rose-400 border-rose-500/30",
    dot: "bg-rose-500",
  },
};

const CATEGORY_BAR_COLORS: Record<string, string> = {
  PERSON: "bg-purple-500",
  PLANT: "bg-emerald-500",
  ANIMAL: "bg-lime-500",
  SUBSTANCE: "bg-cyan-500",
  CONCEPT: "bg-amber-500",
  DISEASE: "bg-red-500",
  PLACE: "bg-green-500",
  OBJECT: "bg-slate-500",
  ANATOMY: "bg-rose-500",
};

const CATEGORY_TINT: Record<string, string> = {
  PERSON: "rgba(147, 51, 234, 0.25)",
  PLANT: "rgba(16, 185, 129, 0.25)",
  ANIMAL: "rgba(132, 204, 22, 0.25)",
  SUBSTANCE: "rgba(6, 182, 212, 0.25)",
  CONCEPT: "rgba(245, 158, 11, 0.25)",
  DISEASE: "rgba(239, 68, 68, 0.25)",
  PLACE: "rgba(34, 197, 94, 0.25)",
  OBJECT: "rgba(100, 116, 139, 0.25)",
  ANATOMY: "rgba(244, 63, 94, 0.25)",
};

const BOOK_SHORT_NAMES: Record<string, string> = {
  english_physician_1652: "Culpeper",
  polyanthea_medicinal: "Semedo",
  coloquios_da_orta_1563: "Da Orta",
  historia_medicinal_monardes_1574: "Monardes",
  relation_historique_humboldt_vol3_1825: "Humboldt",
  ricettario_fiorentino_1597: "Ricettario",
};

const BOOK_LANG_FLAGS: Record<string, string> = {
  English: "EN",
  Portuguese: "PT",
  Spanish: "ES",
  Latin: "LA",
  French: "FR",
  Italian: "IT",
};

/* ───── slug helpers ───── */

function slugify(name: string): string {
  return name
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Build a slug for a cluster, appending ID if the base slug collides */
function clusterSlug(cluster: Cluster, allClusters: Cluster[]): string {
  const base = slugify(cluster.canonical_name);
  const hasCollision = allClusters.some(
    (c) => c.id !== cluster.id && slugify(c.canonical_name) === base
  );
  return hasCollision ? `${base}-${cluster.id}` : base;
}

/** Find a cluster by its slug (try base match first, then id-suffixed) */
function findClusterBySlug(slug: string, clusters: Cluster[]): Cluster | null {
  // First try exact base-slug match (unique names)
  const baseMatches = clusters.filter((c) => slugify(c.canonical_name) === slug);
  if (baseMatches.length === 1) return baseMatches[0];

  // Try id-suffixed match (e.g. "verde-113")
  const idMatch = slug.match(/-(\d+)$/);
  if (idMatch) {
    const id = Number(idMatch[1]);
    const found = clusters.find((c) => c.id === id);
    if (found) return found;
  }

  return null;
}

/* ───── helpers ───── */

function cap(r: { text: string; italic: boolean }): { text: string; italic: boolean } {
  if (r.text.length > 0) {
    return { ...r, text: r.text.charAt(0).toUpperCase() + r.text.slice(1) };
  }
  return r;
}

function getIdentification(cluster: Cluster): { text: string; italic: boolean } | null {
  const gt = cluster.ground_truth;
  if (!gt) return null;
  const cat = cluster.category;
  const canonLower = cluster.canonical_name.toLowerCase();

  if (cat === "PERSON") {
    if (gt.birth_year) {
      const dates = `(${gt.birth_year}\u2013${gt.death_year || "?"})`;
      return cap({ text: `${gt.modern_name} ${dates}`, italic: false });
    }
    const nameDiffers = gt.modern_name.toLowerCase() !== canonLower;
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
    if (gt.modern_name.toLowerCase() !== canonLower) return cap({ text: gt.modern_name, italic: false });
    if (gt.family) return cap({ text: `Fam. ${gt.family}`, italic: true });
    return null;
  }

  if (gt.modern_name.toLowerCase() !== canonLower) return cap({ text: gt.modern_name, italic: false });
  if (gt.modern_term && gt.modern_term.toLowerCase() !== canonLower && gt.modern_term.toLowerCase() !== gt.modern_name.toLowerCase()) {
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

/** Group all member variants by book language */
function getVariantsByLanguage(
  members: ClusterMember[],
  books: BookMeta[]
): Record<string, string[]> {
  const byLang: Record<string, Set<string>> = {};
  for (const m of members) {
    const book = books.find((b) => b.id === m.book_id);
    const lang = book?.language || "Unknown";
    if (!byLang[lang]) byLang[lang] = new Set();
    for (const v of m.variants) byLang[lang].add(v);
  }
  const result: Record<string, string[]> = {};
  for (const [lang, set] of Object.entries(byLang)) {
    result[lang] = [...set].sort((a, b) => a.localeCompare(b));
  }
  return result;
}

/** Aggregate mention counts per book_id */
function getMentionsByBook(members: ClusterMember[]): { book_id: string; count: number }[] {
  const counts: Record<string, number> = {};
  for (const m of members) {
    counts[m.book_id] = (counts[m.book_id] || 0) + m.count;
  }
  return Object.entries(counts)
    .map(([book_id, count]) => ({ book_id, count }))
    .sort((a, b) => b.count - a.count);
}

/* ───── sub-components ───── */

function WikiThumbnail({ url, size = "sm" }: { url: string; size?: "sm" | "lg" }) {
  const [thumb, setThumb] = useState<string | null>(null);

  useEffect(() => {
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) return;

      fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`)
        .then((res) => res.json())
        .then((data) => {
          if (data.thumbnail?.source) setThumb(data.thumbnail.source);
        })
        .catch(() => {});
    } catch {
      // invalid URL
    }
  }, [url]);

  if (!thumb) return null;

  const sizeClass = size === "lg" ? "w-32 h-32" : "w-24 h-24";

  return (
    // eslint-disable-next-line @next/next/no-img-element
    <img
      src={thumb}
      alt=""
      className={`${sizeClass} rounded object-cover shrink-0 border border-[var(--border)]`}
    />
  );
}

function WikiExtract({ url, wikiUrl }: { url: string; wikiUrl?: string }) {
  const [paragraphs, setParagraphs] = useState<string[]>([]);
  const [expanded, setExpanded] = useState(false);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    try {
      const urlObj = new URL(url);
      const lang = urlObj.hostname.split(".")[0];
      const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
      if (!title) { setLoading(false); return; }

      fetch(
        `https://${lang}.wikipedia.org/w/api.php?action=query&titles=${encodeURIComponent(title)}&prop=extracts&explaintext=true&exsectionformat=plain&format=json&origin=*`
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
        .catch(() => setLoading(false));
    } catch {
      setLoading(false);
    }
  }, [url]);

  if (loading || paragraphs.length === 0) return null;

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
    <div>
      <p className="text-sm text-[var(--foreground)]/80 leading-relaxed">{preview}</p>
      {expanded && (
        <div className="max-h-[280px] overflow-y-auto space-y-3 text-sm text-[var(--foreground)]/80 leading-relaxed">
          {restOfFirst && <p>{restOfFirst}</p>}
          {paragraphs.slice(1).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
      <div className="flex items-center gap-3 mt-2">
        {hasMore && (
          <button
            onClick={() => setExpanded(!expanded)}
            className="text-xs text-[var(--accent)] hover:underline"
          >
            {expanded ? "Less" : "More"}
          </button>
        )}
        {expanded && wikiUrl && (
          <a
            href={wikiUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="text-xs text-[var(--accent)] hover:underline"
          >
            Read on Wikipedia &rarr;
          </a>
        )}
      </div>
    </div>
  );
}

/** Wikipedia card — receives resolved URL from parent */
function WikiCard({ url, searching }: { url: string | null; searching: boolean }) {
  if (searching) {
    return (
      <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
        <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Wikipedia
        </h3>
        <div className="flex items-center gap-2 text-xs text-[var(--muted)]">
          <div className="w-3 h-3 border border-[var(--muted)] border-t-transparent rounded-full animate-spin" />
          Looking up article...
        </div>
      </div>
    );
  }

  if (!url) {
    return (
      <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
        <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Wikipedia
        </h3>
        <p className="text-xs text-[var(--muted)]">No Wikipedia article found.</p>
      </div>
    );
  }

  return (
    <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
      <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
        Wikipedia
      </h3>
      <WikiExtract url={url} wikiUrl={url} />
    </div>
  );
}

/* ───── main page component ───── */

export default function ClusterDetailPage() {
  const params = useParams();
  const router = useRouter();
  const searchParams = useSearchParams();
  const slug = params.slug as string;
  const fromSlug = searchParams.get("from");

  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);
  const [wikiUrl, setWikiUrl] = useState<string | null>(null);
  const [wikiImage, setWikiImage] = useState<string | null>(null);
  const [wikiSearching, setWikiSearching] = useState(false);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((d) => { setData(d); setLoading(false); })
      .catch(() => setLoading(false));
  }, []);

  const cluster = useMemo(
    () => (data ? findClusterBySlug(slug, data.clusters) : null),
    [data, slug]
  );

  // Prev/next cluster slugs (by sorted order in data)
  const { prevSlug, nextSlug } = useMemo(() => {
    if (!data || !cluster) return { prevSlug: null, nextSlug: null };
    const idx = data.clusters.findIndex((c) => c.id === cluster.id);
    return {
      prevSlug: idx > 0 ? clusterSlug(data.clusters[idx - 1], data.clusters) : null,
      nextSlug: idx >= 0 && idx < data.clusters.length - 1 ? clusterSlug(data.clusters[idx + 1], data.clusters) : null,
    };
  }, [data, cluster]);

  // Keyboard navigation
  const handleKeyDown = useCallback(
    (e: KeyboardEvent) => {
      if (
        e.target instanceof HTMLInputElement ||
        e.target instanceof HTMLSelectElement ||
        e.target instanceof HTMLTextAreaElement
      )
        return;

      if (e.key === "Escape") {
        router.push("/concordance");
        return;
      }
      if (e.key === "ArrowLeft" && prevSlug !== null) {
        router.push(`/concordance/${prevSlug}`);
        return;
      }
      if (e.key === "ArrowRight" && nextSlug !== null) {
        router.push(`/concordance/${nextSlug}`);
        return;
      }
    },
    [router, prevSlug, nextSlug]
  );

  useEffect(() => {
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [handleKeyDown]);

  // Resolve Wikipedia URL + image from ground_truth or by searching
  useEffect(() => {
    setWikiUrl(null);
    setWikiImage(null);
    setWikiSearching(false);
    if (!cluster) return;
    const gt = cluster.ground_truth;
    if (!gt) return;

    let cancelled = false;

    async function resolve() {
      // If we have an explicit wikipedia_url, use it directly
      if (gt!.wikipedia_url) {
        setWikiUrl(gt!.wikipedia_url);
        // Fetch image from the page summary API
        try {
          const urlObj = new URL(gt!.wikipedia_url);
          const lang = urlObj.hostname.split(".")[0];
          const title = decodeURIComponent(urlObj.pathname.split("/wiki/")[1] || "");
          if (title) {
            const res = await fetch(`https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(title)}`);
            if (res.ok) {
              const d = await res.json();
              if (d.originalimage?.source && !cancelled) setWikiImage(d.originalimage.source);
              else if (d.thumbnail?.source && !cancelled) setWikiImage(d.thumbnail.source.replace(/\/\d+px-/, "/800px-"));
            }
          }
        } catch { /* ok */ }
        return;
      }

      // Try to find article from linnaean/modern_name
      const searchTerms = [gt!.linnaean, gt!.modern_name].filter(Boolean) as string[];
      if (searchTerms.length === 0) return;

      setWikiSearching(true);
      for (const term of searchTerms) {
        try {
          const res = await fetch(`https://en.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(term)}`);
          if (!res.ok) continue;
          const d = await res.json();
          if (d.type === "disambiguation") continue;
          if (d.content_urls?.desktop?.page && !cancelled) {
            setWikiUrl(d.content_urls.desktop.page);
            if (d.originalimage?.source) setWikiImage(d.originalimage.source);
            else if (d.thumbnail?.source) setWikiImage(d.thumbnail.source.replace(/\/\d+px-/, "/800px-"));
            setWikiSearching(false);
            return;
          }
        } catch { /* try next */ }
      }
      if (!cancelled) setWikiSearching(false);
    }

    resolve();
    return () => { cancelled = true; };
  }, [cluster]);

  /* ── loading / error states ── */

  if (loading) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-[var(--border)] rounded w-1/4" />
          <div className="h-8 bg-[var(--border)] rounded w-1/3" />
          <div className="h-64 bg-[var(--border)] rounded" />
        </div>
      </div>
    );
  }

  if (!data || !cluster) {
    return (
      <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <p className="text-[var(--muted)] mb-4">Cluster not found.</p>
        <Link
          href="/concordance"
          className="text-sm text-[var(--accent)] hover:underline"
        >
          &larr; Back to Concordance
        </Link>
      </div>
    );
  }

  /* ── derived data ── */

  const gt = cluster.ground_truth;
  const catColor = CATEGORY_COLORS[cluster.category];
  const tintColor = CATEGORY_TINT[cluster.category] || "rgba(100, 116, 139, 0.25)";
  const identification = getIdentification(cluster);
  const bookIds = [...new Set(cluster.members.map((m) => m.book_id))];
  const langCount = new Set(
    bookIds.map((bid) => data.books.find((b) => b.id === bid)?.language).filter(Boolean)
  ).size;
  const mentionsByBook = getMentionsByBook(cluster.members);
  const maxMentions = Math.max(...mentionsByBook.map((b) => b.count), 1);
  const variantsByLang = getVariantsByLanguage(cluster.members, data.books);

  // Subtitle line
  let subtitle: string | null = null;
  if (gt) {
    if ((cluster.category === "PLANT" || cluster.category === "ANIMAL") && gt.linnaean) {
      subtitle = gt.linnaean;
    } else if (cluster.category === "PERSON" && gt.birth_year) {
      subtitle = `${gt.birth_year}\u2013${gt.death_year || "?"}`;
    } else if (gt.modern_name && gt.modern_name.toLowerCase() !== cluster.canonical_name.toLowerCase()) {
      subtitle = gt.modern_name;
    }
  }

  return (
    <div className="max-w-5xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* ─── 1. Breadcrumb ─── */}
      <nav className="flex items-center gap-2 text-sm text-[var(--muted)] mb-6">
        <Link href="/concordance" className="hover:text-[var(--foreground)] transition-colors">
          Concordance
        </Link>
        <span>/</span>
        <span className="text-[var(--foreground)]">{cluster.canonical_name}</span>
        {fromSlug && (() => {
          const fromCluster = data.clusters.find(c => clusterSlug(c, data.clusters) === fromSlug);
          if (!fromCluster) return null;
          return (
            <span className="ml-auto text-xs">
              <Link
                href={`/concordance/${fromSlug}`}
                className="text-[var(--accent)] hover:underline transition-colors"
              >
                &larr; Back to {fromCluster.canonical_name}
              </Link>
            </span>
          );
        })()}
      </nav>

      {/* ─── 2. Hero Header with Wikipedia Image ─── */}
      <div className="relative mb-8 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--background)]">
        {/* Image layer — fades from invisible on left to visible on right */}
        {wikiImage && (
          <div className="absolute inset-0">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={wikiImage}
              alt=""
              className="absolute inset-0 w-full h-full object-cover"
              style={{
                WebkitMaskImage: "linear-gradient(to right, transparent 35%, rgba(0,0,0,0.1) 55%, rgba(0,0,0,0.5) 80%, black 100%)",
                maskImage: "linear-gradient(to right, transparent 35%, rgba(0,0,0,0.1) 55%, rgba(0,0,0,0.5) 80%, black 100%)",
              }}
            />
            {/* Category tint on upper-right corner */}
            <div
              className="absolute inset-0"
              style={{
                background: `radial-gradient(ellipse at top right, ${tintColor} 0%, transparent 60%)`,
              }}
            />
            {/* Subtle bottom fade */}
            <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-[var(--background)] to-transparent" />
            {wikiUrl && (
              <a
                href={wikiUrl}
                target="_blank"
                rel="noopener noreferrer"
                className="absolute bottom-2 right-3 z-20 text-[10px] text-[var(--muted)] opacity-50 hover:opacity-100 hover:text-[var(--accent)] transition-all cursor-pointer"
              >
                Image: Wikipedia
              </a>
            )}
          </div>
        )}

        {/* Content layer */}
        <div className="relative z-10 px-8 py-10" style={{ minHeight: wikiImage ? "200px" : undefined }}>
          <div className="flex items-center gap-3 flex-wrap mb-2">
            <h1 className="text-3xl font-bold">{cluster.canonical_name}</h1>
            <span
              className={`${catColor?.badge || "bg-[var(--border)]"} px-2.5 py-0.5 rounded text-xs font-medium border`}
            >
              {cluster.category}
            </span>
            {cluster.subcategory && cluster.subcategory !== cluster.category && (
              <span className="text-xs text-[var(--muted)]">{cluster.subcategory}</span>
            )}
          </div>
          {subtitle && (
            <p className="text-lg text-[var(--muted)] mt-1">
              {(cluster.category === "PLANT" || cluster.category === "ANIMAL") && gt?.linnaean ? (
                <i>{subtitle}</i>
              ) : (
                subtitle
              )}
            </p>
          )}
          {gt?.note && (
            <blockquote className="text-sm text-[var(--muted)] mt-3 border-l-2 border-[var(--border)] pl-3 leading-relaxed max-w-2xl">
              {gt.note}
            </blockquote>
          )}
          {/* Stats row */}
          <div className="flex flex-wrap gap-x-4 gap-y-1 mt-3 text-sm text-[var(--muted)]">
            <span>
              <strong className="text-[var(--foreground)]">{cluster.book_count}</strong> book{cluster.book_count !== 1 ? "s" : ""}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{cluster.total_mentions}</strong> mention{cluster.total_mentions !== 1 ? "s" : ""}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{cluster.members.length}</strong> entr{cluster.members.length !== 1 ? "ies" : "y"}
            </span>
            <span>
              <strong className="text-[var(--foreground)]">{langCount}</strong> language{langCount !== 1 ? "s" : ""}
            </span>
          </div>
        </div>
      </div>

      {/* ─── 3. Three-Column Info Strip ─── */}
      <div className="grid md:grid-cols-3 gap-4 mb-8">
        {/* Card 1: Identification */}
        <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
            Identification
          </h3>
          {gt ? (
            <div className="space-y-2">
              <div className="flex items-start gap-3">
                {gt.portrait_url ? (
                  // eslint-disable-next-line @next/next/no-img-element
                  <img
                    src={gt.portrait_url}
                    alt=""
                    className="w-12 h-14 rounded object-cover border border-[var(--border)] shrink-0"
                  />
                ) : gt.wikipedia_url && !gt.portrait_url ? (
                  <WikiThumbnail url={gt.wikipedia_url} size="sm" />
                ) : null}
                <div className="flex-1 min-w-0">
                  <p className="text-sm font-semibold">{gt.modern_name}</p>
                  {gt.linnaean && (
                    <p className="text-xs italic text-[var(--muted)]">{gt.linnaean}</p>
                  )}
                  {gt.family && (
                    <p className="text-xs text-[var(--muted)]">
                      Family: <i>{gt.family}</i>
                    </p>
                  )}
                  {gt.birth_year && (
                    <p className="text-xs text-[var(--muted)]">
                      {gt.birth_year}&ndash;{gt.death_year || "?"}
                    </p>
                  )}
                </div>
              </div>
              {gt.description && (
                <p className="text-xs text-[var(--muted)] leading-relaxed">{gt.description}</p>
              )}
              {gt.wikidata_description && !gt.description && (
                <p className="text-xs text-[var(--muted)] leading-relaxed">
                  {gt.wikidata_description}
                </p>
              )}
              <div className="flex items-center gap-2 flex-wrap pt-1">
                <span
                  className={`px-1.5 py-0.5 rounded text-[10px] font-medium ${
                    gt.confidence === "high"
                      ? "bg-green-500/20 text-green-600 dark:text-green-400"
                      : gt.confidence === "medium"
                      ? "bg-yellow-500/20 text-yellow-600 dark:text-yellow-400"
                      : "bg-red-500/20 text-red-600 dark:text-red-400"
                  }`}
                >
                  {gt.confidence} confidence
                </span>
                {gt.wikidata_id && (
                  <a
                    href={`https://www.wikidata.org/wiki/${gt.wikidata_id}`}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="text-[10px] font-mono text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                  >
                    {gt.wikidata_id}
                  </a>
                )}
              </div>
              {gt.semantic_gloss && (
                <p className="text-xs text-[var(--foreground)]/70 leading-relaxed mt-3 pt-3 border-t border-[var(--border)]">
                  {gt.semantic_gloss}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-[var(--muted)]">No identification available.</p>
          )}
        </div>

        {/* Card 2: Wikipedia */}
        <WikiCard url={wikiUrl} searching={wikiSearching} />

        {/* Card 3: Variants by Language */}
        <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
            Variants by Language
          </h3>
          <div className="space-y-2.5">
            {Object.entries(variantsByLang).map(([lang, variants]) => (
              <div key={lang}>
                <p className="text-xs font-medium text-[var(--muted)] mb-1">
                  {BOOK_LANG_FLAGS[lang] || "?"}{" "}
                  <span className="opacity-70">{lang}</span>
                </p>
                <div className="flex flex-wrap gap-1">
                  {variants.slice(0, 10).map((v) => (
                    <span
                      key={v}
                      className="px-1.5 py-0.5 text-[11px] rounded bg-[var(--border)]/50 text-[var(--foreground)]"
                    >
                      {v}
                    </span>
                  ))}
                  {variants.length > 10 && (
                    <span className="px-1.5 py-0.5 text-[11px] text-[var(--muted)]">
                      +{variants.length - 10} more
                    </span>
                  )}
                </div>
              </div>
            ))}
          </div>
        </div>
      </div>

      {/* ─── 3b. Cross-References Panel (full-width) ─── */}
      {cluster.cross_references && cluster.cross_references.filter(r => r.target_cluster_id !== null).length > 0 && (() => {
        const refs = cluster.cross_references!.filter(r => r.target_cluster_id !== null);
        const synonyms = refs.filter(r => r.link_type === "same_referent" || r.link_type === "cross_linguistic" || r.link_type === "orthographic_variant");
        const contested = refs.filter(r => r.link_type === "contested_identity");
        const related = refs.filter(r => r.link_type === "conceptual_overlap" || r.link_type === "derivation");

        const LINK_TYPE_LABELS: Record<string, { label: string; color: string }> = {
          same_referent: { label: "synonym", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
          cross_linguistic: { label: "translation", color: "bg-blue-500/15 text-blue-700 dark:text-blue-400" },
          orthographic_variant: { label: "variant", color: "bg-slate-500/15 text-slate-700 dark:text-slate-400" },
          contested_identity: { label: "contested", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
          conceptual_overlap: { label: "related", color: "bg-purple-500/15 text-purple-700 dark:text-purple-400" },
          derivation: { label: "derived", color: "bg-cyan-500/15 text-cyan-700 dark:text-cyan-400" },
        };

        const RefItem = ({ xref: r }: { xref: CrossReference }) => {
          const typeInfo = LINK_TYPE_LABELS[r.link_type] || { label: r.link_type, color: "bg-gray-500/15 text-gray-600" };
          const targetSlug = r.target_cluster_id !== null
            ? (() => {
                const targetCluster = data.clusters.find(c => c.id === r.target_cluster_id);
                return targetCluster ? clusterSlug(targetCluster, data.clusters) : null;
              })()
            : null;
          return (
            <div className="flex items-start gap-2 py-1.5 group">
              <span className={`shrink-0 px-1.5 py-0.5 rounded text-[10px] font-medium mt-0.5 ${typeInfo.color}`}>
                {typeInfo.label}
              </span>
              <div className="flex-1 min-w-0">
                <div className="flex items-baseline gap-1.5 flex-wrap">
                  {targetSlug ? (
                    <Link
                      href={`/concordance/${targetSlug}?from=${encodeURIComponent(slug)}`}
                      className="text-sm font-medium hover:text-[var(--accent)] transition-colors"
                    >
                      {r.found_name}
                    </Link>
                  ) : (
                    <span className="text-sm font-medium">{r.found_name}</span>
                  )}
                  {r.target_cluster_name && r.target_cluster_name !== r.found_name && (
                    <span className="text-xs text-[var(--muted)]">
                      ({r.target_cluster_name})
                    </span>
                  )}
                  <span className="text-[10px] text-[var(--muted)] font-mono">
                    {BOOK_SHORT_NAMES[r.source_book] || r.source_book}
                  </span>
                </div>
                {r.evidence_snippet && (
                  <p className="text-[11px] text-[var(--muted)] leading-relaxed mt-0.5 line-clamp-2">
                    &ldquo;{r.evidence_snippet.slice(0, 150)}{r.evidence_snippet.length > 150 ? "\u2026" : ""}&rdquo;
                  </p>
                )}
              </div>
            </div>
          );
        };

        // Check if we have content for at least one column
        const hasContent = synonyms.length > 0 || contested.length > 0 || related.length > 0;
        if (!hasContent) return null;

        return (
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)] mb-8">
            <div className="grid md:grid-cols-3 gap-6">
              {/* Column 1: Synonyms & Translations */}
              <div>
                <h4 className="text-[10px] uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Synonyms &amp; Translations
                  {synonyms.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{synonyms.length}</span>
                  )}
                </h4>
                {synonyms.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {synonyms.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {synonyms.length > 8 && (
                      <p className="text-[10px] text-[var(--muted)] pt-2">
                        +{synonyms.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>

              {/* Column 2: Contested Identities */}
              <div>
                <h4 className="text-[10px] uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Contested Identities
                  {contested.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{contested.length}</span>
                  )}
                </h4>
                {contested.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {contested.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {contested.length > 8 && (
                      <p className="text-[10px] text-[var(--muted)] pt-2">
                        +{contested.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>

              {/* Column 3: Related Entities */}
              <div>
                <h4 className="text-[10px] uppercase tracking-wider text-[var(--muted)] font-medium mb-2 pb-1.5 border-b border-[var(--border)]">
                  Related Entities
                  {related.length > 0 && (
                    <span className="ml-1.5 font-mono opacity-60">{related.length}</span>
                  )}
                </h4>
                {related.length > 0 ? (
                  <div className="divide-y divide-[var(--border)]/40">
                    {related.slice(0, 8).map((r, i) => <RefItem key={i} xref={r} />)}
                    {related.length > 8 && (
                      <p className="text-[10px] text-[var(--muted)] pt-2">
                        +{related.length - 8} more
                      </p>
                    )}
                  </div>
                ) : (
                  <p className="text-xs text-[var(--muted)] opacity-50 py-2">None found</p>
                )}
              </div>
            </div>
          </div>
        );
      })()}

      {/* ─── 4. Mention Distribution Chart ─── */}
      <section className="mb-8">
        <h2 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Mention Distribution
        </h2>
        <div className="space-y-2">
          {mentionsByBook.map(({ book_id, count }) => {
            const book = data.books.find((b) => b.id === book_id);
            const pct = (count / maxMentions) * 100;
            return (
              <div key={book_id} className="flex items-center gap-3">
                <div className="w-24 shrink-0 flex items-center gap-1.5 text-xs">
                  <span className="font-mono text-[var(--muted)]">
                    {BOOK_LANG_FLAGS[book?.language || ""] || "?"}
                  </span>
                  <span className="truncate">
                    {BOOK_SHORT_NAMES[book_id] || book?.title || book_id}
                  </span>
                </div>
                <div className="flex-1 h-5 bg-[var(--border)]/30 rounded overflow-hidden">
                  <div
                    className={`h-full rounded ${CATEGORY_BAR_COLORS[cluster.category] || "bg-gray-500"} transition-all`}
                    style={{ width: `${Math.max(pct, 2)}%` }}
                  />
                </div>
                <span className="w-10 text-right text-xs font-mono text-[var(--muted)] tabular-nums">
                  {count}
                </span>
              </div>
            );
          })}
        </div>
      </section>

      {/* ─── 5. Names Across Texts Mosaic ─── */}
      <section className="mb-8">
        <h2 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          Names Across Texts
        </h2>
        <div className="space-y-4">
          {data.books
            .filter((b) => cluster.members.some((m) => m.book_id === b.id))
            .map((book) => {
              const bookMembers = cluster.members.filter((m) => m.book_id === book.id);
              return (
                <div key={book.id}>
                  <h3 className="text-xs font-medium mb-2 flex items-center gap-2">
                    <span>{BOOK_SHORT_NAMES[book.id] || book.title}</span>
                    <span className="text-[var(--muted)]">{book.year}</span>
                    <span className="font-mono text-[var(--muted)] text-[11px]">
                      {BOOK_LANG_FLAGS[book.language] || "?"}
                    </span>
                  </h3>
                  <div className="flex flex-wrap gap-2">
                    {bookMembers.map((member) => (
                      <Link
                        key={member.entity_id}
                        href={`/books/${encodeURIComponent(book.id)}/entity/${encodeURIComponent(member.entity_id)}`}
                        className="group/tile px-3 py-2 rounded-lg border border-[var(--border)] bg-[var(--card)] hover:bg-[var(--border)]/40 transition-colors"
                      >
                        <span className="text-sm font-medium group-hover/tile:text-[var(--accent)] transition-colors">
                          {member.name}
                        </span>
                        <span className="text-xs text-[var(--muted)] ml-2 font-mono tabular-nums">
                          {member.count}
                        </span>
                        {member.variants.length > 1 && (
                          <span className="text-[10px] text-[var(--muted)] ml-1.5">
                            ({member.variants.length} variants)
                          </span>
                        )}
                      </Link>
                    ))}
                  </div>
                </div>
              );
            })}
        </div>
      </section>

      {/* ─── 6. Comparison Table ─── */}
      <section className="mb-8">
        <h2 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
          All Entries
        </h2>
        <div className="border border-[var(--border)] rounded-lg overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-[var(--border)] bg-[var(--card)]">
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium w-10">
                    Lang
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium">
                    Book
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium">
                    Name
                  </th>
                  <th className="text-left px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium hidden md:table-cell">
                    Context
                  </th>
                  <th className="text-right px-3 py-2 text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium w-14">
                    Count
                  </th>
                  <th className="px-3 py-2 w-16" />
                </tr>
              </thead>
              <tbody className="divide-y divide-[var(--border)]">
                {[...cluster.members]
                  .sort((a, b) => b.count - a.count)
                  .map((member) => {
                    const book = data.books.find((b) => b.id === member.book_id);
                    return (
                      <tr
                        key={`${member.book_id}-${member.entity_id}`}
                        className="hover:bg-[var(--border)]/20 transition-colors"
                      >
                        <td className="px-3 py-2 font-mono text-xs text-[var(--muted)]">
                          {BOOK_LANG_FLAGS[book?.language || ""] || "?"}
                        </td>
                        <td className="px-3 py-2 text-xs">
                          {BOOK_SHORT_NAMES[member.book_id] || book?.title || member.book_id}
                        </td>
                        <td className="px-3 py-2">
                          <span className="font-medium">{member.name}</span>
                          {member.variants.length > 1 && (
                            <span className="text-xs text-[var(--muted)] ml-1.5">
                              +{member.variants.length - 1} variant{member.variants.length - 1 !== 1 ? "s" : ""}
                            </span>
                          )}
                        </td>
                        <td className="px-3 py-2 text-xs text-[var(--muted)] hidden md:table-cell max-w-xs truncate">
                          {member.contexts[0]
                            ? `"${member.contexts[0].length > 100 ? member.contexts[0].slice(0, 97) + "\u2026" : member.contexts[0]}"`
                            : ""}
                        </td>
                        <td className="px-3 py-2 text-right font-mono text-xs tabular-nums">
                          {member.count}
                        </td>
                        <td className="px-3 py-2 text-right">
                          <Link
                            href={`/books/${encodeURIComponent(member.book_id)}/entity/${encodeURIComponent(member.entity_id)}`}
                            className="text-xs text-[var(--accent)] hover:underline whitespace-nowrap"
                          >
                            View &rarr;
                          </Link>
                        </td>
                      </tr>
                    );
                  })}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* ─── 7. Navigation ─── */}
      <nav className="flex items-center justify-between pt-6 border-t border-[var(--border)]">
        {prevSlug !== null ? (
          <Link
            href={`/concordance/${prevSlug}`}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--border)]/30 transition-colors"
          >
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M15 19l-7-7 7-7" />
            </svg>
            Previous
          </Link>
        ) : (
          <span />
        )}
        <Link
          href="/concordance"
          className="px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
        >
          Back to Concordance
        </Link>
        {nextSlug !== null ? (
          <Link
            href={`/concordance/${nextSlug}`}
            className="inline-flex items-center gap-2 px-3 py-2 text-sm text-[var(--muted)] hover:text-[var(--foreground)] border border-[var(--border)] rounded-lg hover:bg-[var(--border)]/30 transition-colors"
          >
            Next
            <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M9 5l7 7-7 7" />
            </svg>
          </Link>
        ) : (
          <span />
        )}
      </nav>

      {/* Keyboard hint */}
      <p className="text-[10px] text-[var(--muted)] mt-4 text-center opacity-40">
        Use arrow keys to navigate between clusters &middot; Escape to return to list
      </p>
    </div>
  );
}
