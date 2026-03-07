import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Analytics } from "@vercel/analytics/next"
const geistSans = Geist({
  variable: "--font-geist-sans",
  subsets: ["latin"],
});

const geistMono = Geist_Mono({
  variable: "--font-geist-mono",
  subsets: ["latin"],
});

export const metadata: Metadata = {
  metadataBase: new URL("https://ranqora.vercel.app"),
  title: "Ranqora | AI Dataset Discovery Platform",
  description: "The intelligent search engine for medical, foundational, and computer vision datasets. Find, rank, and evaluate high-quality open ML datasets from HuggingFace, Kaggle, and ArXiv, powered by semantic search.",
  keywords: ["Ranqora", "AI datasets", "machine learning datasets", "dataset search engine", "huggingface", "kaggle datasets", "open data", "semantic search"],
  authors: [{ name: "Ranqora AI" }],
  icons: {
    icon: "/favicon.svg",
  },
  openGraph: {
    title: "Ranqora | Premium Dataset Intelligence",
    description: "Accelerate your AI pipelines. Rank and discover open source datasets securely with multi-source retrieval.",
    url: "https://ranqora.vercel.app",
    siteName: "Ranqora Platform",
    locale: "en_US",
    type: "website",
  },
  twitter: {
    card: "summary_large_image",
    title: "Ranqora | AI Dataset Discovery",
    description: "Multi-source intelligent semantic search over ML datasets.",
  },
  robots: {
    index: true,
    follow: true,
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en" suppressHydrationWarning>
      <head>
        <link rel="icon" type="image/svg+xml" href="/favicon.svg" />
      </head>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >      <Analytics />
        <Providers>
          {children}
        </Providers>
        {/* Structured Data for SEO / Frontend Governance */}
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{
            __html: JSON.stringify({
              "@context": "https://schema.org",
              "@type": "WebSite",
              name: "Ranqora AI",
              url: "https://ranqora.vercel.app",
              potentialAction: {
                "@type": "SearchAction",
                target: "https://ranqora.vercel.app/search/results?q={search_term_string}",
                "query-input": "required name=search_term_string"
              }
            }),
          }}
        />
      </body>
    </html>
  );
}
