import type { Metadata } from "next";
import Link from "next/link";
import styles from "./page.module.css";

export const metadata: Metadata = { title: "About" };

export default function AboutPage() {
  return (
    <article className={`shell ${styles.page}`}>
      <header>
        <h1>About</h1>
        <p className={styles.intro}>
          Premodern Concordance is a cross-linguistic guide to scientific and
          medical terminology in historical sources. It connects modern research
          terms to older names, spellings, translations, and neighboring ideas
          while keeping every result attached to its original passage.
        </p>
        <p className={styles.method}>
          Search the <Link href="/entries">concordance</Link>, read the indexed
          <Link href="/sources"> sources</Link>, or begin with a
          <Link href="/search"> term</Link>.
        </p>
      </header>

      <section>
        <h2 className="eyebrow">Personnel</h2>
        <div className={styles.people}>
          <div>
            <h3>Benjamin Breen</h3>
            <p>Department of History, UC Santa Cruz</p>
          </div>
          <div>
            <h3>Mackenzie Cooley</h3>
            <p>Department of History, Hamilton College</p>
          </div>
        </div>
      </section>

      <section>
        <h2 className="eyebrow">Colophon</h2>
        <div className={styles.colophon}>
          <div>
            <h3>Typography</h3>
            <ul>
              <li><span>System UI</span> — interface and body text</li>
              <li><span className={styles.blackletter}>UnifrakturMaguntia</span> — blackletter display</li>
              <li><span className={styles.serif}>EB Garamond</span> — source reading</li>
              <li><span className={styles.grotesk}>Space Grotesk</span> — alternate title display</li>
            </ul>
          </div>
          <div>
            <h3>Framework</h3>
            <ul>
              <li><span>Next.js 16</span> — application framework</li>
              <li><span>libSQL / Turso</span> — public entity registry</li>
              <li><span>Vercel</span> — deployment target</li>
            </ul>
          </div>
          <div>
            <h3>Research method</h3>
            <p>
              Curated entries combine multilingual retrieval, model-assisted
              preprocessing, and passage-level editorial review.
            </p>
          </div>
          <div>
            <h3>Site code</h3>
            <p>
              The project source is available on
              <a href="https://github.com/benjaminbreen/premodern-concordance" target="_blank" rel="noreferrer"> GitHub</a>.
            </p>
          </div>
        </div>
      </section>
    </article>
  );
}
