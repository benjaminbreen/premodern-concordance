"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState, useRef, useCallback } from "react";

// ── Multilingual title translations ────────────────────────────────────

const TITLES: { line1: string; line2: string }[] = [
  { line1: "Premodern", line2: "Concordance" },
  { line1: "Concordancia", line2: "Premoderna" },
  { line1: "Concordância", line2: "Pré-moderna" },
  { line1: "Concordance", line2: "Prémoderne" },
  { line1: "Concordanza", line2: "Premoderna" },
  { line1: "Vormoderne", line2: "Konkordanz" },
  { line1: "Premoderne", line2: "Concordantie" },
  { line1: "Concordança", line2: "Premoderna" },
  { line1: "Concordantia", line2: "Praemoderna" },
  { line1: "Concordança", line2: "Premodèrna" },
  { line1: "Concordancia", line2: "Premoderna" },
  { line1: "Concordanță", line2: "Premodernă" },
  { line1: "Förmodern", line2: "Konkordans" },
  { line1: "Førmoderne", line2: "Konkordans" },
  { line1: "Předmoderní", line2: "Konkordance" },
  { line1: "Concordanza", line2: "Premoderna" },
  { line1: "Concordàntzia", line2: "Premoderna" },
  { line1: "Cuncurdanza", line2: "Premoderna" },
  { line1: "Predmoderna", line2: "Konkordancija" },
  { line1: "Antaŭmoderna", line2: "Konkordanco" },
  { line1: "Konkordansi", line2: "Pramodern" },
  { line1: "Concordantia", line2: "Premoderne" },
];

const FONTS = [
  { family: "inherit", label: "default" },
  { family: "'UnifrakturMaguntia', cursive", label: "gothic" },
  { family: "'EB Garamond', serif", label: "garamond" },
  { family: "'Space Grotesk', sans-serif", label: "grotesk" },
];

function InteractiveTitle() {
  const [showForeign, setShowForeign] = useState(false);
  const [foreignIdx, setForeignIdx] = useState(1);
  const [fontIdx, setFontIdx] = useState(0);
  const lastIdx = useRef(1);

  const handleEnter = () => {
    // Pick a random non-English title, different from last
    let next: number;
    do { next = 1 + Math.floor(Math.random() * (TITLES.length - 1)); } while (next === lastIdx.current && TITLES.length > 2);
    lastIdx.current = next;
    // Set content first (foreign span is at opacity 0, so no flash)
    setForeignIdx(next);
    // Trigger fade on next frame so the content is painted before transition starts
    requestAnimationFrame(() => {
      setShowForeign(true);
    });
  };

  const handleLeave = () => {
    setShowForeign(false);
  };

  const handleClick = () => {
    setFontIdx((prev) => (prev + 1) % FONTS.length);
  };

  const english = TITLES[0];
  const foreign = TITLES[foreignIdx];
  const font = FONTS[fontIdx];

  return (
    <h1
      className="text-4xl md:text-5xl font-bold tracking-tight leading-[1.15] mb-4 cursor-pointer select-none relative"
      style={{ fontFamily: font.family }}
      onMouseEnter={handleEnter}
      onMouseLeave={handleLeave}
      onClick={handleClick}
    >
      <span
        className="block"
        style={{
          opacity: showForeign ? 0 : 1,
          transition: "opacity 500ms ease-in-out",
        }}
      >
        {english.line1}<br />{english.line2}
      </span>
      <span
        className="absolute top-0 left-0"
        style={{
          opacity: showForeign ? 1 : 0,
          transition: "opacity 500ms ease-in-out",
        }}
        aria-hidden
      >
        {foreign.line1}<br />{foreign.line2}
      </span>
    </h1>
  );
}

// ── Types ──────────────────────────────────────────────────────────────

interface ConcordanceStats {
  total_clusters: number;
  clusters_all_books: number;
  with_wikidata?: number;
  by_category: Record<string, number>;
}

interface BookMeta {
  id: string;
  title: string;
  author: string;
  year: number;
  language: string;
}

interface ClusterPreview {
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  members: { name: string; book_id: string }[];
  ground_truth?: {
    modern_name: string;
    linnaean?: string;
    wikidata_description?: string;
  };
}

const CAT_COLORS: Record<string, string> = {
  PLANT: "text-emerald-700 dark:text-emerald-400 border-emerald-300 dark:border-emerald-700",
  PERSON: "text-purple-700 dark:text-purple-400 border-purple-300 dark:border-purple-700",
  SUBSTANCE: "text-cyan-700 dark:text-cyan-400 border-cyan-300 dark:border-cyan-700",
  DISEASE: "text-red-700 dark:text-red-400 border-red-300 dark:border-red-700",
  PLACE: "text-green-700 dark:text-green-400 border-green-300 dark:border-green-700",
  CONCEPT: "text-amber-700 dark:text-amber-400 border-amber-300 dark:border-amber-700",
  ANIMAL: "text-lime-700 dark:text-lime-400 border-lime-300 dark:border-lime-700",
  OBJECT: "text-slate-600 dark:text-slate-400 border-slate-300 dark:border-slate-600",
};

export default function Home() {
  const router = useRouter();
  const [searchQuery, setSearchQuery] = useState("");
  const [stats, setStats] = useState<ConcordanceStats | null>(null);
  const [books, setBooks] = useState<BookMeta[]>([]);
  const [examples, setExamples] = useState<ClusterPreview[]>([]);
  const [totalMentions, setTotalMentions] = useState(0);

  useEffect(() => {
    fetch("/data/concordance.json")
      .then((res) => res.json())
      .then((data) => {
        setStats(data.stats);
        setBooks(data.books);
        setTotalMentions(
          (data.clusters as ClusterPreview[]).reduce((sum: number, c: ClusterPreview) => sum + c.total_mentions, 0)
        );
        // Build pool of good candidates: has identification, 2+ books, 5+ mentions
        const candidates = (data.clusters as ClusterPreview[]).filter(
          (c) => c.ground_truth && c.book_count >= 2 && c.total_mentions >= 5
        );

        // Shuffle candidates (Fisher-Yates)
        for (let i = candidates.length - 1; i > 0; i--) {
          const j = Math.floor(Math.random() * (i + 1));
          [candidates[i], candidates[j]] = [candidates[j], candidates[i]];
        }

        // Pick 6 with category diversity: try to get different categories first
        const picked: ClusterPreview[] = [];
        const usedCats = new Set<string>();
        // First pass: one per category
        for (const c of candidates) {
          if (picked.length >= 6) break;
          if (!usedCats.has(c.category)) {
            usedCats.add(c.category);
            picked.push(c);
          }
        }
        // Second pass: fill remaining slots from unused candidates
        for (const c of candidates) {
          if (picked.length >= 6) break;
          if (!picked.includes(c)) {
            picked.push(c);
          }
        }
        setExamples(picked);
      })
      .catch(() => {});
  }, []);

  const languages = [...new Set(books.map((b) => b.language))];

  return (
    <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
      {/* Hero — asymmetric two-column */}
      <div className="grid grid-cols-1 md:grid-cols-2 gap-8 md:gap-16 py-12 md:py-20 items-start animate-fade-up delay-0">
        <div>
          <InteractiveTitle />
          <p className="text-xl text-[var(--muted)] leading-relaxed">
            Cross-linguistic entity matching across early modern texts
          </p>
        </div>
        <div className="md:pt-2 animate-fade-in delay-2">
          <p className="text-[var(--muted)] leading-relaxed mb-6">
            Linking named entities &mdash; people, plants, substances, places,
            diseases &mdash; across {books.length || "several"} multilingual texts
            from the sixteenth to nineteenth centuries. Each cluster preserves
            variant spellings, historical names, and cross-book connections.
          </p>
          <form
            onSubmit={(e) => {
              e.preventDefault();
              if (searchQuery.trim().length >= 2) {
                router.push(`/search?q=${encodeURIComponent(searchQuery.trim())}`);
              }
            }}
            className="relative mb-4"
          >
            <svg
              className="absolute left-3 top-1/2 -translate-y-1/2 w-4 h-4 text-[var(--muted)]"
              fill="none" stroke="currentColor" viewBox="0 0 24 24"
            >
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
            <input
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search entities, plants, people, places..."
              className="w-full pl-9 pr-4 py-2.5 rounded-lg border border-[var(--border)] bg-[var(--card)] text-sm placeholder:text-[var(--muted)] focus:outline-none focus:ring-2 focus:ring-[var(--accent)] focus:border-transparent transition-all"
            />
          </form>
          <div className="flex gap-3">
            <Link
              href="/concordance"
              className="px-5 py-2.5 bg-[var(--foreground)] text-[var(--background)] rounded-lg text-sm font-medium hover:opacity-85 transition-opacity"
            >
              Explore the concordance
            </Link>
            <Link
              href="/books"
              className="px-5 py-2.5 border border-[var(--border)] rounded-lg text-sm font-medium hover:bg-[var(--border)] transition-colors"
            >
              Browse corpus
            </Link>
          </div>
        </div>
      </div>

      {/* Stats strip */}
      {stats && (
        <div className="animate-fade-up delay-3">
          <div className="border-t border-[var(--border)]" />
          <div className="flex flex-wrap gap-x-10 gap-y-4 py-6 items-baseline">
            {[
              { value: stats.total_clusters.toLocaleString(), label: "clusters", href: "/concordance" },
              { value: String(books.length), label: "books", href: "/books" },
              { value: String(languages.length), label: "languages", href: "/data#languages" },
              ...(totalMentions ? [{ value: totalMentions.toLocaleString(), label: "entities", href: "/entities" }] : []),
              ...(books.length >= 2 ? [{ value: `${Math.min(...books.map(b => b.year))}–${Math.max(...books.map(b => b.year))}`, label: "timespan", href: "/timeline" }] : []),
            ].map((stat) => (
              <Link
                key={stat.value + stat.label}
                href={stat.href}
                className="flex items-baseline gap-2 group"
              >
                <span className="text-3xl font-bold tracking-tight group-hover:text-[var(--accent)] transition-colors">
                  {stat.value}
                </span>
                {stat.label && <span className="text-sm text-[var(--muted)] group-hover:text-[var(--accent)] transition-colors">{stat.label}</span>}
              </Link>
            ))}
          </div>
          <div className="border-t border-[var(--border)]" />
        </div>
      )}

      {/* Example clusters */}
      {examples.length > 0 && (
        <div className="py-16 animate-fade-up delay-7">
          <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-5">
            Example clusters
          </h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-px bg-[var(--border)] border border-[var(--border)] rounded-lg overflow-hidden">
            {examples.map((cluster) => {
              const variants = [...new Set(
                cluster.members.map((m) => m.name)
              )].filter((n) => n.toLowerCase() !== cluster.canonical_name.toLowerCase());
              return (
                <Link
                  key={cluster.canonical_name}
                  href={`/concordance?highlight=${encodeURIComponent(cluster.canonical_name)}`}
                  className="bg-[var(--card)] p-5 hover:bg-[var(--border)]/30 transition-colors block"
                >
                  <div className="flex items-center gap-2 mb-1">
                    <span className="font-semibold">{cluster.canonical_name}</span>
                    <span className={`px-1.5 py-0.5 rounded border text-[10px] font-semibold uppercase tracking-wide bg-transparent ${CAT_COLORS[cluster.category] || "text-gray-500 border-gray-300"}`}>
                      {cluster.category}
                    </span>
                  </div>
                  <div className="text-sm text-[var(--muted)] mb-2">
                    {cluster.ground_truth?.linnaean ? (
                      <em>{cluster.ground_truth.linnaean}</em>
                    ) : cluster.ground_truth?.modern_name &&
                      cluster.ground_truth.modern_name.toLowerCase() !== cluster.canonical_name.toLowerCase() ? (
                      cluster.ground_truth.modern_name
                    ) : cluster.ground_truth?.wikidata_description ? (
                      <span className="line-clamp-1">{cluster.ground_truth.wikidata_description}</span>
                    ) : null}
                    {cluster.ground_truth?.linnaean || cluster.ground_truth?.modern_name || cluster.ground_truth?.wikidata_description ? (
                      <span> &middot; </span>
                    ) : null}
                    {cluster.book_count} books &middot; {cluster.total_mentions.toLocaleString()}&times;
                  </div>
                  <div className="flex flex-wrap gap-1.5">
                    {variants.slice(0, 4).map((v) => (
                      <span
                        key={v}
                        className="text-xs px-1.5 py-0.5 rounded bg-[var(--background)] text-[var(--muted)]"
                      >
                        {v}
                      </span>
                    ))}
                  </div>
                </Link>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}
