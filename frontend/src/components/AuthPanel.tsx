import { useState, type FormEvent } from 'react'
import { supabase } from '../lib/supabase'
import { useAuth } from '../stores/auth'
import { LockKeyhole, UserRoundPlus, LogIn } from 'lucide-react'

export function AuthPanel() {
  const [mode, setMode] = useState<'login' | 'signup'>('signup')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [name, setName] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [message, setMessage] = useState('')
  const setAuth = useAuth(s => s.setAuth)
  async function submit(event: FormEvent) {
    event.preventDefault()
    setError(''); setMessage('')
    if (!supabase) { setError('Configure VITE_SUPABASE_URL and VITE_SUPABASE_ANON_KEY first.'); return }
    setBusy(true)
    try {
      if (mode === 'signup') {
        const { data, error } = await supabase.auth.signUp({ email, password, options: { data: { full_name: name.trim() } } })
        if (error) throw error
        if (data.session && data.user) setAuth(data.session.access_token, { id: data.user.id, email: data.user.email || email, display_name: name.trim() })
        else setMessage('Check your email for a confirmation link, then sign in. If you already have an account, use Sign in.')
      } else {
        const { data, error } = await supabase.auth.signInWithPassword({ email, password })
        if (error) throw error
        if (!data.session) throw new Error('Sign-in requires a confirmed account.')
        setAuth(data.session.access_token, { id: data.user.id, email: data.user.email || email, display_name: data.user.user_metadata?.full_name })
      }
      setPassword('')
    } catch (err) { setError(err instanceof Error ? err.message : 'Authentication failed') }
    finally { setBusy(false) }
  }
  return <section className="rounded-2xl border border-[#34465b] bg-[#121d29] p-6 md:p-8 max-w-xl mx-auto shadow-2xl" aria-label="Account access">
    <div className="flex items-center gap-3 mb-3"><span className="rounded-xl bg-[#253a51] p-3 text-[#bfd4f0]"><LockKeyhole size={22}/></span><div><h2 className="text-xl font-semibold">{mode === 'signup' ? 'Create your trading workspace' : 'Welcome back'}</h2><p className="text-sm text-[var(--color-text-mid)]">Secure account access with Supabase Auth</p></div></div>
    <div className="flex gap-2 my-5 border-b border-[#34465b] pb-3"><button type="button" onClick={()=>{setMode('signup');setError('');setMessage('')}} className={'px-4 py-2 rounded-lg text-sm '+(mode==='signup'?'bg-[#bfd4f0] text-[#0b121b]':'text-[var(--color-text-mid)]')}><UserRoundPlus size={15} className="inline mr-2"/>Register</button><button type="button" onClick={()=>{setMode('login');setError('');setMessage('')}} className={'px-4 py-2 rounded-lg text-sm '+(mode==='login'?'bg-[#bfd4f0] text-[#0b121b]':'text-[var(--color-text-mid)]')}><LogIn size={15} className="inline mr-2"/>Sign in</button></div>
    <form onSubmit={submit} className="space-y-4">
      {mode==='signup' && <label className="block text-sm">Full name<input value={name} onChange={e=>setName(e.target.value)} required maxLength={100} autoComplete="name" className="mt-1 w-full rounded-lg bg-[#0b121b] border border-[#34465b] px-3 py-3"/></label>}
      <label className="block text-sm">Email<input type="email" value={email} onChange={e=>setEmail(e.target.value)} required autoComplete="email" className="mt-1 w-full rounded-lg bg-[#0b121b] border border-[#34465b] px-3 py-3"/></label>
      <label className="block text-sm">Password<input type="password" value={password} onChange={e=>setPassword(e.target.value)} required minLength={6} autoComplete={mode==='signup'?'new-password':'current-password'} className="mt-1 w-full rounded-lg bg-[#0b121b] border border-[#34465b] px-3 py-3"/></label>
      <button disabled={busy || !supabase} className="w-full rounded-lg bg-[#bfd4f0] text-[#0b121b] font-semibold px-5 py-3 disabled:opacity-50">{busy?'Please wait…':mode==='signup'?'Create account':'Sign in'}</button>
    </form>
    {error&&<p role="alert" className="mt-4 text-sm text-red-300">{error}</p>}{message&&<p role="status" className="mt-4 text-sm text-emerald-300">{message}</p>}
    {!supabase&&<p className="mt-4 text-xs text-amber-300">Supabase environment variables are missing. Registration is disabled until configured.</p>}
    <p className="mt-5 text-xs text-[var(--color-text-dim)]">Your account identifies your session. Trading execution remains restricted to authorized operators until per-user trade isolation is completed.</p>
  </section>
}
