import { useEffect, useState } from 'react'
import { api, type ExchangeKey } from '../api/client'
import { useAuth } from '../stores/auth'
import { Trash2 } from 'lucide-react'

const EXCHANGES = ['bybit', 'mexc', 'binance'] as const

export function Settings() {
  const { token } = useAuth()
  const [keys, setKeys] = useState<ExchangeKey[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(false)
  const [form, setForm] = useState({
    exchange: 'bybit',
    api_key: '',
    api_secret: '',
    passphrase: '',
    label: '',
  })

  const load = async () => {
    if (!token) return
    setLoading(true)
    try {
      setKeys(await api.listKeys())
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    load()
  }, [token])

  const add = async (e: React.FormEvent) => {
    e.preventDefault()
    setError(null)
    setLoading(true)
    try {
      await api.addKey({
        exchange: form.exchange,
        api_key: form.api_key,
        api_secret: form.api_secret,
        passphrase: form.passphrase || undefined,
        label: form.label || form.exchange,
      })
      setForm({ exchange: 'bybit', api_key: '', api_secret: '', passphrase: '', label: '' })
      await load()
    } catch (err: any) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  const remove = async (id: number) => {
    if (!confirm('Remove this API key?')) return
    setLoading(true)
    try {
      await api.deleteKey(id)
      await load()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  if (!token) {
    return (
      <div className="p-6 max-w-[800px] mx-auto">
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-text-mid)] mt-2">
          Sign in from the Bot page first to manage exchange API keys.
        </p>
      </div>
    )
  }

  return (
    <div className="p-6 max-w-[800px] mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
          Connect exchange accounts (encrypted at rest). Prefer trade-only keys with withdrawals
          disabled.
        </p>
      </div>

      {error && (
        <div className="rounded-md border border-[var(--color-bear)]/40 bg-[var(--color-bear)]/10 px-4 py-3 text-sm text-[var(--color-bear)]">
          {error}
        </div>
      )}

      <section className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] divide-y divide-[var(--color-panel-border)]">
        <div className="px-5 py-4">
          <h2 className="text-sm font-medium">Connected exchanges</h2>
          <div className="mt-4 space-y-2">
            {loading && keys.length === 0 && (
              <div className="text-sm text-[var(--color-text-dim)]">Loading…</div>
            )}
            {!loading && keys.length === 0 && (
              <div className="text-sm text-[var(--color-text-dim)]">No keys connected yet.</div>
            )}
            {keys.map((k) => (
              <div
                key={k.id}
                className="flex items-center justify-between px-3 py-2.5 rounded-md bg-white/[0.03]"
              >
                <div>
                  <div className="text-sm capitalize">
                    {k.exchange} {k.label && k.label !== k.exchange ? `· ${k.label}` : ''}
                  </div>
                  <div className="text-xs text-[var(--color-text-dim)] font-[var(--font-mono)]">
                    {k.api_key_hint}
                  </div>
                </div>
                <button
                  onClick={() => remove(k.id)}
                  className="p-2 text-[var(--color-text-dim)] hover:text-[var(--color-bear)]"
                  title="Remove"
                >
                  <Trash2 className="w-4 h-4" />
                </button>
              </div>
            ))}
          </div>
        </div>

        <form onSubmit={add} className="px-5 py-4 space-y-3">
          <h2 className="text-sm font-medium">Add API key</h2>
          <div className="grid grid-cols-2 gap-3">
            <select
              value={form.exchange}
              onChange={(e) => setForm({ ...form, exchange: e.target.value })}
              className="px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm"
            >
              {EXCHANGES.map((ex) => (
                <option key={ex} value={ex}>
                  {ex}
                </option>
              ))}
            </select>
            <input
              value={form.label}
              onChange={(e) => setForm({ ...form, label: e.target.value })}
              placeholder="Label (optional)"
              className="px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm"
            />
          </div>
          <input
            required
            value={form.api_key}
            onChange={(e) => setForm({ ...form, api_key: e.target.value })}
            placeholder="API Key"
            className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm font-[var(--font-mono)]"
          />
          <input
            required
            type="password"
            value={form.api_secret}
            onChange={(e) => setForm({ ...form, api_secret: e.target.value })}
            placeholder="API Secret"
            className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm font-[var(--font-mono)]"
          />
          <input
            value={form.passphrase}
            onChange={(e) => setForm({ ...form, passphrase: e.target.value })}
            placeholder="Passphrase (if required)"
            className="w-full px-3 py-2 rounded-md bg-white/5 border border-[var(--color-panel-border)] text-sm font-[var(--font-mono)]"
          />
          <button
            type="submit"
            disabled={loading}
            className="px-4 py-2 rounded-md bg-[var(--color-accent)]/20 text-[var(--color-accent)] text-sm font-medium hover:bg-[var(--color-accent)]/30 disabled:opacity-50"
          >
            Save key
          </button>
        </form>
      </section>
    </div>
  )
}
