import type { Metadata } from "next";
import Link from "next/link";
import { EntryKindBadge } from "@/components/ui/entry-kind";
import { SearchBox } from "@/components/ui/search-box";
import { StatusNote } from "@/components/ui/status-note";
import { firstQueryValue, type QueryValue } from "@/config/query";
import { searchEntries } from "@/server/repositories/search";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "Search" };
export const dynamic = "force-dynamic";

export default async function SearchPage({ searchParams }: { searchParams: Promise<{ q?: QueryValue }> }) {
  const query = await searchParams;
  const q = firstQueryValue(query.q);
  const results = q.trim() ? await searchEntries(q) : [];
  return (
    <div className={`shell ${styles.page}`}>
      <header className={styles.header}>
        <p className="eyebrow">Search</p>
        <h1>Search the concordance</h1>
        <SearchBox defaultValue={q} />
      </header>
      {q.trim() ? (
        <section aria-live="polite">
          <p className={styles.summary}>{results.length} {results.length === 1 ? "entry" : "entries"} matching “{q}”</p>
          <div className={styles.results}>
            {results.map((result) => (
              <Link href={`/entry/${result.slug}`} key={result.id} className={styles.result}>
                <div className={styles.resultTop}>
                  <EntryKindBadge kind={result.kind} />
                  <StatusNote status={result.status} />
                </div>
                <h2>{result.preferredLabel}</h2>
                {result.matchedLabel !== result.preferredLabel && <p className={styles.match}>Matched historical form: <strong>{result.matchedLabel}</strong></p>}
                <p>{result.scopeNote}</p>
                <span>{result.sourceCount} sources · {result.passageCount} passages</span>
              </Link>
            ))}
            {!results.length && <p className={styles.empty}>No entries match “{q}”.</p>}
          </div>
        </section>
      ) : <p className={styles.empty}>Try a modern name, historical spelling, translation, or taxonomic term.</p>}
    </div>
  );
}
