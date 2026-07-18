import type { EntryKind } from "@/contracts/domain";
import styles from "./entry-kind.module.css";

const labels: Record<EntryKind, string> = {
  ORGANISM_TAXON: "Organism",
  SUBSTANCE_MATERIAL: "Material",
  DISEASE_CONDITION: "Condition",
  ANATOMY: "Anatomy",
  PRACTICE_METHOD: "Practice",
  ROLE_OCCUPATION: "Occupation",
  CONCEPT_THEORY: "Concept",
  PHENOMENON_PROCESS: "Phenomenon",
  OBJECT_INSTRUMENT: "Object"
};

export function EntryKindBadge({ kind }: { kind: EntryKind }) {
  return <span className={styles.badge} data-kind={kind}>{labels[kind]}</span>;
}
