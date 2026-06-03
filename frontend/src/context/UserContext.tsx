import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import type { UserInfo } from '../types'

interface UserContextValue {
  user: UserInfo | null
  loading: boolean
  refetch: () => void
  clearUser: () => void
}

const UserContext = createContext<UserContextValue>({
  user: null,
  loading: true,
  refetch: () => {},
  clearUser: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)

  const fetchUser = useCallback(() => {
    setLoading(true)
    // Plain fetch — a 401 just means "not logged in", no error dispatch needed
    fetch('/auth/me', { credentials: 'include' })
      .then(r => r.ok ? r.json() : null)
      .then((u: UserInfo | null) => { setUser(u); setLoading(false) })
      .catch(() => { setUser(null); setLoading(false) })
  }, [])

  const clearUser = useCallback(() => setUser(null), [])

  useEffect(() => { fetchUser() }, [fetchUser])

  return (
    <UserContext.Provider value={{ user, loading, refetch: fetchUser, clearUser }}>
      {children}
    </UserContext.Provider>
  )
}

export function useCurrentUser() {
  return useContext(UserContext)
}
