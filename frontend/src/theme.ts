export type Theme = 'dark' | 'light'

const THEME_KEY = 'makhal_reader_theme'

export function getSavedTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

/** Page background per theme, mirrored into <meta name="theme-color"> for Safari's chrome. */
const THEME_COLORS: Record<Theme, string> = { dark: '#101211', light: '#F6F8FB' }

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
  document.querySelector('meta[name="theme-color"]')?.setAttribute('content', THEME_COLORS[theme])
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {}
}

export function initializeTheme() {
  applyTheme(getSavedTheme())
}
