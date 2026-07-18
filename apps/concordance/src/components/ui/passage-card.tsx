import Link from "next/link";
import type { Passage } from "@/contracts/domain";
import { ExpandedContext } from "./expanded-context";
import { StatusNote } from "./status-note";
import styles from "./passage-card.module.css";

function highlighted(text: string, surface: string | null, matchStart: number | null, matchEnd: number | null) {
  if (!surface) return text;
  const characters = Array.from(text);
  if (matchStart !== null && matchEnd !== null && matchStart >= 0 && matchEnd > matchStart && matchEnd <= characters.length) {
    return (
      <>
        {characters.slice(0, matchStart).join("")}<mark>{characters.slice(matchStart, matchEnd).join("")}</mark>{characters.slice(matchEnd).join("")}
      </>
    );
  }
  const start = text.toLocaleLowerCase().indexOf(surface.toLocaleLowerCase());
  if (start < 0) return text;
  return (
    <>
      {text.slice(0, start)}<mark>{text.slice(start, start + surface.length)}</mark>{text.slice(start + surface.length)}
    </>
  );
}

export function PassageCard({ passage, entrySlug }: { passage: Passage; entrySlug?: string }) {
  const location = passage.printedPage ? `p. ${passage.printedPage}` : passage.scanLeaf !== null ? `scan leaf ${passage.scanLeaf}` : null;
  const citationUrl = `/passage/${passage.id}${entrySlug ? `?entry=${encodeURIComponent(entrySlug)}` : ""}`;
  return (
    <article className={styles.card}>
      <div className={styles.meta}>
        <div>
          <Link href={`/source/${passage.source.id}`} className={styles.source}>{passage.source.title}</Link>
          <span>{passage.source.author ? `${passage.source.author}, ` : ""}{passage.source.publicationYear}</span>
        </div>
        <StatusNote status={passage.status} />
      </div>
      <blockquote className="passage-text">{highlighted(passage.displayText, passage.surfaceForm, passage.matchStart, passage.matchEnd)}</blockquote>
      <ExpandedContext passageId={passage.id} />
      <footer className={styles.footer}>
        <span>{passage.source.languageLabel}{location ? ` · ${location}` : ""}</span>
        <div>
          <Link href={citationUrl}>Cite passage</Link>
          <a href={passage.scanUrl} target="_blank" rel="noreferrer">Open scan ↗</a>
        </div>
      </footer>
    </article>
  );
}
