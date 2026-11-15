import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import { Layout } from './components/Layout'
import { DemoTrading } from './pages/DemoTrading'
import { Billing } from './pages/Billing'
import { Connections } from './pages/Connections'
import { AuthPanel } from './components/AuthPanel'
import { useAuth } from './stores/auth'

function Home() {
 const token = useAuth(s => s.token)
 return token ? <DemoTrading /> : <main className="mx-auto max-w-xl p-6 md:p-12 space-y-6"><div className="space-y-2"><p className="text-xs uppercase tracking-[.2em] text-sky-300">Aether / Autonomous trading</p><h1 className="text-3xl font-semibold">Your trading agent, one dashboard.</h1><p className="text-sm text-[var(--color-text-mid)]">Sign in or create an account to manage your agent, connection and membership.</p></div><AuthPanel /></main>
}
function Protected({children}:{children:React.ReactNode}) { const token=useAuth(s=>s.token); return token ? <>{children}</> : <Navigate to="/" replace /> }
export default function App(){return <BrowserRouter><Routes><Route element={<Layout/>}><Route index element={<Home/>}/><Route path="connections" element={<Protected><Connections/></Protected>}/><Route path="membership" element={<Protected><Billing/></Protected>}/><Route path="*" element={<Navigate to="/" replace/>}/></Route></Routes></BrowserRouter>}
