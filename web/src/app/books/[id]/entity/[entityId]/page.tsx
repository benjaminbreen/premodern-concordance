"use client";

import React, { useEffect, useState, useCallback } from "react";
import Link from "next/link";
import { useParams, useRouter } from "next/navigation";

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

const CATEGORY_COLORS: Record<string, string> = {
  PERSON: "bg-purple-500/20 text-purple-600 dark:text-purple-400 border-purple-500/30",
  PLANT: "bg-emerald-500/20 text-emerald-600 dark:text-emerald-400 border-emerald-500/30",
  ANIMAL: "bg-lime-500/20 text-lime-600 dark:text-lime-400 border-lime-500/30",
  SUBSTANCE: "bg-cyan-500/20 text-cyan-600 dark:text-cyan-400 border-cyan-500/30",
  CONCEPT: "bg-amber-500/20 text-amber-600 dark:text-amber-400 border-amber-500/30",
  DISEASE: "bg-red-500/20 text-red-600 dark:text-red-400 border-red-500/30",
  PLACE: "bg-green-500/20 text-green-600 dark:text-green-400 border-green-500/30",
  OBJECT: "bg-slate-500/20 text-slate-600 dark:text-slate-400 border-slate-500/30",
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
};

function HighlightedExcerpt({ excerpt, term }: { excerpt: string; term: string }) {
  const escaped = term.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
  const parts = excerpt.split(new RegExp(`(${escaped})`, "gi"));
  return (
    <span className="text-[var(--muted)]">
      ...{parts.map((part, i) =>
        part.toLowerCase() === term.toLowerCase() ? (
          <strong key={i} className="text-[var(--foreground)] bg-[var(--accent)]/10 px-0.5 rounded">
            {part}
          </strong>
        ) : (
          <React.Fragment key={i}>{part}</React.Fragment>
        )
      )}...
    </span>
  );
}

function TranslatableExcerpt({
  excerpt,
  term,
  language,
}: {
  excerpt: string;
  term: string;
  language: string;
}) {
  const [showTranslation, setShowTranslation] = useState(false);
  const [translation, setTranslation] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(false);

  const handleClick = useCallback(async () => {
    // If we already have a translation, just toggle
    if (translation) {
      setShowTranslation((prev) => !prev);
      return;
    }

    // Fetch translation
    setLoading(true);
    setError(false);
    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: excerpt, language }),
      });
      const data = await res.json();
      if (data.error) {
        setError(true);
      } else {
        setTranslation(data.translation);
        setShowTranslation(true);
      }
    } catch {
      setError(true);
    } finally {
      setLoading(false);
    }
  }, [excerpt, language, translation]);

  // Don't offer translation for English texts
  const isEnglish = language === "English";

  return (
    <div>
      <div className="text-sm leading-relaxed">
        {showTranslation && translation ? (
          <span className="text-[var(--muted)]">
            ...{translation}...
          </span>
        ) : (
          <HighlightedExcerpt excerpt={excerpt} term={term} />
        )}
      </div>
      {!isEnglish && (
        <button
          onClick={handleClick}
          disabled={loading}
          className="mt-1.5 inline-flex items-center gap-1.5 text-xs text-[var(--muted)] hover:text-[var(--accent)] transition-colors disabled:opacity-50"
        >
          {loading ? (
            <>
              <div className="w-3 h-3 border border-[var(--accent)] border-t-transparent rounded-full animate-spin" />
              Translating...
            </>
          ) : error ? (
            <span className="text-red-500">Translation failed - click to retry</span>
          ) : showTranslation ? (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
              </svg>
              Show original
            </>
          ) : (
            <>
              <svg className="w-3.5 h-3.5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 5h12M9 3v2m1.048 9.5A18.022 18.022 0 016.412 9m6.088 9h7M11 21l5-10 5 10M12.751 5C11.783 10.77 8.07 15.61 3 18.129" />
              </svg>
              Translate to English
            </>
          )}
        </button>
      )}
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

export default function EntityDetailPage() {
  const params = useParams();
  const router = useRouter();
  const [entity, setEntity] = useState<Entity | null>(null);
  const [bookTitle, setBookTitle] = useState("");
  const [bookLanguage, setBookLanguage] = useState("");
  const [loading, setLoading] = useState(true);
  const [wikiData, setWikiData] = useState<WikiData | null>(null);
  const [entityIds, setEntityIds] = useState<string[]>([]);
  const [currentIndex, setCurrentIndex] = useState(-1);

  useEffect(() => {
    const bookFiles: Record<string, string> = {
      "semedo-polyanthea-1741": "/data/semedo_entities.json",
      "english_physician_1652": "/data/culpeper_entities.json",
      "coloquios_da_orta_1563": "/data/orta_entities.json",
      "historia_medicinal_monardes_1574": "/data/monardes_entities.json",
      "relation_historique_humboldt_vol3_1825": "/data/humboldt_entities.json",
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
          setBookLanguage(data.book.language || "");
          // Store the full entity ID list (sorted by count desc, matching book page order)
          const ids = data.entities.map((e: Entity) => e.id);
          setEntityIds(ids);
          const idx = ids.indexOf(params.entityId as string);
          setCurrentIndex(idx);
          const found = data.entities.find(
            (e: Entity) => e.id === params.entityId
          );
          if (found) {
            setEntity(found);
            break;
          }
        }
      }
      setLoading(false);
    });
  }, [params.id, params.entityId]);

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
            {mentions.map((mention, idx) => (
              <div
                key={idx}
                className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]"
              >
                <div className="flex items-start gap-3">
                  <span className="text-xs text-[var(--muted)] font-mono mt-1 shrink-0">
                    {idx + 1}.
                  </span>
                  <TranslatableExcerpt
                    excerpt={mention.excerpt}
                    term={mention.matched_term}
                    language={bookLanguage}
                  />
                </div>
              </div>
            ))}
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
