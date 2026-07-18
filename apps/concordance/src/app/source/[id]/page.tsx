import Link from "next/link";
import { notFound } from "next/navigation";
import { PassageCard } from "@/components/ui/passage-card";
import { firstQueryValue, type QueryValue } from "@/config/query";
import { getSource, getSourcePassages } from "@/server/repositories/sources";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

export default async function SourcePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ offset?: QueryValue }> }) {
  const { id } = await params;
  const query = await searchParams;
  const parsedOffset = Number.parseInt(firstQueryValue(query.offset, "0"), 10);
  const offset = Number.isFinite(parsedOffset) ? Math.max(parsedOffset, 0) : 0;
  const pageSize = 20;
  const [source, passages] = await Promise.all([getSource(id), getSourcePassages(id, pageSize, offset)]);
  if (!source) notFound();
  return (
    <div className={`shell ${styles.page}`}>
      <header><p className="eyebrow">Source witness</p><h1>{source.title}</h1><p className={styles.byline}>{source.author ? `${source.author} · ` : ""}{source.publicationYear} · {source.languageLabel}</p><p>{source.citationText}</p><a href={source.archiveUrl} target="_blank" rel="noreferrer">Open {source.archiveProvider ?? "archive"} record ↗</a></header>
      <section><p className="eyebrow">Indexed evidence</p><h2>{source.passageCount} passages</h2>{passages.map((passage) => <PassageCard key={passage.id} passage={passage} />)}
        {(offset > 0 || offset + passages.length < source.passageCount) && <nav className={styles.pagination} aria-label="Source passage pages">
          {offset > 0 ? <Link href={`/source/${source.id}?offset=${Math.max(0, offset - pageSize)}`}>← Earlier passages</Link> : <span />}
          {offset + passages.length < source.passageCount && <Link href={`/source/${source.id}?offset=${offset + pageSize}`}>Later passages →</Link>}
        </nav>}
      </section>
    </div>
  );
}
