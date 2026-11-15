import { useEffect, useState } from 'react'
import { api } from '../api/client'
import { useAuth } from '../stores/auth'

type Decision = {id:number;symbol:string;direction:string;confidence:number;status:string;reason:string;created_at:string}
type Agent = {enabled:boolean;server_allowed:boolean;environment:string;decisions:Decision[]}
type Metrics = {closed_trades_sample:number;decisive_trades:number;wins:number;losses:number;win_rate_pct:number|null;wilson_95_pct:number[]|null;sum_exchange_closed_pnl:number;scope:string;limitations:string}
type ExchangeItem = Record<string,string>
const panel = 'rounded-2xl border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-5'
export function DemoTrading(){
 const token=useAuth(s=>s.token)
 const [connection,setConnection]=useState<{connected:boolean;configured:boolean;accounts?:Array<{totalEquity:string}>}|null>(null)
 const [agent,setAgent]=useState<Agent|null>(null)
 const [metrics,setMetrics]=useState<Metrics|null>(null)
 const [positions,setPositions]=useState<ExchangeItem[]>([])
 const [orders,setOrders]=useState<ExchangeItem[]>([])
 const [error,setError]=useState('')
 const [busy,setBusy]=useState(false)
 const [cycle,setCycle]=useState('')
 async function refresh(){
   if(!token)return
   const results=await Promise.allSettled([api.demoStatus(),api.demoAgentStatus(),api.demoAgentMetrics(),api.demoPositions(),api.demoOrders()])
   const [c,a,m,p,o]=results
   if(c.status==='fulfilled')setConnection(c.value)
   if(a.status==='fulfilled')setAgent(a.value)
   if(m.status==='fulfilled')setMetrics(m.value)
   if(p.status==='fulfilled')setPositions((p.value.list||[]).filter(x=>Number(x.size)>0))
   if(o.status==='fulfilled')setOrders(o.value.list||[])
   const failed=results.find(x=>x.status==='rejected')
   setError(failed?.status==='rejected'?String(failed.reason):'')
 }
 useEffect(()=>{if(!token)return;void refresh();const timer=setInterval(()=>void refresh(),15000);return()=>clearInterval(timer)},[token])
 async function action(kind:'start'|'stop'|'cycle'){
   setBusy(true);setError('')
   try{if(kind==='start')await api.demoAgentStart();if(kind==='stop')await api.demoAgentStop();if(kind==='cycle'){const result=await api.demoAgentCycle();setCycle(`${result.status}: ${result.reason||result.symbol||'Cycle completed'}`)}await refresh()}
   catch(e){setError(String(e))}finally{setBusy(false)}
 }
 return <main className="p-5 md:p-8 space-y-5 max-w-6xl">
   <header className="flex flex-wrap items-end justify-between gap-4"><div><p className="text-xs uppercase tracking-[.2em] text-sky-300">Agent dashboard / Bybit demo</p><h1 className="text-3xl font-semibold tracking-tight mt-2">Your trading agent</h1><p className="text-sm text-[var(--color-text-mid)] mt-2 max-w-2xl">Your strategy selects markets, entries, size and protection. Demo exchange fills are measured separately from model scores. No live-money orders.</p></div><span className="rounded-full border border-sky-800 px-3 py-1.5 text-xs text-sky-300">DEMO ONLY · 15s refresh</span></header>
   {!token?<section className={panel}>Log in as the operator to access the demo environment.</section>:<>
   <section className="grid gap-3 md:grid-cols-4">
     {[['Exchange',connection?.connected?'Connected':'Disconnected'],['Agent',agent?.enabled?'Scanning / eligible':'Paused'],['Demo equity',connection?.accounts?.[0]?.totalEquity?`$${Number(connection.accounts[0].totalEquity).toLocaleString()}`:'—'],['Open positions',String(positions.length)]].map(([label,value])=><div className={panel} key={label}><p className="text-xs text-[var(--color-text-mid)] uppercase tracking-wider">{label}</p><p className="text-xl font-semibold mt-3">{value}</p></div>)}
   </section>
   <section className={panel}><div className="flex flex-wrap justify-between items-start gap-4"><div><h2 className="text-lg font-semibold">Demo automation</h2><p className="text-sm text-[var(--color-text-mid)] mt-2 max-w-2xl">Uses the latest scanner recommendations and server-side risk gates. Only opens an order if the exchange confirms acceptable market conditions, sizing and protective levels.</p></div><div className="flex gap-2"><button disabled={busy||!agent?.server_allowed||!connection?.connected||agent?.enabled} onClick={()=>void action('start')} className="rounded-lg bg-sky-200 text-slate-950 px-4 py-2 text-sm font-semibold disabled:opacity-40">Start demo agent</button><button disabled={busy||!agent?.enabled} onClick={()=>void action('stop')} className="rounded-lg border border-[var(--color-panel-border)] px-4 py-2 text-sm disabled:opacity-40">Pause entries</button></div></div>
   {!agent?.server_allowed&&<p className="mt-4 text-sm text-amber-300">Server lock is active. Set ENABLE_AUTONOMOUS_DEMO=true only when you're ready to submit demo orders.</p>}
   <div className="mt-4 flex flex-wrap gap-3 items-center"><button disabled={busy||!agent?.enabled} onClick={()=>void action('cycle')} className="rounded-lg border border-[var(--color-panel-border)] px-3 py-2 text-sm disabled:opacity-40">Evaluate now</button><span className="text-xs text-[var(--color-text-mid)]">Pause prevents new entries; existing exchange positions remain open with their protective orders.</span></div>{cycle&&<p className="mt-3 text-sm text-sky-300">{cycle}</p>}</section>
   <section className={panel}><h2 className="text-lg font-semibold">Observed demo performance</h2><p className="text-xs text-[var(--color-text-mid)] mt-1">Exchange-reported closed P&amp;L · latest 100 records · not a predicted live win rate</p><div className="grid grid-cols-2 md:grid-cols-4 gap-5 mt-5">{[['Win rate',metrics?.win_rate_pct==null?'Insufficient data':`${metrics.win_rate_pct}%`],['Closed records',String(metrics?.closed_trades_sample??'—')],['Wins / losses',metrics?`${metrics.wins} / ${metrics.losses}`:'—'],['Closed P&L',metrics?`${metrics.sum_exchange_closed_pnl.toFixed(2)} USDT`:'—']].map(([k,v])=><div key={k}><p className="text-xs text-[var(--color-text-mid)]">{k}</p><p className="text-xl font-semibold mt-1">{v}</p></div>)}</div>
   <p className="text-xs text-[var(--color-text-mid)] mt-4">95% Wilson interval: {metrics?.wilson_95_pct?`${metrics.wilson_95_pct[0]}%–${metrics.wilson_95_pct[1]}%`:'Not available'}. Includes any manual trades on the same demo account; do not interpret this as agent-only accuracy. Demo liquidity, slippage and funding differ from live trading.</p></section>
   <div className="grid md:grid-cols-2 gap-4"><section className={panel}><h2 className="font-semibold">Open exchange positions</h2><div className="mt-4 space-y-3">{positions.length?positions.map((p,i)=><div key={`${p.symbol}-${i}`} className="border-t border-[var(--color-panel-border)] pt-3 text-sm"><p className="font-medium">{p.symbol} · {p.side} · {p.size}</p><p className="text-xs text-[var(--color-text-mid)] mt-1">P&L {p.unrealisedPnl} · SL {p.stopLoss||'Missing'} · TP {p.takeProfit||'Missing'}</p></div>):<p className="text-sm text-[var(--color-text-mid)]">No open positions</p>}</div></section><section className={panel}><h2 className="font-semibold">Exchange orders</h2><div className="mt-4 space-y-3">{orders.length?orders.slice(0,10).map((o,i)=><div key={`${o.orderId}-${i}`} className="border-t border-[var(--color-panel-border)] pt-3 text-sm">{o.symbol} · {o.side} · {o.orderStatus} <span className="text-xs text-[var(--color-text-mid)]">{o.qty}</span></div>):<p className="text-sm text-[var(--color-text-mid)]">No outstanding orders</p>}</div></section></div>
   <section className={panel}><h2 className="font-semibold">Agent decision log</h2><p className="text-xs text-[var(--color-text-mid)] mt-1">Trade submission is not the same as a confirmed fill.</p><div className="mt-4 overflow-x-auto"><table className="w-full text-left text-sm"><thead className="text-xs text-[var(--color-text-mid)]"><tr><th className="pb-3">Time</th><th>Market</th><th>Side</th><th>Score</th><th>Status</th><th>Reason</th></tr></thead><tbody>{agent?.decisions.map(d=><tr key={d.id} className="border-t border-[var(--color-panel-border)]"><td className="py-3 whitespace-nowrap">{new Date(d.created_at).toLocaleString()}</td><td>{d.symbol}</td><td>{d.direction}</td><td>{d.confidence}</td><td>{d.status}</td><td className="text-xs text-[var(--color-text-mid)]">{d.reason}</td></tr>)}</tbody></table>{!agent?.decisions.length&&<p className="text-sm text-[var(--color-text-mid)] py-3">No demo decisions recorded yet.</p>}</div></section>
   {error&&<p role="alert" className="text-sm text-red-300">{error}</p>}
   </>}
 </main>
}
