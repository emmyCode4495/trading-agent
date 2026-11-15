import { useEffect, useState } from 'react'
import { Bot as BotIcon, Power, Shield, Wallet, LogIn, LogOut } from 'lucide-react'
import { api, type BotSettings } from '../api/client'
import { useAuth } from '../stores/auth'
import clsx from 'clsx'

export function Bot() {
  const { token, user, setAuth, logout } = useAuth()
  const [bot, setBot] = useState<BotSettings | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [mode, setMode] = useState<'login' | 'register'>('login')
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [displayName, setDisplayName] = useState('')

  const loadBot = async () => {
    if (!token) return
    setLoading(true)
    setError(null)
    try {
      const b = await api.getBot()
      setBot(b)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (token) loadBot()
    else setBot(null)
  }, [token])

  const handleAuth = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      const res =
        mode === 'login'
          ? await api.login(email, password)
          : await api.register(email, password, displayName || undefined)
      setAuth(res.access_token, res.user)
      setPassword('')
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const toggleActive = async () => {
    if (!bot) return
    setLoading(true)
    setError(null)
    try {
      const next = bot.is_active ? await api.deactivateBot() : await api.activateBot()
      setBot(next)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  const updateField = async (patch: Partial<BotSettings>) => {
    setLoading(true)
    setError(null)
    try {
      const next = await api.updateBot(patch)
      setBot(next)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <div className="p-6 max-w-[420px] mx-auto space-y-6">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Bot Control</h1>
          <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
            Sign in to activate the bot and manage risk
          </p>
        </div>

        <form
          onSubmit={handleAuth}
          className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-5 space-y-4"
        >
          <div className="flex gap-2 text-sm">
            <button
              type="button"
              onClick={() => setMode('login')}
              className={clsx(
                'px-3 py-1.5 rounded-md',
                mode === 'login' ? 'bg-white/10 text-white' : 'text-[var(--color-text-dim)]'
              )}
            >
              Login
            </button>
            <button
              type="button"
              onClick={() => setMode('register')}
              className={clsx(
                'px-3 py-1.5 rounded-md',
                mode === 'register' ? 'bg-white/10 text-white' : 'text-[var(--color-text-dim)]'
              )}
            >
              Register
            </button>
          </div>

          {mode === 'register' && (
            <input
              value={displayName}
              onChange={(e) => setDisplayName(e.target.value)}
              placeholder="Display name"
              className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm"
            />
          )}
          <input
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="Email"
            className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm"
          />
          <input
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            placeholder="Password (min 8)"
            className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm"
          />

          {error && (
            <div className="text-sm text-[var(--color-bear)] bg-[var(--color-bear)]/10 px-3 py-2 rounded">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={loading}
            className="w-full inline-flex items-center justify-center gap-2 px-4 py-2.5 rounded-md bg-[var(--color-accent)] text-white text-sm font-medium hover:opacity-90 disabled:opacity-50"
          >
            <LogIn className="w-4 h-4" />
            {mode === 'login' ? 'Sign in' : 'Create account'}
          </button>
        </form>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[900px] mx-auto space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-semibold tracking-tight">Bot Control</h1>
          <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
            Signed in as {user?.display_name || user?.email}
          </p>
        </div>
        <button
          onClick={logout}
          className="inline-flex items-center gap-2 text-sm text-[var(--color-text-mid)] hover:text-white"
        >
          <LogOut className="w-4 h-4" />
          Sign out
        </button>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10 px-4 py-3 text-sm text-[var(--color-bear)]">
          {error}
        </div>
      )}

      {loading && !bot ? (
        <div className="text-[var(--color-text-dim)]">Loading bot settings…</div>
      ) : bot ? (
        <>
          <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-5 flex items-center justify-between gap-4">
            <div className="flex items-center gap-3">
              <div
                className={clsx(
                  'w-10 h-10 rounded-full flex items-center justify-center',
                  bot.is_active ? 'bg-[var(--color-bull)]/15' : 'bg-white/5'
                )}
              >
                <BotIcon
                  className={clsx('w-5 h-5', bot.is_active ? 'text-[var(--color-bull)]' : 'text-[var(--color-text-dim)]')}
                />
              </div>
              <div>
                <div className="font-medium">
                  Bot is {bot.is_active ? 'ON' : 'OFF'}
                  {bot.paper_trading && (
                    <span className="ml-2 text-xs text-[var(--color-amber)]">PAPER</span>
                  )}
                </div>
                <div className="text-xs text-[var(--color-text-dim)]">
                  Min confidence {bot.min_confidence} · max {bot.max_open_positions} positions
                </div>
              </div>
            </div>
            <button
              onClick={toggleActive}
              disabled={loading}
              className={clsx(
                'inline-flex items-center gap-2 px-4 py-2 rounded-md text-sm font-medium',
                bot.is_active
                  ? 'bg-[var(--color-bear)]/15 text-[var(--color-bear)]'
                  : 'bg-[var(--color-bull)]/15 text-[var(--color-bull)]'
              )}
            >
              <Power className="w-4 h-4" />
              {bot.is_active ? 'Deactivate' : 'Activate'}
            </button>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <Field
              label="Allocated capital (USD)"
              value={bot.allocated_capital_usd}
              onSave={(v) => updateField({ allocated_capital_usd: Number(v) })}
            />
            <Field
              label="Risk per trade (%)"
              value={bot.risk_per_trade_pct}
              onSave={(v) => updateField({ risk_per_trade_pct: Number(v) })}
            />
            <Field
              label="Max open positions"
              value={bot.max_open_positions}
              onSave={(v) => updateField({ max_open_positions: Number(v) })}
            />
            <Field
              label="Daily loss limit (%)"
              value={bot.daily_loss_limit_pct}
              onSave={(v) => updateField({ daily_loss_limit_pct: Number(v) })}
            />
            <Field
              label="Min confidence"
              value={bot.min_confidence}
              onSave={(v) => updateField({ min_confidence: Number(v) })}
            />
            <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-4">
              <label className="text-xs text-[var(--color-text-dim)]">Paper trading</label>
              <div className="mt-2 flex items-center gap-3">
                <button
                  onClick={() => updateField({ paper_trading: !bot.paper_trading })}
                  className={clsx(
                    'px-3 py-1.5 rounded text-sm',
                    bot.paper_trading
                      ? 'bg-[var(--color-amber)]/20 text-[var(--color-amber)]'
                      : 'bg-white/5 text-[var(--color-text-mid)]'
                  )}
                >
                  {bot.paper_trading ? 'ON (safe)' : 'OFF (live)'}
                </button>
              </div>
              <p className="mt-2 text-[11px] text-[var(--color-text-dim)]">
                Keep paper ON until you have connected keys and verified behavior.
              </p>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 text-left">
            <Feature
              icon={<Wallet className="w-4 h-4" />}
              title="Non-custodial"
              desc="You fund your own exchange accounts. We only store encrypted trade keys."
            />
            <Feature
              icon={<Shield className="w-4 h-4" />}
              title="Risk controls"
              desc="Per-trade size, daily loss limit, max positions, and min confidence."
            />
            <Feature
              icon={<Power className="w-4 h-4" />}
              title="One-click activate"
              desc="Turn the bot on/off anytime. Live execution needs connected keys."
            />
          </div>
        </>
      ) : null}
    </div>
  )
}

function Field({
  label,
  value,
  onSave,
}: {
  label: string
  value: number
  onSave: (v: string) => void
}) {
  const [local, setLocal] = useState(String(value))
  useEffect(() => setLocal(String(value)), [value])
  return (
    <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-4">
      <label className="text-xs text-[var(--color-text-dim)]">{label}</label>
      <div className="mt-2 flex gap-2">
        <input
          value={local}
          onChange={(e) => setLocal(e.target.value)}
          className="flex-1 px-3 py-1.5 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm font-[var(--font-mono)]"
        />
        <button
          onClick={() => onSave(local)}
          className="px-3 py-1.5 rounded-md bg-white/10 text-sm hover:bg-white/15"
        >
          Save
        </button>
      </div>
    </div>
  )
}

function Feature({
  icon,
  title,
  desc,
}: {
  icon: React.ReactNode
  title: string
  desc: string
}) {
  return (
    <div className="rounded-md bg-white/[0.03] p-4">
      <div className="flex items-center gap-2 text-[var(--color-text)] mb-1.5">
        {icon}
        <span className="font-medium text-sm">{title}</span>
      </div>
      <p className="text-xs text-[var(--color-text-mid)] leading-relaxed">{desc}</p>
    </div>
  )
}
