"use client";

import { useEffect, useLayoutEffect, useState, useRef, useCallback } from "react";
import Link from "next/link";
import { useParams, usePathname, useRouter } from "next/navigation";
import { BookProvider, type BookData, type ConcordanceData } from "./BookContext";

const bookFiles: Record<string, string> = {
  "semedo-polyanthea-1741": "/data/semedo_entities.json",
  polyanthea_medicinal: "/data/semedo_entities.json",
  english_physician_1652: "/data/culpeper_entities.json",
  coloquios_da_orta_1563: "/data/orta_entities.json",
  historia_medicinal_monardes_1574: "/data/monardes_entities.json",
  relation_historique_humboldt_vol3_1825: "/data/humboldt_entities.json",
  ricettario_fiorentino_1597: "/data/ricettario_entities.json",
  principles_of_psychology_james_1890: "/data/james_psychology_entities.json",
  origin_of_species_darwin_1859: "/data/darwin_origin_entities.json",
};

export default function BookDetailLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const params = useParams();
  const pathname = usePathname();
  const bookId = params.id as string;

  const [bookData, setBookData] = useState<BookData | null>(null);
  const [concordanceData, setConcordanceData] = useState<ConcordanceData | null>(null);
  const [loading, setLoading] = useState(true);

  const isEntityDetailPage = /\/entity\//.test(pathname);

  useEffect(() => {
    const dataFile = bookFiles[bookId];
    if (!dataFile) {
      // Try all files and match by ID
      const allFiles = Object.values(bookFiles);
      Promise.all(
        allFiles.map((f) =>
          fetch(f)
            .then((res) => res.json())
            .catch(() => null)
        )
      ).then((results) => {
        const match = results.find((r) => r?.book?.id === bookId);
        if (match) setBookData(match);
        // Still fetch concordance
        fetch("/data/concordance.json")
          .then((res) => res.json())
          .then((c) => setConcordanceData(c))
          .catch(() => {})
          .finally(() => setLoading(false));
      });
      return;
    }

    Promise.all([
      fetch(dataFile).then((res) => res.json()),
      fetch("/data/concordance.json").then((res) => res.json()),
    ])
      .then(([book, concordance]) => {
        setBookData(book);
        setConcordanceData(concordance);
      })
      .catch(() => {})
      .finally(() => setLoading(false));
  }, [bookId]);

  // Entity detail pages manage their own layout — just pass through
  if (isEntityDetailPage) {
    return <>{children}</>;
  }

  if (loading) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-8">
        <div className="animate-pulse space-y-4">
          <div className="h-4 bg-[var(--border)] rounded w-48"></div>
          <div className="h-10 bg-[var(--border)] rounded w-64 mt-4"></div>
          <div className="h-64 bg-[var(--border)] rounded mt-6"></div>
        </div>
      </div>
    );
  }

  if (!bookData) {
    return (
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-16">
        <p>Book not found.</p>
      </div>
    );
  }

  // Determine active tab from pathname
  const activeTab = pathname.endsWith("/about")
    ? "about"
    : pathname.endsWith("/research")
      ? "research"
      : pathname.endsWith("/knowledge-graph")
        ? "knowledge-graph"
        : "entities";

  const tabs = [
    { key: "entities", label: "Entities", href: `/books/${bookData.book.id}` },
    { key: "about", label: "About", href: `/books/${bookData.book.id}/about` },
    { key: "knowledge-graph", label: "Knowledge Graph", href: `/books/${bookData.book.id}/knowledge-graph` },
    { key: "research", label: "Research", href: `/books/${bookData.book.id}/research` },
  ];

  return (
    <BookProvider value={{ bookData, concordanceData: concordanceData! }}>
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8">
        {/* Breadcrumb */}
        <nav className="mb-0 text-sm">
          <Link
            href="/books"
            className="text-[var(--muted)] hover:text-[var(--foreground)]"
          >
            Books
          </Link>
          <span className="text-[var(--muted)] mx-3">/</span>
          <span>{bookData.book.title}</span>
        </nav>
      </div>

      {/* Sticky tab bar */}
      <div className="sticky top-16 z-40 bg-[var(--background)]/80 backdrop-blur-sm border-b border-[var(--border)]">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
          <AnimatedTabs tabs={tabs} activeTab={activeTab} />
        </div>
      </div>

      {/* Page content */}
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-8 pb-8">
        {children}
      </div>
    </BookProvider>
  );
}

// ── Animated Tab Switcher ────────────────────────────────────────────────────

function AnimatedTabs({
  tabs,
  activeTab,
}: {
  tabs: { key: string; label: string; href: string }[];
  activeTab: string;
}) {
  const router = useRouter();
  const navRef = useRef<HTMLElement>(null);
  const tabRefs = useRef<Record<string, HTMLAnchorElement | null>>({});
  const [indicator, setIndicator] = useState({ left: 0, width: 0 });
  const [animated, setAnimated] = useState(false);

  // Arrow key navigation between tabs
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key !== "ArrowLeft" && e.key !== "ArrowRight") return;

      // Don't hijack arrow keys inside inputs, textareas, or contenteditable
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable) return;

      const currentIdx = tabs.findIndex((t) => t.key === activeTab);
      const nextIdx = e.key === "ArrowRight"
        ? Math.min(currentIdx + 1, tabs.length - 1)
        : Math.max(currentIdx - 1, 0);

      if (nextIdx !== currentIdx) {
        e.preventDefault();
        router.push(tabs[nextIdx].href);
      }
    };

    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [activeTab, tabs, router]);

  const measure = useCallback(() => {
    const activeEl = tabRefs.current[activeTab];
    const navEl = navRef.current;
    if (!activeEl || !navEl) return;

    const navRect = navEl.getBoundingClientRect();
    const tabRect = activeEl.getBoundingClientRect();

    // Inset matches the tab padding (px-3 = 12px mobile, px-4 = 16px desktop)
    const inset = window.innerWidth >= 640 ? 16 : 12;

    setIndicator({
      left: tabRect.left - navRect.left + inset,
      width: tabRect.width - inset * 2,
    });
  }, [activeTab]);

  // Position indicator before paint (no flash)
  useLayoutEffect(() => {
    measure();
  }, [measure]);

  // Enable spring transition after initial positioning
  useEffect(() => {
    const frame = requestAnimationFrame(() => setAnimated(true));
    return () => cancelAnimationFrame(frame);
  }, []);

  // Reposition on resize
  useEffect(() => {
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, [measure]);

  return (
    <nav
      ref={navRef}
      className="relative flex gap-1 mt-1"
    >
      {tabs.map((tab) => (
        <Link
          key={tab.key}
          ref={(el) => {
            tabRefs.current[tab.key] = el;
          }}
          href={tab.href}
          className={`relative px-4 sm:px-5 py-3.5 text-base font-semibold tracking-[-0.01em] transition-colors duration-200 ${
            activeTab === tab.key
              ? "text-[var(--foreground)]"
              : "text-[var(--muted)] hover:text-[var(--foreground)]"
          }`}
        >
          {tab.label}
        </Link>
      ))}

      {/* Sliding indicator with spring overshoot */}
      <span
        className="absolute -bottom-px h-[2px] bg-[var(--foreground)] rounded-full pointer-events-none"
        style={{
          left: indicator.left,
          width: indicator.width,
          transition: animated
            ? "left 450ms cubic-bezier(0.2, 1.3, 0.5, 1), width 350ms cubic-bezier(0.25, 1, 0.5, 1)"
            : "none",
          willChange: "left, width",
        }}
      />
    </nav>
  );
}
