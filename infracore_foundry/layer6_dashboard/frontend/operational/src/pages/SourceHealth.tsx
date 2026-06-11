import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { Search, ChevronDown, ChevronRight, Database } from 'lucide-react'
import StatusBadge from '../components/StatusBadge'
import clsx from 'clsx'

interface SyncHistoryEntry {
  run_at: string
  records: number
  status: 'completed' | 'failed' | 'running'
  duration_sec: number
}

interface SourceData {
  source_name: string
  source_type: string
  client: string
  last_sync: string
  records_last_run: number
  consecutive_failures: number
  status: 'healthy' | 'degraded' | 'down' | 'unknown'
  sync_history: SyncHistoryEntry[]
}

interface SourcesResponse {
  sources: SourceData[]
}

const TYPE_COLORS: Record<string, string> = {
  api: 'bg-blue-50 text-blue-700 border-blue-200',
  database: 'bg-purple-50 text-purple-700 border-purple-200',
  sftp: 'bg-orange-50 text-orange-700 border-orange-200',
  scraper: 'bg-teal-50 text-teal-700 border-teal-200',
  webhook: 'bg-pink-50 text-pink-700 border-pink-200',
}

export default function SourceHealth() {
  const [search, setSearch] = useState('')
  const [expandedRow, setExpandedRow] = useState<string | null>(null)
  const [typeFilter, setTypeFilter] = useState<string>('all')

  const { data, isLoading, isError } = useQuery<SourcesResponse>({
    queryKey: ['sources'],
    queryFn: async () => {
      const res = await axios.get<SourcesResponse>('/api/v1/sources')
      return res.data
    },
    refetchInterval: 60_000,
  })

  const sources = data?.sources ?? []

  const types = ['all', ...Array.from(new Set(sources.map(s => s.source_type)))]

  const filtered = sources.filter(s => {
    const matchesSearch =
      s.source_name.toLowerCase().includes(search.toLowerCase()) ||
      s.client.toLowerCase().includes(search.toLowerCase())
    const matchesType = typeFilter === 'all' || s.source_type === typeFilter
    return matchesSearch && matchesType
  })

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Data Source Health</h1>
        <p className="text-sm text-gray-500 mt-1">All registered ingestion sources</p>
      </div>

      {/* Filters */}
      <div className="flex gap-3 mb-5">
        <div className="relative flex-1 max-w-xs">
          <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-400" />
          <input
            type="text"
            placeholder="Search sources…"
            value={search}
            onChange={e => setSearch(e.target.value)}
            className="w-full pl-9 pr-3 py-2 text-sm border border-gray-200 rounded-lg bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          />
        </div>
        <select
          value={typeFilter}
          onChange={e => setTypeFilter(e.target.value)}
          className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/10"
        >
          {types.map(t => (
            <option key={t} value={t}>
              {t === 'all' ? 'All types' : t}
            </option>
          ))}
        </select>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load source data.
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading sources…</div>
        ) : filtered.length === 0 ? (
          <div className="flex flex-col items-center justify-center py-16 text-gray-400">
            <Database size={36} className="mb-3 opacity-30" />
            <p className="text-sm">No sources found</p>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-6" />
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Source Name</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Type</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Client</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Last Sync</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Records</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Failures</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Status</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {filtered.map(source => (
                <>
                  <tr
                    key={source.source_name}
                    className="hover:bg-gray-50 cursor-pointer transition-colors"
                    onClick={() =>
                      setExpandedRow(r => (r === source.source_name ? null : source.source_name))
                    }
                  >
                    <td className="px-4 py-3 text-gray-400">
                      {expandedRow === source.source_name ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-medium text-sm text-gray-900">{source.source_name}</span>
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={clsx(
                          'text-xs font-medium px-2 py-0.5 rounded-md border',
                          TYPE_COLORS[source.source_type] ?? 'bg-gray-50 text-gray-600 border-gray-200',
                        )}
                      >
                        {source.source_type}
                      </span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{source.client}</td>
                    <td className="px-4 py-3 text-sm text-gray-500">{source.last_sync}</td>
                    <td className="px-4 py-3 text-sm tabular-nums text-gray-700">
                      {source.records_last_run.toLocaleString()}
                    </td>
                    <td className="px-4 py-3">
                      <span
                        className={clsx(
                          'text-sm font-semibold tabular-nums',
                          source.consecutive_failures > 0 ? 'text-red-600' : 'text-gray-400',
                        )}
                      >
                        {source.consecutive_failures}
                      </span>
                    </td>
                    <td className="px-4 py-3">
                      <StatusBadge status={source.status} />
                    </td>
                  </tr>
                  {expandedRow === source.source_name && (
                    <tr key={`${source.source_name}-expand`}>
                      <td colSpan={8} className="bg-gray-50 px-8 py-4 border-t border-gray-100">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                          Sync History
                        </p>
                        {source.sync_history.length === 0 ? (
                          <p className="text-xs text-gray-400">No history available</p>
                        ) : (
                          <table className="text-xs w-full max-w-2xl">
                            <thead>
                              <tr className="text-gray-400">
                                <th className="text-left pb-1.5 pr-6">Run At</th>
                                <th className="text-left pb-1.5 pr-6">Records</th>
                                <th className="text-left pb-1.5 pr-6">Status</th>
                                <th className="text-left pb-1.5">Duration</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {source.sync_history.map((h, i) => (
                                <tr key={i}>
                                  <td className="py-1.5 pr-6 text-gray-600">{h.run_at}</td>
                                  <td className="py-1.5 pr-6 tabular-nums text-gray-700">
                                    {h.records.toLocaleString()}
                                  </td>
                                  <td className="py-1.5 pr-6">
                                    <StatusBadge status={h.status} />
                                  </td>
                                  <td className="py-1.5 text-gray-500">{h.duration_sec}s</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
