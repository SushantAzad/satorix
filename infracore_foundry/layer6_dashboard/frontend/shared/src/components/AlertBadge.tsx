import React from 'react'
import type { AlertSeverity } from '../api/types'

const COLORS: Record<AlertSeverity, string> = {
  CRITICAL: 'bg-red-600 text-white',
  HIGH:     'bg-red-100 text-red-700 border border-red-300',
  MEDIUM:   'bg-amber-100 text-amber-700 border border-amber-300',
  LOW:      'bg-gray-100 text-gray-600 border border-gray-300',
}

export function AlertBadge({ severity }: { severity: AlertSeverity }) {
  return <span className={`inline-block px-2 py-0.5 rounded text-xs font-semibold uppercase tracking-wide ${COLORS[severity]}`}>{severity}</span>
}
