import { notFound } from "next/navigation";
import Link from "next/link";
import { PassageCard } from "@/components/ui/passage-card";
import { firstQueryValue, type QueryValue } from "@/config/query";
import { getPassage } from "@/server/repositories/passages";
import styles from "./page.module.css";

export const dynamic = "force-dynamic";

export default async function PassagePage({ params, searchParams }: { params: Promise<{ id: string }>; searchParams: Promise<{ entry?: QueryValue }> }) {
  const { id } = await params;
  const query = await searchParams;
  const entry = firstQueryValue(query.entry) || undefined;
  const passage = await getPassage(id, entry);
  if (!passage) notFound();
  return (
    <div className={`shell ${styles.page}`}>
      <header><p className="eyebrow">Citable passage</p><h1>{passage.source.title}</h1><p>{passage.source.citationText}</p></header>
      <PassageCard passage={passage} entrySlug={entry} />
      <section className={styles.citation}>
        <h2>Citation</h2>
        <p>{passage.source.citationText}{passage.printedPage ? ` Page ${passage.printedPage}.` : ""} Premodern Concordance passage <code>{passage.id}</code>.</p>
        <div><Link href={`/source/${passage.source.id}`}>View source record</Link><a href={passage.source.archiveUrl} target="_blank" rel="noreferrer">Archive record ↗</a></div>
      </section>
    </div>
  );
}
