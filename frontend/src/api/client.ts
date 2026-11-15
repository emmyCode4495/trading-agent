import type { ScanLatest, Market, Position, Status, Calibration, Opportunity } from '../types'
import { useAuth } from '../stores/auth'

const BASE = import.meta.env.VITE_API_URL || ''
const unavailable = () => { throw new Error('Exchange key storage is not enabled. Do not enter API secrets.') }

async function request<T>(path: string, options?: RequestInit & { auth?: boolean }): Promise<T> {
  const headers: Record<string, string> = {
    'Content-Type': 'application/json',
    ...(options?.headers as Record<string, string> | undefined),
  }
  if (options?.auth !== false) {
    const token = useAuth.getState().token
    if (token) headers['Authorization'] = `Bearer ${token}`
  }
  const res = await fetch(`${BASE}${path}`, {
    ...options,
    headers,
  })
  if (!res.ok) {
    let detail = `HTTP ${res.status}`
    try {
      const body = await res.json()
      detail = body.detail || JSON.stringify(body)
    } catch {
      // Response body was already consumed by res.json(); retain HTTP status.
    }
    throw new Error(typeof detail === 'string' ? detail : JSON.stringify(detail))
  }
  if (res.status === 204) return undefined as T
  return res.json()
}

export interface MarketsResponse {
  quote_asset: string
  total_discovered: number
  total_screened: number
  markets: Market[]
}

export interface PositionsResponse {
  open: Position[]
  recently_resolved: Position[]
  recent?: Position[]
}

export interface BotSettings {
  is_active: boolean
  paper_trading: boolean
  allocated_capital_usd: number
  risk_per_trade_pct: number
  max_open_positions: number
  daily_loss_limit_pct: number
  preferred_exchanges: string
  min_confidence: number
  updated_at?: string
}

export interface ExchangeKey {
  id: number
  exchange: string
  label: string
  is_active: boolean
  api_key_hint: string
  last_validated_at?: string | null
  validation_error?: string | null
  created_at?: string
}

export const api = {
  demoAgentStatus: () => request<{enabled:boolean;server_allowed:boolean;environment:string;decisions:Array<{id:number;symbol:string;direction:string;confidence:number;status:string;reason:string;created_at:string}>}>('/api/demo/agent/status'),
  demoAgentStart: () => request('/api/demo/agent/start',{method:'POST'}),
  demoAgentStop: () => request('/api/demo/agent/stop',{method:'POST'}),
  demoAgentCycle: () => request<{status:string;reason?:string;symbol?:string}>('/api/demo/agent/cycle',{method:'POST'}),
  demoAgentMetrics: () => request<{closed_trades_sample:number;decisive_trades:number;wins:number;losses:number;win_rate_pct:number|null;wilson_95_pct:number[]|null;sum_exchange_closed_pnl:number;scope:string;limitations:string}>('/api/demo/agent/metrics'),
  demoStatus: () => request<{configured:boolean;connected:boolean;environment:string;accounts?:Array<{totalEquity:string;coin:Array<{coin:string;walletBalance:string}>}>}>('/api/demo/bybit/status'),
  demoPositions: () => request<{list:Array<Record<string,string>>}>('/api/demo/bybit/positions'),
  demoOrders: () => request<{list:Array<Record<string,string>>}>('/api/demo/bybit/orders'),
  demoPlaceOrder: (data:{symbol:string;side:'Buy'|'Sell';qty:string;price:string;confirm:string}) => request('/api/demo/bybit/orders',{method:'POST',body:JSON.stringify(data)}),
  demoCancelOrder: (symbol:string,order_id:string) => request('/api/demo/bybit/orders/cancel',{method:'POST',body:JSON.stringify({symbol,order_id})}),
  billingPlans: () => request<Array<{id:string;amount_usd:number;currency:string;interval:string}>>('/api/billing/plans',{auth:false}),
  billingRegister: (email:string,password:string) => request<{access_token:string;user:{id:number;email:string}}>('/api/billing/register',{method:'POST',auth:false,body:JSON.stringify({email,password})}),
  billingLogin: (email:string,password:string) => request<{access_token:string;user:{id:number;email:string}}>('/api/billing/login',{method:'POST',auth:false,body:JSON.stringify({email,password})}),
  billingMe: () => request<{active:boolean;subscription:{plan:string;status:string;paid_until:number;cancel_at_period_end:number}|null;payments:Array<{provider_tx_id:string;plan:string;amount:number;currency:string;created_at:number}>}>('/api/billing/me'),
  billingCheckout: (plan:string) => request<{checkout_url:string;reference:string}>('/api/billing/checkout',{method:'POST',body:JSON.stringify({plan})}),
  billingVerify: (transaction_id:number) => request('/api/billing/verify',{method:'POST',body:JSON.stringify({transaction_id})}),
  billingCancel: () => request('/api/billing/cancel',{method:'POST'}),
  status: () => request<Status>('/api/status', {}),
  latestScan: () => request<ScanLatest>('/api/scan/latest', {}),
  runScan: () => request<ScanLatest>('/api/scan/run', { method: 'POST' }),
  markets: (quote = 'USDT') =>
    request<MarketsResponse>(`/api/markets?quote_asset=${encodeURIComponent(quote)}`, {}),
  positions: async () => {
    const res = await request<PositionsResponse>('/api/positions')
    return {
      open: Array.isArray(res?.open) ? res.open : [],
      recent: Array.isArray(res?.recently_resolved)
        ? res.recently_resolved
        : Array.isArray(res?.recent)
          ? res.recent
          : [],
    }
  },
  calibration: () => request<Calibration>('/api/calibration'),
  report: (symbol: string) =>
    request<Opportunity>(`/api/report/latest?symbol=${encodeURIComponent(symbol)}`, {}),
  history: (symbol: string, limit = 30) =>
    request<Opportunity[]>(`/api/history?symbol=${encodeURIComponent(symbol)}&limit=${limit}`, {
    }),

  login: (email: string, password: string) => request<{access_token:string;user:{id:number;email:string;display_name:string}}>('/api/auth/login',{method:'POST',auth:false,body:JSON.stringify({email,password})}),
  me: () => request<{id:number;email:string;display_name:string}>('/api/auth/me'),
  listKeys: async (): Promise<ExchangeKey[]> => unavailable(),
  addKey: async (_data: {exchange: string;api_key: string;api_secret: string;passphrase?: string;label?: string}): Promise<never> => unavailable(),
  deleteKey: async (_id: number): Promise<void> => unavailable(),
  getBot: () => request<BotSettings>('/api/bot'),
  updateBot: (data: Pick<BotSettings,'risk_per_trade_pct'|'max_open_positions'|'daily_loss_limit_pct'|'min_confidence'>) => request<BotSettings>('/api/bot',{method:'PUT',body:JSON.stringify(data)}),
  activateBot: () => request<BotSettings>('/api/bot/activate',{method:'POST'}),
  deactivateBot: () => request<BotSettings>('/api/bot/deactivate',{method:'POST'}),
}
