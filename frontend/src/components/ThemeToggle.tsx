import { Moon, Sun } from 'lucide-react'
import type { Theme } from '../theme'
import { IconButton } from './ui'

interface ThemeToggleProps {
  theme: Theme
  onToggle: () => void
}

export function ThemeToggle({ theme, onToggle }: ThemeToggleProps) {
  const isLight = theme === 'light'

  return (
    <IconButton
      onClick={onToggle}
      icon={isLight ? Moon : Sun}
      label={isLight ? 'Passer en mode sombre' : 'Passer en mode clair'}
      active={isLight}
    />
  )
}
