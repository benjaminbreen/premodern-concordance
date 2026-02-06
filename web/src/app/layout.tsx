"use client";

import { useState, useEffect } from "react";
import Link from "next/link";
import "./globals.css";

function ThemeToggle() {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const stored = localStorage.getItem("theme");
    const prefersDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
    setDark(stored === "dark" || (!stored && prefersDark));
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("dark", dark);
    localStorage.setItem("theme", dark ? "dark" : "light");
  }, [dark]);

  return (
    <button
      onClick={() => setDark(!dark)}
      className="p-2 rounded-lg hover:bg-[var(--border)] transition-colors"
      aria-label="Toggle dark mode"
    >
      {dark ? (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ) : (
        <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
        </svg>
      )}
    </button>
  );
}

function Logotype() {
  return (
    <Link
      href="/"
      className="text-lg font-semibold tracking-tight hover:text-[var(--accent)] transition-colors duration-300"
    >
      Premodern Concordance
    </Link>
  );
}

function FooterLogotype() {
  const [hovered, setHovered] = useState(false);

  return (
    <Link
      href="/"
      className="inline-block relative"
      onMouseEnter={() => setHovered(true)}
      onMouseLeave={() => setHovered(false)}
    >
      {/* Blackletter PC */}
      <span
        className="text-4xl leading-none transition-all duration-500 ease-out inline-block"
        style={{
          fontFamily: "'UnifrakturMaguntia', cursive",
          opacity: hovered ? 0 : 0.8,
          transform: hovered ? "scale(0.8) translateY(-4px)" : "scale(1) translateY(0)",
          filter: hovered ? "blur(4px)" : "blur(0)",
        }}
      >
        PC
      </span>
      {/* Full name in sans-serif */}
      <span
        className="absolute left-0 top-0 text-sm font-medium tracking-tight whitespace-nowrap transition-all duration-500 ease-out"
        style={{
          fontFamily: "system-ui, -apple-system, Helvetica, sans-serif",
          opacity: hovered ? 0.9 : 0,
          transform: hovered ? "translateY(0)" : "translateY(8px)",
          filter: hovered ? "blur(0)" : "blur(4px)",
        }}
      >
        Premodern Concordance
      </span>
    </Link>
  );
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <title>Premodern Concordance</title>
        <meta name="description" content="Cross-linguistic concordance of early modern natural knowledge" />
        <link rel="preconnect" href="https://fonts.googleapis.com" />
        <link rel="preconnect" href="https://fonts.gstatic.com" crossOrigin="anonymous" />
        <link href="https://fonts.googleapis.com/css2?family=UnifrakturMaguntia&family=EB+Garamond:ital,wght@0,400;0,700;1,400&family=Space+Grotesk:wght@400;700&display=swap" rel="stylesheet" />
      </head>
      <body className="min-h-screen flex flex-col bg-[var(--background)] text-[var(--foreground)]">
        <header className="sticky top-0 z-50 border-b border-[var(--border)] bg-[var(--background)]/80 backdrop-blur-sm">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
            <div className="flex items-center justify-between h-16">
              <div className="flex items-center gap-8">
                <Logotype />
                <nav className="hidden sm:flex items-center gap-6">
                  <Link href="/books" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                    Books
                  </Link>
                  <Link href="/concordance" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                    Concordance
                  </Link>
                  <Link href="/search" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                    Search
                  </Link>
                  <Link href="/methodology" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                    Methodology
                  </Link>
                  <Link href="/about" className="text-[var(--muted)] hover:text-[var(--foreground)] transition-colors">
                    About
                  </Link>
                </nav>
              </div>
              <ThemeToggle />
            </div>
          </div>
        </header>
        <main className="flex-1">{children}</main>
        <footer className="mt-auto border-t border-[var(--border)] bg-[#1c1917] dark:bg-[#0c0a09] text-[#fafaf9]">
          <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-12">
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-8">
              {/* Logotype */}
              <div className="col-span-2 sm:col-span-1">
                <FooterLogotype />
              </div>

              {/* Empty spacer column */}
              <div className="hidden sm:block" />

              {/* Corpus */}
              <div>
                <h3 className="text-xs uppercase tracking-widest font-medium opacity-50 mb-4">Corpus</h3>
                <ul className="space-y-2.5 text-sm">
                  <li><Link href="/books" className="footer-link text-[#fafaf9]/70">Books</Link></li>
                  <li><Link href="/concordance" className="footer-link text-[#fafaf9]/70">Concordance</Link></li>
                  <li><Link href="/search" className="footer-link text-[#fafaf9]/70">Search</Link></li>
                </ul>
              </div>

              {/* About */}
              <div>
                <h3 className="text-xs uppercase tracking-widest font-medium opacity-50 mb-4">Project</h3>
                <ul className="space-y-2.5 text-sm">
                  <li><Link href="/methodology" className="footer-link text-[#fafaf9]/70">Methodology</Link></li>
                  <li><Link href="/about" className="footer-link text-[#fafaf9]/70">About</Link></li>
                  <li><a href="https://github.com" target="_blank" rel="noopener noreferrer" className="footer-link text-[#fafaf9]/70">GitHub</a></li>
                </ul>
              </div>
            </div>

            {/* Bottom rule */}
            <div className="mt-10 pt-6 border-t border-[#fafaf9]/20 opacity-30">
              <p className="text-xs">
                A cross-linguistic concordance of early modern natural knowledge.
              </p>
            </div>
          </div>
        </footer>
      </body>
    </html>
  );
}
