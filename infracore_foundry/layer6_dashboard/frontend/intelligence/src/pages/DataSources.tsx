import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import {
  Plus, RefreshCw, Trash2, CheckCircle2, AlertCircle,
  Clock, Database, Loader2
} from 'lucide-react'
import { sourcesApi } from '../api/sources'
import type { DataSource } from '../api/sources'
import { CONNECTOR_MAP } from '../lib/connectorMetadata'
import { AddSourceWizard } from '../components/connectors/AddSourceWizard'

// ── Status helpers ────────────────────────────────────────────────────────────

function StatusBadge({ status }: { status?: string }) {
  const s = (status ?? 'unknown').toLowerCase()
  if (s === 'active' || s === 'connected')
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-green-700 bg-green-50 px-2 py-0.5 rounded-full"><CheckCircle2 className="h-3 w-3" />Active</span>
  if (s === 'error' || s === 'failed')
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-red-700 bg-red-50 px-2 py-0.5 rounded-full"><AlertCircle className="h-3 w-3" />Error</span>
  if (s === 'syncing')
    return <span className="inline-flex items-center gap-1 text-xs font-medium text-blue-700 bg-blue-50 px-2 py-0.5 rounded-full"><Loader2 className="h-3 w-3 animate-spin" />Syncing</span>
  return <span className="inline-flex items-center gap-1 text-xs font-medium text-gray-500 bg-gray-100 px-2 py-0.5 rounded-full"><Clock className="h-3 w-3" />Pending</span>
}

function formatLastSync(ts?: string | null): string {
  if (!ts) return 'Never'
  const d = new Date(ts)
  const diff = Date.now() - d.getTime()
  const mins = Math.floor(diff / 60_000)
  if (mins < 1) return 'Just now'
  if (mins < 60) return `${mins}m ago`
  const hrs = Math.floor(mins / 60)
  if (hrs < 24) return `${hrs}h ago`
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' })
}

// ── Source card ───────────────────────────────────────────────────────────────

function SourceCard({ source, onSync, onDelete, syncing }: {
  source: DataSource
  onSync: () => void
  onDelete: () => void
  syncing: boolean
}) {
  const meta = CONNECTOR_MAP[source.source_type]

  return (
    <div className="group rounded-xl border border-gray-200 bg-white p-5 hover:border-gray-300 hover:shadow-sm transition-all">
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <span className="text-2xl flex-shrink-0">{meta?.icon ?? '🔌'}</span>
          <div className="min-w-0">
            <p className="text-sm font-semibold text-gray-900 truncate">{source.source_name}</p>
            <p className="text-xs text-gray-400">{meta?.displayName ?? source.source_type}</p>
          </div>
        </div>
        <StatusBadge status={source.status} />
      </div>

      <div className="mt-4 flex items-center justify-between text-xs text-gray-400">
        <div className="flex items-center gap-1">
          <Database className="h-3 w-3" />
          {source.record_count != null ? `${source.record_count.toLocaleString()} records` : 'No sync yet'}
        </div>
        <div className="flex items-center gap-1">
          <Clock className="h-3 w-3" />
          {formatLastSync(source.last_sync)}
        </div>
      </div>

      <div className="mt-4 flex items-center gap-2 opacity-0 group-hover:opacity-100 transition-opacity">
        <button
          onClick={onSync}
          disabled={syncing}
          className="flex items-center gap-1.5 text-xs text-gray-600 hover:text-gray-900 transition-colors disabled:opacity-50"
          title="Sync now"
        >
          <RefreshCw className={`h-3.5 w-3.5 ${syncing ? 'animate-spin' : ''}`} />
          Sync
        </button>
        <span className="text-gray-200">|</span>
        <button
          onClick={onDelete}
          className="flex items-center gap-1.5 text-xs text-red-500 hover:text-red-700 transition-colors"
          title="Remove source"
        >
          <Trash2 className="h-3.5 w-3.5" />
          Remove
        </button>
      </div>
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function DataSources() {
  const qc = useQueryClient()
  const [showWizard, setShowWizard] = useState(false)
  const [syncingIds, setSyncingIds] = useState<Set<string>>(new Set())

  const { data: sources = [], isLoading, isError } = useQuery({
    queryKey: ['sources'],
    queryFn: sourcesApi.list,
    refetchInterval: 30_000,
  })

  const deleteMut = useMutation({
    mutationFn: sourcesApi.delete,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['sources'] }),
  })

  const handleSync = async (id: string) => {
    setSyncingIds(prev => new Set(prev).add(id))
    try {
      await sourcesApi.sync(id)
      await qc.invalidateQueries({ queryKey: ['sources'] })
    } finally {
      setSyncingIds(prev => { const s = new Set(prev); s.delete(id); return s })
    }
  }

  // Group sources by category
  const grouped = sources.reduce<Record<string, DataSource[]>>((acc, s) => {
    const cat = CONNECTOR_MAP[s.source_type]?.category ?? 'Other'
    if (!acc[cat]) acc[cat] = []
    acc[cat].push(s)
    return acc
  }, {})

  return (
    <div className="max-w-6xl mx-auto px-6 py-8 space-y-8">

      {/* Header */}
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-xl font-bold text-gray-900">Data Sources</h1>
          <p className="text-sm text-gray-500 mt-0.5">
            {sources.length} source{sources.length !== 1 ? 's' : ''} connected
          </p>
        </div>
        <button
          onClick={() => setShowWizard(true)}
          className="flex items-center gap-2 h-9 px-4 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 transition-colors"
        >
          <Plus className="h-4 w-4" />
          Add Source
        </button>
      </div>

      {/* Loading */}
      {isLoading && (
        <div className="flex items-center justify-center py-20 text-gray-400">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          <span className="text-sm">Loading sources...</span>
        </div>
      )}

      {/* Error */}
      {isError && (
        <div className="rounded-xl border border-red-200 bg-red-50 p-6 text-center">
          <AlertCircle className="h-8 w-8 text-red-400 mx-auto mb-2" />
          <p className="text-sm font-medium text-red-700">Could not load data sources</p>
          <p className="text-xs text-red-500 mt-1">Layer 1 API may be unavailable. Check your connection.</p>
        </div>
      )}

      {/* Empty state */}
      {!isLoading && !isError && sources.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-300 p-12 text-center">
          <div className="text-4xl mb-4">🔌</div>
          <h3 className="text-base font-semibold text-gray-900">No data sources yet</h3>
          <p className="text-sm text-gray-500 mt-1 max-w-sm mx-auto">
            Connect your company's data sources — ERP, CRM, government APIs, databases, and more.
          </p>
          <button
            onClick={() => setShowWizard(true)}
            className="mt-6 inline-flex items-center gap-2 h-9 px-5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 transition-colors"
          >
            <Plus className="h-4 w-4" />
            Add Your First Source
          </button>
        </div>
      )}

      {/* Grouped source cards */}
      {Object.entries(grouped).map(([category, items]) => (
        <div key={category} className="space-y-4">
          <h2 className="text-xs font-semibold text-gray-500 uppercase tracking-wider">{category}</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
            {items.map(s => (
              <SourceCard
                key={s.id}
                source={s}
                syncing={syncingIds.has(s.id)}
                onSync={() => handleSync(s.id)}
                onDelete={() => {
                  if (confirm(`Remove "${s.source_name}"? This cannot be undone.`))
                    deleteMut.mutate(s.id)
                }}
              />
            ))}
          </div>
        </div>
      ))}

      {/* Wizard modal */}
      {showWizard && <AddSourceWizard onClose={() => setShowWizard(false)} />}
    </div>
  )
}
