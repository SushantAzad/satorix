import { Outlet, NavLink } from 'react-router-dom'
import {
  Activity,
  Zap,
  Database,
  ArrowRight,
  GitBranch,
  BarChart2,
  Bell,
} from 'lucide-react'
import clsx from 'clsx'

const navItems = [
  { to: '/', icon: Activity, label: 'System Health', end: true },
  { to: '/kafka', icon: Zap, label: 'Kafka Monitor' },
  { to: '/sources', icon: Database, label: 'Source Health' },
  { to: '/ingestion', icon: ArrowRight, label: 'Ingestion Queue' },
  { to: '/imports', icon: Database, label: 'CSV Import' },
  { to: '/ontology', icon: GitBranch, label: 'Ontology Health' },
  { to: '/models', icon: BarChart2, label: 'Model Performance' },
  { to: '/alerts-analytics', icon: Bell, label: 'Alert Analytics' },
]

export default function Layout() {
  return (
    <div className="flex h-screen overflow-hidden bg-gray-50">
      {/* Sidebar */}
      <aside className="w-60 flex-shrink-0 bg-white border-r border-gray-200 flex flex-col">
        <div className="px-5 py-5 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-widest">Satorix Ops</p>
          <p className="text-sm text-gray-500 mt-0.5">Operational Dashboard</p>
        </div>
        <nav className="flex-1 px-3 py-4 space-y-0.5 overflow-y-auto scrollbar-thin">
          {navItems.map(({ to, icon: Icon, label, end }) => (
            <NavLink
              key={to}
              to={to}
              end={end}
              className={({ isActive }) =>
                clsx(
                  'flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition-colors',
                  isActive
                    ? 'bg-gray-100 text-gray-900'
                    : 'text-gray-500 hover:bg-gray-50 hover:text-gray-700',
                )
              }
            >
              <Icon size={16} />
              {label}
            </NavLink>
          ))}
        </nav>
        <div className="px-5 py-4 border-t border-gray-100">
          <p className="text-xs text-gray-400">Port 3001 · Internal Tool</p>
        </div>
      </aside>

      {/* Main content */}
      <main className="flex-1 overflow-y-auto scrollbar-thin">
        <Outlet />
      </main>
    </div>
  )
}
