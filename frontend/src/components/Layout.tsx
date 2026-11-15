import { NavLink, Outlet, useLocation } from 'react-router-dom'
import { LayoutDashboard, Settings, Radio, ShieldCheck, CreditCard } from 'lucide-react'
import clsx from 'clsx'
import { useAuth } from '../stores/auth'
import { supabase } from '../lib/supabase'
const nav = [
 {to:'/',label:'Dashboard',icon:LayoutDashboard},
 {to:'/connections',label:'Connections',icon:Settings},
 {to:'/membership',label:'Membership',icon:CreditCard},
]
export function Layout(){
 const location=useLocation()
 const user=useAuth(s=>s.user)
 const logout=useAuth(s=>s.logout)
 const current=nav.find(n=>n.to===location.pathname)?.label || 'Dashboard'
 return <div className="min-h-screen bg-[var(--color-bg)] lg:flex">
  <aside className="lg:w-[246px] lg:fixed lg:inset-y-0 lg:left-0 shrink-0 border-b lg:border-b-0 lg:border-r border-[var(--color-panel-border)] bg-[#0d131b] flex flex-col z-10">
   <div className="px-6 pt-7 pb-6 border-b border-[var(--color-panel-border)]">
    <div className="flex items-center gap-3"><span className="w-9 h-9 grid place-items-center rounded-lg border border-[#405169] bg-[#1b2b3c]"><Radio size={19} className="text-[#b8d2ff]"/></span><div><div className="font-semibold tracking-[.16em] text-[13px]">AETHER</div><div className="text-[10px] tracking-[.16em] text-[var(--color-text-dim)] uppercase mt-0.5">Trading intelligence</div></div></div>
   </div>
   <div className="hidden lg:block px-6 pt-7 pb-3 text-[10px] font-semibold uppercase tracking-[.2em] text-[var(--color-text-dim)]">Workspace</div>
   <nav aria-label="Main navigation" className="flex lg:flex-col overflow-x-auto lg:overflow-visible gap-1 px-3 py-3 lg:py-1 lg:px-3 lg:space-y-1">
    {nav.map(({to,label,icon:Icon})=><NavLink key={to} to={to} end={to==='/'} className={({isActive})=>clsx('flex shrink-0 items-center gap-3 rounded-lg px-3 py-3 text-[13px] font-medium transition-colors border',isActive?'border-[#34465b] bg-[#1d2a39] text-white':'border-transparent text-[var(--color-text-mid)] hover:bg-white/5 hover:text-white')}><Icon size={17}/><span>{label}</span></NavLink>)}
   </nav>
   <div className="hidden lg:block mt-auto p-5"><div className="rounded-lg border border-[var(--color-panel-border)] bg-[#141e29] p-4"><div className="flex gap-2 items-center text-xs font-semibold"><ShieldCheck size={15} className="text-[var(--color-bull)]"/> Research workspace</div><p className="text-[11px] leading-relaxed text-[var(--color-text-dim)] mt-2">The agent trades only when server-side checks pass. Demo results do not guarantee live returns.</p></div><div className="mt-4 text-[10px] tracking-wide text-[var(--color-text-dim)]">AETHER / TERMINAL</div></div>
  </aside>
  <div className="min-w-0 flex-1 lg:ml-[246px]"><header className="h-[62px] border-b border-[var(--color-panel-border)] flex items-center justify-between px-5 md:px-8"><div className="flex items-center gap-3"><span className="text-[11px] uppercase tracking-[.16em] text-[var(--color-text-dim)] hidden sm:inline">Workspace</span><span className="text-[var(--color-text-dim)] hidden sm:inline">/</span><span className="font-semibold text-[13px]">{current}</span></div><div className="flex items-center gap-3">{user ? <><span className="text-xs text-[var(--color-text-mid)] max-w-[160px] truncate" title={user.email}>{user.display_name || user.email}</span><button className="text-xs rounded border border-[#3a4655] px-3 py-1.5" onClick={async()=>{if(supabase) await supabase.auth.signOut(); logout()}}>Sign out</button></> : <NavLink to="/" className="text-xs rounded border border-[#3a4655] px-3 py-1.5">Register / Sign in</NavLink>}</div></header><main className="min-w-0"><Outlet/></main></div>
 </div>
}
