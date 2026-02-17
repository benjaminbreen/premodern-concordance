/**
 * Canonical book ID mappings.
 * Import from here instead of defining locally.
 */

/** Short display names keyed by book ID. */
export const BOOK_SHORT_NAMES: Record<string, string> = {
  english_physician_1652: "Culpeper",
  polyanthea_medicinal: "Semedo",
  coloquios_da_orta_1563: "Da Orta",
  historia_medicinal_monardes_1574: "Monardes",
  relation_historique_humboldt_vol3_1825: "Humboldt",
  ricettario_fiorentino_1597: "Ricettario",
  origin_of_species_darwin_1859: "Darwin",
  principles_of_psychology_james_1890: "James",
  pseudodoxia_epidemica_browne_1646: "Browne",
  first_principles_spencer_1862: "Spencer",
  connexion_physical_sciences_somerville_1858: "Somerville",
  kosmos_humboldt_1845: "Humboldt (Kosmos)",
  quatro_libros_naturaleza_hernandez_1615: "Hernández",
  epoques_nature_buffon_1778: "Buffon",
  medecine_experimentale_bernard_1865: "Bernard",
};

/** Cover image paths keyed by book ID. */
export const BOOK_COVERS: Record<string, string> = {
  polyanthea_medicinal: "/images/covers/semedo.png",
  english_physician_1652: "/images/covers/culpeper.png",
  coloquios_da_orta_1563: "/images/covers/orta.png",
  historia_medicinal_monardes_1574: "/images/covers/monardes.png",
  relation_historique_humboldt_vol3_1825: "/images/covers/humboldt.png",
  ricettario_fiorentino_1597: "/images/covers/ricettario.png",
  principles_of_psychology_james_1890: "/images/covers/james.png",
  origin_of_species_darwin_1859: "/images/covers/darwin.png",
  pseudodoxia_epidemica_browne_1646: "/images/covers/browne.png",
  first_principles_spencer_1862: "/images/covers/spencer.png",
  connexion_physical_sciences_somerville_1858: "/images/covers/somerville.png",
  kosmos_humboldt_1845: "/images/covers/kosmos.png",
  quatro_libros_naturaleza_hernandez_1615: "/images/covers/hernandez.png",
  epoques_nature_buffon_1778: "/images/covers/buffon.png",
  medecine_experimentale_bernard_1865: "/images/covers/bernard.png",
};

/** Publication year keyed by book ID. */
export const BOOK_YEARS: Record<string, number> = {
  coloquios_da_orta_1563: 1563,
  historia_medicinal_monardes_1574: 1574,
  ricettario_fiorentino_1597: 1597,
  english_physician_1652: 1652,
  polyanthea_medicinal: 1741,
  relation_historique_humboldt_vol3_1825: 1825,
  pseudodoxia_epidemica_browne_1646: 1646,
  origin_of_species_darwin_1859: 1859,
  connexion_physical_sciences_somerville_1858: 1858,
  first_principles_spencer_1862: 1862,
  principles_of_psychology_james_1890: 1890,
  kosmos_humboldt_1845: 1845,
  quatro_libros_naturaleza_hernandez_1615: 1615,
  epoques_nature_buffon_1778: 1778,
  medecine_experimentale_bernard_1865: 1865,
};

/** 2-letter language code keyed by book ID. */
export const BOOK_LANGS: Record<string, string> = {
  coloquios_da_orta_1563: "PT",
  historia_medicinal_monardes_1574: "ES",
  ricettario_fiorentino_1597: "IT",
  english_physician_1652: "EN",
  polyanthea_medicinal: "PT",
  relation_historique_humboldt_vol3_1825: "FR",
  pseudodoxia_epidemica_browne_1646: "EN",
  origin_of_species_darwin_1859: "EN",
  connexion_physical_sciences_somerville_1858: "EN",
  first_principles_spencer_1862: "EN",
  principles_of_psychology_james_1890: "EN",
  kosmos_humboldt_1845: "EN",
  quatro_libros_naturaleza_hernandez_1615: "ES",
  epoques_nature_buffon_1778: "FR",
  medecine_experimentale_bernard_1865: "FR",
};

/** Short title keyed by book ID. */
export const BOOK_TITLES: Record<string, string> = {
  coloquios_da_orta_1563: "Colóquios dos Simples",
  historia_medicinal_monardes_1574: "Historia Medicinal",
  ricettario_fiorentino_1597: "Ricettario Fiorentino",
  english_physician_1652: "The English Physician",
  polyanthea_medicinal: "Polyanthea Medicinal",
  relation_historique_humboldt_vol3_1825: "Relation Historique",
  pseudodoxia_epidemica_browne_1646: "Pseudodoxia Epidemica",
  origin_of_species_darwin_1859: "On the Origin of Species",
  connexion_physical_sciences_somerville_1858: "On the Connexion of the Physical Sciences",
  first_principles_spencer_1862: "First Principles",
  principles_of_psychology_james_1890: "Principles of Psychology",
  kosmos_humboldt_1845: "Cosmos",
  quatro_libros_naturaleza_hernandez_1615: "Quatro Libros de la Naturaleza",
  epoques_nature_buffon_1778: "Les Époques de la Nature",
  medecine_experimentale_bernard_1865: "Introduction à la médecine expérimentale",
};

/** Full-text file paths keyed by book ID. */
export const BOOK_TEXTS: Record<string, string> = {
  polyanthea_medicinal: "/texts/polyanthea_medicinal.txt",
  english_physician_1652: "/texts/english_physician_1652.txt",
  coloquios_da_orta_1563: "/texts/coloquios_da_orta_1563.txt",
  historia_medicinal_monardes_1574: "/texts/historia_medicinal_monardes_1574.txt",
  relation_historique_humboldt_vol3_1825: "/texts/relation_historique_humboldt_vol3_1825.txt",
  ricettario_fiorentino_1597: "/texts/ricettario_fiorentino_1597.txt",
  origin_of_species_darwin_1859: "/texts/origin_of_species_darwin_1859.txt",
  pseudodoxia_epidemica_browne_1646: "/texts/pseudodoxia_epidemica_browne_1646.txt",
  first_principles_spencer_1862: "/texts/first_principles_spencer_1862.txt",
  connexion_physical_sciences_somerville_1858: "/texts/connexion_physical_sciences_somerville_1858.txt",
  kosmos_humboldt_1845: "/texts/kosmos_humboldt_1845.txt",
  quatro_libros_naturaleza_hernandez_1615: "/texts/quatro_libros_naturaleza_hernandez_1615.txt",
  epoques_nature_buffon_1778: "/texts/epoques_nature_buffon_1778.txt",
  medecine_experimentale_bernard_1865: "/texts/medecine_experimentale_bernard_1865.txt",
};

/** Distinctive color per book for cross-book visualizations. */
export const BOOK_COLORS: Record<string, string> = {
  coloquios_da_orta_1563: "#22c55e",
  historia_medicinal_monardes_1574: "#f59e0b",
  ricettario_fiorentino_1597: "#ef4444",
  pseudodoxia_epidemica_browne_1646: "#8b5cf6",
  english_physician_1652: "#3b82f6",
  polyanthea_medicinal: "#ec4899",
  relation_historique_humboldt_vol3_1825: "#06b6d4",
  kosmos_humboldt_1845: "#14b8a6",
  connexion_physical_sciences_somerville_1858: "#f97316",
  origin_of_species_darwin_1859: "#84cc16",
  first_principles_spencer_1862: "#a855f7",
  principles_of_psychology_james_1890: "#e11d48",
  quatro_libros_naturaleza_hernandez_1615: "#d97706",
  epoques_nature_buffon_1778: "#059669",
  medecine_experimentale_bernard_1865: "#7c3aed",
};

/** Maps book_id to the person identity_id of its author. */
export const CORPUS_AUTHOR_IDS: Record<string, string | null> = {
  origin_of_species_darwin_1859: "darwin",
  relation_historique_humboldt_vol3_1825: "humboldt",
  kosmos_humboldt_1845: "humboldt",
  first_principles_spencer_1862: "spencer",
  principles_of_psychology_james_1890: "james",
  historia_medicinal_monardes_1574: "monardes",
  connexion_physical_sciences_somerville_1858: "somerville",
  pseudodoxia_epidemica_browne_1646: "browne",
  coloquios_da_orta_1563: "orta",
  english_physician_1652: "culpeper",
  polyanthea_medicinal: "semedo",
  ricettario_fiorentino_1597: null,
  quatro_libros_naturaleza_hernandez_1615: "hernandez",
  epoques_nature_buffon_1778: "buffon",
  medecine_experimentale_bernard_1865: "bernard",
};
