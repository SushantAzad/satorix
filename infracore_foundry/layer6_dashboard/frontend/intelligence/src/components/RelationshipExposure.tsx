import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { apiClient } from '@shared/api/client'

export function RelationshipExposure({ entityType, entityId }: { entityType: string; entityId: string }) {
  const query = useQuery({
    queryKey: ['relationship-exposure', entityType, entityId],
    queryFn: () => apiClient.get(`/api/v1/focused-intelligence/exposure/${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`).then(r => r.data),
    staleTime: 0,
  })
  const data = query.data
  return <section className="border border-amber-200 rounded-xl bg-amber-50/40 p-4 text-sm space-y-2" aria-label="Relationship exposure">
    <h2 className="font-semibold text-gray-900">Relationship exposure</h2>
    {query.isFetching && <p>Checking connected companies…</p>}
    {(query.isError || data?.status === 'unavailable') && <p role="alert">Exposure unavailable — do not interpret this as no exposure.</p>}
    {data?.status === 'available' && <>
      <p>{data.high_count} high · {data.medium_count} medium · {data.low_count} low · {data.unknown_count} unassessed companies</p>
      {data.high_count > 0 && <p className="font-medium text-amber-900">Connected to a high-risk company — review recommended.</p>}
      {data.companies.length === 0 && <p>No qualifying direct company links found in loaded data. This is not risk clearance.</p>}
      {data.companies.map((c: any) => <div key={c.entity_id} className="border-t border-amber-200 pt-2">
        <Link className="text-blue-700 underline break-words" to={`/entity/company/${encodeURIComponent(c.entity_id)}`}>{c.name}</Link>
        <p>Company’s recorded risk: {c.score ?? 'Unknown'} · {c.band === 'NONE' ? 'Unassessed' : c.band}{c.synthetic ? ' · Synthetic' : ''}</p>
        <details><summary className="cursor-pointer">Relationship evidence</summary>
          {c.relationships.map((r: any, i: number) => <div className="mt-2 break-words" key={i}>
            <p>{r.source_id} → {r.type} → {r.target_id}</p>
            <pre className="text-xs whitespace-pre-wrap">{JSON.stringify(r.properties, null, 2)}</pre>
          </div>)}
        </details>
      </div>)}
      <p className="text-xs text-gray-600">{data.scope} Independent of graph display filters. Indirect, inferred and shared-address links are excluded.</p>
      <p className="text-xs text-gray-600">{data.notice} The entity’s own recorded score is unchanged.</p>
    </>}
  </section>
}
