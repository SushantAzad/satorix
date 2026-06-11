import React, { useState, useEffect } from 'react'
import { useNavigate } from 'react-router-dom'
import { Search as SearchIcon } from 'lucide-react'
import { useQuery } from '@tanstack/react-query'
import { useAlertStore } from '@shared/store/alertStore'
import { useEntityStore } from '@shared/store/entityStore'
import { entitiesApi } from '@shared/api/entities'
import { alertsApi } from '@shared/api/alerts'
import { RiskBadge } from '@shared/components/RiskBadge'
import { AlertBadge } from '@shared/components/AlertBadge'
import type { SearchResult } from '@shared/api/types'

const TYPE_ICONS: Record<string, string> = { company: '🏢', director: '👤', project: '🏗️', regulatory_action: '⚠️', legal_case: '⚖️', default: '📄' }

export function Search() {
  const nav = useNavigate()
  const { alerts, setAlerts } = useAlertStore()
  const { recentViews } = useEntityStore()
  const [q, setQ] = useState('')
  const [showDropdown, setShowDropdown] = useState(false)

  useQuery({ queryKey: ['init-alerts'], queryFn: async () => { const r = await alertsApi.list({ limit: 20 }); setAlerts(r.alerts); return r }, staleTime: 60_000 })

  const { data: results, isLoading } = useQuery({
    queryKey: ['search', q],
    queryFn: () => entitiesApi.search(q, 12),
    enabled: q.length >= 2,
    staleTime: 10_000,
  })

  useEffect(() => { setShowDropdown(q.length >= 2 && !!(results?.length)) }, [q, results])

  const handleSelect = (r: SearchResult) => { setQ(''); setShowDropdown(false); nav(`/entity/${r.entityType}/${r.entityId}`) }

  const criticalAlerts = alerts.filter(a => !a.isAcknowledged && (a.severity === 'CRITICAL' || a.severity === 'HIGH')).slice(0, 8)

  return (
    <div className="flex flex-col items-center min-h-[calc(100vh-56px)] bg-white px-4 py-16">
      <div className="w-full max-w-2xl">
        {/* Header */}
        <div className="text-center mb-10">
          <p className="text-sm font-medium text-gray-400 uppercase tracking-widest mb-3">Satorix Intelligence</p>
          <h1 className="text-4xl font-bold text-gray-900 tracking-tight mb-3">What do you need to know?</h1>
          <p className="text-gray-400 text-base">Search any company, director, CIN, DIN, or project across India's corporate landscape</p>
        </div>

        {/* Search bar */}
        <div className="relative mb-3">
          <SearchIcon className="absolute left-4 top-1/2 -translate-y-1/2 h-5 w-5 text-gray-400" />
          <input
            value={q}
            onChange={e => setQ(e.target.value)}
            onFocus={() => q.length >= 2 && setShowDropdown(true)}
            onBlur={() => setTimeout(() => setShowDropdown(false), 200)}
            placeholder='Try "Infracore" or "L45201MH2003PLC142301"'
            autoFocus
            className="w-full h-14 pl-12 pr-4 border-2 border-gray-200 rounded-2xl text-base bg-white focus:border-gray-900 focus:outline-none transition-all shadow-sm"
          />
          {isLoading && q.length >= 2 && (
            <div className="absolute right-4 top-1/2 -translate-y-1/2">
              <div className="h-4 w-4 border-2 border-gray-300 border-t-gray-900 rounded-full animate-spin" />
            </div>
          )}
          {/* Typeahead dropdown */}
          {showDropdown && results && results.length > 0 && (
            <div className="absolute top-full mt-2 left-0 right-0 bg-white border border-gray-200 rounded-2xl shadow-xl z-50 overflow-hidden">
              {results.map((r) => (
                <button key={r.entityId} onMouseDown={() => handleSelect(r)}
                  className="w-full flex items-center gap-3 px-4 py-3 hover:bg-gray-50 transition-colors border-b border-gray-50 last:border-b-0 text-left">
                  <span className="text-xl">{TYPE_ICONS[r.entityType] ?? TYPE_ICONS.default}</span>
                  <div className="flex-1 min-w-0">
                    <p className="font-semibold text-gray-900 truncate">{r.name}</p>
                    <p className="text-xs text-gray-400 truncate">{r.description || r.entityType}</p>
                  </div>
                  <RiskBadge band={r.riskBand} score={r.riskScore} size="sm" />
                </button>
              ))}
            </div>
          )}
        </div>

        <p className="text-center text-xs text-gray-400 mb-12">
          {results?.length ? `${results.length} results` : 'Search across MCA21, SEBI, IBBI, and connected data sources'}
        </p>

        {/* Recent views */}
        {recentViews.length > 0 && (
          <div className="mb-10">
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Recently Viewed</p>
            <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
              {recentViews.slice(0, 3).map(e => (
                <div key={`${e.entityType}-${e.entityId}`}
                  onClick={() => nav(`/entity/${e.entityType}/${e.entityId}`)}
                  className="p-4 bg-white border border-gray-200 rounded-xl shadow-sm cursor-pointer hover:border-gray-400 hover:shadow transition-all">
                  <p className="font-medium text-gray-900 truncate text-sm">{e.name}</p>
                  <div className="flex items-center justify-between mt-2">
                    <span className="text-xs text-gray-400 capitalize">{e.entityType}</span>
                    <RiskBadge band={e.riskScore >= 70 ? 'HIGH' : e.riskScore >= 40 ? 'MEDIUM' : 'LOW'} score={e.riskScore} size="sm" />
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Live alerts ticker */}
        {criticalAlerts.length > 0 && (
          <div>
            <div className="flex items-center justify-between mb-3">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Live Alerts</p>
              <button onClick={() => nav('/alerts')} className="text-xs text-gray-500 hover:text-gray-900 transition-colors">View all →</button>
            </div>
            <div className="space-y-2">
              {criticalAlerts.slice(0, 4).map(a => (
                <div key={a.alertId} onClick={() => nav('/alerts')}
                  className="flex items-center gap-3 p-3 bg-white border border-gray-200 rounded-xl cursor-pointer hover:border-gray-300 hover:shadow-sm transition-all">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${a.severity === 'CRITICAL' ? 'bg-red-500 animate-pulse' : 'bg-amber-500'}`} />
                  <div className="flex-1 min-w-0">
                    <p className="text-sm font-medium text-gray-900 truncate">{a.title}</p>
                    <p className="text-xs text-gray-400 truncate">{a.affectedEntityName || a.affectedEntityId}</p>
                  </div>
                  <AlertBadge severity={a.severity} />
                </div>
              ))}
            </div>
          </div>
        )}
      </div>
    </div>
  )
}
