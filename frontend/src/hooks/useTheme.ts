import { useEffect, useState } from 'react'
import { applyTheme, getSavedTheme, saveTheme, type Theme } from '../theme'

export function useTheme() {
  const [theme, setTheme] = useState<Theme>(getSavedTheme)

  useEffect(() => {
    applyTheme(theme)
    saveTheme(theme)
  }, [theme])

  return {
    theme,
    setTheme,
    toggleTheme: () => setTheme(current => (current === 'dark' ? 'light' : 'dark')),
  }
}
