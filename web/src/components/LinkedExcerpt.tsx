"use client";

import Link from "next/link";
import React from "react";

export interface PersonLinkInfo {
  name: string;
  variants: string[];
  entityId: string;
  href: string; // pre-computed: concordance slug or book entity page
}

/**
 * Renders excerpt text with:
 *  - the matched term highlighted (bold)
 *  - recognized person names as clickable links
 */
export function LinkedExcerpt({
  excerpt,
  matchedTerm,
  personLinks,
}: {
  excerpt: string;
  matchedTerm?: string;
  personLinks: PersonLinkInfo[];
}) {
  const matchedLower = matchedTerm?.toLowerCase();

  // Build all patterns to match in the text
  // Collect unique strings → their rendering info
  const personLookup = new Map<string, PersonLinkInfo>();
  for (const person of personLinks) {
    const allNames = new Set([person.name, ...person.variants]);
    for (const name of allNames) {
      if (name.length < 3) continue;
      // Don't link the same term that's being highlighted
      if (matchedLower && name.toLowerCase() === matchedLower) continue;
      personLookup.set(name.toLowerCase(), person);
    }
  }

  // Collect all patterns: person names + matched term
  const allPatterns: string[] = [];
  for (const key of personLookup.keys()) {
    allPatterns.push(key);
  }
  if (matchedTerm) {
    allPatterns.push(matchedTerm.toLowerCase());
  }

  if (allPatterns.length === 0) {
    return <span className="text-[var(--muted)]">...{excerpt}...</span>;
  }

  // Sort longest first so regex prefers longer matches
  allPatterns.sort((a, b) => b.length - a.length);

  // Build combined regex with word boundaries
  const escaped = allPatterns.map((p) =>
    p.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")
  );
  const regex = new RegExp(`(\\b(?:${escaped.join("|")})\\b)`, "gi");

  const parts = excerpt.split(regex);

  return (
    <span className="text-[var(--muted)]">
      ...
      {parts.map((part, i) => {
        const lower = part.toLowerCase();

        // Priority 1: highlight the matched term
        if (matchedLower && lower === matchedLower) {
          return (
            <strong
              key={i}
              className="text-[var(--foreground)] bg-[var(--accent)]/10 px-0.5 rounded"
            >
              {part}
            </strong>
          );
        }

        // Priority 2: link to a person entity
        const person = personLookup.get(lower);
        if (person) {
          return (
            <Link
              key={i}
              href={person.href}
              className="text-purple-500 dark:text-purple-400 hover:underline decoration-purple-500/40"
              onClick={(e) => e.stopPropagation()}
            >
              {part}
            </Link>
          );
        }

        // Plain text
        return <React.Fragment key={i}>{part}</React.Fragment>;
      })}
      ...
    </span>
  );
}

/**
 * Given a list of all entities and concordance clusters for a book,
 * builds the PersonLinkInfo array for use with LinkedExcerpt.
 */
export function buildPersonLinks(
  entities: { id: string; name: string; category: string; variants: string[] }[],
  bookId: string,
  concordanceClusters?: {
    id: number;
    canonical_name: string;
    category: string;
    members: { entity_id: string; book_id: string }[];
  }[]
): PersonLinkInfo[] {
  const persons = entities.filter((e) => e.category === "PERSON");

  return persons.map((person) => {
    let href = `/books/${bookId}/entity/${person.id}`;

    // Try concordance cluster first
    if (concordanceClusters) {
      const cluster = concordanceClusters.find(
        (c) =>
          c.category === "PERSON" &&
          c.members.some(
            (m) => m.book_id === bookId && m.entity_id === person.id
          )
      );
      if (cluster) {
        const base = cluster.canonical_name
          .toLowerCase()
          .trim()
          .replace(/[^a-z0-9]+/g, "-")
          .replace(/^-|-$/g, "");
        const hasCollision = concordanceClusters.some(
          (c) =>
            c.id !== cluster.id &&
            c.canonical_name
              .toLowerCase()
              .trim()
              .replace(/[^a-z0-9]+/g, "-")
              .replace(/^-|-$/g, "") === base
        );
        href = `/concordance/${hasCollision ? `${base}-${cluster.id}` : base}`;
      }
    }

    return {
      name: person.name,
      variants: person.variants || [],
      entityId: person.id,
      href,
    };
  });
}
