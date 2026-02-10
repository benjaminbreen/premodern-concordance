"use client";

import React, { useEffect, useState, useCallback, useRef, useMemo } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { CAT_BADGE as CATEGORY_COLORS, CAT_TINT as CATEGORY_TINT } from "@/lib/colors";
import {
  buildEntityNameIndex,
  buildSlugMap,
  AutoLinkedText,
  type ClusterPreview,
} from "@/components/EntityHoverCard";

interface Mention {
  offset: number;
  matched_term: string;
  excerpt: string;
}

interface Entity {
  id: string;
  name: string;
  category: string;
  subcategory?: string;
  count: number;
  contexts: string[];
  variants: string[];
  mentions?: Mention[];
}


function HighlightedExcerpt({
  excerpt,
  term,
  nameIndex,
  excludeClusterId,
}: {
  excerpt: string;
  term: string;
  nameIndex?: Map<string, ClusterPreview>;
  excludeClusterId?: number;
}) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = excerpt.split(new RegExp(`(${escaped})`, "gi"));
  return (
    <span className="text-[var(--muted)]">
      ...{parts.map((part, i) =>
        part.toLowerCase() === term.toLowerCase() ? (
          <strong key={i} className="text-[var(--foreground)] bg-[var(--accent)]/10 px-0.5 rounded">
            {part}
          </strong>
        ) : nameIndex && nameIndex.size > 0 ? (
          <AutoLinkedText key={i} text={part} nameIndex={nameIndex} excludeClusterId={excludeClusterId} />
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}...
    </span>
  );
}

function ExcerptCard({
  mention,
  idx,
  bookId,
  bookLanguage,
  bookTitle,
  bookAuthor,
  bookYear,
  nameIndex,
  excludeClusterId,
  pageMap,
  pageNums,
  pageMapIaId,
}: {
  mention: Mention;
  idx: number;
  bookId: string;
  bookLanguage: string;
  bookTitle: string;
  bookAuthor: string;
  bookYear: number;
  nameIndex?: Map<string, ClusterPreview>;
  excludeClusterId?: number;
  pageMap: Record<string, number> | null;
  pageNums: Record<string, string> | null;
  pageMapIaId: string | null;
}) {
  const [showTranslation, setShowTranslation] = useState(false);
  const [translation, setTranslation] = useState<string | null>(null);
  const [translating, setTranslating] = useState(false);
  const [translateError, setTranslateError] = useState(false);
  const [citeOpen, setCiteOpen] = useState(false);
  const [copied, setCopied] = useState<string | null>(null);
  const citeRef = useRef<HTMLDivElement>(null);

  const isEnglish = bookLanguage === "English";

  const handleTranslate = useCallback(async () => {
    if (translation) {
      setShowTranslation((prev) => !prev);
      return;
    }
    setTranslating(true);
    setTranslateError(false);
    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: mention.excerpt, language: bookLanguage }),
      });
      const data = await res.json();
      if (data.error) {
        setTranslateError(true);
      } else {
        setTranslation(data.translation);
        setShowTranslation(true);
      }
    } catch {
      setTranslateError(true);
    } finally {
      setTranslating(false);
    }
  }, [mention.excerpt, bookLanguage, translation]);

  // Close cite dropdown on outside click
  useEffect(() => {
    if (!citeOpen) return;
    const handler = (e: MouseEvent) => {
      if (citeRef.current && !citeRef.current.contains(e.target as Node)) {
        setCiteOpen(false);
      }
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [citeOpen]);

  // Page/source lookup
  const offsetStr = String(mention.offset);
  const leaf = pageMap?.[offsetStr];
  const printedPage = pageNums?.[offsetStr];
  const iaId = pageMapIaId || BOOK_IA_IDS[bookId];
  const directPageUrl =
    leaf && iaId ? `https://archive.org/details/${iaId}/page/n${leaf}` : null;
  const iaUrl =
    directPageUrl ||
    buildIASearchUrl(bookId, mention.excerpt, mention.matched_term);
  const displayPage = printedPage || (leaf ? String(leaf) : null);

  // Citation generation
  const authorParts = bookAuthor.split(" ");
  const lastName = authorParts[authorParts.length - 1];
  const firstName = authorParts.slice(0, -1).join(" ");
  const pg = displayPage;

  const formats = [
    {
      key: "chicago",
      label: "Chicago",
      plain: `${bookAuthor}, ${bookTitle} (${bookYear})${pg ? ", " + pg : ""}.`,
      rendered: (
        <>
          {bookAuthor}, <em>{bookTitle}</em> ({bookYear})
          {pg ? `, ${pg}` : ""}.
        </>
      ),
    },
    {
      key: "apa",
      label: "APA",
      plain: `${lastName}, ${firstName ? firstName[0] + ". " : ""}(${bookYear}). ${bookTitle}.${pg ? " p. " + pg + "." : ""}`,
      rendered: (
        <>
          {lastName}, {firstName ? firstName[0] + ". " : ""}({bookYear}).{" "}
          <em>{bookTitle}</em>.{pg ? ` p. ${pg}.` : ""}
        </>
      ),
    },
    {
      key: "mla",
      label: "MLA",
      plain: `${lastName}, ${firstName}. ${bookTitle}. ${bookYear}${pg ? ", p. " + pg : ""}.`,
      rendered: (
        <>
          {lastName}, {firstName}. <em>{bookTitle}</em>. {bookYear}
          {pg ? `, p. ${pg}` : ""}.
        </>
      ),
    },
  ];

  const handleCopy = async (key: string) => {
    const fmt = formats.find((f) => f.key === key);
    if (!fmt) return;
    await navigator.clipboard.writeText(fmt.plain);
    setCopied(key);
    setTimeout(() => setCopied(null), 1500);
  };

  return (
    <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
      <div className="flex items-start gap-3">
        <span className="text-xs text-[var(--muted)] font-mono mt-1 shrink-0">
          {idx + 1}.
        </span>
        <div className="flex-1 min-w-0 text-sm leading-relaxed">
          {showTranslation && translation ? (
            <span className="text-[var(--muted)]">...{translation}...</span>
          ) : (
            <HighlightedExcerpt
              excerpt={mention.excerpt}
              term={mention.matched_term}
              nameIndex={nameIndex}
              excludeClusterId={excludeClusterId}
            />
          )}
        </div>
      </div>

      {/* Toolbar */}
      <div className="grid grid-cols-3 items-center mt-3 pt-2 border-t border-[var(--border)]/40">
        {/* Left: Translate */}
        <div>
          {!isEnglish && (
            <button
              onClick={handleTranslate}
              disabled={translating}
              className="text-[11px] px-2.5 py-1 rounded border border-[var(--border)] text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all disabled:opacity-50 tracking-wide"
            >
              {translating
                ? "Translating\u2026"
                : translateError
                  ? "Retry"
                  : showTranslation
                    ? "Original"
                    : "Translate"}
            </button>
          )}
        </div>

        {/* Center: Page / Source */}
        <div className="text-center">
          {iaUrl && (
            <a
              href={iaUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="text-[11px] text-[var(--muted)] hover:text-[var(--accent)] transition-colors tracking-wide inline-flex items-center gap-1 justify-center"
            >
              {displayPage ? (
                <span className="font-mono">p.&thinsp;{displayPage}</span>
              ) : (
                "Source text"
              )}
              <svg
                className="w-2.5 h-2.5 opacity-50"
                fill="none"
                stroke="currentColor"
                viewBox="0 0 24 24"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14"
                />
              </svg>
            </a>
          )}
        </div>

        {/* Right: Cite */}
        <div className="text-right relative" ref={citeRef}>
          <button
            onClick={() => setCiteOpen((o) => !o)}
            className="text-[11px] px-2.5 py-1 rounded border border-[var(--border)] text-[var(--muted)] hover:border-[var(--accent)] hover:text-[var(--accent)] transition-all tracking-wide"
          >
            Cite
          </button>
          {citeOpen && (
            <div className="absolute right-0 bottom-full mb-2 w-72 bg-[var(--card)] border border-[var(--border)] rounded-lg shadow-lg z-50 p-1">
              {formats.map(({ key, label, rendered }) => (
                <button
                  key={key}
                  onClick={() => handleCopy(key)}
                  className="w-full text-left px-3 py-2.5 rounded-md hover:bg-[var(--accent)]/10 transition-colors cursor-pointer group"
                >
                  <span className="flex items-center justify-between mb-1">
                    <span className="text-[10px] uppercase tracking-[0.15em] text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors">
                      {label}
                    </span>
                    <span className={`text-[10px] transition-colors ${copied === key ? "text-[var(--accent)]" : "text-[var(--muted)] opacity-0 group-hover:opacity-100"}`}>
                      {copied === key ? "Copied!" : "Click to copy"}
                    </span>
                  </span>
                  <p className="text-xs leading-relaxed text-[var(--foreground)]">
                    {rendered}
                  </p>
                </button>
              ))}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

interface WikiData {
  imageUrl: string | null;
  extract: string;
  pageUrl: string;
}

const LANG_TO_WIKI: Record<string, string> = {
  Portuguese: "pt",
  Spanish: "es",
  French: "fr",
  Italian: "it",
  German: "de",
  Dutch: "nl",
  Latin: "la",
  English: "en",
};

async function tryWikipedia(searchName: string, lang: string): Promise<WikiData | null> {
  try {
    const res = await fetch(
      `https://${lang}.wikipedia.org/api/rest_v1/page/summary/${encodeURIComponent(searchName)}`
    );
    if (!res.ok) return null;

    const data = await res.json();
    // Skip disambiguation pages
    if (data.type === "disambiguation") return null;

    const imageUrl = data.thumbnail?.source
      ? (data.originalimage?.source || data.thumbnail.source.replace(/\/\d+px-/, "/800px-"))
      : null;

    return {
      imageUrl,
      extract: "",
      pageUrl: data.content_urls?.desktop?.page || `https://${lang}.wikipedia.org/wiki/${encodeURIComponent(searchName)}`,
    };
  } catch {
    return null;
  }
}

async function fetchWikipediaData(entityName: string, bookLanguage?: string): Promise<WikiData | null> {
  const searchName = entityName
    .replace(/[()]/g, "")
    .replace(/ſ/g, "s")  // long s
    .trim();

  // Try the book's language Wikipedia first, then fall back to English
  const primaryLang = LANG_TO_WIKI[bookLanguage || ""] || "en";
  const langsToTry = primaryLang !== "en" ? [primaryLang, "en"] : ["en"];

  for (const lang of langsToTry) {
    const result = await tryWikipedia(searchName, lang);
    if (result) return result;
  }
  return null;
}

const BOOK_IA_IDS: Record<string, string> = {
  "english_physician_1652": "b30335310",
  "polyanthea_medicinal": "b3040941x",
  "coloquios_da_orta_1563": "coloquiosdossimp01ortauoft",
  "historia_medicinal_monardes_1574": "primeraysegunda01monagoog",
  "relation_historique_humboldt_vol3_1825": "relationhistoriq03humb",
  "ricettario_fiorentino_1597": "hin-wel-all-00000667-001",
  "principles_of_psychology_james_1890": "theprinciplesofp01jameuoft",
};

function buildIASearchUrl(bookId: string, excerpt: string, term: string): string | null {
  const iaId = BOOK_IA_IDS[bookId];
  if (!iaId) return null;
  // Clean excerpt: remove line-break hyphens, OCR artifacts, normalize whitespace
  const cleaned = excerpt
    .replace(/\u00AD/g, "")       // soft hyphens
    .replace(/-\s+/g, "")         // line-break hyphens
    .replace(/[^\w\s\u00C0-\u024F]/g, " ")  // strip punctuation
    .replace(/\s+/g, " ")
    .trim();
  const words = cleaned.split(" ").filter(w => w.length > 1);
  if (words.length < 2) return null;
  // Pick 3 words from near the middle of the excerpt (less likely to be cut off)
  const mid = Math.floor(words.length / 2);
  const start = Math.max(0, mid - 1);
  const phrase = words.slice(start, start + 3).join(" ");
  // Wrap in quotes for exact phrase matching on IA
  return `https://archive.org/details/${iaId}?q=${encodeURIComponent(`"${phrase}"`)}`;
}

function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

interface ConcordanceCluster {
  id: number;
  canonical_name: string;
  category: string;
  members: { entity_id: string; book_id: string }[];
}

export default function EntityDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [entity, setEntity] = useState<Entity | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [bookAuthor, setBookAuthor] = useState("");
  const [bookYear, setBookYear] = useState(0);
  const [bookLanguage, setBookLanguage] = useState("");
  const [loading, setLoading] = useState(true);
  const [wikiData, setWikiData] = useState<WikiData | null>(null);
  const [entityIds, setEntityIds] = useState<string[]>([]);
  const [currentIndex, setCurrentIndex] = useState(-1);
  const [concordanceSlug, setConcordanceSlug] = useState<string | null>(null);
  const [concordanceName, setConcordanceName] = useState<string | null>(null);
  const [concordanceClusterId, setConcordanceClusterId] = useState<number | undefined>(undefined);
  const [allEntities, setAllEntities] = useState<Entity[]>([]);
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  const [concordanceClusters, setConcordanceClusters] = useState<any[]>([]);
  const [pageMap, setPageMap] = useState<Record<string, number> | null>(null);
  const [pageNums, setPageNums] = useState<Record<string, string> | null>(null);
  const [pageMapIaId, setPageMapIaId] = useState<string | null>(null);

  const nameIndex = useMemo(() => {
    if (concordanceClusters.length === 0) return new Map<string, ClusterPreview>();
    const slugMap = buildSlugMap(concordanceClusters);
    return buildEntityNameIndex(concordanceClusters, slugMap);
  }, [concordanceClusters]);

  useEffect(() => {
    const bookFiles: Record<string, string> = {
      "semedo-polyanthea-1741": "/data/semedo_entities.json",
      "polyanthea_medicinal": "/data/semedo_entities.json",
      "english_physician_1652": "/data/culpeper_entities.json",
      "coloquios_da_orta_1563": "/data/orta_entities.json",
      "historia_medicinal_monardes_1574": "/data/monardes_entities.json",
      "relation_historique_humboldt_vol3_1825": "/data/humboldt_entities.json",
      "ricettario_fiorentino_1597": "/data/ricettario_entities.json",
      "principles_of_psychology_james_1890": "/data/james_psychology_entities.json",
      "origin_of_species_darwin_1859": "/data/darwin_origin_entities.json",
    };

    const dataFile = bookFiles[params.id as string];
    const filesToSearch = dataFile ? [dataFile] : Object.values(bookFiles);

    Promise.all(
      filesToSearch.map((f) => fetch(f).then((res) => res.json()).catch(() => null))
    ).then((results) => {
      for (const data of results) {
        if (!data) continue;
        if (dataFile || data.book.id === params.id) {
          setBookTitle(data.book.title);
          setBookAuthor(data.book.author || "");
          setBookYear(data.book.year || 0);
          setBookLanguage(data.book.language || "");
          // Store the full entity ID list (sorted by count desc, matching book page order)
          const ids = data.entities.map((e: Entity) => e.id);
          setEntityIds(ids);
          const rawEntityId = params.entityId as string;
          const entityId = decodeURIComponent(rawEntityId).normalize("NFC");
          const idx = ids.indexOf(entityId);
          setCurrentIndex(idx);
          const found = data.entities.find(
            (e: Entity) => e.id.normalize("NFC") === entityId
          );
          if (found) {
            setEntity(found);
            setAllEntities(data.entities);
            break;
          }
        }
      }
      setLoading(false);
    });
  }, [params.id, params.entityId]);

  // Find matching concordance cluster + load clusters for entity hover cards
  useEffect(() => {
    if (!entity) return;
    // Map URL book IDs to concordance book IDs (only Semedo differs)
    const urlBookId = params.id as string;
    const bookId = urlBookId === "semedo-polyanthea-1741" ? "polyanthea_medicinal" : urlBookId;
    const entityId = decodeURIComponent(params.entityId as string).normalize("NFC");

    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((data) => {
        const clusters: ConcordanceCluster[] = data.clusters;
        // Store full clusters for nameIndex building
        setConcordanceClusters(data.clusters);
        const match = clusters.find((c) =>
          c.members.some((m) => m.book_id === bookId && m.entity_id === entityId)
        );
        if (match) {
          const base = slugify(match.canonical_name);
          const hasCollision = clusters.some(
            (c) => c.id !== match.id && slugify(c.canonical_name) === base
          );
          setConcordanceSlug(hasCollision ? `${base}-${match.id}` : base);
          setConcordanceName(match.canonical_name);
          setConcordanceClusterId(match.id);
        }
      })
      .catch(() => {});
  }, [entity, params.id, params.entityId]);

  // Load page map for IA page links
  useEffect(() => {
    const bookId = (params.id as string) === "semedo-polyanthea-1741" ? "polyanthea_medicinal" : params.id as string;
    fetch(`/data/page_maps/${bookId}.json`)
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data?.leaves) {
          setPageMap(data.leaves);
          setPageMapIaId(data.ia_id);
          if (data.pages) setPageNums(data.pages);
        }
      })
      .catch(() => {});
  }, [params.id]);

  // Fetch Wikipedia data when entity loads
  useEffect(() => {
    if (!entity) return;
    setWikiData(null); // Reset for new entity
    fetchWikipediaData(entity.name, bookLanguage).then((data) => {
      if (data) setWikiData(data);
    });
  }, [entity, bookLanguage]);

  const navigateTo = useCallback((direction: "prev" | "next") => {
    if (entityIds.length === 0 || currentIndex === -1) return;
    const newIndex = direction === "next"
      ? Math.min(currentIndex + 1, entityIds.length - 1)
      : Math.max(currentIndex - 1, 0);
    if (newIndex !== currentIndex) {
      router.push(`/books/${params.id}/entity/${entityIds[newIndex]}`);
    }
  }, [entityIds, currentIndex, params.id, router]);

  // Keyboard navigation
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      // Don't navigate if user is typing in an input
      if (e.target instanceof HTMLInputElement || e.target instanceof HTMLTextAreaElement) return;
      if (e.key === "ArrowRight" || e.key === "ArrowDown") {
        e.preventDefault();
        navigateTo("next");
      } else if (e.key === "ArrowLeft" || e.key === "ArrowUp") {
        e.preventDefault();
        navigateTo("prev");
      }
    }
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [navigateTo]);

  if (loading) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-[var(--border)] rounded w-1/4"></div>
          <div className="h-4 bg-[var(--border)] rounded w-1/2"></div>
          <div className="h-64 bg-[var(--border)] rounded"></div>
        </div>
      </div>
    );
  }

  if (!entity) {
    return (
      <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <p>Entity not found.</p>
        <Link href={`/books/${params.id}`} className="text-[var(--accent)] hover:underline mt-4 block">
          Back to book
        </Link>
      </div>
    );
  }

  const badgeClass = CATEGORY_COLORS[entity.category] || "bg-[var(--border)]";
  const tintColor = CATEGORY_TINT[entity.category] || "rgba(100, 116, 139, 0.25)";
  const mentions = entity.mentions || [];

  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Breadcrumb */}
      <nav className="mb-6 text-sm">
        <Link href="/books" className="text-[var(--muted)] hover:text-[var(--foreground)]">
          Books
        </Link>
        <span className="text-[var(--muted)] mx-2">/</span>
        <Link href={`/books/${params.id}`} className="text-[var(--muted)] hover:text-[var(--foreground)]">
          {bookTitle}
        </Link>
        <span className="text-[var(--muted)] mx-2">/</span>
        <span>{entity.name}</span>
      </nav>

      {/* Hero Header with Wikipedia Image */}
      <div className="relative mb-8 rounded-xl overflow-hidden border border-[var(--border)] bg-[var(--background)]">
        {/* Image layer — fades from invisible on left to visible on right */}
        {wikiData?.imageUrl && (
          <div className="absolute inset-0">
            <img
              src={wikiData.imageUrl}
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
            {/* Subtle bottom fade so image doesn't hard-cut */}
            <div className="absolute inset-x-0 bottom-0 h-12 bg-gradient-to-t from-[var(--background)] to-transparent" />
            <a
              href={wikiData.pageUrl}
              target="_blank"
              rel="noopener noreferrer"
              className="absolute bottom-2 right-3 z-20 text-[10px] text-[var(--muted)] opacity-50 hover:opacity-100 hover:text-[var(--accent)] transition-all cursor-pointer"
            >
              Image: Wikipedia
            </a>
          </div>
        )}

        {/* Content layer — normal page colors */}
        <div className="relative z-10 px-8 py-10" style={{ minHeight: "200px" }}>
          <div className="flex items-start justify-between gap-4">
            <div>
              <div className="flex items-start gap-4 mb-3">
                <h1 className="text-4xl font-bold">{entity.name}</h1>
                <span className={`${badgeClass} px-3 py-1 rounded text-sm font-medium border mt-2`}>
                  {entity.category}
                </span>
              </div>
              {entity.subcategory && entity.subcategory !== `OTHER_${entity.category}` && (
                <p className="text-[var(--muted)] text-sm mb-4">{entity.subcategory.toLowerCase()}</p>
              )}
              <div className="flex gap-6 text-sm text-[var(--muted)]">
                <span><strong className="text-[var(--foreground)]">{entity.count}</strong> occurrences</span>
                <span><strong className="text-[var(--foreground)]">{mentions.length}</strong> excerpts</span>
                <span><strong className="text-[var(--foreground)]">{entity.variants.length}</strong> variants</span>
              </div>
            </div>
            {concordanceSlug && (
              <Link
                href={`/concordance/${concordanceSlug}`}
                title={`View the cross-book concordance page for ${concordanceName}`}
                className="shrink-0 mt-2 inline-flex items-center gap-2 px-4 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--card)]/80 backdrop-blur-sm text-sm font-medium hover:bg-[var(--border)]/60 hover:border-[var(--foreground)]/20 transition-colors"
              >
                <svg className="w-4 h-4 text-[var(--muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={1.5} d="M3.75 6A2.25 2.25 0 016 3.75h2.25A2.25 2.25 0 0110.5 6v2.25a2.25 2.25 0 01-2.25 2.25H6a2.25 2.25 0 01-2.25-2.25V6zM3.75 15.75A2.25 2.25 0 016 13.5h2.25a2.25 2.25 0 012.25 2.25V18a2.25 2.25 0 01-2.25 2.25H6A2.25 2.25 0 013.75 18v-2.25zM13.5 6a2.25 2.25 0 012.25-2.25H18A2.25 2.25 0 0120.25 6v2.25A2.25 2.25 0 0118 10.5h-2.25a2.25 2.25 0 01-2.25-2.25V6zM13.5 15.75a2.25 2.25 0 012.25-2.25H18a2.25 2.25 0 012.25 2.25V18A2.25 2.25 0 0118 20.25h-2.25A2.25 2.25 0 0113.5 18v-2.25z" />
                </svg>
                Concordance
              </Link>
            )}
          </div>
        </div>
      </div>

      {/* Meta cards */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
        <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <div className="text-2xl font-bold">{entity.count}</div>
          <div className="text-xs text-[var(--muted)]">Occurrences</div>
        </div>
        <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <div className="text-2xl font-bold">{mentions.length}</div>
          <div className="text-xs text-[var(--muted)]">Excerpts Found</div>
        </div>
        <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <div className="text-2xl font-bold">{entity.variants.length}</div>
          <div className="text-xs text-[var(--muted)]">Spelling Variants</div>
        </div>
        <div className="p-3 rounded-lg border border-[var(--border)] bg-[var(--card)]">
          <div className="text-2xl font-bold">{entity.contexts.length}</div>
          <div className="text-xs text-[var(--muted)]">Descriptions</div>
        </div>
      </div>

      {/* Variants */}
      {entity.variants.length > 1 && (
        <div className="mb-6">
          <h3 className="text-sm font-medium text-[var(--muted)] mb-2">Spelling Variants</h3>
          <div className="flex flex-wrap gap-2">
            {entity.variants.map((v, i) => (
              <span key={i} className="px-2 py-1 text-sm rounded border border-[var(--border)] bg-[var(--card)]">
                {v}
              </span>
            ))}
          </div>
        </div>
      )}

      {/* Contexts */}
      {entity.contexts.length > 0 && (
        <div className="mb-8">
          <h3 className="text-sm font-medium text-[var(--muted)] mb-2">Descriptions</h3>
          <ul className="list-disc list-inside text-sm text-[var(--muted)] space-y-1">
            {entity.contexts.map((ctx, i) => (
              <li key={i}>{ctx}</li>
            ))}
          </ul>
        </div>
      )}

      {/* All Excerpts */}
      <div>
        <h2 className="text-xl font-semibold mb-4">
          Excerpts from Text
          <span className="text-sm font-normal text-[var(--muted)] ml-2">
            ({mentions.length} found)
          </span>
        </h2>

        {mentions.length === 0 ? (
          <p className="text-[var(--muted)] text-sm">No text excerpts found for this entity.</p>
        ) : (
          <div className="space-y-3">
            {mentions.map((mention, idx) => {
              const resolvedBookId = (params.id as string) === "semedo-polyanthea-1741" ? "polyanthea_medicinal" : params.id as string;
              return (
                <ExcerptCard
                  key={idx}
                  mention={mention}
                  idx={idx}
                  bookId={resolvedBookId}
                  bookLanguage={bookLanguage}
                  bookTitle={bookTitle}
                  bookAuthor={bookAuthor}
                  bookYear={bookYear}
                  nameIndex={nameIndex}
                  excludeClusterId={concordanceClusterId}
                  pageMap={pageMap}
                  pageNums={pageNums}
                  pageMapIaId={pageMapIaId}
                />
              );
            })}
          </div>
        )}
      </div>

      {/* Navigation */}
      <div className="mt-8 pt-6 border-t border-[var(--border)]">
        <div className="flex items-center justify-between">
          <button
            onClick={() => navigateTo("prev")}
            disabled={currentIndex <= 0}
            className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[var(--border)] transition-colors flex items-center gap-2"
          >
            <span>&larr;</span> Previous
          </button>
          <Link
            href={`/books/${params.id}`}
            className="text-[var(--accent)] hover:underline text-sm"
          >
            Back to {bookTitle}
          </Link>
          <button
            onClick={() => navigateTo("next")}
            disabled={currentIndex >= entityIds.length - 1}
            className="px-4 py-2 rounded-lg border border-[var(--border)] text-sm disabled:opacity-30 disabled:cursor-not-allowed hover:bg-[var(--border)] transition-colors flex items-center gap-2"
          >
            Next <span>&rarr;</span>
          </button>
        </div>
        <p className="text-center text-xs text-[var(--muted)] mt-3">
          Use arrow keys to navigate between entities
        </p>
      </div>
    </div>
  );
}
