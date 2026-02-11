"use client";

import React, { useState, useMemo, useEffect, useRef, useCallback } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useBookContext } from "../BookContext";
import { CAT_HEX as CATEGORY_COLORS_HEX, CATEGORY_ORDER } from "@/lib/colors";
import { BOOK_SHORT_NAMES, BOOK_COVERS, BOOK_TEXTS } from "@/lib/books";
import {
  forceSimulation,
  forceLink,
  forceManyBody,
  forceCenter,
  forceCollide,
  type SimulationNodeDatum,
  type SimulationLinkDatum,
} from "d3-force";
import { scaleSqrt, scaleLinear } from "d3-scale";

// ── Interfaces ──────────────────────────────────────────────────────────────

interface BibliographyEntry {
  author: string;
  year: number;
  title: string;
  type: "monograph" | "article" | "chapter" | "edition";
  venue?: string;
  url?: string;
  essential?: boolean;
}

// ── Constants ───────────────────────────────────────────────────────────────


const BOOK_METADATA: Record<string, { internetArchiveUrl: string }> = {
  polyanthea_medicinal: { internetArchiveUrl: "https://archive.org/details/polyanthea-medicinal" },
  english_physician_1652: { internetArchiveUrl: "https://archive.org/details/englishphysician00culp" },
  coloquios_da_orta_1563: { internetArchiveUrl: "https://archive.org/details/coloquiosdossim00teleGoogle" },
  historia_medicinal_monardes_1574: { internetArchiveUrl: "https://archive.org/details/primerasegundayt00mona" },
  relation_historique_humboldt_vol3_1825: { internetArchiveUrl: "https://archive.org/details/relationhistoriq03humb" },
  ricettario_fiorentino_1597: { internetArchiveUrl: "https://archive.org/details/ricettariofiorentino1597" },
  principles_of_psychology_james_1890: { internetArchiveUrl: "https://archive.org/details/theprinciplesofp01jameuoft" },
  origin_of_species_darwin_1859: { internetArchiveUrl: "https://archive.org/details/onoriginofspecie00darw" },
};

// ── Bibliography Data ───────────────────────────────────────────────────────

const BOOK_BIBLIOGRAPHY: Record<string, BibliographyEntry[]> = {
  polyanthea_medicinal: [
    { author: "Walker, Timothy D.", year: 2013, title: "Acquisition and Circulation of Medical Knowledge within the Early Modern Portuguese Colonial Empire", type: "chapter", venue: "In Science in the Spanish and Portuguese Empires, 1500–1800, ed. Daniela Bleichmar et al., Stanford UP", essential: true, url: "https://doi.org/10.1515/9780804786515-005" },
    { author: "Dias, José Pedro Sousa", year: 2005, title: "A Farmácia e a História: Uma Introdução à História da Farmácia, da Farmacologia e da Terapêutica", type: "monograph", venue: "Lisbon: Faculdade de Farmácia da Universidade de Lisboa", essential: true },
    { author: "Walker, Timothy D.", year: 2005, title: "Doctors, Folk Medicine and the Inquisition: The Repression of Magical Healing in Portugal during the Enlightenment", type: "monograph", venue: "Leiden: Brill", essential: true, url: "https://doi.org/10.1163/9789047406884" },
    { author: "Pita, João Rui", year: 1998, title: "Farmácia, Medicina e Saúde Pública em Portugal (1772–1836)", type: "monograph", venue: "Coimbra: Minerva" },
    { author: "Lemos, Maximiano de", year: 1991, title: "História da Medicina em Portugal", type: "monograph", venue: "Lisbon: Dom Quixote, 2 vols." },
    { author: "Walker, Timothy D.", year: 2009, title: "The Medicines Trade in the Portuguese Atlantic World: Acquisition and Dissemination of Healing Knowledge from Brazil (c. 1580–1800)", type: "article", venue: "Social History of Medicine 26(3): 403–431", url: "https://doi.org/10.1093/shm/hkt015" },
    { author: "Conde, Antónia Fialho", year: 2018, title: "Curvo Semedo's Medical Practices and the Portuguese Inquisition", type: "article", venue: "História, Ciências, Saúde – Manguinhos 25(4): 1023–1040", url: "https://doi.org/10.1590/S0104-59702018000500005" },
    { author: "Soares, Márcio de Sousa", year: 2009, title: "Médicos e Mezinheiros na Corte Imperial: Uma Herança Colonial", type: "article", venue: "História, Ciências, Saúde – Manguinhos 8(2): 407–438", url: "https://doi.org/10.1590/S0104-59702001000300006" },
    { author: "Marques, Vera Regina Beltrão", year: 1999, title: "Natureza em Boiões: Medicinas e Boticários no Brasil Setecentista", type: "monograph", venue: "Campinas: Editora Unicamp" },
    { author: "Abreu, Laurinda", year: 2010, title: "Pina Manique: An Enlightened Reformer in Portugal?", type: "monograph", venue: "Bern: Peter Lang" },
  ],
  english_physician_1652: [
    { author: "Tobyn, Graeme", year: 1997, title: "Culpeper's Medicine: A Practice of Western Holistic Medicine", type: "monograph", venue: "Shaftesbury: Element Books", essential: true },
    { author: "Woolley, Benjamin", year: 2004, title: "The Herbalist: Nicholas Culpeper and the Fight for Medical Freedom", type: "monograph", venue: "London: HarperCollins", essential: true },
    { author: "Geneva, Ann", year: 1995, title: "Astrology and the Seventeenth-Century Mind: William Lilly and the Language of the Stars", type: "monograph", venue: "Manchester: Manchester UP", essential: true },
    { author: "Wear, Andrew", year: 2000, title: "Knowledge and Practice in English Medicine, 1550–1680", type: "monograph", venue: "Cambridge: Cambridge UP", url: "https://doi.org/10.1017/CBO9780511612640" },
    { author: "Webster, Charles", year: 1975, title: "The Great Instauration: Science, Medicine, and Reform 1626–1660", type: "monograph", venue: "London: Duckworth" },
    { author: "Elmer, Peter", year: 2004, title: "The Library of Dr John Webster: The Making of a Seventeenth-Century Radical", type: "monograph", venue: "London: Wellcome Trust" },
    { author: "Furdell, Elizabeth Lane", year: 2002, title: "Publishing and Medicine in Early Modern England", type: "monograph", venue: "Rochester, NY: University of Rochester Press" },
    { author: "Stobart, Anne", year: 2016, title: "Household Medicine in Seventeenth-Century England", type: "monograph", venue: "London: Bloomsbury Academic", url: "https://doi.org/10.5040/9781474219587" },
    { author: "Leong, Elaine", year: 2018, title: "Recipes and Everyday Knowledge: Medicine, Science, and the Household in Early Modern England", type: "monograph", venue: "Chicago: University of Chicago Press", url: "https://doi.org/10.7208/chicago/9780226583617.001.0001" },
    { author: "Kassell, Lauren", year: 2005, title: "Medicine and Magic in Elizabethan London: Simon Forman, Astrologer, Alchemist, and Physician", type: "monograph", venue: "Oxford: Oxford UP", url: "https://doi.org/10.1093/acprof:oso/9780199279050.001.0001" },
    { author: "Poole, William", year: 2004, title: "Nicholas Culpeper as Book Man", type: "article", venue: "Huntington Library Quarterly 67(3): 413–442", url: "https://doi.org/10.1525/hlq.2004.67.3.413" },
    { author: "Thulesius, Olav", year: 1992, title: "Nicholas Culpeper: English Physician and Astrologer", type: "monograph", venue: "New York: St. Martin's Press" },
  ],
  coloquios_da_orta_1563: [
    { author: "Pearson, M. N.", year: 2001, title: "The World of the Indian Ocean, 1500–1800: Studies in Economic, Social and Cultural History", type: "monograph", venue: "Aldershot: Ashgate", essential: true },
    { author: "Grove, Richard", year: 1996, title: "Green Imperialism: Colonial Expansion, Tropical Island Edens and the Origins of Environmentalism, 1600–1860", type: "monograph", venue: "Cambridge: Cambridge UP", essential: true, url: "https://doi.org/10.1017/CBO9780511620584" },
    { author: "Fontes da Costa, Palmira", year: 2015, title: "Medicine, Trade, and Empire: Garcia de Orta's Colloquies on the Simples and Drugs of India (1563) in Context", type: "monograph", venue: "Farnham: Ashgate", essential: true },
    { author: "Boxer, C. R.", year: 1963, title: "Two Pioneers of Tropical Medicine: Garcia d'Orta and Nicolás Monardes", type: "monograph", venue: "London: Wellcome Historical Medical Library", essential: true },
    { author: "Costa, Catarina Madruga", year: 2020, title: "Garcia de Orta's Colóquios dos Simples: Conversations on the Medico-botanical Frontier", type: "article", venue: "Early Science and Medicine 25(4): 349–375", url: "https://doi.org/10.1163/15733823-00254P04" },
    { author: "Walker, Timothy D.", year: 2013, title: "The Role and Practices of the Curandeiro and Saludador in Early Modern Portuguese Society", type: "article", venue: "História, Ciências, Saúde – Manguinhos 11 (suppl. 1): 223–237", url: "https://doi.org/10.1590/S0104-59702004000400011" },
    { author: "Mathew, K. S.", year: 1997, title: "Indo-Portuguese Trade and the Fuggers of Germany", type: "monograph", venue: "New Delhi: Manohar" },
    { author: "Subrahmanyam, Sanjay", year: 2012, title: "The Portuguese Empire in Asia, 1500–1700: A Political and Economic History", type: "monograph", venue: "Chichester: Wiley-Blackwell, 2nd ed." },
    { author: "Cook, Harold J.", year: 2007, title: "Matters of Exchange: Commerce, Medicine, and Science in the Dutch Golden Age", type: "monograph", venue: "New Haven: Yale UP" },
    { author: "Ferrão, José E. Mendes", year: 2005, title: "A Aventura das Plantas e os Descobrimentos Portugueses", type: "monograph", venue: "Lisbon: Instituto de Investigação Científica Tropical, 3rd ed." },
    { author: "Bracht, Fabiano", year: 2019, title: "Garcia de Orta e a Circulação de Saberes sobre Drogas no Império Português", type: "article", venue: "Revista de História (São Paulo) 178: 1–34", url: "https://doi.org/10.11606/issn.2316-9141.rh.2019.142344" },
  ],
  historia_medicinal_monardes_1574: [
    { author: "Norton, Marcy", year: 2008, title: "Sacred Gifts, Profane Pleasures: A History of Tobacco and Chocolate in the Atlantic World", type: "monograph", venue: "Ithaca: Cornell UP", essential: true },
    { author: "Bleichmar, Daniela", year: 2012, title: "Visible Empire: Botanical Expeditions and Visual Culture in the Hispanic Enlightenment", type: "monograph", venue: "Chicago: University of Chicago Press", essential: true, url: "https://doi.org/10.7208/chicago/9780226058559.001.0001" },
    { author: "Boxer, C. R.", year: 1963, title: "Two Pioneers of Tropical Medicine: Garcia d'Orta and Nicolás Monardes", type: "monograph", venue: "London: Wellcome Historical Medical Library", essential: true },
    { author: "Slater, John", year: 2014, title: "Todos son hojas: Literatura e historia natural en el barroco español", type: "monograph", venue: "Madrid: CSIC" },
    { author: "Barrera-Osorio, Antonio", year: 2006, title: "Experiencing Nature: The Spanish American Empire and the Early Scientific Revolution", type: "monograph", venue: "Austin: University of Texas Press", essential: true },
    { author: "Goodman, Jordan", year: 1994, title: "Tobacco in History: The Cultures of Dependence", type: "monograph", venue: "London: Routledge" },
    { author: "Pardo-Tomás, José", year: 2002, title: "Oviedo, Monardes, Hernández: El Tesoro Natural de América", type: "monograph", venue: "Madrid: Nivola" },
    { author: "López Piñero, José María", year: 1989, title: "Los Orígenes en España de los Estudios sobre la Salud Pública", type: "monograph", venue: "Madrid: Ministerio de Sanidad" },
    { author: "Huguet-Termes, Teresa", year: 2001, title: "New World Materia Medica in Spanish Renaissance Medicine: From Scholarly Reception to Practical Impact", type: "article", venue: "Medical History 45(3): 359–376", url: "https://doi.org/10.1017/S0025727300068290" },
    { author: "Schiebinger, Londa", year: 2004, title: "Plants and Empire: Colonial Bioprospecting in the Atlantic World", type: "monograph", venue: "Cambridge, MA: Harvard UP" },
    { author: "Crawford, Matthew J.", year: 2016, title: "The Andean Wonder Drug: Cinchona Bark and Imperial Science in the Spanish Atlantic, 1630–1800", type: "monograph", venue: "Pittsburgh: University of Pittsburgh Press", url: "https://doi.org/10.2307/j.ctt1k3s9wm" },
    { author: "Delbourgo, James and Dew, Nicholas (eds.)", year: 2008, title: "Science and Empire in the Atlantic World", type: "monograph", venue: "New York: Routledge" },
  ],
  relation_historique_humboldt_vol3_1825: [
    { author: "Wulf, Andrea", year: 2015, title: "The Invention of Nature: Alexander von Humboldt's New World", type: "monograph", venue: "New York: Knopf", essential: true },
    { author: "Walls, Laura Dassow", year: 2009, title: "The Passage to Cosmos: Alexander von Humboldt and the Shaping of America", type: "monograph", venue: "Chicago: University of Chicago Press", essential: true, url: "https://doi.org/10.7208/chicago/9780226871837.001.0001" },
    { author: "Rupke, Nicolaas", year: 2008, title: "Alexander von Humboldt: A Metabiography", type: "monograph", venue: "Chicago: University of Chicago Press", essential: true },
    { author: "Dettelbach, Michael", year: 1996, title: "Humboldtian Science", type: "chapter", venue: "In Cultures of Natural History, ed. N. Jardine et al., Cambridge UP" },
    { author: "Pratt, Mary Louise", year: 1992, title: "Imperial Eyes: Travel Writing and Transculturation", type: "monograph", venue: "London: Routledge", essential: true },
    { author: "Cannon, Susan Faye", year: 1978, title: "Science in Culture: The Early Victorian Period", type: "monograph", venue: "New York: Science History Publications" },
    { author: "Nicolson, Malcolm", year: 1987, title: "Alexander von Humboldt, Humboldtian Science and the Origins of the Study of Vegetation", type: "article", venue: "History of Science 25(2): 167–194", url: "https://doi.org/10.1177/007327538702500203" },
    { author: "Helferich, Gerard", year: 2004, title: "Humboldt's Cosmos: Alexander von Humboldt and the Latin American Journey That Changed the Way We See the World", type: "monograph", venue: "New York: Gotham Books" },
    { author: "Rebok, Sandra", year: 2014, title: "Humboldt and Jefferson: A Transatlantic Friendship of the Enlightenment", type: "monograph", venue: "Charlottesville: University of Virginia Press" },
    { author: "Sachs, Aaron", year: 2006, title: "The Humboldt Current: Nineteenth-Century Exploration and the Roots of American Environmentalism", type: "monograph", venue: "New York: Viking" },
    { author: "Ette, Ottmar", year: 2009, title: "Alexander von Humboldt und die Globalisierung", type: "monograph", venue: "Frankfurt: Suhrkamp" },
  ],
  ricettario_fiorentino_1597: [
    { author: "Gentilcore, David", year: 1998, title: "Healers and Healing in Early Modern Italy", type: "monograph", venue: "Manchester: Manchester UP", essential: true },
    { author: "Findlen, Paula", year: 1994, title: "Possessing Nature: Museums, Collecting, and Scientific Culture in Early Modern Italy", type: "monograph", venue: "Berkeley: University of California Press", essential: true },
    { author: "Leong, Elaine and Rankin, Alisha (eds.)", year: 2011, title: "Secrets and Knowledge in Medicine and Science, 1500–1800", type: "monograph", venue: "Farnham: Ashgate", essential: true },
    { author: "Palmer, Richard", year: 1985, title: "Pharmacy in the Republic of Venice in the Sixteenth Century", type: "chapter", venue: "In The Medical Renaissance of the Sixteenth Century, ed. A. Wear et al., Cambridge UP" },
    { author: "Siraisi, Nancy G.", year: 1990, title: "Medieval and Early Renaissance Medicine: An Introduction to Knowledge and Practice", type: "monograph", venue: "Chicago: University of Chicago Press" },
    { author: "Park, Katharine", year: 1985, title: "Doctors and Medicine in Early Renaissance Florence", type: "monograph", venue: "Princeton: Princeton UP" },
    { author: "Eamon, William", year: 1994, title: "Science and the Secrets of Nature: Books of Secrets in Medieval and Early Modern Culture", type: "monograph", venue: "Princeton: Princeton UP" },
    { author: "Cavallo, Sandra and Storey, Tessa", year: 2013, title: "Healthy Living in Late Renaissance Italy", type: "monograph", venue: "Oxford: Oxford UP", url: "https://doi.org/10.1093/acprof:oso/9780199678136.001.0001" },
    { author: "Rankin, Alisha", year: 2013, title: "Panaceia's Daughters: Noblewomen as Healers in Early Modern Germany", type: "monograph", venue: "Chicago: University of Chicago Press", url: "https://doi.org/10.7208/chicago/9780226040264.001.0001" },
    { author: "Pomata, Gianna", year: 2010, title: "Sharing Cases: The Observationes in Early Modern Medicine", type: "article", venue: "Early Science and Medicine 15(3): 193–236", url: "https://doi.org/10.1163/157338210X493932" },
    { author: "Giglioni, Guido", year: 2010, title: "What Ever Happened to Francis Bacon's Natural Philosophy?", type: "article", venue: "Early Science and Medicine 15(6): 539–552", url: "https://doi.org/10.1163/157338210X516143" },
  ],
  principles_of_psychology_james_1890: [
    { author: "Richardson, Robert D.", year: 2006, title: "William James: In the Maelstrom of American Modernism", type: "monograph", venue: "Boston: Houghton Mifflin", essential: true },
    { author: "Menand, Louis", year: 2001, title: "The Metaphysical Club: A Story of Ideas in America", type: "monograph", venue: "New York: Farrar, Straus and Giroux", essential: true },
    { author: "Leary, David E.", year: 2018, title: "The Routledge Guidebook to James's Principles of Psychology", type: "monograph", venue: "London: Routledge", essential: true, url: "https://doi.org/10.4324/9781315676623" },
    { author: "Taylor, Eugene", year: 1996, title: "William James on Consciousness beyond the Margin", type: "monograph", venue: "Princeton: Princeton UP", essential: true },
    { author: "Myers, Gerald E.", year: 1986, title: "William James: His Life and Thought", type: "monograph", venue: "New Haven: Yale UP" },
    { author: "Bordogna, Francesca", year: 2008, title: "William James at the Boundaries: Philosophy, Science, and the Geography of Knowledge", type: "monograph", venue: "Chicago: University of Chicago Press", url: "https://doi.org/10.7208/chicago/9780226066523.001.0001" },
    { author: "Croce, Paul Jerome", year: 1995, title: "Science and Religion in the Era of William James: Eclipse of Certainty, 1820–1880", type: "monograph", venue: "Chapel Hill: University of North Carolina Press" },
    { author: "Gale, Richard M.", year: 1999, title: "The Divided Self of William James", type: "monograph", venue: "Cambridge: Cambridge UP", url: "https://doi.org/10.1017/CBO9781139173100" },
    { author: "Simon, Linda", year: 1998, title: "Genuine Reality: A Life of William James", type: "monograph", venue: "New York: Harcourt Brace" },
    { author: "Bjork, Daniel W.", year: 1983, title: "The Compromised Scientist: William James in the Development of American Psychology", type: "monograph", venue: "New York: Columbia UP" },
    { author: "Johnson, Mark", year: 2006, title: "Mind Incarnate: From Dewey to Damasio", type: "article", venue: "Daedalus 135(3): 46–54", url: "https://doi.org/10.1162/daed.2006.135.3.46" },
    { author: "Hatfield, Gary", year: 2002, title: "Psychology, Philosophy, and Cognitive Science: Reflections on the History and Philosophy of Experimental Psychology", type: "article", venue: "Mind & Language 17(3): 207–232", url: "https://doi.org/10.1111/1468-0017.00196" },
  ],
  origin_of_species_darwin_1859: [
    { author: "Browne, Janet", year: 1995, title: "Charles Darwin: Voyaging", type: "monograph", venue: "London: Jonathan Cape", essential: true },
    { author: "Browne, Janet", year: 2002, title: "Charles Darwin: The Power of Place", type: "monograph", venue: "London: Jonathan Cape", essential: true },
    { author: "Desmond, Adrian and Moore, James", year: 1991, title: "Darwin", type: "monograph", venue: "London: Michael Joseph", essential: true },
    { author: "Secord, James A.", year: 2000, title: "Victorian Sensation: The Extraordinary Publication, Reception, and Secret Authorship of Vestiges of the Natural History of Creation", type: "monograph", venue: "Chicago: University of Chicago Press", essential: true, url: "https://doi.org/10.7208/chicago/9780226158259.001.0001" },
    { author: "Ospovat, Dov", year: 1981, title: "The Development of Darwin's Theory: Natural History, Natural Theology, and Natural Selection, 1838–1859", type: "monograph", venue: "Cambridge: Cambridge UP" },
    { author: "Richards, Robert J.", year: 1992, title: "The Meaning of Evolution: The Morphological Construction and Ideological Reconstruction of Darwin's Theory", type: "monograph", venue: "Chicago: University of Chicago Press" },
    { author: "Bowler, Peter J.", year: 1996, title: "Life's Splendid Drama: Evolutionary Biology and the Reconstruction of Life's Ancestry, 1860–1940", type: "monograph", venue: "Chicago: University of Chicago Press" },
    { author: "Kohn, David (ed.)", year: 1985, title: "The Darwinian Heritage", type: "monograph", venue: "Princeton: Princeton UP" },
    { author: "Hodge, Jonathan and Radick, Gregory (eds.)", year: 2009, title: "The Cambridge Companion to Darwin", type: "monograph", venue: "Cambridge: Cambridge UP, 2nd ed.", url: "https://doi.org/10.1017/CCOL9780521884754" },
    { author: "Sloan, Phillip R.", year: 2009, title: "Darwin, Vital Matter, and the Transformism of Species", type: "article", venue: "Journal of the History of Biology 42(4): 677–725", url: "https://doi.org/10.1007/s10739-009-9194-3" },
    { author: "Endersby, Jim", year: 2009, title: "Sympathetic Science: Charles Darwin, Joseph Hooker, and the Passions of Victorian Naturalists", type: "article", venue: "Victorian Studies 51(2): 299–320", url: "https://doi.org/10.2979/VIC.2009.51.2.299" },
  ],
};

// ── TYPE_LABELS ─────────────────────────────────────────────────────────────

const TYPE_LABELS: Record<string, { label: string; color: string }> = {
  monograph: { label: "Book", color: "bg-blue-500/15 text-blue-700 dark:text-blue-400" },
  article: { label: "Article", color: "bg-amber-500/15 text-amber-700 dark:text-amber-400" },
  chapter: { label: "Chapter", color: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-400" },
  edition: { label: "Edition", color: "bg-purple-500/15 text-purple-700 dark:text-purple-400" },
};

// ── CategoryRing SVG ────────────────────────────────────────────────────────

function CategoryRing({ byCategory, total, size = 120 }: { byCategory: Record<string, number>; total: number; size?: number }) {
  const r = size / 2;
  const strokeWidth = size * 0.1;
  const innerR = r - strokeWidth / 2 - 1;
  const circumference = 2 * Math.PI * innerR;

  let offset = 0;

  return (
    <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
      {CATEGORY_ORDER.map((category) => {
        const count = byCategory[category] || 0;
        if (count === 0) return null;
        const pct = count / total;
        const dash = pct * circumference;
        const gap = circumference - dash;
        const currentOffset = offset;
        offset += dash;
        return (
          <circle
            key={category}
            cx={r}
            cy={r}
            r={innerR}
            fill="none"
            stroke={CATEGORY_COLORS_HEX[category] || "#888"}
            strokeWidth={strokeWidth}
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={-currentOffset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${r} ${r})`}
          />
        );
      })}
    </svg>
  );
}

// ── Main Page ───────────────────────────────────────────────────────────────

export default function BookResearchPage() {
  const { bookData } = useBookContext();
  const [showAll, setShowAll] = useState(false);

  const categorySorted = useMemo(() => {
    if (!bookData) return [];
    return CATEGORY_ORDER
      .filter((c) => bookData.stats.by_category[c] && bookData.stats.by_category[c] > 0)
      .map((c) => ({ category: c, count: bookData.stats.by_category[c] }));
  }, [bookData]);

  const bibliography = useMemo(() => {
    if (!bookData) return [];
    return BOOK_BIBLIOGRAPHY[bookData.book.id] || [];
  }, [bookData]);

  const essentialSources = useMemo(() => bibliography.filter((b) => b.essential), [bibliography]);
  const additionalSources = useMemo(() => bibliography.filter((b) => !b.essential), [bibliography]);

  const coverSrc = BOOK_COVERS[bookData.book.id];
  const meta = BOOK_METADATA[bookData.book.id];
  const categoriesCount = Object.keys(bookData.stats.by_category).filter(
    (k) => bookData.stats.by_category[k] > 0
  ).length;

  return (
    <>
      {/* Split panel */}
      <div className="flex flex-col lg:flex-row gap-8 lg:gap-12">
        {/* ── Sidebar ── */}
        <aside className="lg:w-[280px] lg:shrink-0">
          <div className="lg:sticky lg:top-24 space-y-6">
            {/* Cover */}
            {coverSrc && (
              <img
                src={coverSrc}
                alt={`Title page of ${bookData.book.title}`}
                className="w-full rounded-lg shadow-lg border border-[var(--border)]"
              />
            )}

            {/* Category ring */}
            <div className="flex flex-col items-center">
              <CategoryRing
                byCategory={bookData.stats.by_category}
                total={bookData.stats.total_entities}
                size={140}
              />
              <div className="mt-3 space-y-1 w-full">
                {categorySorted.slice(0, 4).map(({ category, count }) => (
                  <div key={category} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-1.5 text-[var(--muted)]">
                      <span
                        className="inline-block w-2 h-2 rounded-sm shrink-0"
                        style={{ backgroundColor: CATEGORY_COLORS_HEX[category] || "#888" }}
                      />
                      {category.charAt(0) + category.slice(1).toLowerCase()}
                    </span>
                    <span className="font-mono text-[var(--foreground)] text-xs">
                      {count.toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            </div>

            {/* Quick stats */}
            <div className="text-sm text-[var(--muted)] space-y-1 pt-2 border-t border-[var(--border)]">
              <div className="flex justify-between">
                <span>Total entities</span>
                <span className="font-mono text-[var(--foreground)]">
                  {bookData.stats.total_entities.toLocaleString()}
                </span>
              </div>
              <div className="flex justify-between">
                <span>Categories</span>
                <span className="font-mono text-[var(--foreground)]">{categoriesCount}</span>
              </div>
            </div>

            {/* Action links */}
            <div className="space-y-2 pt-2">
              {BOOK_TEXTS[bookData.book.id] && (
                <a
                  href={BOOK_TEXTS[bookData.book.id]}
                  download
                  className="w-full px-4 py-2 border border-[var(--border)] rounded-lg text-sm text-[var(--foreground)] hover:bg-[var(--border)] transition-colors flex items-center justify-between"
                >
                  Download .txt
                  <svg className="w-4 h-4 text-[var(--muted)]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4" />
                  </svg>
                </a>
              )}
              {meta && (
                <a
                  href={meta.internetArchiveUrl}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="w-full px-4 py-2 border border-[var(--border)] rounded-lg text-sm text-[var(--foreground)] hover:bg-[var(--border)] transition-colors flex items-center justify-between"
                >
                  Internet Archive
                  <span className="text-[var(--muted)]">&rarr;</span>
                </a>
              )}
            </div>
          </div>
        </aside>

        {/* ── Content ── */}
        <article className="flex-1 min-w-0 space-y-12">
          {/* Header */}
          <section>
            <h1 className="text-3xl font-bold mb-2">Research &amp; Sources</h1>
            <p className="text-lg text-[var(--muted)]">
              {bookData.book.title}
            </p>
            <p className="text-sm text-[var(--muted)] mt-2 max-w-2xl leading-relaxed">
              Curated secondary literature for contextualizing this text. Essential readings are highlighted; additional sources provide deeper historiographic coverage.
            </p>
          </section>

          {/* Essential Sources */}
          {essentialSources.length > 0 && (
            <section>
              <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
                Essential Reading
                <span className="ml-2 font-mono opacity-60">{essentialSources.length}</span>
              </h2>
              <div className="space-y-0 divide-y divide-[var(--border)]">
                {essentialSources.map((entry, idx) => (
                  <BibEntry key={idx} entry={entry} />
                ))}
              </div>
            </section>
          )}

          {/* Additional Sources */}
          {additionalSources.length > 0 && (
            <section>
              <div className="flex items-baseline justify-between mb-4">
                <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)]">
                  Additional Sources
                  <span className="ml-2 font-mono opacity-60">{additionalSources.length}</span>
                </h2>
                {additionalSources.length > 5 && (
                  <button
                    onClick={() => setShowAll(!showAll)}
                    className="text-xs text-[var(--muted)] hover:text-[var(--foreground)] transition-colors"
                  >
                    {showAll ? "Show fewer" : `Show all ${additionalSources.length}`}
                  </button>
                )}
              </div>
              <div className="space-y-0 divide-y divide-[var(--border)]">
                {(showAll ? additionalSources : additionalSources.slice(0, 5)).map((entry, idx) => (
                  <BibEntry key={idx} entry={entry} />
                ))}
              </div>
              {!showAll && additionalSources.length > 5 && (
                <button
                  onClick={() => setShowAll(true)}
                  className="mt-3 text-sm text-[var(--muted)] hover:text-[var(--foreground)] transition-colors flex items-center gap-1.5"
                >
                  <span>+{additionalSources.length - 5} more sources</span>
                  <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M19 9l-7 7-7-7" />
                  </svg>
                </button>
              )}
            </section>
          )}

          {/* Shared Knowledge Network */}
          <SharedKnowledgeNetwork />

          {/* Cultural Impact (stub) */}
          <section>
            <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
              Cultural Impact
            </h2>
            <div className="border-2 border-dashed border-[var(--border)] rounded-lg p-8 flex flex-col items-center justify-center text-center">
              <p className="text-sm text-[var(--muted)]">
                Cultural impact analysis &mdash; coming soon
              </p>
            </div>
          </section>
        </article>
      </div>
    </>
  );
}

// ── BibEntry Component ──────────────────────────────────────────────────────

function BibEntry({ entry }: { entry: BibliographyEntry }) {
  const typeInfo = TYPE_LABELS[entry.type] || { label: entry.type, color: "bg-gray-500/15 text-gray-600" };
  const scholarQuery = `"${entry.title}" ${entry.author.split(",")[0]}`;
  const scholarUrl = `https://scholar.google.com/scholar?q=${encodeURIComponent(scholarQuery)}`;

  return (
    <div className="py-3.5 group">
      <div className="flex items-start gap-3">
        <div className="flex-1 min-w-0">
          <p className="text-sm leading-relaxed">
            <span className="font-medium text-[var(--foreground)]">{entry.author}</span>
            <span className="text-[var(--muted)] font-mono text-xs ml-1.5">({entry.year})</span>
          </p>
          <p className="text-sm text-[var(--foreground)]/80 italic mt-0.5 leading-relaxed">
            {entry.title}
          </p>
          {entry.venue && (
            <p className="text-xs text-[var(--muted)] mt-0.5 leading-relaxed">
              {entry.venue}
            </p>
          )}
        </div>
        <div className="flex items-center gap-1.5 shrink-0 mt-1">
          <span className={`px-1.5 py-0.5 rounded text-xs font-medium ${typeInfo.color}`}>
            {typeInfo.label}
          </span>
          {entry.url && (
            <a
              href={entry.url}
              target="_blank"
              rel="noopener noreferrer"
              className="px-2.5 py-1 rounded-md border border-[var(--accent)]/30 bg-[var(--accent)]/5 text-xs font-medium text-[var(--accent)] hover:bg-[var(--accent)]/15 transition-colors inline-flex items-center gap-1"
              title="View at publisher"
            >
              View
              <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M10 6H6a2 2 0 00-2 2v10a2 2 0 002 2h10a2 2 0 002-2v-4M14 4h6m0 0v6m0-6L10 14" />
              </svg>
            </a>
          )}
          <a
            href={scholarUrl}
            target="_blank"
            rel="noopener noreferrer"
            className="px-2.5 py-1 rounded-md border border-[var(--border)] text-xs font-medium text-[var(--muted)] hover:text-[var(--foreground)] hover:bg-[var(--card)] transition-colors inline-flex items-center gap-1"
            title="Search on Google Scholar"
          >
            Scholar
            <svg className="w-3 h-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M21 21l-6-6m2-5a7 7 0 11-14 0 7 7 0 0114 0z" />
            </svg>
          </a>
        </div>
      </div>
    </div>
  );
}

// ── Shared Knowledge Network ────────────────────────────────────────────────

interface NetworkNode extends SimulationNodeDatum {
  bookId: string;
  label: string;
  radius: number;
  isCurrent: boolean;
  categoryBreakdown: Record<string, number>;
  totalShared: number;
}

interface NetworkLink extends SimulationLinkDatum<NetworkNode> {
  sharedClusters: number;
  totalSharedMentions: number;
  normalized: number;
  categoryBreakdown: Record<string, number>;
  topShared: { name: string; slug: string; mentions: number }[];
}

function MiniCategoryRing({
  breakdown,
  total,
  cx,
  cy,
  r,
  strokeW,
}: {
  breakdown: Record<string, number>;
  total: number;
  cx: number;
  cy: number;
  r: number;
  strokeW: number;
}) {
  const circumference = 2 * Math.PI * r;
  let offset = 0;
  return (
    <>
      {CATEGORY_ORDER.map((cat) => {
        const count = breakdown[cat] || 0;
        if (count === 0) return null;
        const pct = count / total;
        const dash = pct * circumference;
        const gap = circumference - dash;
        const currentOffset = offset;
        offset += dash;
        return (
          <circle
            key={cat}
            cx={cx}
            cy={cy}
            r={r}
            fill="none"
            stroke={CATEGORY_COLORS_HEX[cat] || "#888"}
            strokeWidth={strokeW}
            strokeDasharray={`${dash} ${gap}`}
            strokeDashoffset={-currentOffset}
            strokeLinecap="butt"
            transform={`rotate(-90 ${cx} ${cy})`}
            style={{ pointerEvents: "none" }}
          />
        );
      })}
    </>
  );
}

function SharedKnowledgeNetwork() {
  const { bookData, concordanceData } = useBookContext();
  const router = useRouter();
  const containerRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const simRef = useRef<ReturnType<typeof forceSimulation<NetworkNode>> | null>(null);
  const [, setTick] = useState(0);
  const [hoveredNode, setHoveredNode] = useState<NetworkNode | null>(null);
  const [phase, setPhase] = useState<"hub" | "nodes" | "edges" | "ready">("hub");
  const [dimensions, setDimensions] = useState({ width: 660, height: 420 });
  const prefersReducedMotion = useRef(false);

  useEffect(() => {
    prefersReducedMotion.current = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  }, []);

  const currentBookId = bookData.book.id;

  // Compute edges from concordance data
  const edges = useMemo(() => {
    const edgeMap = new Map<
      string,
      {
        sharedClusters: number;
        totalSharedMentions: number;
        categoryBreakdown: Record<string, number>;
        topShared: { name: string; slug: string; mentions: number }[];
      }
    >();

    for (const cluster of concordanceData.clusters) {
      const bookIds = new Set(cluster.members.map((m) => m.book_id));
      if (!bookIds.has(currentBookId)) continue;

      for (const otherId of bookIds) {
        if (otherId === currentBookId) continue;
        if (!edgeMap.has(otherId)) {
          edgeMap.set(otherId, {
            sharedClusters: 0,
            totalSharedMentions: 0,
            categoryBreakdown: {},
            topShared: [],
          });
        }
        const edge = edgeMap.get(otherId)!;
        edge.sharedClusters++;
        edge.totalSharedMentions += cluster.total_mentions;
        edge.categoryBreakdown[cluster.category] =
          (edge.categoryBreakdown[cluster.category] || 0) + 1;
        edge.topShared.push({
          name: cluster.canonical_name,
          slug: cluster.stable_key || cluster.canonical_name.toLowerCase().replace(/[^a-z0-9]+/g, "-"),
          mentions: cluster.total_mentions,
        });
      }
    }

    // Sort topShared and keep top 5
    for (const edge of edgeMap.values()) {
      edge.topShared.sort((a, b) => b.mentions - a.mentions);
      edge.topShared = edge.topShared.slice(0, 5);
    }

    return edgeMap;
  }, [concordanceData.clusters, currentBookId]);

  // Build nodes and links for d3-force
  const { nodes, links } = useMemo(() => {
    const maxShared = Math.max(1, ...Array.from(edges.values()).map((e) => e.sharedClusters));
    const radiusScale = scaleSqrt().domain([0, maxShared]).range([18, 36]);
    const { width: w, height: h } = dimensions;

    // Current book's category breakdown from bookData.stats
    const hubCategoryBreakdown = bookData.stats.by_category;
    const hubTotal = Object.values(hubCategoryBreakdown).reduce((s, v) => s + v, 0);

    const hubNode: NetworkNode = {
      bookId: currentBookId,
      label: BOOK_SHORT_NAMES[currentBookId] || bookData.book.title,
      radius: 42,
      isCurrent: true,
      categoryBreakdown: hubCategoryBreakdown,
      totalShared: hubTotal,
      fx: w / 2,
      fy: h / 2,
    };

    const satelliteNodes: NetworkNode[] = [];
    const networkLinks: NetworkLink[] = [];

    let idx = 0;
    for (const [otherId, edge] of edges) {
      const catTotal = Object.values(edge.categoryBreakdown).reduce((s, v) => s + v, 0);
      const normalized = edge.sharedClusters / maxShared;
      const angle = (idx / edges.size) * 2 * Math.PI - Math.PI / 2;
      const initR = 120 + (1 - normalized) * 60;

      const node: NetworkNode = {
        bookId: otherId,
        label: BOOK_SHORT_NAMES[otherId] || otherId,
        radius: radiusScale(edge.sharedClusters),
        isCurrent: false,
        categoryBreakdown: edge.categoryBreakdown,
        totalShared: catTotal,
        x: w / 2 + Math.cos(angle) * initR,
        y: h / 2 + Math.sin(angle) * initR,
      };
      satelliteNodes.push(node);

      networkLinks.push({
        source: hubNode,
        target: node,
        sharedClusters: edge.sharedClusters,
        totalSharedMentions: edge.totalSharedMentions,
        normalized,
        categoryBreakdown: edge.categoryBreakdown,
        topShared: edge.topShared,
      });
      idx++;
    }

    return { nodes: [hubNode, ...satelliteNodes], links: networkLinks };
  }, [edges, currentBookId, bookData, dimensions]);

  // Force simulation
  useEffect(() => {
    if (nodes.length < 2) return;
    const { width: w, height: h } = dimensions;

    const sim = forceSimulation<NetworkNode>(nodes)
      .force(
        "link",
        forceLink<NetworkNode, NetworkLink>(links)
          .id((d) => d.bookId)
          .distance((d) => 80 + (1 - d.normalized) * 120)
          .strength((d) => 0.3 + d.normalized * 0.4)
      )
      .force("charge", forceManyBody().strength(-300).distanceMax(300))
      .force("center", forceCenter(w / 2, h / 2).strength(0.08))
      .force(
        "collide",
        forceCollide<NetworkNode>()
          .radius((d) => d.radius + 8)
          .strength(0.8)
      )
      .alpha(0.8)
      .alphaDecay(0.02)
      .velocityDecay(0.4);

    sim.on("tick", () => {
      for (const n of nodes) {
        const r = n.radius;
        if (n.fx == null) n.x = Math.max(r + 10, Math.min(w - r - 10, n.x!));
        if (n.fy == null) n.y = Math.max(r + 20, Math.min(h - r - 20, n.y!));
      }
      setTick((t) => t + 1);
    });

    simRef.current = sim;
    return () => {
      sim.stop();
    };
  }, [nodes, links, dimensions]);

  // ResizeObserver
  useEffect(() => {
    const container = containerRef.current;
    if (!container) return;
    const ro = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const w = entry.contentRect.width;
      if (w > 0) {
        const h = Math.min(420, Math.max(300, w * 0.636));
        setDimensions({ width: w, height: h });
      }
    });
    ro.observe(container);
    return () => ro.disconnect();
  }, []);

  // Entrance animation
  useEffect(() => {
    if (prefersReducedMotion.current) {
      setPhase("ready");
      return;
    }
    setPhase("hub");
    const t1 = setTimeout(() => setPhase("nodes"), 400);
    const t2 = setTimeout(() => setPhase("edges"), 600);
    const t3 = setTimeout(() => setPhase("ready"), 1100);
    return () => {
      clearTimeout(t1);
      clearTimeout(t2);
      clearTimeout(t3);
    };
  }, []);

  const { width, height } = dimensions;

  // Tooltip content
  const tooltipContent = useMemo(() => {
    if (!hoveredNode) return null;
    if (hoveredNode.isCurrent) {
      const totalClusters = concordanceData.clusters.filter((c) =>
        c.members.some((m) => m.book_id === currentBookId)
      ).length;
      return {
        title: bookData.book.title,
        subtitle: `${bookData.book.author}, ${bookData.book.year}`,
        detail: `${totalClusters} concordance clusters`,
        items: [],
      };
    }
    const edge = links.find(
      (l) => (l.target as NetworkNode).bookId === hoveredNode.bookId
    );
    if (!edge) return null;
    return {
      title: hoveredNode.label,
      subtitle: `${edge.sharedClusters} shared clusters`,
      detail: `${edge.totalSharedMentions.toLocaleString()} total mentions`,
      items: edge.topShared.slice(0, 3),
    };
  }, [hoveredNode, links, concordanceData.clusters, currentBookId, bookData]);

  if (nodes.length < 2) return null;

  return (
    <section>
      <h2 className="text-sm font-medium uppercase tracking-wider text-[var(--muted)] mb-4">
        Shared Knowledge Network
      </h2>
      <div ref={containerRef} className="relative w-full">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full h-auto"
          role="img"
          aria-label={`Network graph showing how ${bookData.book.title} shares concordance entities with other books in the corpus`}
        >
          <defs>
            <radialGradient id="skn-bg-grad" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="var(--accent)" stopOpacity={0.03} />
              <stop offset="100%" stopColor="var(--card)" stopOpacity={0} />
            </radialGradient>
            <pattern
              id="skn-grid"
              x="0"
              y="0"
              width="30"
              height="30"
              patternUnits="userSpaceOnUse"
            >
              <circle cx="15" cy="15" r="0.5" fill="var(--muted)" opacity="0.12" />
            </pattern>
          </defs>

          {/* Background */}
          <rect width={width} height={height} fill="url(#skn-bg-grad)" rx={8} />
          <rect width={width} height={height} fill="url(#skn-grid)" rx={8} />

          {/* Edges */}
          {links.map((link, i) => {
            const source = link.source as NetworkNode;
            const target = link.target as NetworkNode;
            if (source.x == null || target.x == null) return null;
            const sx = source.x!,
              sy = source.y!,
              tx = target.x!,
              ty = target.y!;
            const mx = (sx + tx) / 2,
              my = (sy + ty) / 2;
            const dx = tx - sx,
              dy = ty - sy;
            const len = Math.sqrt(dx * dx + dy * dy) || 1;
            const perpX = -dy / len,
              perpY = dx / len;
            const curveOff = 15 + link.normalized * 10;
            const cx = mx + perpX * curveOff,
              cy_ = my + perpY * curveOff;

            const isHighlighted =
              hoveredNode &&
              ((source as NetworkNode).bookId === hoveredNode.bookId ||
                (target as NetworkNode).bookId === hoveredNode.bookId);
            const isDimmed = hoveredNode && !isHighlighted;

            const pathD = `M ${sx} ${sy} Q ${cx} ${cy_} ${tx} ${ty}`;
            const pathLen = len * 1.1;
            const strokeW = 1 + link.normalized * 4;

            const showEdge = phase === "edges" || phase === "ready";

            return (
              <path
                key={i}
                d={pathD}
                fill="none"
                stroke={isHighlighted ? "var(--accent)" : "var(--muted)"}
                strokeWidth={isHighlighted ? strokeW + 1 : strokeW}
                strokeOpacity={
                  isDimmed ? 0.04 : isHighlighted ? 0.4 : 0.08 + link.normalized * 0.15
                }
                strokeDasharray={showEdge ? "none" : `${pathLen}`}
                strokeDashoffset={showEdge ? 0 : pathLen}
                style={{
                  transition: prefersReducedMotion.current
                    ? "none"
                    : "stroke-dashoffset 0.5s ease-out, stroke-opacity 0.2s, stroke-width 0.2s",
                }}
                onMouseEnter={() => {
                  const targetNode = nodes.find(
                    (n) => n.bookId === (target as NetworkNode).bookId && !n.isCurrent
                  );
                  if (targetNode) setHoveredNode(targetNode);
                }}
                onMouseLeave={() => setHoveredNode(null)}
              />
            );
          })}

          {/* Hub orbit ring */}
          {nodes[0] && nodes[0].x != null && (
            <circle
              cx={nodes[0].x}
              cy={nodes[0].y}
              r={nodes[0].radius + 6}
              fill="none"
              stroke="var(--accent)"
              strokeWidth={1}
              strokeOpacity={phase === "hub" || phase === "ready" ? 0.25 : 0}
              strokeDasharray="4 4"
              style={{
                transition: prefersReducedMotion.current ? "none" : "stroke-opacity 0.4s",
              }}
            />
          )}

          {/* Nodes */}
          {nodes
            .slice()
            .sort((a, b) => {
              if (a.isCurrent) return 1;
              if (b.isCurrent) return -1;
              if (hoveredNode?.bookId === a.bookId) return 1;
              if (hoveredNode?.bookId === b.bookId) return -1;
              return 0;
            })
            .map((node) => {
              if (node.x == null || node.y == null) return null;
              const isHovered = hoveredNode?.bookId === node.bookId;
              const isDimmed = hoveredNode && !isHovered && !node.isCurrent;
              const r = node.radius;

              const showHub = true;
              const showSatellite =
                node.isCurrent || phase === "nodes" || phase === "edges" || phase === "ready";

              if (!node.isCurrent && !showSatellite) return null;

              const nodeOpacity = node.isCurrent
                ? phase === "hub" || phase === "nodes" || phase === "edges" || phase === "ready"
                  ? 1
                  : 0
                : showSatellite
                  ? isDimmed
                    ? 0.4
                    : 1
                  : 0;

              const ringR = node.isCurrent ? r - 3 : r - 2;
              const ringStroke = node.isCurrent ? 3 : 2.5;

              return (
                <g
                  key={node.bookId}
                  style={{
                    cursor: node.isCurrent ? "default" : "pointer",
                    opacity: nodeOpacity,
                    transition: prefersReducedMotion.current ? "none" : "opacity 0.3s",
                  }}
                  onMouseEnter={() => setHoveredNode(node)}
                  onMouseLeave={() => setHoveredNode(null)}
                  onClick={() => {
                    if (!node.isCurrent) router.push(`/books/${node.bookId}`);
                  }}
                  tabIndex={node.isCurrent ? undefined : 0}
                  role={node.isCurrent ? undefined : "link"}
                  aria-label={
                    node.isCurrent
                      ? undefined
                      : `Navigate to ${node.label}`
                  }
                  onKeyDown={(e) => {
                    if (!node.isCurrent && (e.key === "Enter" || e.key === " ")) {
                      e.preventDefault();
                      router.push(`/books/${node.bookId}`);
                    }
                  }}
                >
                  {/* Fill circle */}
                  <circle
                    cx={node.x}
                    cy={node.y}
                    r={r}
                    fill={node.isCurrent ? "var(--accent)" : "var(--card)"}
                    fillOpacity={node.isCurrent ? 0.15 : 0.8}
                    stroke={
                      isHovered
                        ? "var(--accent)"
                        : node.isCurrent
                          ? "var(--accent)"
                          : "var(--border)"
                    }
                    strokeWidth={isHovered ? 2 : node.isCurrent ? 1.5 : 1}
                    strokeOpacity={node.isCurrent ? 0.6 : isHovered ? 0.8 : 0.5}
                    style={{
                      transition: "stroke-width 0.15s, stroke-opacity 0.15s",
                    }}
                  />

                  {/* Category ring */}
                  {node.totalShared > 0 && (
                    <MiniCategoryRing
                      breakdown={node.categoryBreakdown}
                      total={node.totalShared}
                      cx={node.x!}
                      cy={node.y!}
                      r={ringR}
                      strokeW={ringStroke}
                    />
                  )}

                  {/* Label */}
                  <text
                    x={node.x}
                    y={node.y! + r + 13}
                    textAnchor="middle"
                    className="fill-[var(--foreground)]"
                    fontSize={node.isCurrent ? 12 : 10}
                    fontWeight={node.isCurrent ? 600 : 400}
                    opacity={isDimmed ? 0.3 : 0.85}
                    style={{
                      pointerEvents: "none",
                      transition: "opacity 0.2s",
                    }}
                  >
                    {node.label}
                  </text>
                </g>
              );
            })}
        </svg>

        {/* Tooltip */}
        {hoveredNode && tooltipContent && (() => {
          const nodeYPct = ((hoveredNode.y ?? 0) / height) * 100;
          const nodeXPct = ((hoveredNode.x ?? 0) / width) * 100;
          const onLeft = nodeXPct < 50;
          return (
            <div
              className="absolute z-50 pointer-events-none"
              style={{
                top: `${nodeYPct}%`,
                ...(onLeft
                  ? { left: `${nodeXPct + 8}%`, transform: "translateY(-50%)" }
                  : { right: `${100 - nodeXPct + 8}%`, transform: "translateY(-50%)" }),
              }}
            >
              <div className="bg-[var(--foreground)] text-[var(--background)] rounded-lg px-4 py-3 shadow-xl max-w-[240px]">
                <p className="font-semibold text-sm">{tooltipContent.title}</p>
                <p className="text-xs opacity-70 mt-0.5">{tooltipContent.subtitle}</p>
                <p className="text-xs opacity-70">{tooltipContent.detail}</p>
                {tooltipContent.items.length > 0 && (
                  <div className="mt-2 border-t border-[var(--background)]/20 pt-1.5 space-y-0.5">
                    {tooltipContent.items.map((item, i) => (
                      <p key={i} className="text-xs opacity-80 truncate">
                        {item.name}
                      </p>
                    ))}
                  </div>
                )}
                {!hoveredNode.isCurrent && (
                  <p className="text-xs opacity-50 mt-1.5">Click to visit &rarr;</p>
                )}
              </div>
            </div>
          );
        })()}

        {/* SR-only table */}
        <table className="sr-only">
          <caption>
            Shared knowledge connections for {bookData.book.title}
          </caption>
          <thead>
            <tr>
              <th>Book</th>
              <th>Shared clusters</th>
              <th>Total mentions</th>
            </tr>
          </thead>
          <tbody>
            {links.map((link, i) => {
              const target = link.target as NetworkNode;
              return (
                <tr key={i}>
                  <td>{target.label}</td>
                  <td>{link.sharedClusters}</td>
                  <td>{link.totalSharedMentions}</td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
    </section>
  );
}
