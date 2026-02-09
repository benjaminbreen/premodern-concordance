"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import { useBookContext } from "../BookContext";
import { CAT_HEX as CATEGORY_COLORS_HEX, CAT_BADGE as CATEGORY_COLORS_BADGE, CATEGORY_ORDER } from "@/lib/colors";
import { BOOK_COVERS, BOOK_TEXTS } from "@/lib/books";

// ── Interfaces ──────────────────────────────────────────────────────────────

interface BookMetadataEntry {
  description: string;
  internetArchiveUrl: string;
  wikipediaUrl: string | null;
  ngramsTerm: string;
  ngramsYearStart: number;
  tags: string[];
}

// ── Constants ───────────────────────────────────────────────────────────────

const BOOK_METADATA: Record<string, BookMetadataEntry> = {
  polyanthea_medicinal: {
    description:
      "A comprehensive Portuguese materia medica by the Jesuit physician João Curvo Semedo, cataloguing hundreds of medicinal substances drawn from European, Asian, and American traditions. First published in 1697, it became one of the most widely consulted medical references in the Lusophone world.",
    internetArchiveUrl: "https://archive.org/details/polyanthea-medicinal",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Jo%C3%A3o_Curvo_Semedo",
    ngramsTerm: "Polyanthea Medicinal",
    ngramsYearStart: 1690,
    tags: ["materia medica", "Portuguese medicine", "Jesuit science", "early modern pharmacy"],
  },
  english_physician_1652: {
    description:
      "Nicholas Culpeper's famous herbal, combining Galenic humoral theory with astrological medicine and practical botany. It democratized medical knowledge by publishing in English rather than Latin, making it one of the best-selling books of the seventeenth century.",
    internetArchiveUrl: "https://archive.org/details/englishphysician00culp",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Culpeper%27s_Complete_Herbal",
    ngramsTerm: "Culpeper herbal",
    ngramsYearStart: 1650,
    tags: ["herbal", "astrology", "botany", "English medicine"],
  },
  coloquios_da_orta_1563: {
    description:
      "Garcia da Orta's pioneering dialogue on the medicinal simples and drugs of India, published in Goa in 1563. Drawing on decades of firsthand observation and interviews with local practitioners, it was the first European work to systematically describe South Asian materia medica.",
    internetArchiveUrl: "https://archive.org/details/coloquiosdossim00teleGoogle",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Garcia_de_Orta",
    ngramsTerm: "Garcia da Orta",
    ngramsYearStart: 1560,
    tags: ["materia medica", "botany", "Goa", "Portuguese India", "dialogue"],
  },
  historia_medicinal_monardes_1574: {
    description:
      "Nicolás Monardes's landmark account of medicinal plants and substances brought from the New World to Spain. Written from Seville without Monardes ever crossing the Atlantic, it introduced European audiences to tobacco, sassafras, guaiacum, and dozens of other American remedies.",
    internetArchiveUrl: "https://archive.org/details/primerasegundayt00mona",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Nicol%C3%A1s_Monardes",
    ngramsTerm: "Monardes medicinal",
    ngramsYearStart: 1570,
    tags: ["New World drugs", "materia medica", "Seville", "tobacco", "Spanish medicine"],
  },
  relation_historique_humboldt_vol3_1825: {
    description:
      "The third volume of Alexander von Humboldt's monumental account of his five-year expedition across Spanish America (1799–1804). Rich in geographic, botanical, and ethnographic observation, it documents the natural and cultural landscapes of Venezuela, Cuba, and Colombia.",
    internetArchiveUrl: "https://archive.org/details/relationhistoriq03humb",
    wikipediaUrl: "https://en.wikipedia.org/wiki/Alexander_von_Humboldt",
    ngramsTerm: "Humboldt Relation historique",
    ngramsYearStart: 1810,
    tags: ["exploration", "natural history", "geography", "South America", "Enlightenment science"],
  },
  ricettario_fiorentino_1597: {
    description:
      "The official pharmacopoeia of Florence, compiled by the College of Physicians and Apothecaries. This 1597 edition codifies recipes for compound medicines, distillations, and preparations, reflecting the professionalization of pharmacy in late Renaissance Italy.",
    internetArchiveUrl: "https://archive.org/details/ricettariofiorentino1597",
    wikipediaUrl: null,
    ngramsTerm: "Ricettario Fiorentino",
    ngramsYearStart: 1550,
    tags: ["pharmacopoeia", "recipes", "Florence", "Renaissance medicine", "apothecary"],
  },
  principles_of_psychology_james_1890: {
    description:
      "William James's foundational treatise on psychology, published in 1890 after twelve years of writing. It established psychology as a distinct scientific discipline and introduced enduring concepts such as the stream of consciousness and the James-Lange theory of emotion.",
    internetArchiveUrl: "https://archive.org/details/theprinciplesofp01jameuoft",
    wikipediaUrl: "https://en.wikipedia.org/wiki/The_Principles_of_Psychology",
    ngramsTerm: "Principles of Psychology James",
    ngramsYearStart: 1885,
    tags: ["psychology", "consciousness", "pragmatism", "Harvard", "emotion"],
  },
  origin_of_species_darwin_1859: {
    description:
      "Charles Darwin's revolutionary work arguing that species evolve through natural selection. Published in 1859, it transformed biology and natural history by providing a mechanism for the transmutation of species, drawing on decades of observation from the Beagle voyage and subsequent research.",
    internetArchiveUrl: "https://archive.org/details/onoriginofspecie00darw",
    wikipediaUrl: "https://en.wikipedia.org/wiki/On_the_Origin_of_Species",
    ngramsTerm: "Origin of Species",
    ngramsYearStart: 1855,
    tags: ["natural selection", "evolution", "natural history", "biology", "Victorian science"],
  },
};


function slugify(name: string): string {
  return name.toLowerCase().trim().replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, "");
}

// ── CategoryRing SVG ────────────────────────────────────────────────────────

function CategoryRing({ byCategory, total, size = 120 }: { byCategory: Record<string, number>; total: number; size?: number }) {
  const r = size / 2;
  const strokeWidth = size * 0.1;
  const innerR = r - strokeWidth / 2 - 1;
  const circumference = 2 * Math.PI * innerR;

  let offset = 0;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {CATEGORY_ORDER.map((category) => {
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
            stroke={CATEGORY_COLORS_HEX[category] || "#888"}
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

// ── TranslatablePassage ─────────────────────────────────────────────────────

function TranslatablePassage({
  excerpt,
  matchedTerm,
  language,
}: {
  excerpt: string;
  matchedTerm: string;
  language: string;
}) {
  const [translation, setTranslation] = useState<string | null>(null);
  const [showTranslation, setShowTranslation] = useState(false);
  const [translating, setTranslating] = useState(false);
  const [fadeState, setFadeState] = useState<"visible" | "fading-out" | "fading-in">("visible");

  const isNonEnglish = language && language !== "English";

  const handleClick = async () => {
    if (!isNonEnglish) return;

    if (translation) {
      setFadeState("fading-out");
      setTimeout(() => {
        setShowTranslation((prev) => !prev);
        setFadeState("fading-in");
        setTimeout(() => setFadeState("visible"), 50);
      }, 250);
      return;
    }

    setTranslating(true);
    try {
      const res = await fetch("/api/translate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: excerpt, language }),
      });
      const result = await res.json();
      if (result.translation) {
        setTranslation(result.translation);
        setFadeState("fading-out");
        setTimeout(() => {
          setShowTranslation(true);
          setFadeState("fading-in");
          setTimeout(() => setFadeState("visible"), 50);
        }, 250);
      }
    } catch {
      // silently fail
    } finally {
      setTranslating(false);
    }
  };

  const displayText = showTranslation && translation ? translation : excerpt;

  // Highlight matched term in bold
  const highlighted = useMemo(() => {
    if (!matchedTerm) return displayText;
    const idx = displayText.toLowerCase().indexOf(matchedTerm.toLowerCase());
    if (idx === -1) return displayText;
    const before = displayText.slice(0, idx);
    const match = displayText.slice(idx, idx + matchedTerm.length);
    const after = displayText.slice(idx + matchedTerm.length);
    return (
      <>
        {before}
        <strong className="text-[var(--foreground)] font-semibold">{match}</strong>
        {after}
      </>
    );
  }, [displayText, matchedTerm]);

  return (
    <div
      className={`border-l-2 border-[var(--accent)] pl-4 py-2 ${
        isNonEnglish ? "cursor-pointer group" : ""
      }`}
      onClick={handleClick}
      title={isNonEnglish ? (showTranslation ? "Click to show original" : "Click to translate to English") : undefined}
    >
      <p
        className={`text-sm leading-relaxed transition-opacity duration-250 ease-in-out ${
          showTranslation ? "text-[var(--foreground)]/80 italic" : "text-[var(--muted)]"
        } ${
          fadeState === "fading-out" ? "opacity-0" : fadeState === "fading-in" ? "opacity-0" : "opacity-100"
        }`}
        style={{ transition: "opacity 250ms ease" }}
      >
        {translating ? (
          <span className="inline-flex items-center gap-1.5 text-[var(--muted)] not-italic">
            <span className="w-3 h-3 border-2 border-[var(--accent)] border-t-transparent rounded-full animate-spin inline-block" />
            Translating&hellip;
          </span>
        ) : (
          <>
            &ldquo;{highlighted}&rdquo;
            {showTranslation && (
              <span className="text-[10px] text-[var(--accent)] ml-1.5 not-italic font-medium">EN</span>
            )}
          </>
        )}
      </p>
      {isNonEnglish && !translating && (
        <p className="text-[10px] text-[var(--muted)] mt-1 opacity-0 group-hover:opacity-60 transition-opacity">
          {showTranslation ? "Click to show original" : "Click to translate"}
        </p>
      )}
    </div>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function BookAboutPage() {
  const { bookData, concordanceData } = useBookContext();

  // ── Concordance stats ──

  const concordanceStats = useMemo(() => {
    if (!concordanceData || !bookData) return null;
    const id = bookData.book.id;
    const clusters = concordanceData.clusters.filter((c) =>
      c.members.some((m) => m.book_id === id)
    );
    const shared = clusters.filter((c) => c.book_count > 1);
    const topShared = [...clusters]
      .sort((a, b) => b.total_mentions - a.total_mentions)
      .slice(0, 8);

    return { total: clusters.length, shared: shared.length, topShared };
  }, [concordanceData, bookData]);

  // ── Top entities ──

  const topEntities = useMemo(() => {
    if (!bookData) return [];
    return [...bookData.entities].sort((a, b) => b.count - a.count).slice(0, 10);
  }, [bookData]);

  // ── Key passages ──

  const keyPassages = useMemo(() => {
    if (!bookData) return [];
    return [...bookData.entities]
      .filter((e) => e.mentions && e.mentions.some((m) => m.excerpt.length > 100))
      .sort((a, b) => b.count - a.count)
      .slice(0, 5)
      .map((e) => {
        const best = e.mentions!.find((m) => m.excerpt.length > 100) || e.mentions![0];
        return { entity: e, mention: best };
      });
  }, [bookData]);

  // ── Category breakdown (sorted) ──

  const categorySorted = useMemo(() => {
    if (!bookData) return [];
    return CATEGORY_ORDER
      .filter((c) => bookData.stats.by_category[c] && bookData.stats.by_category[c] > 0)
      .map((c) => ({ category: c, count: bookData.stats.by_category[c] }));
  }, [bookData]);

  // ── Dominant category ──

  const dominantCategory = useMemo(() => {
    if (categorySorted.length === 0) return null;
    return [...categorySorted].sort((a, b) => b.count - a.count)[0];
  }, [categorySorted]);

  const meta = BOOK_METADATA[bookData.book.id];
  const coverSrc = BOOK_COVERS[bookData.book.id];
  const categoriesCount = Object.keys(bookData.stats.by_category).filter(
    (k) => bookData.stats.by_category[k] > 0
  ).length;

  return (
    <>
      {/* Split panel */}
      <div className="flex flex-col lg:flex-row gap-8 lg:gap-12">
        {/* ── Sidebar ── */}
        <aside className="lg:w-[280px] lg:shrink-0">
          <div className="lg:sticky lg:top-24 space-y-6">
            {/* Cover */}
            {coverSrc && (
              <img
                src={coverSrc}
                alt={`Title page of ${bookData.book.title}`}
                className="w-full rounded-lg shadow-lg border border-[var(--border)]"
              />
            )}

            {/* Category ring */}
            <div className="flex flex-col items-center">
              <CategoryRing
                byCategory={bookData.stats.by_category}
                total={bookData.stats.total_entities}
                size={140}
              />
              <div className="mt-3 space-y-1 w-full">
                {categorySorted.slice(0, 4).map(({ category, count }) => (
                  <div key={category} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-[var(--muted)]">
                      <span
                        className="inline-block w-2 h-2 rounded-sm shrink-0"
                        style={{ backgroundColor: CATEGORY_COLORS_HEX[category] || "#888" }}
                      />
                      {category.charAt(0) + category.slice(1).toLowerCase()}
                    </span>
                    <span className="font-mono text-[var(--foreground)] text-xs">
                      {count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick stats */}
            <div className="text-sm text-[var(--muted)] space-y-1 pt-2 border-t border-[var(--border)]">
              <div className="flex justify-between">
                <span>Total entities</span>
                <span className="font-mono text-[var(--foreground)]">
                  {bookData.stats.total_entities.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Categories</span>
                <span className="font-mono text-[var(--foreground)]">{categoriesCount}</span>
              </div>
            </div>

            {/* Action links */}
            <div className="space-y-2 pt-2">
              {BOOK_TEXTS[bookData.book.id] && (
                <a
                  href={BOOK_TEXTS[bookData.book.id]}
                  download
                  className="w-full px-4 py-2 border border-[var(--border)] rounded-lg text-sm text-[var(--foreground)] hover:bg-[var(--border)] transition-colors flex items-center justify-between"
                >
                  Download .txt
                  <svg className="w-4 h-4 text-[var(--muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                </a>
              )}
              {meta && (
                <a
                  href={meta.internetArchiveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2 border border-[var(--border)] rounded-lg text-sm text-[var(--foreground)] hover:bg-[var(--border)] transition-colors flex items-center justify-between"
                >
                  Internet Archive
                  <span className="text-[var(--muted)]">&rarr;</span>
                </a>
              )}
            </div>
          </div>
        </aside>

        {/* ── Content ── */}
        <article className="flex-1 min-w-0 space-y-12">
          {/* 1. Metadata */}
          <section>
            <h1 className="text-3xl font-bold mb-2">{bookData.book.title}</h1>
            <p className="text-lg text-[var(--muted)] mb-3">
              {bookData.book.author} &middot; {bookData.book.year}
              <span className="ml-3 text-sm bg-[var(--border)] px-2 py-0.5 rounded">
                {bookData.book.language}
              </span>
            </p>
            {meta && (
              <>
                <p className="text-sm text-[var(--muted)] leading-relaxed max-w-2xl mb-4">
                  {meta.description}
                </p>
                <div className="flex flex-wrap gap-1.5">
                  {meta.tags.map((tag) => (
                    <span
                      key={tag}
                      className="px-2 py-0.5 rounded-full text-[11px] border border-[var(--border)] text-[var(--muted)]"
                    >
                      {tag}
                    </span>
                  ))}
                </div>
              </>
            )}
          </section>

          {/* 2. At a Glance */}
          <section>
            <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
              At a Glance
            </h2>

            {/* Category bar */}
            <div className="flex h-3 rounded-full overflow-hidden mb-6">
              {categorySorted.map(({ category, count }) => (
                <div
                  key={category}
                  style={{
                    width: `${(count / bookData.stats.total_entities) * 100}%`,
                    backgroundColor: CATEGORY_COLORS_HEX[category] || "#888",
                  }}
                  title={`${category}: ${count}`}
                />
              ))}
            </div>

            {/* Stat cards */}
            <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
              <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
                <div className="text-2xl font-bold tabular-nums">
                  {bookData.stats.total_entities.toLocaleString()}
                </div>
                <div className="text-xs text-[var(--muted)] mt-1">Total entities</div>
              </div>
              <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
                <div className="text-2xl font-bold tabular-nums">
                  {concordanceStats?.total ?? "—"}
                </div>
                <div className="text-xs text-[var(--muted)] mt-1">Concordance clusters</div>
              </div>
              <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
                <div className="text-2xl font-bold tabular-nums">
                  {concordanceStats?.shared ?? "—"}
                </div>
                <div className="text-xs text-[var(--muted)] mt-1">Shared across books</div>
              </div>
              {dominantCategory && (
                <div className="p-4 rounded-lg border border-[var(--border)] bg-[var(--card)]">
                  <div className="flex items-center gap-2">
                    <span
                      className="w-3 h-3 rounded-sm"
                      style={{ backgroundColor: CATEGORY_COLORS_HEX[dominantCategory.category] || "#888" }}
                    />
                    <span className="text-lg font-bold">
                      {dominantCategory.category.charAt(0) + dominantCategory.category.slice(1).toLowerCase()}
                    </span>
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">Dominant category</div>
                </div>
              )}
            </div>
          </section>

          {/* 3. Top Entities */}
          <section>
            <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
              Top Entities
            </h2>
            <div className="space-y-1">
              {topEntities.map((entity, idx) => (
                <Link
                  key={entity.id}
                  href={`/books/${bookData.book.id}/entity/${entity.id}`}
                  className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-[var(--card)] transition-colors group"
                >
                  <div className="flex items-center gap-3 min-w-0">
                    <span className="text-xs text-[var(--muted)] font-mono w-5 shrink-0">
                      {idx + 1}
                    </span>
                    <span className="font-medium truncate group-hover:text-[var(--accent)] transition-colors">
                      {entity.name}
                    </span>
                    <span
                      className={`${CATEGORY_COLORS_BADGE[entity.category] || "bg-[var(--border)]"} px-1.5 py-0.5 rounded text-[10px] font-medium border shrink-0`}
                    >
                      {entity.category}
                    </span>
                  </div>
                  <span className="font-mono text-sm text-[var(--muted)] shrink-0 ml-2">
                    {entity.count}
                  </span>
                </Link>
              ))}
            </div>
          </section>

          {/* 4. Key Passages */}
          {keyPassages.length > 0 && (
            <section>
              <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
                Key Passages
              </h2>
              <div className="space-y-4">
                {keyPassages.map(({ entity, mention }) => (
                  <div key={entity.id}>
                    <div className="flex items-baseline gap-2 mb-1.5">
                      <Link
                        href={`/books/${bookData.book.id}/entity/${entity.id}`}
                        className="text-sm font-medium hover:text-[var(--accent)] transition-colors"
                      >
                        {entity.name}
                      </Link>
                      <span
                        className={`${CATEGORY_COLORS_BADGE[entity.category] || "bg-[var(--border)]"} px-1.5 py-0.5 rounded text-[10px] font-medium border`}
                      >
                        {entity.category}
                      </span>
                    </div>
                    <TranslatablePassage
                      excerpt={mention.excerpt}
                      matchedTerm={mention.matched_term}
                      language={bookData.book.language}
                    />
                  </div>
                ))}
              </div>
            </section>
          )}

          {/* 5. Concordance Connections */}
          {concordanceStats && (
            <section>
              <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
                Concordance Connections
              </h2>
              <p className="text-sm text-[var(--muted)] mb-4">
                This book appears in{" "}
                <span className="font-mono text-[var(--foreground)]">{concordanceStats.total}</span>{" "}
                concordance clusters, <span className="font-mono text-[var(--foreground)]">{concordanceStats.shared}</span>{" "}
                spanning multiple books.
              </p>
              <div className="space-y-1">
                {concordanceStats.topShared.map((cluster) => (
                  <Link
                    key={cluster.id}
                    href={`/concordance/${slugify(cluster.canonical_name)}`}
                    className="flex items-center justify-between py-2 px-3 rounded-lg hover:bg-[var(--card)] transition-colors group"
                  >
                    <div className="flex items-center gap-2 min-w-0">
                      <span className="font-medium truncate group-hover:text-[var(--accent)] transition-colors">
                        {cluster.canonical_name}
                      </span>
                      {cluster.book_count > 1 && (
                        <span className="text-[10px] text-[var(--muted)] bg-[var(--border)] px-1.5 py-0.5 rounded shrink-0">
                          {cluster.book_count} books
                        </span>
                      )}
                    </div>
                    <span className="font-mono text-sm text-[var(--muted)] shrink-0 ml-2">
                      {cluster.total_mentions} mentions
                    </span>
                  </Link>
                ))}
              </div>
            </section>
          )}

          {/* 6. External Resources */}
          {meta && (
            <section>
              <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
                External Resources
              </h2>
              <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
                {/* Google Ngram Viewer */}
                <a
                  href={`https://books.google.com/ngrams/graph?content=${encodeURIComponent(meta.ngramsTerm)}&year_start=${meta.ngramsYearStart}&year_end=2019&corpus=en-2019&smoothing=3`}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-4 rounded-lg border border-[var(--border)] hover:bg-[var(--card)] transition-colors group"
                >
                  <div className="text-sm font-medium group-hover:text-[var(--accent)] transition-colors">
                    Google Ngram Viewer
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">
                    Search &ldquo;{meta.ngramsTerm}&rdquo; &rarr;
                  </div>
                </a>

                {/* Wikipedia */}
                <a
                  href={
                    meta.wikipediaUrl ||
                    `https://en.wikipedia.org/w/index.php?search=${encodeURIComponent(bookData.book.title)}`
                  }
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-4 rounded-lg border border-[var(--border)] hover:bg-[var(--card)] transition-colors group"
                >
                  <div className="text-sm font-medium group-hover:text-[var(--accent)] transition-colors">
                    Wikipedia
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">
                    {meta.wikipediaUrl ? "View article" : "Search Wikipedia"} &rarr;
                  </div>
                </a>

                {/* Internet Archive */}
                <a
                  href={meta.internetArchiveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="p-4 rounded-lg border border-[var(--border)] hover:bg-[var(--card)] transition-colors group"
                >
                  <div className="text-sm font-medium group-hover:text-[var(--accent)] transition-colors">
                    Internet Archive
                  </div>
                  <div className="text-xs text-[var(--muted)] mt-1">
                    Read full text &rarr;
                  </div>
                </a>
              </div>
            </section>
          )}

        </article>
      </div>
    </>
  );
}
