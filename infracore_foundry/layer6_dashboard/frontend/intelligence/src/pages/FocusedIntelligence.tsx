import { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'
import { RelationshipExposure } from '../components/RelationshipExposure'

export function FocusedIntelligence() {
  const { cin } = useParams()
  const [input, setInput] = useState(cin || '')
  const [id, setId] = useState(cin || '')
  const query = useQuery({ queryKey: ['focused-intelligence', id], enabled: !!id,
    queryFn: () => apiClient.get(`/api/v1/focused-intelligence/${encodeURIComponent(id)}`).then(r => r.data) })
  const data = query.data
  return <div className="max-w-4xl mx-auto p-8 space-y-5">
    <h1 className="text-2xl font-semibold">Intelligence</h1>
    <p>Explainable risk context and relationship review signals from your imported records.</p>
    <form className="flex gap-3" onSubmit={e => { e.preventDefault(); setId(input.trim()) }}>
      <input aria-label="Company ID" placeholder="Company ID / CIN" className="border rounded p-2 flex-1" value={input} onChange={e => setInput(e.target.value)} />
      <button disabled={!input.trim()} className="bg-gray-900 text-white rounded px-4">Analyze</button>
    </form>
    {query.isFetching && <p>Analyzing…</p>}
    {query.isError && <p role="alert">Analysis unavailable. Check the company ID and service status.</p>}
    {data && <section className="border rounded p-5 space-y-3">
      <h2 className="text-xl font-semibold">{data.name}</h2>
      {data.synthetic && <p className="text-amber-700">SYNTHETIC TEST DATA</p>}
      <p>Recorded risk: {data.risk_score ?? 'Unknown'} · {data.risk_band}</p>
      <p>{data.directors.length} directors · {data.relationship_count} loaded relationships</p>
      <h3 className="font-semibold">Companies sharing directors</h3>
      {data.companies_sharing_directors.length === 0 && <p>None found within loaded coverage.</p>}
      {data.companies_sharing_directors.map((key: string) => <p key={key}><Link className="text-blue-700 underline" to={`/entity/company/${encodeURIComponent(key)}`}>{key}</Link></p>)}
      <h3 className="font-semibold">Review signals</h3>
      {data.review_signals.map((s: string) => <p key={s}>{s}</p>)}
      <p className="text-sm text-gray-500">{data.limitations}</p>
      <Link className="text-blue-700 underline" to={`/network/company/${encodeURIComponent(id)}`}>Explore evidence and connections</Link>
      <RelationshipExposure entityType="company" entityId={id} />
      <p><Link className="text-blue-700 underline" to={`/reports?entity=${encodeURIComponent('company/' + id)}`}>Create report and optional Gemini AI review</Link></p>
    </section>}
  </div>
}
