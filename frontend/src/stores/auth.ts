import { create } from 'zustand'
import { persist } from 'zustand/middleware'
import { supabase } from '../lib/supabase'

interface User {
  id: number | string
  email: string
  display_name?: string | null
}

interface AuthState {
  token: string | null
  user: User | null
  setAuth: (token: string, user: User) => void
  logout: () => void
}

export const useAuth = create<AuthState>()(
  persist(
    (set) => ({
      token: null,
      user: null,
      setAuth: (token, user) => set({ token, user }),
      logout: () => set({ token: null, user: null }),
    }),
    { name: 'aether-auth' }
  )
)

// Supabase is authoritative; never keep a stale JWT after logout or expiration.
if (supabase) {
  supabase.auth.getSession().then(({ data }) => {
    const session = data.session
    if (session) useAuth.getState().setAuth(session.access_token, {
      id: session.user.id, email: session.user.email || '',
      display_name: session.user.user_metadata?.full_name || session.user.email,
    })
    else useAuth.getState().logout()
  })
  supabase.auth.onAuthStateChange((_event, session) => {
    if (session) useAuth.getState().setAuth(session.access_token, {
      id: session.user.id, email: session.user.email || '',
      display_name: session.user.user_metadata?.full_name || session.user.email,
    })
    else useAuth.getState().logout()
  })
}
