import Link from "next/link";
import { reviewModeEnabled } from "@/server/reviews/config";
import { ThemeToggle } from "./theme-toggle";
import styles from "./site-header.module.css";

const links = [
  ["/search", "Search"],
  ["/entries", "Entries"],
  ["/sources", "Sources"],
  ["/about", "About"]
] as const;

export function SiteHeader() {
  const visibleLinks = reviewModeEnabled()
    ? [...links, ["/review/findings", "Review"] as const]
    : links;
  return (
    <header className={styles.header}>
      <div className={`shell ${styles.inner}`}>
        <Link href="/" className={styles.wordmark}>Premodern Concordance</Link>
        <nav aria-label="Primary navigation" className={styles.nav}>
          {visibleLinks.map(([href, label]) => <Link key={href} href={href}>{label}</Link>)}
        </nav>
        <div className={styles.theme}><ThemeToggle /></div>
      </div>
    </header>
  );
}
