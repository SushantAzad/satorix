import React from 'react'
import { useNavigate } from 'react-router-dom'
import { RiskBadge } from './RiskBadge'
import type { SearchResult } from '../api/types'

const TYPE_ICONS: Record<string, string> = {
  company: '🏢', director: '👤', project: '🏗️', regulatory_action: '⚠️', legal_case: '⚖️', address: '📍', insolvency_proceeding: '🔴'
}

export function EntityCard({ entity, compact = false }: { entity: SearchResult; compact?: boolean }) {
  const nav = useNavigate()
  return (
    <div onClick={() => nav(`/entity/${entity.entityType}/${entity.entityId}`)}
      className={`bg-white border border-gray-200 rounded-xl shadow-sm p-4 cursor-pointer hover:border-gray-400 hover:shadow transition-all duration-150 ${compact ? 'p-3' : ''}`}>
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-2 min-w-0">
          <span className="text-xl flex-shrink-0">{TYPE_ICONS[entity.entityType] ?? '📄'}</span>
          <div className="min-w-0">
            <p className="font-medium text-gray-900 truncate">{entity.name}</p>
            {!compact && <p className="text-xs text-gray-500 truncate mt-0.5">{entity.description}</p>}
          </div>
        </div>
        <RiskBadge band={entity.riskBand} score={entity.riskScore} size="sm" />
      </div>
    </div>
  )
}
