# Live Trading Platform — Hybrid Architecture

**Goal**: Multi-user live trading bot platform.  
Users connect their own exchange API keys (Bybit / MEXC / Binance), fund their accounts, activate the bot, and the system detects high-quality opportunities across a unified market universe and executes on their behalf.

**Clients**:
- **Web** (primary, full terminal) — React + TypeScript + Vite + Tailwind
- **Mobile** (companion) — Expo (with development builds / prebuild so native modules are available when needed)

**Backend**: Existing FastAPI + Python intelligence layer (agents, scanner, decision engine). Extended for multi-user, multi-exchange execution, and real-time WebSocket.

---

## High-Level Architecture

```
┌──────────────────────────────────────────────────────────────────────────┐
│                         Clients                                          │
│  ┌─────────────────────┐          ┌──────────────────────────────────┐  │
│  │  Web (React)        │          │  Mobile (Expo)                   │  │
│  │  - Full dashboard   │          │  - Status & P&L                  │  │
│  │  - Markets browser  │          │  - Activate / Pause bot          │  │
│  │  - Bot controls     │          │  - Push notifications            │  │
│  │  - Charts & history │          │  - Secure key entry (biometrics) │  │
│  │  - Settings         │          │  - Quick overview                │  │
│  └──────────┬──────────┘          └───────────────┬──────────────────┘  │
│             │  REST + WebSocket                   │                      │
└─────────────┼─────────────────────────────────────┼──────────────────────┘
              │                                     │
┌─────────────▼─────────────────────────────────────▼──────────────────────┐
│                         FastAPI Backend                                  │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Auth & Users                                                      │ │
│  │  - JWT / Telegram / Wallet auth                                    │ │
│  │  - Encrypted API key storage (per exchange)                        │ │
│  │  - Bot activation state + risk limits per user                     │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Intelligence Layer (existing, shared)                             │ │
│  │  Scanner → Agents (trend, momentum, structure, risk, volume, …)    │ │
│  │  → Decision Engine → Ranked Opportunities                          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Markets Layer                                                     │ │
│  │  Unified universe: Bybit + MEXC + Binance (spot / futures)         │ │
│  │  Liquidity screening, best-price / best-liquidity routing          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Execution Layer                                                   │ │
│  │  ExecutionAdapter interface                                        │ │
│  │  Adapters: Bybit, MEXC, Binance, (optional Hyperliquid)            │ │
│  │  Per-user order placement, position tracking, risk checks          │ │
│  └────────────────────────────────────────────────────────────────────┘ │
│  ┌────────────────────────────────────────────────────────────────────┐ │
│  │  Real-time                                                         │ │
│  │  WebSocket: prices, positions, bot events, scan updates            │ │
│  └────────────────────────────────────────────────────────────────────┘ │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## Key Design Decisions

### 1. Non-custodial
Users fund their own exchange accounts. The platform only receives API keys (trade permission, no withdrawal ideally).  
This is the only realistic path without heavy licensing.

### 2. Shared Intelligence, Per-User Execution
- One shared scanner + agent pipeline produces ranked opportunities.
- A runner then matches opportunities to every active user who has:
  - Bot enabled
  - Sufficient allocated capital
  - A connected exchange that supports the pair
  - Risk limits not exceeded

### 3. Unified Markets
`list_markets()` returns the union of Bybit + MEXC + Binance with:
- `exchange` provenance
- normalized symbol (`BTC/USDT`)
- 24h volume, price change, best bid/ask where available
- liquidity score

Users can filter by exchange or see “best across all”.

### 4. Clients
- **Web** is the full trading terminal (tables, multi-panel, charts, history, settings).
- **Mobile (Expo)** is the companion: glanceable status, activate/pause, push alerts, secure API-key entry.
- Both talk to the exact same REST + WebSocket API.
- Shared TypeScript types can later live in a `packages/shared` folder.

### 5. Expo without limitations
Use **Expo with development builds** (or prebuild / continuous native generation).  
This gives access to native modules (SecureStore, biometrics, background fetch, local notifications, etc.) while keeping the Expo workflow and EAS Build.

---

## Backend Evolution Path (kept intact for now)

Current endpoints stay and will be extended:

| Area              | Current                          | Future additions                                      |
|-------------------|----------------------------------|-------------------------------------------------------|
| Status / Scan     | `/api/status`, `/api/scan/*`     | User-scoped scan preference                           |
| Markets           | `/api/markets`                   | Unified multi-exchange + filters                      |
| Positions         | `/api/positions`                 | Per-user positions + live P&L                         |
| Auth / Users      | none                             | `/api/auth/*`, `/api/users/me`, API-key management    |
| Bot Control       | none                             | `/api/bot/status`, `/api/bot/activate`, risk settings |
| Execution         | Hyperliquid-centric              | Multi-exchange ExecutionAdapter                       |
| Real-time         | Polling                          | WebSocket `/ws`                                       |

---

## Frontend Structure (Web)

```
frontend/
├── package.json
├── vite.config.ts
├── tailwind.config.js
├── index.html
├── src/
│   ├── main.tsx
│   ├── App.tsx
│   ├── api/          # typed API client
│   ├── components/   # UI building blocks
│   ├── pages/        # Dashboard, Markets, Positions, Settings, Bot
│   ├── hooks/        # useStatus, useScan, usePositions, useWebSocket
│   ├── stores/       # Zustand or simple context for auth + bot state
│   ├── types/        # shared API types
│   └── lib/          # utils, formatting
```

## Mobile Structure (future)

```
mobile/                 # Expo (SDK 52+ recommended)
├── app/                # Expo Router
├── src/
│   ├── api/            # same client as web (or shared package)
│   ├── components/
│   └── ...
```

---

## Security Notes

- API keys encrypted at rest (Fernet / AES-GCM with server-side key or KMS later).
- Prefer exchange API keys that **disable withdrawals**.
- Rate-limit sensitive endpoints.
- Bot has hard daily loss limits and max position size per user.
- Paper-trading mode first.

---

## Next Implementation Steps

1. Scaffold React + Vite + TypeScript + Tailwind web frontend.
2. Connect it to the existing backend endpoints (status, scan, markets, positions…).
3. Build a modern dark trading-terminal UI that already feels like the future product.
4. Extend backend with user model + bot activation (next phase).
5. Scaffold Expo mobile app that reuses the same API contract.

This document is the source of truth for the hybrid architecture.
