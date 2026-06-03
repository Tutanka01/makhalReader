import { createContext, useContext, useState, useEffect, useCallback, type ReactNode } from 'react'
import apiClient from '../apiClient'
import type { UserInfo } from '../types'

interface UserContextValue {
  user: UserInfo | null
  loading: boolean
  error: string | null
  refetch: () => void
}

const UserContext = createContext<UserContextValue>({
  user: null,
  loading: true,
  error: null,
  refetch: () => {},
})

export function UserProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<UserInfo | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchUser = useCallback(() => {
    setLoading(true)
    setError(null)
    apiClient.get<UserInfo>('/auth/me').then(u => {
      setUser(u)
      setLoading(false)
    }).catch(err => {
      setError(err?.detail || 'Failed to fetch user')
      setLoading(false)
    })
  }, [])

  useEffect(() => { fetchUser() }, [fetchUser])

  return (
    <UserContext.Provider value={{ user, loading, error, refetch: fetchUser }}>
      {children}
    </UserContext.Provider>
  )
}

export function useCurrentUser() {
  return useContext(UserContext)
}
