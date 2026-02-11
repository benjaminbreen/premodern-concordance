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
};
