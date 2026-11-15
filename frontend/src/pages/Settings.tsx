export function Settings() {
  return (
    <div className="p-6 max-w-[800px] mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
          Account, exchanges, and risk preferences
        </p>
      </div>

      <section className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] divide-y divide-[var(--color-panel-border)]">
        <div className="px-5 py-4">
          <h2 className="text-sm font-medium">Connected exchanges</h2>
          <p className="text-xs text-[var(--color-text-dim)] mt-1">
            API keys will be stored encrypted. Prefer keys with trade permission only (no
            withdrawals).
          </p>
          <div className="mt-4 space-y-2">
            {['Bybit', 'MEXC', 'Binance'].map((ex) => (
              <div
                key={ex}
                className="flex items-center justify-between px-3 py-2.5 rounded-md bg-white/[0.03]"
              >
                <span className="text-sm">{ex}</span>
                <span className="text-xs text-[var(--color-text-dim)]">Not connected</span>
              </div>
            ))}
          </div>
        </div>

        <div className="px-5 py-4">
          <h2 className="text-sm font-medium">Risk defaults</h2>
          <p className="text-xs text-[var(--color-text-dim)] mt-1 mb-4">
            Applied when you activate the bot. Editable later per session.
          </p>
          <div className="grid grid-cols-2 gap-4 text-sm">
            <div>
              <label className="text-xs text-[var(--color-text-dim)]">Max capital allocation</label>
              <div className="mt-1 px-3 py-2 rounded-md bg-white/[0.03] text-[var(--color-text-mid)]">
                Coming soon
              </div>
            </div>
            <div>
              <label className="text-xs text-[var(--color-text-dim)]">Risk per trade</label>
              <div className="mt-1 px-3 py-2 rounded-md bg-white/[0.03] text-[var(--color-text-mid)]">
                Coming soon
              </div>
            </div>
          </div>
        </div>
      </section>
    </div>
  )
}
