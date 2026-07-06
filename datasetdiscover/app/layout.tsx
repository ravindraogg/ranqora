import type { Metadata } from "next";
import { Geist, Geist_Mono } from "next/font/google";
import "./globals.css";
import { Providers } from "./providers";
import { Analytics } from "@vercel/analytics/next"
import Script from "next/script";


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

  verification: {
    google: "Q_-AyHu0q-s4F1njGTOP8tDBy-iVvzwEZqRLoiS1-CI",
  },

  title: "Ranqora | AI Dataset Discovery Platform",

  description:
    "The intelligent search engine for medical, foundational, and computer vision datasets. Find, rank, and evaluate high-quality open ML datasets from HuggingFace, Kaggle, and ArXiv, powered by semantic search.",

  keywords: [
    "Ranqora",
    "AI datasets",
    "machine learning datasets",
    "dataset search engine",
    "huggingface",
    "kaggle datasets",
    "open data",
    "semantic search"
  ],

  authors: [{ name: "Ranqora AI" }],

  icons: {
    icon: "/favicon.svg",
  },

  alternates: {
    canonical: "https://ranqora.vercel.app",
  },

  openGraph: {
    title: "Ranqora | Premium Dataset Intelligence",
    description:
      "Accelerate your AI pipelines. Rank and discover open source datasets securely with multi-source retrieval.",
    url: "https://ranqora.vercel.app",
    siteName: "Ranqora Platform",
    locale: "en_US",
    type: "website",
    images: [
      {
        url: "/favicon.svg",
        width: 1200,
        height: 630,
        alt: "Ranqora AI Dataset Discovery Platform",
      },
    ],
  },

  twitter: {
    card: "summary_large_image",
    title: "Ranqora | AI Dataset Discovery",
    description:
      "Multi-source intelligent semantic search over ML datasets.",
    images: ["/og-image.png"],
  },

  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body
        className={`${geistSans.variable} ${geistMono.variable} antialiased`}
      >
        <Analytics />
        <Script
          async
          src="https://www.googletagmanager.com/gtag/js?id=G-WRP8ZXELDM"
        />
        <Script id="google-analytics">
          {`
            window.dataLayer = window.dataLayer || [];
            function gtag(){dataLayer.push(arguments);}
            gtag('js', new Date());

            gtag('config', 'G-WRP8ZXELDM');
          `}
        </Script>
        <Providers>
          {children}
        </Providers>

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
