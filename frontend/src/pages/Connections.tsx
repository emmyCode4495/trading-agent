import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'

export function Connections(){
 const user=useAuth(s=>s.user)
 const [data,setData]=useState<{connected:boolean;configured:boolean;environment?:string}|null>(null)
 const [error,setError]=useState('')
 const [busy,setBusy]=useState(false)
 async function refresh(){setBusy(true);setError('');try{setData(await api.demoStatus())}catch(e){setError(e instanceof Error?e.message:String(e))}finally{setBusy(false)}}
 useEffect(()=>{void refresh()},[])
 return <main className="p-5 md:p-8 max-w-3xl space-y-5">
 <div><p className="text-xs uppercase tracking-[.2em] text-sky-300">Account setup</p><h1 className="text-3xl font-semibold mt-2">Connections</h1><p className="text-sm text-[var(--color-text-mid)] mt-2">Manage your trading account connection. Exchange credentials are handled by the backend, never entered into the dashboard.</p></div>
 <section className="rounded-2xl border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-6 space-y-4"><div className="flex justify-between items-center"><h2 className="font-semibold">Bybit Demo</h2><span className="text-sm text-[var(--color-text-mid)]">{data?.connected?'Connected':data?.configured?'Connection unavailable':'Not configured'}</span></div><p className="text-sm text-[var(--color-text-mid)]">{data?.connected?'Demo exchange connection is responding.':data?.configured?'The server has demo credentials, but the exchange is not reachable.':'Configure demo API credentials securely on the backend. This version does not yet support separate exchange credentials for every customer.'}</p><button disabled={busy} onClick={()=>void refresh()} className="rounded-lg border border-[var(--color-panel-border)] px-4 py-2 text-sm">{busy?'Checking…':'Check connection'}</button>{error&&<p role="alert" className="text-sm text-red-300">{error}</p>}</section>
 <section className="rounded-2xl border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-6 space-y-2"><h2 className="font-semibold">Signed-in account</h2><p className="text-sm text-[var(--color-text-mid)]">{user?.email||'Unknown'}</p><p className="text-xs text-amber-300">User-specific exchange credential storage and trading-workspace isolation must be completed before enabling customer automation.</p></section>
 </main>
}
