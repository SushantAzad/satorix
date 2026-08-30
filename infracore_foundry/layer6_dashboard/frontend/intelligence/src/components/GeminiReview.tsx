import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'

export function GeminiReview({ reportId }: { reportId: string }) {
  const qc = useQueryClient()
  const [preview, setPreview] = useState<any>(null)
  const [consent, setConsent] = useState(false)
  const status = useQuery({ queryKey: ['gemini-status'], queryFn: () => apiClient.get('/api/v1/gemini/status').then(r => r.data) })
  const inspect = useMutation({ mutationFn: () => apiClient.get(`/api/v1/gemini/reports/${reportId}/preview`).then(r => r.data),
    onSuccess: data => { setPreview(data); setConsent(false) } })
  const send = useMutation({ mutationFn: () => apiClient.post(`/api/v1/gemini/reports/${reportId}`, {
    consent, evidence_sha256: preview.sha256,
  }, { timeout: 90000 }).then(r => r.data), retry: false,
    onSuccess: () => { setPreview(null); setConsent(false); qc.invalidateQueries({ queryKey: ['report', reportId] }) } })
  return <section className="border rounded p-4 mb-4 space-y-3">
    <h4 className="font-semibold">Gemini intelligence review (optional)</h4>
    <p className="text-sm">Synthetic and real imported records are supported. AI drafts do not change recorded scores and require human review.</p>
    <p className="text-sm">{status.isError ? 'Gemini configuration could not be loaded.' : status.data?.message}</p>
    <button className="border rounded px-3 py-2" disabled={inspect.isPending || send.isPending} onClick={() => inspect.mutate()}>Preview data to send</button>
    {preview && <>
      <p className="text-sm">{preview.notice}</p>
      <details><summary>Exact evidence payload</summary><pre className="text-xs whitespace-pre-wrap break-all max-h-64 overflow-auto">{JSON.stringify(preview.payload, null, 2)}</pre></details>
      <label className="block text-sm"><input type="checkbox" checked={consent} onChange={e => setConsent(e.target.checked)} /> I authorize sending this evidence to Google Gemini, including any real names and identifiers, and understand charges may apply.</label>
      <button className="border rounded px-3 py-2" disabled={!consent || !status.data?.ready || send.isPending} onClick={() => send.mutate()}>{send.isPending ? 'Generating AI draft…' : 'Send to Gemini'}</button>
    </>}
    {(inspect.isError || send.isError) && <p role="alert" className="text-red-600">{(send.error as any)?.response?.data?.detail || 'Could not complete this action. Local report remains available.'}</p>}
    {send.isSuccess && <p>AI review saved in this report. Review it below before relying on it.</p>}
  </section>
}
