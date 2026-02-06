import { NextRequest, NextResponse } from "next/server";
import { GoogleGenerativeAI } from "@google/generative-ai";

export async function POST(request: NextRequest) {
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return NextResponse.json(
      { error: "GEMINI_API_KEY not configured" },
      { status: 500 }
    );
  }

  let body: { text: string; language: string };
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const { text, language } = body;
  if (!text || !language) {
    return NextResponse.json(
      { error: "Missing text or language" },
      { status: 400 }
    );
  }

  const prompt = [
    `Translate the following excerpt from an early modern ${language} text (1500-1800) into clear modern English.`,
    `This is from a historical medical or natural-philosophical source. Preserve the meaning faithfully,`,
    `but render archaic vocabulary and spelling into understandable modern English.`,
    `Return ONLY the translated text, no commentary or notes.`,
    ``,
    `Text:`,
    text,
  ].join("\n");

  try {
    const genAI = new GoogleGenerativeAI(apiKey);
    const model = genAI.getGenerativeModel({ model: "gemini-2.5-flash-lite" });
    const result = await model.generateContent(prompt);
    const translation = result.response.text().trim();

    return NextResponse.json({ translation });
  } catch (e) {
    const message = e instanceof Error ? e.message : "Translation failed";
    return NextResponse.json({ error: message }, { status: 500 });
  }
}
