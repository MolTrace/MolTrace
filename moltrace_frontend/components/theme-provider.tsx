'use client'

import * as React from 'react'

type ThemeName = 'light' | 'dark' | 'system'
type ResolvedTheme = 'light' | 'dark'
type ThemeSetter = ThemeName | ((theme: ThemeName) => ThemeName)

type ThemeProviderProps = {
  children: React.ReactNode
  attribute?: 'class' | `data-${string}` | string | string[]
  defaultTheme?: ThemeName
  disableTransitionOnChange?: boolean
  enableColorScheme?: boolean
  enableSystem?: boolean
  forcedTheme?: ThemeName
  storageKey?: string
  themes?: ThemeName[]
  value?: Partial<Record<ThemeName, string>>
}

type ThemeContextValue = {
  forcedTheme?: ThemeName
  resolvedTheme: ResolvedTheme
  setTheme: (theme: ThemeSetter) => void
  systemTheme?: ResolvedTheme
  theme: ThemeName
  themes: ThemeName[]
}

const THEME_MEDIA = '(prefers-color-scheme: dark)'
const DEFAULT_THEMES: ThemeName[] = ['light', 'dark']
const ThemeContext = React.createContext<ThemeContextValue | null>(null)

function getSystemTheme(): ResolvedTheme {
  if (typeof window === 'undefined') return 'light'
  return window.matchMedia(THEME_MEDIA).matches ? 'dark' : 'light'
}

function resolveTheme(theme: ThemeName, enableSystem: boolean, systemTheme: ResolvedTheme): ResolvedTheme {
  if (theme === 'system') return enableSystem ? systemTheme : 'light'
  return theme
}

function disableTransitions(nonce?: string): () => void {
  const css = document.createElement('style')
  if (nonce) css.setAttribute('nonce', nonce)
  css.appendChild(
    document.createTextNode('*,*::before,*::after{transition:none!important}'),
  )
  document.head.appendChild(css)
  return () => {
    window.getComputedStyle(document.body)
    setTimeout(() => {
      css.remove()
    }, 1)
  }
}

function applyTheme({
  attribute,
  disableTransitionOnChange,
  enableColorScheme,
  resolvedTheme,
  themes,
  value,
}: {
  attribute: ThemeProviderProps['attribute']
  disableTransitionOnChange: boolean
  enableColorScheme: boolean
  resolvedTheme: ResolvedTheme
  themes: ThemeName[]
  value: ThemeProviderProps['value']
}) {
  const root = document.documentElement
  const attrs = Array.isArray(attribute) ? attribute : [attribute ?? 'class']
  const mappedTheme = value?.[resolvedTheme] ?? resolvedTheme
  const mappedThemes = themes.map((theme) => value?.[theme] ?? theme)
  const restoreTransitions = disableTransitionOnChange ? disableTransitions() : null

  for (const attr of attrs) {
    if (attr === 'class') {
      root.classList.remove(...mappedThemes)
      root.classList.add(mappedTheme)
    } else if (attr.startsWith('data-')) {
      root.setAttribute(attr, mappedTheme)
    }
  }

  if (enableColorScheme) {
    root.style.colorScheme = resolvedTheme
  }

  restoreTransitions?.()
}

export function ThemeProvider({
  attribute = 'class',
  children,
  defaultTheme = 'system',
  disableTransitionOnChange = false,
  enableColorScheme = true,
  enableSystem = true,
  forcedTheme,
  storageKey = 'theme',
  themes = DEFAULT_THEMES,
  value,
}: ThemeProviderProps) {
  const [theme, setThemeState] = React.useState<ThemeName>(defaultTheme)
  const [systemTheme, setSystemTheme] = React.useState<ResolvedTheme>('light')

  React.useEffect(() => {
    setSystemTheme(getSystemTheme())
    if (forcedTheme) {
      setThemeState(forcedTheme)
      return
    }
    try {
      const stored = window.localStorage.getItem(storageKey) as ThemeName | null
      if (stored === 'light' || stored === 'dark' || stored === 'system') {
        setThemeState(stored)
        return
      }
    } catch {
      /* localStorage can be unavailable in restricted browser contexts. */
    }
    setThemeState(defaultTheme)
  }, [defaultTheme, forcedTheme, storageKey])

  React.useEffect(() => {
    if (!enableSystem) return
    const media = window.matchMedia(THEME_MEDIA)
    const handleChange = () => setSystemTheme(getSystemTheme())
    media.addEventListener('change', handleChange)
    return () => media.removeEventListener('change', handleChange)
  }, [enableSystem])

  React.useEffect(() => {
    const handleStorage = (event: StorageEvent) => {
      if (event.key !== storageKey) return
      if (event.newValue === 'light' || event.newValue === 'dark' || event.newValue === 'system') {
        setThemeState(event.newValue)
      } else if (event.newValue == null) {
        setThemeState(defaultTheme)
      }
    }
    window.addEventListener('storage', handleStorage)
    return () => window.removeEventListener('storage', handleStorage)
  }, [defaultTheme, storageKey])

  const activeTheme = forcedTheme ?? theme
  const resolvedTheme = resolveTheme(activeTheme, enableSystem, systemTheme)

  React.useEffect(() => {
    applyTheme({
      attribute,
      disableTransitionOnChange,
      enableColorScheme,
      resolvedTheme,
      themes,
      value,
    })
  }, [attribute, disableTransitionOnChange, enableColorScheme, resolvedTheme, themes, value])

  const setTheme = React.useCallback(
    (nextTheme: ThemeSetter) => {
      setThemeState((currentTheme) => {
        const next = typeof nextTheme === 'function' ? nextTheme(currentTheme) : nextTheme
        try {
          window.localStorage.setItem(storageKey, next)
        } catch {
          /* localStorage can be unavailable in restricted browser contexts. */
        }
        return next
      })
    },
    [storageKey],
  )

  const contextValue = React.useMemo<ThemeContextValue>(
    () => ({
      forcedTheme,
      resolvedTheme,
      setTheme,
      systemTheme: enableSystem ? systemTheme : undefined,
      theme,
      themes: enableSystem ? [...themes, 'system'] : themes,
    }),
    [enableSystem, forcedTheme, resolvedTheme, setTheme, systemTheme, theme, themes],
  )

  return <ThemeContext.Provider value={contextValue}>{children}</ThemeContext.Provider>
}

export function useTheme(): ThemeContextValue {
  return (
    React.useContext(ThemeContext) ?? {
      resolvedTheme: 'light',
      setTheme: () => {},
      systemTheme: 'light',
      theme: 'light',
      themes: DEFAULT_THEMES,
    }
  )
}
