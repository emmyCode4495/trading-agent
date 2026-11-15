import { useEffect, useState } from 'react'
import { api, type BotSettings } from '../api/client'
import { useAuth } from '../stores/auth'
export function Bot(){
 const token=useAuth(s=>s.token),[state,setState]=useState<BotSettings|null>(null),[error,setError]=useState(''),[busy,setBusy]=useState(false)
 const refresh=()=>api.getBot().then(setState).catch(e=>setError(e.message))
 useEffect(()=>{if(token)refresh()},[token])
 if(!token)return <div className="p-8 max-w-2xl"><h1 className="text-2xl font-semibold mb-4">Execution controls</h1><p className="text-[var(--color-text-mid)]">Sign in under Connections to view operator controls.</p></div>
 return <div className="p-8 max-w-2xl space-y-5"><h1 className="text-2xl font-semibold">Execution controls</h1><div className="rounded-xl border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-6 space-y-4"><p className="text-amber-300 font-semibold">Live execution locked — market analysis only</p><p className="text-sm text-[var(--color-text-mid)]">Protective orders, daily loss enforcement, and exchange position reconciliation must be verified before live orders can be enabled. No button here will place an order.</p>{state&&<><div className="grid grid-cols-2 gap-4 text-sm"><div>Master switch: <b>{state.master_enabled?'On':'Off'}</b></div><div>Execution: <b>{state.is_active?'Active':'Disabled'}</b></div><div>Risk per trade: {state.risk_per_trade_pct}%</div><div>Minimum confidence: {state.min_confidence}%</div></div><button disabled={busy} className="rounded-lg border border-[var(--color-panel-border)] px-4 py-2 hover:bg-white/5" onClick={async()=>{setBusy(true);try{setState(await api.deactivateBot());setError('')}catch(e){setError(String(e))}finally{setBusy(false)}}}>Emergency disable execution</button></>}{error&&<p role="alert" className="text-red-300 text-sm">{error}</p>}</div></div>
}
