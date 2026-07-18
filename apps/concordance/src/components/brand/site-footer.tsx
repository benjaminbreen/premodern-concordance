import Link from "next/link";
import styles from "./site-footer.module.css";

const corpusLinks = [
  ["/search", "Search"],
  ["/entries", "Entries"],
  ["/sources", "Sources"]
] as const;

const projectLinks = [
  ["/about", "About"]
] as const;

export function SiteFooter() {
  return (
    <footer className={styles.footer}>
      <div className={`shell ${styles.inner}`}>
        <div className={styles.grid}>
          <Link className={styles.signature} href="/" aria-label="Premodern Concordance home">
            <span className={styles.monogram} aria-hidden><span>P</span><span>C</span></span>
            <span className={styles.fullName} aria-hidden><span>Premodern</span><span>Concordance</span></span>
          </Link>

          <div className={styles.spacer} />

          <nav aria-label="Corpus links">
            <h2>Corpus</h2>
            <ul>
              {corpusLinks.map(([href, label]) => <li key={href}><Link href={href}>{label}</Link></li>)}
            </ul>
          </nav>

          <nav aria-label="Project links">
            <h2>Project</h2>
            <ul>
              {projectLinks.map(([href, label]) => <li key={href}><Link href={href}>{label}</Link></li>)}
              <li><a href="https://github.com/benjaminbreen/premodern-concordance" target="_blank" rel="noreferrer">GitHub</a></li>
            </ul>
          </nav>
        </div>

        <div className={styles.bottom}>
          <p>A cross-linguistic concordance of historical scientific and medical terms.</p>
        </div>
      </div>
    </footer>
  );
}
