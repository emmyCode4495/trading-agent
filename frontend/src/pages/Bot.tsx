import { Bot as BotIcon, Power, Shield, Wallet } from 'lucide-react'

export function Bot() {
  return (
    <div className="p-6 max-w-[900px] mx-auto space-y-6">
      <div>
        <h1 className="text-xl font-semibold tracking-tight">Bot Control</h1>
        <p className="text-sm text-[var(--color-text-mid)] mt-0.5">
          Activate the live trading agent for your connected accounts
        </p>
      </div>

      {/* Coming soon card */}
      <div className="rounded-lg border border-[var(--color-panel-border)] bg-[var(--color-panel)] p-8 text-center space-y-4">
        <div className="mx-auto w-12 h-12 rounded-full bg-[var(--color-accent)]/15 flex items-center justify-center">
          <BotIcon className="w-6 h-6 text-[var(--color-accent)]" />
        </div>
        <h2 className="text-lg font-medium">Multi-user bot activation coming next</h2>
        <p className="text-sm text-[var(--color-text-mid)] max-w-md mx-auto">
          You will connect your Bybit / MEXC / Binance API keys, set capital allocation and risk
          limits, then turn the bot on. The shared intelligence layer will execute high-confidence
          opportunities on your accounts.
        </p>
        <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 pt-4 text-left">
          <Feature
            icon={<Wallet className="w-4 h-4" />}
            title="Non-custodial"
            desc="You fund your own exchange accounts. We only use trade-permission API keys."
          />
          <Feature
            icon={<Shield className="w-4 h-4" />}
            title="Risk controls"
            desc="Per-trade size, daily loss limit, max open positions, and kill switch."
          />
          <Feature
            icon={<Power className="w-4 h-4" />}
            title="One-click activate"
            desc="Turn the bot on/off anytime from web or the Expo mobile app."
          />
        </div>
      </div>

      <div className="rounded-lg border border-dashed border-[var(--color-panel-border)] p-5 text-sm text-[var(--color-text-dim)]">
        <strong className="text-[var(--color-text-mid)]">Backend status:</strong> Intelligence
        layer (scanner + agents + decision engine) is already live. Next phase adds user accounts,
        encrypted key storage, and multi-exchange execution adapters.
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
