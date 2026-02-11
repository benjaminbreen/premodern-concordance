"use client";

import { createContext, useContext } from "react";

export interface Mention {
  offset: number;
  matched_term: string;
  excerpt: string;
}

export interface Entity {
  id: string;
  name: string;
  category: string;
  subcategory?: string;
  count: number;
  contexts: string[];
  variants: string[];
  mentions?: Mention[];
}

export interface BookData {
  book: {
    id: string;
    title: string;
    author: string;
    year: number;
    language: string;
    description: string;
  };
  entities: Entity[];
  stats: {
    total_entities: number;
    by_category: Record<string, number>;
    extraction_method: string;
    chunks_processed: number;
  };
}

export interface ConcordanceCluster {
  id: number;
  stable_key?: string;
  canonical_name: string;
  category: string;
  book_count: number;
  total_mentions: number;
  members: {
    entity_id: string;
    book_id: string;
    name: string;
    category: string;
    subcategory: string;
    count: number;
    variants: string[];
    contexts: string[];
  }[];
}

export interface ConcordanceData {
  clusters: ConcordanceCluster[];
}

interface BookContextType {
  bookData: BookData;
  concordanceData: ConcordanceData;
}

const BookContext = createContext<BookContextType | null>(null);

export function BookProvider({
  value,
  children,
}: {
  value: BookContextType;
  children: React.ReactNode;
}) {
  return <BookContext.Provider value={value}>{children}</BookContext.Provider>;
}

export function useBookContext() {
  const ctx = useContext(BookContext);
  if (!ctx) throw new Error("useBookContext must be used within BookProvider");
  return ctx;
}
