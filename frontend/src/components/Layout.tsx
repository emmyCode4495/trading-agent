import { NavLink, Outlet } from 'react-router-dom'
import {
  LayoutDashboard,
  CandlestickChart,
  Activity,
  Settings,
  Bot,
  Radio,
} from 'lucide-react'
import clsx from 'clsx'

const nav = [
  { to: '/', label: 'Dashboard', icon: LayoutDashboard },
  { to: '/markets', label: 'Markets', icon: CandlestickChart },
  { to: '/positions', label: 'Positions', icon: Activity },
  { to: '/bot', label: 'Bot', icon: Bot },
  { to: '/settings', label: 'Settings', icon: Settings },
]

export function Layout() {
  return (
    <div className="flex h-full min-h-screen bg-[var(--color-bg)]">
      {/* Sidebar */}
      <aside className="w-56 shrink-0 border-r border-[var(--color-panel-border)] bg-[var(--color-panel)] flex flex-col">
        <div className="px-5 py-5 border-b border-[var(--color-panel-border)]">
          <div className="flex items-center gap-2">
            <Radio className="w-5 h-5 text-[var(--color-accent)]" />
            <span className="font-[var(--font-display)] text-sm tracking-wide font-semibold">
              AETHER
            </span>
          </div>
          <p className="text-[11px] text-[var(--color-text-dim)] mt-1">
            Multi-exchange live bot
          </p>
        </div>

        <nav className="flex-1 py-4 px-3 space-y-0.5">
          {nav.map(({ to, label, icon: Icon }) => (
            <NavLink
              key={to}
              to={to}
              end={to === '/'}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-md text-sm transition-colors',
                  isActive
                    ? 'bg-white/5 text-white'
                    : 'text-[var(--color-text-mid)] hover:text-white hover:bg-white/[0.03]'
                )
              }
            >
              <Icon className="w-4 h-4 shrink-0" />
              {label}
            </NavLink>
          ))}
        </nav>

        <div className="px-4 py-4 border-t border-[var(--color-panel-border)] text-[11px] text-[var(--color-text-dim)]">
          Backend · FastAPI · Multi-CEX
        </div>
      </aside>

      {/* Main */}
      <main className="flex-1 overflow-auto">
        <Outlet />
      </main>
    </div>
  )
}
