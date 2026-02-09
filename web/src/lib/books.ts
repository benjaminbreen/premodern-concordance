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
};
