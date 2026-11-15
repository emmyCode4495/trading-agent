import type { ScanLatest, Market, Position, Status, Calibration, Opportunity } from '../types'

const BASE = import.meta.env.VITE_API_URL || ''

async function request<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${BASE}${path}`, {
    headers: { 'Content-Type': 'application/json', ...options?.headers },
    ...options,
  })
  if (!res.ok) {
    const text = await res.text()
    throw new Error(text || `HTTP ${res.status}`)
  }
  return res.json()
}

export const api = {
  status: () => request<Status>('/api/status'),
  latestScan: () => request<ScanLatest>('/api/scan/latest'),
  runScan: () => request<ScanLatest>('/api/scan/run', { method: 'POST' }),
  markets: (quote = 'USDT') => request<Market[]>(`/api/markets?quote_asset=${quote}`),
  positions: () => request<{ open: Position[]; recent: Position[] }>('/api/positions'),
  calibration: () => request<Calibration>('/api/calibration'),
  report: (symbol: string) => request<Opportunity>(`/api/report/latest?symbol=${encodeURIComponent(symbol)}`),
  history: (symbol: string, limit = 30) =>
    request<Opportunity[]>(`/api/history?symbol=${encodeURIComponent(symbol)}&limit=${limit}`),
}
