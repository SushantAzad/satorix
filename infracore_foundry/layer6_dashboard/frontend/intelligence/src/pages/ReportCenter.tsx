import React, { useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'
import { FileText, Download, Trash2 } from 'lucide-react'
import type { Report } from '@shared/api/types'

const REPORT_TYPES = [
  { id: 'corporate_due_diligence', label: 'Corporate Due Diligence', desc: 'Full entity profile with ownership, risk, and regulatory exposure' },
  { id: 'regulatory_exposure', label: 'Regulatory Exposure', desc: 'SEBI, NCLT, MCA enforcement actions and timeline' },
  { id: 'portfolio_health', label: 'Portfolio Health', desc: 'Group-level risk and financial health overview' },
  { id: 'peer_comparison', label: 'Peer Comparison', desc: 'Benchmark against sector peers on key metrics' },
]

export function ReportCenter() {
  const qc = useQueryClient()
  const [form, setForm] = useState({ entityType: 'company', entityId: '', reportType: 'corporate_due_diligence', depth: 'standard' })
  const [error, setError] = useState('')

  const { data: reports, isLoading } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: () => apiClient.get('/api/v1/reports').then(r => r.data),
    staleTime: 30_000,
  })

  const genMut = useMutation({
    mutationFn: () => apiClient.post('/api/v1/reports/generate', {
      entity_type: form.entityType,
      entity_id: form.entityId,
      report_type: form.reportType,
      depth: form.depth,
    }).then(r => r.data),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['reports'] })
      setForm(f => ({ ...f, entityId: '' }))
    },
    onError: (e: any) => setError(e.response?.data?.detail || 'Generation failed'),
  })

  const delMut = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/api/v1/reports/${id}`),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['reports'] }),
  })

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Report Center</h1>
      <p className="text-sm text-gray-400 mb-8">Generate board-ready intelligence reports in seconds</p>

      {/* Generate form */}
      <div className="bg-white border border-gray-200 rounded-2xl p-6 shadow-sm mb-8">
        <h2 className="text-base font-semibold text-gray-900 mb-4">Generate New Report</h2>
        <div className="grid grid-cols-2 gap-4 mb-4">
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Entity Type</label>
            <select
              value={form.entityType}
              onChange={e => setForm(f => ({ ...f, entityType: e.target.value }))}
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gray-900">
              <option value="company">Company</option>
              <option value="director">Director</option>
              <option value="project">Project</option>
            </select>
          </div>
          <div>
            <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-1.5">Entity ID / CIN / DIN</label>
            <input
              value={form.entityId}
              onChange={e => setForm(f => ({ ...f, entityId: e.target.value }))}
              placeholder="e.g. L45201MH2003PLC142301"
              className="w-full px-3 py-2 border border-gray-200 rounded-lg text-sm focus:outline-none focus:border-gray-900"
            />
          </div>
        </div>
        <div className="mb-4">
          <label className="block text-xs font-medium text-gray-500 uppercase tracking-wide mb-2">Report Type</label>
          <div className="grid grid-cols-2 gap-2">
            {REPORT_TYPES.map(rt => (
              <label
                key={rt.id}
                className={`flex items-start gap-2.5 p-3 border rounded-xl cursor-pointer transition-colors ${
                  form.reportType === rt.id ? 'border-gray-900 bg-gray-50' : 'border-gray-200 hover:border-gray-300'
                }`}>
                <input
                  type="radio"
                  name="reportType"
                  value={rt.id}
                  checked={form.reportType === rt.id}
                  onChange={e => setForm(f => ({ ...f, reportType: e.target.value }))}
                  className="mt-0.5"
                />
                <div>
                  <p className="text-sm font-medium text-gray-900">{rt.label}</p>
                  <p className="text-xs text-gray-400 mt-0.5">{rt.desc}</p>
                </div>
              </label>
            ))}
          </div>
        </div>
        {error && <div className="mb-3 text-sm text-red-600 bg-red-50 border border-red-200 rounded-lg px-3 py-2">{error}</div>}
        <button
          onClick={() => { setError(''); genMut.mutate() }}
          disabled={!form.entityId || genMut.isPending}
          className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {genMut.isPending ? 'Generating...' : 'Generate Report'}
        </button>
        {genMut.isPending && <p className="text-xs text-gray-400 mt-2">This may take 15–30 seconds</p>}
      </div>

      {/* Reports list */}
      <div>
        <h2 className="text-base font-semibold text-gray-900 mb-4">Recent Reports</h2>
        {isLoading ? <LoadingSpinner /> : !reports?.length ? (
          <div className="text-center py-12 text-gray-400 border border-dashed border-gray-200 rounded-xl">
            <FileText className="h-8 w-8 mx-auto mb-2 opacity-40" />
            <p className="font-medium text-gray-900 mb-1">No reports yet</p>
            <p className="text-sm">Generate your first report above</p>
          </div>
        ) : (
          <div className="space-y-3">
            {reports.map(r => (
              <div key={r.id} className="bg-white border border-gray-200 rounded-xl p-4 shadow-sm flex items-center justify-between gap-4">
                <div className="flex items-center gap-3">
                  <div className={`w-2 h-2 rounded-full flex-shrink-0 ${
                    r.status === 'completed' ? 'bg-green-500' :
                    r.status === 'failed' ? 'bg-red-500' :
                    'bg-amber-400 animate-pulse'
                  }`} />
                  <div>
                    <p className="font-medium text-gray-900">{r.entityName || r.entityId}</p>
                    <p className="text-xs text-gray-400">
                      {r.reportType.replace(/_/g, ' ')} · {r.status} · {r.generatedAt ? new Date(r.generatedAt).toLocaleDateString() : 'Pending'}
                    </p>
                  </div>
                </div>
                <div className="flex items-center gap-2">
                  {r.status === 'completed' && (
                    <button className="p-1.5 border border-gray-200 rounded-lg text-gray-400 hover:text-gray-900 hover:border-gray-400 transition-colors">
                      <Download className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    onClick={() => delMut.mutate(r.id)}
                    className="p-1.5 border border-gray-200 rounded-lg text-gray-400 hover:text-red-600 hover:border-red-200 transition-colors">
                    <Trash2 className="h-4 w-4" />
                  </button>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
