import Link from "next/link";
import { InteractiveTitle } from "@/components/brand/interactive-title";
import { SearchBox } from "@/components/ui/search-box";
import { appPath } from "@/config/app-path";
import { getReleaseStats } from "@/server/repositories/release";
import { listSources } from "@/server/repositories/sources";
import styles from "./page.module.css";

const sampleTerms = ["cinchona", "human species", "engineer", "consciousness", "cosmos"];

const coverBySource: Record<string, string> = {
  pseudodoxia_epidemica_browne_1646: "browne.png",
  polyanthea_medicinal: "semedo.png",
  epoques_nature_buffon_1778: "buffon.png",
  lehrbuch_naturphilosophie_oken_1809: "oken.png",
  relation_historique_humboldt_vol3_1825: "humboldt.png",
  kosmos_humboldt_1845: "kosmos.png",
  connexion_physical_sciences_somerville_1858: "somerville.png",
  origin_of_species_darwin_1859: "darwin.png",
  first_principles_spencer_1862: "spencer.png",
  medecine_experimentale_bernard_1865: "bernard.png",
  principles_of_psychology_james_1890: "james.png"
};

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const [stats, sources] = await Promise.all([getReleaseStats(), listSources()]);
  const displaySources = sources.filter((source) => coverBySource[source.id]).slice(0, 9);
  const languageCount = new Set(sources.map((source) => source.languageCode)).size;
  const years = sources.map((source) => source.publicationYear);
  const timespan = `${Math.min(...years)}–${Math.max(...years)}`;
  return (
    <div className={`shell ${styles.page}`}>
      <section className={styles.hero} aria-labelledby="home-title">
        <div className={`${styles.titleColumn} fade-up`} id="home-title">
          <InteractiveTitle />
          <p className={styles.subtitle}>Cross-linguistic term history across scientific and medical texts.</p>
        </div>
        <div className={`${styles.introduction} fade-up`}>
          <p>
            Search historical terms across languages and centuries, then read each
            result in its original passage and edition.
          </p>
          <SearchBox />
          <div className={styles.examples}>
            <span>Explore:</span>
            {sampleTerms.map((term) => <Link key={term} href={`/search?q=${encodeURIComponent(term)}`}>{term}</Link>)}
          </div>
        </div>
      </section>

      <section className={styles.metrics} aria-label="Current collection">
        <div><strong>{stats.entryCount}</strong><span>entries</span></div>
        <div><strong>{stats.sourceCount}</strong><span>sources</span></div>
        <div><strong>{languageCount}</strong><span>languages</span></div>
        <div><strong>{stats.passageCount}</strong><span>passages</span></div>
        <div><strong>{timespan}</strong><span>timespan</span></div>
      </section>

      <section className={styles.corpus} aria-labelledby="corpus-heading">
        <div className={styles.corpusHeading}>
          <h2 className="eyebrow" id="corpus-heading">The corpus</h2>
          <Link href="/sources">View all sources</Link>
        </div>
        <div className={styles.coverRail}>
          {displaySources.map((source) => (
            <Link className={styles.coverLink} href={`/source/${source.id}`} key={source.id}>
              {/* eslint-disable-next-line @next/next/no-img-element */}
              <img src={appPath(`/images/covers/${coverBySource[source.id]}`)} alt={`Title page of ${source.title}`} />
              <span><strong>{source.title}</strong><small>{source.author} · {source.publicationYear}</small></span>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
