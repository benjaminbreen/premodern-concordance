import styles from "./search-box.module.css";
import { appPath } from "@/config/app-path";

export function SearchBox({ defaultValue = "" }: { defaultValue?: string }) {
  return (
    <form className={styles.form} action={appPath("/search")} role="search">
      <label className={styles.label} htmlFor="site-search">Search the concordance</label>
      <div className={styles.row}>
        <span className={styles.icon} aria-hidden>⌕</span>
        <input
          id="site-search"
          name="q"
          type="search"
          defaultValue={defaultValue}
          placeholder="Try cinchona, engineer, consciousness…"
          autoComplete="off"
        />
        <button type="submit">Search</button>
      </div>
    </form>
  );
}
