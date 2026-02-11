"use client";

import { useEffect, useState, useCallback, useRef } from "react";
import Link from "next/link";

// ── Scrolling concordance ticker ──────────────────────────────────────

interface ClusterSlim {
  canonical_name: string;
  members: { name: string; book_id: string }[];
}

const TICKER_FONTS = [
  "inherit",
  "'UnifrakturMaguntia', cursive",
  "'EB Garamond', serif",
  "'Space Grotesk', sans-serif",
];

function ConcordanceTicker() {
  const [names, setNames] = useState<string[]>([]);
  const [pool, setPool] = useState<ClusterSlim[]>([]);
  const [key, setKey] = useState(0);
  const [fontIdx, setFontIdx] = useState(0);
  const lastIdx = useRef(-1);

  // Load cluster data once
  useEffect(() => {
    fetch("/data/concordance.json")
      .then((r) => r.json())
      .then((data) => {
        // Keep clusters with 3+ distinct member names for visual interest
        const good = (data.clusters as ClusterSlim[]).filter((c) => {
          const unique = new Set(c.members.map((m) => m.name));
          return unique.size >= 3;
        });
        setPool(good);
      })
      .catch(() => {});
  }, []);

  const pickNext = useCallback(() => {
    if (!pool.length) return;
    let idx: number;
    do {
      idx = Math.floor(Math.random() * pool.length);
    } while (idx === lastIdx.current && pool.length > 1);
    lastIdx.current = idx;

    const cluster = pool[idx];
    // Deduplicate names, canonical first
    const seen = new Set<string>();
    const result: string[] = [];
    const addName = (n: string) => {
      const lower = n.toLowerCase();
      if (!seen.has(lower)) {
        seen.add(lower);
        result.push(n);
      }
    };
    addName(cluster.canonical_name);
    for (const m of cluster.members) addName(m.name);

    setNames(result.slice(0, 8));
    setKey((k) => k + 1);
  }, [pool]);

  // Pick first cluster when pool loads
  useEffect(() => {
    if (pool.length > 0 && names.length === 0) pickNext();
  }, [pool, names.length, pickNext]);

  if (!names.length) return (
    <div className="h-48 flex items-center justify-center overflow-hidden">
      <span className="text-2xl tracking-tight text-[var(--muted)]/30 select-none">
        mercury &middot; mercurio &middot; azogue &middot; vif-argent &middot; hydrargyrum
      </span>
    </div>
  );

  return (
    <div className="h-48 flex items-center overflow-hidden relative mt-8">
      {/* Fade edges */}
      <div className="absolute left-0 top-0 bottom-0 w-20 z-10 bg-gradient-to-r from-[var(--background)] to-transparent pointer-events-none" />
      <div className="absolute right-0 top-0 bottom-0 w-20 z-10 bg-gradient-to-l from-[var(--background)] to-transparent pointer-events-none" />

      <div
        key={key}
        className="whitespace-nowrap animate-scroll-across cursor-pointer"
        style={{ fontFamily: TICKER_FONTS[fontIdx], transition: "font-family 0s" }}
        onClick={() => setFontIdx((f) => (f + 1) % TICKER_FONTS.length)}
        onAnimationEnd={pickNext}
      >
        {names.map((name, i) => (
          <span key={i}>
            {i > 0 && (
              <span className="mx-5 text-[var(--border)] select-none">&middot;</span>
            )}
            <span className={`text-3xl tracking-tight ${
              i === 0
                ? "text-[var(--foreground)] font-medium"
                : "text-[var(--muted)]/50"
            }`}>
              {name}
            </span>
          </span>
        ))}
      </div>
    </div>
  );
}

// ── Page ──────────────────────────────────────────────────────────────

export default function AboutPage() {
  return (
    <div className="max-w-4xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
      {/* Title */}
      <h1 className="text-3xl font-bold mb-3">About</h1>
      <p className="text-[var(--muted)] max-w-2xl mb-8 leading-relaxed">
        The Premodern Concordance is a prototype for a larger project that will use
        computational methods to link named entities &mdash; people, plants,
        substances, places, diseases, and concepts &mdash; across multilingual
        early modern texts relating to natural and scientific knowledge. The goal is to make the unstable, polyglot terminology
        of premodern natural knowledge searchable and comparable across languages,
        centuries, and traditions, and then to explore new research possibilities and questions unlocked by this.
      </p>

      <p className="text-lg leading-relaxed mb-12">
        Our methodology is described{" "}
        <Link href="/methodology" className="underline underline-offset-4 decoration-[var(--border)] hover:decoration-[var(--foreground)] transition-colors">
          here
        </Link>, and a full data set is available{" "}
        <Link href="/data" className="underline underline-offset-4 decoration-[var(--border)] hover:decoration-[var(--foreground)] transition-colors">
          here
        </Link>{" "}
        <span className="text-[var(--muted)]">(in progress)</span>.
      </p>

      {/* Personnel */}
      <section className="mb-16">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-6">
          Personnel
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-8">
          <div>
            <h3 className="font-semibold mb-1">Benjamin Breen</h3>
            <p className="text-sm text-[var(--muted)]">
              Department of History, UC Santa Cruz
            </p>
          </div>
          <div>
            <h3 className="font-semibold mb-1">Mackenzie Cooley</h3>
            <p className="text-sm text-[var(--muted)]">
              Department of History, Hamilton College
            </p>
          </div>
        </div>
      </section>

      {/* Colophon */}
      <section className="mb-16">
        <h2 className="text-xs uppercase tracking-widest text-[var(--muted)] font-medium mb-6">
          Colophon
        </h2>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-x-12 gap-y-6 text-sm">
          <div>
            <h3 className="font-semibold mb-2">Typography</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">System UI</span> &mdash; body text
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'UnifrakturMaguntia', cursive" }}>UnifrakturMaguntia</span> &mdash; logotype, blackletter display
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'EB Garamond', serif" }}>EB Garamond</span> &mdash; early modern serif
              </li>
              <li>
                <span className="text-[var(--foreground)]" style={{ fontFamily: "'Space Grotesk', sans-serif" }}>Space Grotesk</span> &mdash; geometric display
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Framework</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">Next.js 16</span> &mdash; React framework
              </li>
              <li>
                <span className="text-[var(--foreground)]">Tailwind CSS 4</span> &mdash; styling
              </li>
              <li>
                <span className="text-[var(--foreground)]">Vercel</span> &mdash; hosting
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Research models</h3>
            <ul className="text-[var(--muted)] space-y-1">
              <li>
                <span className="text-[var(--foreground)]">BGE-M3</span> &mdash; fine-tuned cross-lingual embeddings for entity matching (current model was fine-tuned on 500 matched multi-lingual pairs of early modern natural concepts/terms)
              </li>
              <li>
                <span className="text-[var(--foreground)]">Google Gemini 2.5 Flash Lite</span> &mdash; entity extraction, enrichment, and verification
              </li>
              <li>
                <span className="text-[var(--foreground)]">OpenAI text-embedding-3-small</span> &mdash; semantic search index
              </li>
            </ul>
          </div>
          <div>
            <h3 className="font-semibold mb-2">Site code</h3>
            <p className="text-[var(--muted)]">
              Built with assistance from{" "}
              <a
                href="https://claude.ai/claude-code"
                target="_blank"
                rel="noopener noreferrer"
                className="text-[var(--foreground)] underline underline-offset-2 decoration-[var(--border)] hover:decoration-[var(--foreground)] transition-colors"
              >
                Claude Code
              </a>{" "}
              (Claude Opus 4.5).
            </p>
          </div>
        </div>
      </section>

      {/* Concordance ticker */}
      <ConcordanceTicker />
    </div>
  );
}
