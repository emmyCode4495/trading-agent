export type Direction = 'LONG' | 'SHORT' | 'WAIT'
export type Bias = 'bullish' | 'bearish' | 'neutral'
export type PositionStatus = 'open' | 'win' | 'loss' | 'expired'

export interface Opportunity {
  symbol: string
  direction: Direction
  bias: Bias
  confidence: number
  entry_price?: number
  target_price?: number
  invalidation_price?: number
  market_regime?: string
  risk_level?: string
  evidence?: string[]
  created_at?: string
}

export interface ScanLatest {
  scan_id?: number
  scan_run_id?: number
  created_at?: string
  finished_at?: string
  error?: string | null
  markets_discovered?: number
  markets_screened?: number
  symbols_analyzed?: string[] | number
  opportunities: Opportunity[]
  duration_seconds?: number
}

export interface Market {
  symbol: string
  base_asset: string
  quote_asset: string
  status: string
  last_price: number
  quote_volume_24h: number
  price_change_pct_24h: number
  exchange?: string
  passed_screen?: boolean
}

export interface Position {
  id: number
  symbol: string
  direction: Direction
  entry_price: number
  current_price?: number
  target_price?: number
  invalidation_price?: number
  status: PositionStatus
  pnl_pct?: number
  created_at: string
  resolved_at?: string
  confidence?: number
}

export interface Status {
  scanner_running: boolean
  last_scan_at?: string
  next_scan_at?: string
  last_position_check_at?: string
  open_positions_count?: number
}

export interface Calibration {
  total_resolved: number
  wins: number
  losses: number
  expired: number
  win_rate: number
  avg_pnl_pct?: number
}
