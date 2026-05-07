import type { Metadata, Viewport } from 'next'
import { Analytics } from '@vercel/analytics/next'
import { ThemeProvider } from '@/components/theme-provider'
import { OfflineBanner } from '@/src/components/pwa/OfflineBanner'
import { InstallAppPrompt } from '@/src/components/pwa/InstallAppPrompt'
import { PWAUpdateManager } from '@/src/components/pwa/PWAUpdateManager'
import './globals.css'

export const metadata: Metadata = {
  title: 'MolTrace | AI-Native Scientific Intelligence Platform',
  description: 'AI-powered spectroscopy interpretation, reaction optimization, and regulatory intelligence for chemistry and R&D teams.',
  generator: 'v0.app',
  icons: {
    icon: [
      {
        url: '/icons/moltrace-mark.svg',
        sizes: 'any',
        type: 'image/svg+xml',
      },
      {
        url: '/icons/icon-192.png',
        sizes: '192x192',
        type: 'image/png',
      },
      {
        url: '/icons/icon-512.png',
        sizes: '512x512',
        type: 'image/png',
      },
    ],
    apple: [{ url: '/icons/icon-192.png', sizes: '192x192', type: 'image/png' }],
    shortcut: '/icons/moltrace-mark.svg',
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
