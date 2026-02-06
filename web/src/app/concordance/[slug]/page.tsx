"use client";

import { useEffect, useState, useCallback, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

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

function WikiExtract({ url }: { url: string }) {
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
      {hasMore && !expanded && (
        <button
          onClick={() => setExpanded(true)}
          className="mt-2 text-xs text-[var(--accent)] hover:underline"
        >
          Keep reading &rarr;
        </button>
      )}
      {expanded && (
        <div className="mt-2 max-h-[280px] overflow-y-auto space-y-3 text-sm text-[var(--foreground)]/80 leading-relaxed border-t border-[var(--border)] pt-2">
          {restOfFirst && <p>{restOfFirst}</p>}
          {paragraphs.slice(1).map((p, i) => (
            <p key={i}>{p}</p>
          ))}
        </div>
      )}
      <p className="text-[9px] text-[var(--muted)] mt-1.5 opacity-40">Source: Wikipedia</p>
    </div>
  );
}

/* ───── main page component ───── */

export default function ClusterDetailPage() {
  const params = useParams();
  const router = useRouter();
  const slug = params.slug as string;

  const [data, setData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);

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
      </nav>

      {/* ─── 2. Compact Header ─── */}
      <header className="mb-8">
        <div className="flex items-start gap-3 flex-wrap">
          {gt?.portrait_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={gt.portrait_url}
              alt={cluster.canonical_name}
              className="w-16 h-20 rounded object-cover border border-[var(--border)] shrink-0"
            />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-3 flex-wrap">
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
      </header>

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
            </div>
          ) : (
            <p className="text-xs text-[var(--muted)]">No identification available.</p>
          )}
        </div>

        {/* Card 2: Wikipedia */}
        {gt?.wikipedia_url ? (
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
            <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
              Wikipedia
            </h3>
            <WikiExtract url={gt.wikipedia_url} />
            <a
              href={gt.wikipedia_url}
              target="_blank"
              rel="noopener noreferrer"
              className="inline-flex items-center gap-1 mt-3 text-xs text-[var(--accent)] hover:underline"
            >
              Read on Wikipedia &rarr;
            </a>
          </div>
        ) : (
          <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
            <h3 className="text-[10px] uppercase tracking-widest text-[var(--muted)] font-medium mb-3">
              Wikipedia
            </h3>
            <p className="text-xs text-[var(--muted)]">No Wikipedia article linked.</p>
          </div>
        )}

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
