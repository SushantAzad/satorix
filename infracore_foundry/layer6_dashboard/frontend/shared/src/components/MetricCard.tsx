import React from 'react'
import type { MetricData } from '../api/types'

const TREND_ICONS = { up: '↑', down: '↓', stable: '→' }
const VALUE_COLORS = { red: 'text-red-600', amber: 'text-amber-600', green: 'text-green-600', gray: 'text-gray-900' }

export function MetricCard({ metric }: { metric: MetricData }) {
  const trendColor = metric.trend === 'up' ? (metric.color === 'red' ? 'text-red-500' : 'text-green-500') :
                     metric.trend === 'down' ? (metric.color === 'red' ? 'text-green-500' : 'text-red-500') : 'text-gray-400'
  return (
    <div className="bg-white border border-gray-200 rounded-xl shadow-sm p-4 min-w-[140px] flex flex-col gap-1">
      <p className="text-xs font-medium text-gray-500 uppercase tracking-wider">{metric.label}</p>
      <div className="flex items-baseline gap-1.5">
        <span className={`text-2xl font-semibold tabular-nums ${VALUE_COLORS[metric.color] ?? 'text-gray-900'}`}>
          {metric.value !== null && metric.value !== undefined ? String(metric.value) : '—'}
        </span>
        {metric.unit && <span className="text-sm text-gray-400">{metric.unit}</span>}
        {metric.trend && <span className={`text-sm font-medium ${trendColor}`}>{TREND_ICONS[metric.trend]}</span>}
      </div>
      {metric.source && <p className="text-xs text-gray-400 truncate">{metric.source}</p>}
    </div>
  )
}
