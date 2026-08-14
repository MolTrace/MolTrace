import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { SpeedInsights } from '@vercel/speed-insights/next'
import { SITE_URL, SITE_NAME, SITE_TAGLINE, SITE_DESCRIPTION } from '@/lib/seo/site'
import { SHELL_MODE_INLINE_SCRIPT } from '@/src/lib/shell/shell-mode'
import { OrganizationJsonLd } from '@/components/seo/json-ld'
import { ThemeProvider } from '@/components/theme-provider'
import { DeveloperModeProvider } from '@/components/developer-mode-provider'
import { IncludedModulesProvider } from '@/src/lib/modules/included-modules-provider'
import { Toaster } from '@/components/ui/toaster'
import { OfflineBanner } from '@/src/components/pwa/OfflineBanner'
import { InstallAppPrompt } from '@/src/components/pwa/InstallAppPrompt'
import { PWAUpdateManager } from '@/src/components/pwa/PWAUpdateManager'
import { DevToolsBridge } from '@/components/dev/devtools-bridge'
import './globals.css'

const PWA_ASSET_VERSION = '2026-08-09-neon-prism-raised-m-v1'
const versionedIcon = (src: string) => `${src}?v=${PWA_ASSET_VERSION}`

export const metadata: Metadata = {
  metadataBase: new URL(SITE_URL),
  title: {
    default: `${SITE_NAME} | ${SITE_TAGLINE}`,
    // Per-route `title` strings render as "About · MolTrace" etc.; this template
    // only applies to child pages that set a plain string title without their
    // own suffix. Pages here already suffix themselves, so keep it minimal.
    template: `%s | ${SITE_NAME}`,
  },
  description: SITE_DESCRIPTION,
  applicationName: SITE_NAME,
  generator: 'v0.app',
  keywords: [
    'spectroscopy interpretation',
    'NMR structure elucidation',
    'reaction optimization',
    'Bayesian optimization chemistry',
    'regulatory intelligence',
    'pharmaceutical R&D software',
    'audit-ready AI',
    '21 CFR Part 11',
    'GxP',
    'cheminformatics',
  ],
  authors: [{ name: SITE_NAME, url: SITE_URL }],
  creator: SITE_NAME,
  publisher: SITE_NAME,
  // Explicit, permissive robots directive so crawlers get rich SERP features.
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      'max-image-preview': 'large',
      'max-snippet': -1,
      'max-video-preview': -1,
    },
  },
  // Google Search Console meta-tag verification. Set NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION
  // to the token from Search Console → this emits <meta name="google-site-verification">.
  verification: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION
    ? { google: process.env.NEXT_PUBLIC_GOOGLE_SITE_VERIFICATION }
    : undefined,
  alternates: { canonical: '/' },
  openGraph: {
    type: 'website',
    siteName: SITE_NAME,
    locale: 'en_US',
    url: SITE_URL,
    title: `${SITE_NAME} | ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
  },
  twitter: {
    card: 'summary_large_image',
    title: `${SITE_NAME} | ${SITE_TAGLINE}`,
    description: SITE_DESCRIPTION,
  },
  icons: {
    icon: [
      {
        url: versionedIcon('/icons/moltrace-mark.svg'),
        sizes: 'any',
        type: 'image/svg+xml',
      },
      {
        url: versionedIcon('/icons/icon-192.png'),
        sizes: '192x192',
        type: 'image/png',
      },
      {
        url: versionedIcon('/icons/icon-512.png'),
        sizes: '512x512',
        type: 'image/png',
      },
    ],
    apple: [{ url: versionedIcon('/apple-icon.png'), sizes: '192x192', type: 'image/png' }],
    shortcut: versionedIcon('/icons/moltrace-mark.svg'),
  },
}

export const viewport: Viewport = {
  width: 'device-width',
  initialScale: 1,
}

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode
}>) {
  return (
    <html lang="en" suppressHydrationWarning className="bg-background">
      <head>
        {/* Blocking, and deliberately so: it decides desktop vs mobile shell and
            stamps it on <html> BEFORE anything paints. React cannot make this
            call until hydration and starts by assuming desktop, so on a phone
            the full sidebar painted and was then torn away. Same technique the
            ecosystem uses for theme flashes, and the same reason. */}
        <script dangerouslySetInnerHTML={{ __html: SHELL_MODE_INLINE_SCRIPT }} />
        <DevToolsBridge />
      </head>
      <body suppressHydrationWarning className="font-sans antialiased">
        <OrganizationJsonLd />
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <DeveloperModeProvider>
            {/* Which products this deployment serves. Fetched once at shell mount; every nav
                surface asks this rather than guessing from entitlements. Fails OPEN. */}
            <IncludedModulesProvider>
              <PWAUpdateManager />
              <OfflineBanner />
              {children}
              <InstallAppPrompt />
              <Toaster />
            </IncludedModulesProvider>
          </DeveloperModeProvider>
        </ThemeProvider>
        {/* Vercel injects /_vercel/insights/script.js only when hosted on Vercel.
            On other platforms (e.g. Render) the script 404s and logs a noisy error.
            Gate on the platform-supplied VERCEL env var so non-Vercel deploys stay clean. */}
        {process.env.NODE_ENV === 'production' && process.env.VERCEL && <Analytics />}
        {/* Field Core Web Vitals (LCP/INP/CLS per route, real users) — the render-heavy
            surfaces ship with no field signal otherwise. Same platform gate as <Analytics/>;
            chosen over a hand-rolled useReportWebVitals -> /analytics/events reporter so
            anonymous marketing pageviews never cost a backend hop. */}
        {process.env.NODE_ENV === 'production' && process.env.VERCEL && <SpeedInsights />}
      </body>
    </html>
  )
}
