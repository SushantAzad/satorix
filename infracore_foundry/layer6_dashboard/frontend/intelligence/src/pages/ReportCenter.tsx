import React, { useState, useEffect } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'
import { FileText, Download, Trash2 } from 'lucide-react'
import type { Report } from '@shared/api/types'
import { GeminiReview } from '../components/GeminiReview'

const REPORT_TYPES = [
  { id: 'corporate_due_diligence', label: 'Due Diligence — Available Data', desc: 'Recorded entity, risk, relationships, provenance and explicit coverage gaps' },
]

function ReportValue({ value }: { value: unknown }) {
  if (value === null || value === undefined) return <span className="text-gray-500">Not available</span>
  if (Array.isArray(value)) return value.length
    ? <ul className="space-y-2 list-disc pl-5">{value.map((v, i) => <li key={i}><ReportValue value={v} /></li>)}</ul>
    : <span className="text-gray-500">No records returned (not proof of absence)</span>
  if (typeof value === 'object') return <dl className="space-y-2">{Object.entries(value).map(([key, v]) =>
    <div key={key}><dt className="font-medium text-gray-600">{key.replace(/_/g, ' ')}</dt><dd className="pl-3 break-words"><ReportValue value={v} /></dd></div>)}</dl>
  return <span>{String(value)}</span>
}

export function ReportCenter() {
  const qc = useQueryClient()
  const [searchParams] = useSearchParams()
  const [form, setForm] = useState({ entityType: 'company', entityId: '', reportType: 'corporate_due_diligence' })
  const [error, setError] = useState('')
  const [selectedId, setSelectedId] = useState<string | null>(null)
  const selected = useQuery({
    queryKey: ['report', selectedId],
    enabled: !!selectedId,
    queryFn: () => apiClient.get(`/api/v1/reports/${selectedId}`).then(r => r.data),
  })
  const downloadMut = useMutation({
    mutationFn: (id: string) => apiClient.get(`/api/v1/reports/${id}`).then(r => r.data),
    onSuccess: (data) => {
      const url = URL.createObjectURL(new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `due-diligence-${data.report_id}.json`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
    onError: () => setError('Could not download report. It may have expired; please regenerate it.'),
  })

  useEffect(() => {
    const entity = searchParams.get('entity')
    if (entity && entity.includes('/')) {
      const [type, ...idParts] = entity.split('/')
      const id = idParts.join('/')
      if (type && id) {
        setForm(f => ({ ...f, entityType: type, entityId: id }))
      }
    }
  }, [searchParams])

  const { data: reports, isLoading, isError: listError } = useQuery<Report[]>({
    queryKey: ['reports'],
    queryFn: () => apiClient.get('/api/v1/reports/').then(r => {
      const list = Array.isArray(r.data) ? r.data : []
      // Normalise backend field names to frontend Report type
      return list.map((item: any) => ({
        ...item,
        id: item.id ?? item.report_id,
        entityType: item.entityType ?? item.entity_type,
        entityId: item.entityId ?? item.entity_id,
        reportType: item.reportType ?? item.report_type,
        generatedAt: item.generatedAt ?? item.generated_at,
        status: item.status ?? 'completed',
      })) as Report[]
    }),
    staleTime: 30_000,
  })

  const genMut = useMutation({
    mutationFn: () => apiClient.post('/api/v1/reports/generate', {
      entity_type: form.entityType,
      entity_id: form.entityId.trim(),
      report_type: form.reportType,
    }).then(r => r.data),
    onSuccess: (data: any) => {
      qc.invalidateQueries({ queryKey: ['reports'] })
      if (data?.status === 'failed' || data?.error) {
        setError(typeof data.error === 'string' ? data.error : 'Report generation failed — check Layer 5 is running.')
      } else {
        setSelectedId(data.report_id)
      }
    },
    onError: (e: any) => {
      const detail = e.response?.data?.detail
      if (Array.isArray(detail)) {
        setError(detail.map((d: any) => (typeof d === 'object' ? (d.msg || JSON.stringify(d)) : String(d))).join('; '))
      } else if (typeof detail === 'string') {
        setError(detail)
      } else {
        setError(e.message || 'Report generation failed')
      }
    },
  })

  const delMut = useMutation({
    mutationFn: (id: string) => apiClient.delete(`/api/v1/reports/${id}`),
    onSuccess: (_, id) => {
      qc.invalidateQueries({ queryKey: ['reports'] })
      if (selectedId === id) setSelectedId(null)
    },
    onError: () => setError('Could not delete report. Please retry.'),
  })

  return (
    <div className="max-w-5xl mx-auto px-6 py-8">
      <h1 className="text-2xl font-bold text-gray-900 mb-2">Report Center</h1>
      <p className="text-sm text-gray-500 mb-8">Generate a fresh available-data snapshot. Reports expire after 24 hours; download JSON to keep a copy. External verification, peer comparisons and portfolio reports are not included.</p>

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
          disabled={!form.entityId.trim() || genMut.isPending}
          className="px-5 py-2.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 disabled:opacity-50 disabled:cursor-not-allowed transition-colors">
          {genMut.isPending ? 'Generating...' : 'Generate Report'}
        </button>
        {genMut.isPending && <p className="text-xs text-gray-400 mt-2">This may take 15–30 seconds</p>}
      </div>

      {selectedId && <section className="bg-white border border-gray-200 rounded-xl p-6 mb-8">
        <div className="flex justify-between gap-3 mb-4"><h2 className="font-semibold">Report Preview</h2>
          <button onClick={() => setSelectedId(null)}>Close</button></div>
        {selected.isLoading ? <LoadingSpinner /> : selected.isError
          ? <p role="alert" className="text-red-600">Report could not be loaded. It may have expired; generate a fresh report.</p>
          : selected.data && <>
            <h3 className="text-xl font-semibold mb-2">{selected.data.report_content.title}</h3>
            <p className="text-sm text-gray-500 mb-3">{new Date(selected.data.generated_at).toLocaleString()} · Partial coverage</p>
            {selected.data.report_content.synthetic && <p className="bg-amber-50 text-amber-900 p-3 mb-4">SYNTHETIC TEST DATA — not production findings</p>}
            <button className="border rounded px-3 py-2 mb-4" disabled={downloadMut.isPending} onClick={() => downloadMut.mutate(selectedId)}>Download JSON</button>
            {Object.entries(selected.data.report_content.sections || {}).map(([key, value]) =>
              <section className="border-t pt-4 mt-4 text-sm" key={key}><h4 className="font-semibold text-base mb-3 capitalize">{key.replace(/_/g, ' ')}</h4><ReportValue value={value} /></section>)}
            {!selected.data.report_content.sections?.gemini_ai_review && <GeminiReview key={selectedId} reportId={selectedId} />}
          </>}
      </section>}

      {/* Reports list */}
      <div>
        <h2 className="text-base font-semibold text-gray-900 mb-4">Recent Reports</h2>
        {listError ? <p role="alert" className="text-red-600">Could not load reports. Please refresh and retry.</p> : isLoading ? <LoadingSpinner /> : !reports?.length ? (
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
                  <button onClick={() => setSelectedId(r.id)} className="text-sm border rounded px-2 py-1">View</button>
                  {r.status === 'completed' && (
                    <button aria-label="Download report JSON" title="Download JSON" disabled={downloadMut.isPending} onClick={() => downloadMut.mutate(r.id)} className="p-1.5 border border-gray-200 rounded-lg text-gray-400 hover:text-gray-900 hover:border-gray-400 transition-colors">
                      <Download className="h-4 w-4" />
                    </button>
                  )}
                  <button
                    aria-label="Delete report"
                    disabled={delMut.isPending}
                    onClick={() => { if (window.confirm('Delete this saved report?')) delMut.mutate(r.id) }}
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
