"use client";

import { useRef, useState } from "react";
import styles from "./interactive-title.module.css";

const titles = [
  ["Premodern", "Concordance"],
  ["Concordancia", "Premoderna"],
  ["Concordância", "Pré-moderna"],
  ["Concordance", "Prémoderne"],
  ["Concordanza", "Premoderna"],
  ["Vormoderne", "Konkordanz"],
  ["Concordantia", "Praemoderna"]
] as const;

const fontClasses = [styles.sans, styles.blackletter, styles.serif, styles.grotesk];

export function InteractiveTitle() {
  const [translationIndex, setTranslationIndex] = useState(0);
  const [fontIndex, setFontIndex] = useState(0);
  const previous = useRef(0);

  function showTranslation() {
    let next = previous.current;
    while (next === previous.current) next = 1 + Math.floor(Math.random() * (titles.length - 1));
    previous.current = next;
    setTranslationIndex(next);
  }

  function showEnglish() {
    setTranslationIndex(0);
  }

  return (
    <button
      type="button"
      className={`${styles.title} ${fontClasses[fontIndex]}`}
      onPointerEnter={showTranslation}
      onPointerLeave={showEnglish}
      onFocus={showTranslation}
      onBlur={showEnglish}
      onClick={() => setFontIndex((fontIndex + 1) % fontClasses.length)}
      aria-label="Premodern Concordance. Hover to translate; activate to change typeface."
    >
      <span>{titles[translationIndex][0]}</span>
      <span>{titles[translationIndex][1]}</span>
    </button>
  );
}
