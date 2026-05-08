import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { ThemeProvider } from '@/components/theme-provider'
import { OfflineBanner } from '@/src/components/pwa/OfflineBanner'
import { InstallAppPrompt } from '@/src/components/pwa/InstallAppPrompt'
import { PWAUpdateManager } from '@/src/components/pwa/PWAUpdateManager'
import './globals.css'

const PWA_ASSET_VERSION = '2026-05-08-v2'
const versionedIcon = (src: string) => `${src}?v=${PWA_ASSET_VERSION}`

export const metadata: Metadata = {
  title: 'MolTrace | AI-Native Scientific Intelligence Platform',
  description: 'AI-powered spectroscopy interpretation, reaction optimization, and regulatory intelligence for chemistry and R&D teams.',
  generator: 'v0.app',
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
      <body suppressHydrationWarning className="font-sans antialiased">
        <ThemeProvider
          attribute="class"
          defaultTheme="light"
          enableSystem
          disableTransitionOnChange
        >
          <PWAUpdateManager />
          <OfflineBanner />
          {children}
          <InstallAppPrompt />
        </ThemeProvider>
        {process.env.NODE_ENV === 'production' && <Analytics />}
      </body>
    </html>
  )
}
