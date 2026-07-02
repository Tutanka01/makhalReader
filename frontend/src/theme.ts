export type Theme = 'dark' | 'light'

const THEME_KEY = 'makhal_reader_theme'

export function getSavedTheme(): Theme {
  try {
    return localStorage.getItem(THEME_KEY) === 'light' ? 'light' : 'dark'
  } catch {
    return 'dark'
  }
}

export function applyTheme(theme: Theme) {
  document.documentElement.dataset.theme = theme
}

export function saveTheme(theme: Theme) {
  try {
    localStorage.setItem(THEME_KEY, theme)
  } catch {}
}

export function initializeTheme() {
  applyTheme(getSavedTheme())
}
