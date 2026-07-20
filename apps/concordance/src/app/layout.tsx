import type { Metadata } from "next";
import { EB_Garamond, Space_Grotesk, UnifrakturMaguntia } from "next/font/google";
import { SiteFooter } from "@/components/brand/site-footer";
import { SiteHeader } from "@/components/brand/site-header";
import "./globals.css";

const space = Space_Grotesk({ subsets: ["latin"], variable: "--font-space", display: "swap" });
const garamond = EB_Garamond({ subsets: ["latin"], variable: "--font-garamond", display: "swap" });
const blackletter = UnifrakturMaguntia({ weight: "400", subsets: ["latin"], variable: "--font-blackletter", display: "swap" });

export const metadata: Metadata = {
  title: { default: "Premodern Concordance", template: "%s — Premodern Concordance" },
  description: "Trace scientific and medical terms through languages, centuries, and primary sources."
};

const themeScript = `(function(){try{var t=localStorage.getItem('theme');if(t==='dark'||(!t&&matchMedia('(prefers-color-scheme:dark)').matches))document.documentElement.classList.add('dark')}catch(e){}})()`;

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" suppressHydrationWarning className={`${space.variable} ${garamond.variable} ${blackletter.variable}`}>
      <head><script dangerouslySetInnerHTML={{ __html: themeScript }} /></head>
      <body>
        <a className="skip-link" href="#main">Skip to content</a>
        <SiteHeader />
        <main id="main">{children}</main>
        <SiteFooter />
      </body>
    </html>
  );
}
