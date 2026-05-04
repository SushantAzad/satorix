import React, { useState, useRef, useEffect, useCallback } from 'react'
import { useNavigate, Link } from 'react-router-dom'
import { Bell, Search, LogOut } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAuthStore } from '@shared/store/authStore'
import { useAlertStore } from '@shared/store/alertStore'
import { entitiesApi } from '@shared/api/entities'
import { RiskBadge } from '@shared/components/RiskBadge'
import type { SearchResult } from '@shared/api/types'

const TYPE_ICONS: Record<string, string> = { company: '🏢', director: '👤', project: '🏗️', regulatory_action: '⚠️', legal_case: '⚖️', address: '📍', default: '📄' }
const TYPE_COLORS: Record<string, string> = { company: 'text-blue-600', director: 'text-purple-600', project: 'text-green-600', regulatory_action: 'text-red-600' }

export function Navigation() {
  const nav = useNavigate()
  const { user, clearAuth } = useAuthStore()
  const unreadCount = useAlertStore(s => s.unacknowledgedCount)
  const [q, setQ] = useState('')
  const [open, setOpen] = useState(false)
  const [userMenu, setUserMenu] = useState(false)
  const inputRef = useRef<HTMLInputElement>(null)
  const dropRef = useRef<HTMLDivElement>(null)

  const { data: results } = useQuery({
    queryKey: ['nav-search', q],
    queryFn: () => entitiesApi.search(q, 8),
    enabled: q.length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => {
    const handler = (e: MouseEvent) => {
      if (dropRef.current && !dropRef.current.contains(e.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', handler)
    return () => document.removeEventListener('mousedown', handler)
  }, [])

  const handleSelect = (r: SearchResult) => {
    setQ('')
    setOpen(false)
    nav(`/entity/${r.entityType}/${r.entityId}`)
  }

  const initials = user?.name?.split(' ').map(n => n[0]).join('').toUpperCase().slice(0, 2) || '?'

  return (
    <nav className="fixed top-0 inset-x-0 h-14 bg-white border-b border-gray-200 z-40 flex items-center px-6 gap-4">
      <Link to="/" className="flex items-center gap-2 flex-shrink-0 mr-4">
        <span className="text-lg font-bold text-gray-900 tracking-tight">Satorix</span>
        <span className="text-xs text-gray-400 font-medium">Intelligence</span>
      </Link>

      {/* Search */}
      <div className="relative flex-1 max-w-xl" ref={dropRef}>
        <div className="relative">
          <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-gray-400" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => { setQ(e.target.value); setOpen(e.target.value.length >= 2) }}
            onFocus={() => q.length >= 2 && setOpen(true)}
            placeholder="Search company, director, CIN, DIN..."
            className="w-full pl-9 pr-4 h-9 border border-gray-200 rounded-xl text-sm bg-gray-50 focus:bg-white focus:border-gray-400 focus:outline-none transition-all"
          />
        </div>
        {open && results && results.length > 0 && (
          <div className="absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg z-50 overflow-hidden">
            {results.map((r) => (
              <button key={r.entityId} onClick={() => handleSelect(r)}
                className="w-full flex items-center gap-3 px-4 py-2.5 hover:bg-gray-50 transition-colors text-left">
                <span className="text-lg flex-shrink-0">{TYPE_ICONS[r.entityType] ?? TYPE_ICONS.default}</span>
                <div className="flex-1 min-w-0">
                  <p className={`text-sm font-medium truncate ${TYPE_COLORS[r.entityType] ?? 'text-gray-900'}`}>{r.name}</p>
                  <p className="text-xs text-gray-400 truncate">{r.description}</p>
                </div>
                <RiskBadge band={r.riskBand} score={r.riskScore} size="sm" />
              </button>
            ))}
          </div>
        )}
        {open && q.length >= 2 && results?.length === 0 && (
          <div className="absolute top-full mt-1 w-full bg-white border border-gray-200 rounded-xl shadow-lg z-50 px-4 py-3 text-sm text-gray-400">No results found for "{q}"</div>
        )}
      </div>

      <div className="flex-1" />

      {/* Alerts */}
      <Link to="/alerts" className="relative p-2 rounded-lg hover:bg-gray-100 transition-colors">
        <Bell className="h-5 w-5 text-gray-600" />
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 min-w-[16px] h-4 bg-red-500 rounded-full text-white text-[10px] font-bold flex items-center justify-center px-1">
            {unreadCount > 99 ? '99+' : unreadCount}
          </span>
        )}
      </Link>

      {/* User menu */}
      <div className="relative">
        <button onClick={() => setUserMenu(!userMenu)}
          className="w-8 h-8 rounded-full bg-gray-900 text-white text-xs font-semibold flex items-center justify-center hover:bg-gray-700 transition-colors">
          {initials}
        </button>
        {userMenu && (
          <div className="absolute right-0 top-full mt-2 w-48 bg-white border border-gray-200 rounded-xl shadow-lg z-50 py-1">
            <div className="px-3 py-2 border-b border-gray-100">
              <p className="text-sm font-medium text-gray-900 truncate">{user?.name}</p>
              <p className="text-xs text-gray-400 truncate">{user?.email}</p>
            </div>
            <button onClick={() => { clearAuth(); window.location.href = '/login' }}
              className="w-full flex items-center gap-2 px-3 py-2 text-sm text-red-600 hover:bg-red-50 transition-colors">
              <LogOut className="h-4 w-4" /><span>Sign out</span>
            </button>
          </div>
        )}
      </div>
    </nav>
  )
}
