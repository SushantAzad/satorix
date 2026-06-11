import React from 'react'
import type { RiskBand } from '../api/types'

const CONFIG: Record<RiskBand, { label: string; dot: string; text: string; bg: string }> = {
  HIGH:   { label: 'HIGH RISK',   dot: 'bg-red-500',    text: 'text-red-700',   bg: 'bg-red-50 border-red-200' },
  MEDIUM: { label: 'MEDIUM RISK', dot: 'bg-amber-500',  text: 'text-amber-700', bg: 'bg-amber-50 border-amber-200' },
  LOW:    { label: 'LOW RISK',    dot: 'bg-green-500',  text: 'text-green-700', bg: 'bg-green-50 border-green-200' },
  NONE:   { label: 'UNSCORED',    dot: 'bg-gray-400',   text: 'text-gray-600',  bg: 'bg-gray-50 border-gray-200' },
}

interface Props { score?: number; band: RiskBand; size?: 'sm' | 'md' | 'lg'; showScore?: boolean }

export function RiskBadge({ score, band, size = 'md', showScore = true }: Props) {
  const c = CONFIG[band] || CONFIG.NONE
  if (size === 'sm') return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-xs font-medium border ${c.bg} ${c.text}`}>
      <span className={`w-1.5 h-1.5 rounded-full ${c.dot}`} />{c.label}
    </span>
  )
  if (size === 'lg') return (
    <div className="flex flex-col items-center">
      <span className={`text-5xl font-bold tabular-nums ${c.text}`}>{score ?? '—'}</span>
      <span className={`mt-1 px-3 py-1 rounded-full text-sm font-semibold border ${c.bg} ${c.text}`}>{c.label}</span>
    </div>
  )
  return (
    <span className={`inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-sm font-semibold border ${c.bg} ${c.text}`}>
      <span className={`w-2 h-2 rounded-full ${c.dot}`} />
      {showScore && score !== undefined ? score : ''} {c.label}
    </span>
  )
}
