'use client'

import * as React from 'react'
import { Toaster as Sonner, ToasterProps } from 'sonner'
import { useTheme } from '@/components/theme-provider'

const Toaster = ({ ...props }: ToasterProps) => {
  const { resolvedTheme, theme } = useTheme()
  const [mounted, setMounted] = React.useState(false)

  React.useEffect(() => {
    setMounted(true)
  }, [])

  const toasterTheme = (
    mounted ? (resolvedTheme ?? theme ?? 'light') : 'light'
  ) as ToasterProps['theme']

  return (
    <Sonner
      theme={toasterTheme}
      className="toaster group"
      style={
        {
          '--normal-bg': 'var(--popover)',
          '--normal-text': 'var(--popover-foreground)',
          '--normal-border': 'var(--border)',
        } as React.CSSProperties
      }
      {...props}
    />
  )
}

export { Toaster }
