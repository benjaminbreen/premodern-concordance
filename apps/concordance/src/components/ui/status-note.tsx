import type { PublicationStatus } from "@/contracts/domain";
import styles from "./status-note.module.css";

export function StatusNote({ status }: { status: PublicationStatus }) {
  if (status === "CORE") return null;
  return (
    <span className={styles.note} title="This connection has not received editorial verification">
      Suggested
    </span>
  );
}
