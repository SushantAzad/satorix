import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useNavigate } from 'react-router-dom'
import { alertsApi } from '@shared/api/alerts'
import { AlertBadge } from '@shared/components/AlertBadge'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'
import { formatDistanceToNow, parseISO } from 'date-fns'

export function AlertsDashboard() {
  const nav = useNavigate()
  const qc = useQueryClient()
  const [filter, setFilter] = useState<{ severity: string; acknowledged: string }>({ severity: '', acknowledged: 'false' })

  const [offset, setOffset] = useState(0)
  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['alerts', filter, offset],
    queryFn: () => alertsApi.list({
      severity: filter.severity || undefined,
      acknowledged: filter.acknowledged === '' ? undefined : filter.acknowledged === 'true',
      limit: 100,
      offset,
    }),
    refetchInterval: 30_000,
  })

  const ackMut = useMutation({
    mutationFn: alertsApi.acknowledge,
    onSuccess: () => qc.invalidateQueries({ queryKey: ['alerts'] }),
  })
  const scanMut = useMutation({ mutationFn: alertsApi.scan,
    onSuccess: () => { setOffset(0); qc.invalidateQueries({ queryKey: ['alerts'] }) } })

  const stats = data ? {
    total: data.total,
    unack: data.unacknowledged,
    critical: data.critical_count,
    high: data.high_count,
  } : null

  if (isLoading) return <div className="flex items-center justify-center min-h-screen"><LoadingSpinner label="Loading alerts..." /></div>

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <div className="flex items-center justify-between mb-8">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">Intelligence Alerts</h1>
          <p className="text-sm text-gray-400 mt-1">On-demand review of recorded company risk and direct relationship exposure. Not a finding of wrongdoing.</p>
          <p className="text-sm mt-2">{data?.last_scan ? `Last successful scan: ${new Date(data.last_scan).toLocaleString()}` : 'No successful scan recorded. Run a scan after importing or changing data.'}</p>
        </div>
        <button className="border rounded px-4 py-2" disabled={scanMut.isPending} onClick={() => scanMut.mutate()}>{scanMut.isPending ? 'Scanning…' : 'Run signal scan'}</button>
      </div>
      {(isError || scanMut.isError || ackMut.isError) && <p role="alert" className="text-red-600 mb-4">{isError ? 'Alerts could not be loaded.' : scanMut.isError ? 'Scan failed. Previous alerts have not been replaced.' : 'Acknowledgement failed.'} Check permissions and service availability. <button onClick={() => refetch()}>Reload</button></p>}

      {/* Stats */}
      {stats && (
        <div className="grid grid-cols-4 gap-4 mb-8">
          {[
            { label: 'Total Active', value: stats.total, color: 'text-gray-900' },
            { label: 'Critical', value: stats.critical, color: 'text-red-600' },
            { label: 'High', value: stats.high, color: 'text-orange-600' },
            { label: 'Unacknowledged', value: stats.unack, color: 'text-amber-600' },
          ].map(s => (
            <div key={s.label} className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm">
              <p className="text-xs text-gray-400 uppercase tracking-wider">{s.label}</p>
              <p className={`text-3xl font-bold mt-1 tabular-nums ${s.color}`}>{s.value}</p>
            </div>
          ))}
        </div>
      )}

      {/* Filters */}
      <div className="flex items-center gap-3 mb-6">
        <select
          value={filter.severity}
          onChange={e => { setOffset(0); setFilter(f => ({ ...f, severity: e.target.value })) }}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:border-gray-400 bg-white">
          <option value="">All Severities</option>
          <option value="CRITICAL">Critical</option>
          <option value="HIGH">High</option>
          <option value="MEDIUM">Medium</option>
          <option value="LOW">Low</option>
        </select>
        <select
          value={filter.acknowledged}
          onChange={e => { setOffset(0); setFilter(f => ({ ...f, acknowledged: e.target.value })) }}
          className="px-3 py-1.5 border border-gray-200 rounded-lg text-sm text-gray-700 focus:outline-none focus:border-gray-400 bg-white">
          <option value="false">Unacknowledged</option>
          <option value="true">Acknowledged</option>
          <option value="">All</option>
        </select>
      </div>

      {/* Alerts list */}
      {isError ? null : !data?.alerts.length ? (
        <div className="text-center py-16 text-gray-400">
          <p className="text-lg font-medium text-gray-900 mb-1">No alerts found</p>
          <p className="text-sm">No matching recorded signals. This does not establish absence of risk.</p>
        </div>
      ) : (
        <div className="space-y-3">
          {data.alerts.map(a => (
            <div key={a.alertId}
              className={`bg-white border rounded-xl p-4 shadow-sm hover:shadow transition-shadow ${
                a.severity === 'CRITICAL' ? 'border-l-4 border-l-red-500 border-red-200' :
                a.severity === 'HIGH' ? 'border-l-4 border-l-orange-500 border-gray-200' :
                'border-gray-200'
              }`}>
              <div className="flex items-start justify-between gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-1.5">
                    <AlertBadge severity={a.severity} />
                    <span className="text-xs text-gray-400">{a.alertType.replace(/_/g, ' ')}</span>
                    <span className="text-gray-300">·</span>
                    <span className="text-xs text-gray-400">{formatDistanceToNow(parseISO(a.createdAt), { addSuffix: true })}</span>
                    {a.source === 'ML_MODEL' && a.confidence && (
                      <span className="text-xs bg-purple-50 text-purple-700 px-1.5 py-0.5 rounded">ML {Math.round(a.confidence * 100)}%</span>
                    )}
                  </div>
                  <p className="font-semibold text-gray-900">{a.title}</p>
                  <p className="text-sm text-gray-500 mt-0.5 line-clamp-2">{a.message}</p>
                  {a.affectedEntityName && (
                    <button
                      onClick={() => nav(`/entity/${a.affectedEntityType}/${a.affectedEntityId}`)}
                      className="mt-2 text-xs text-blue-600 hover:underline">
                      {a.affectedEntityName} →
                    </button>
                  )}
                </div>
                <div className="flex flex-col gap-2 flex-shrink-0">
                  <button
                    onClick={() => nav(`/entity/${a.affectedEntityType}/${a.affectedEntityId}`)}
                    className="px-3 py-1.5 border border-gray-300 text-xs text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                    View Entity
                  </button>
                  {!a.isAcknowledged && (
                    <button
                      onClick={() => ackMut.mutate(a.alertId)}
                      disabled={ackMut.isPending}
                      className="px-3 py-1.5 border border-gray-300 text-xs text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                      Acknowledge
                    </button>
                  )}
                  {a.isAcknowledged && <span className="text-xs text-green-600 text-center">✓ Acknowledged</span>}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
      <div className="flex gap-4 mt-4"><button disabled={!offset} onClick={() => setOffset(Math.max(0, offset - 100))}>Previous</button><button disabled={offset + 100 >= (data?.matching ?? data?.total ?? 0)} onClick={() => setOffset(offset + 100)}>Next</button></div>
    </div>
  )
}
