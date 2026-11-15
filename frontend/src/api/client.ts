import type { ScanLatest, Market, Position, Status, Calibration, Opportunity } from '../types'
import { useAuth } from '../stores/auth'

const BASE = import.meta.env.VITE_API_URL || ''

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
      const text = await res.text()
      if (text) detail = text
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
  status: () => request<Status>('/api/status', { auth: false }),
  latestScan: () => request<ScanLatest>('/api/scan/latest', { auth: false }),
  runScan: () => request<ScanLatest>('/api/scan/run', { method: 'POST', auth: false }),
  markets: (quote = 'USDT') =>
    request<MarketsResponse>(`/api/markets?quote_asset=${encodeURIComponent(quote)}`, { auth: false }),
  positions: async () => {
    const res = await request<PositionsResponse>('/api/positions', { auth: false })
    return {
      open: Array.isArray(res?.open) ? res.open : [],
      recent: Array.isArray(res?.recently_resolved)
        ? res.recently_resolved
        : Array.isArray(res?.recent)
          ? res.recent
          : [],
    }
  },
  calibration: () => request<Calibration>('/api/calibration', { auth: false }),
  report: (symbol: string) =>
    request<Opportunity>(`/api/report/latest?symbol=${encodeURIComponent(symbol)}`, { auth: false }),
  history: (symbol: string, limit = 30) =>
    request<Opportunity[]>(`/api/history?symbol=${encodeURIComponent(symbol)}&limit=${limit}`, {
      auth: false,
    }),

  // Auth
  register: (email: string, password: string, display_name?: string) =>
    request<{ access_token: string; user: { id: number; email: string; display_name?: string } }>(
      '/api/auth/register',
      { method: 'POST', body: JSON.stringify({ email, password, display_name }), auth: false }
    ),
  login: (email: string, password: string) =>
    request<{ access_token: string; user: { id: number; email: string; display_name?: string } }>(
      '/api/auth/login',
      { method: 'POST', body: JSON.stringify({ email, password }), auth: false }
    ),
  me: () => request<{ id: number; email: string; display_name?: string }>('/api/auth/me'),

  // Keys
  listKeys: () => request<ExchangeKey[]>('/api/keys'),
  addKey: (data: {
    exchange: string
    api_key: string
    api_secret: string
    passphrase?: string
    label?: string
  }) => request<ExchangeKey>('/api/keys', { method: 'POST', body: JSON.stringify(data) }),
  deleteKey: (id: number) => request<void>(`/api/keys/${id}`, { method: 'DELETE' }),

  // Bot
  getBot: () => request<BotSettings>('/api/bot'),
  updateBot: (data: Partial<BotSettings>) =>
    request<BotSettings>('/api/bot', { method: 'PATCH', body: JSON.stringify(data) }),
  activateBot: () => request<BotSettings>('/api/bot/activate', { method: 'POST' }),
  deactivateBot: () => request<BotSettings>('/api/bot/deactivate', { method: 'POST' }),
}
