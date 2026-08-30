import React, { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { entitiesApi } from '@shared/api/entities'
import type { CytoscapeNode, CytoscapeEdge } from '@shared/api/types'
import { shortestPath, evidenceIds, sharedConnections } from './investigation'

export function InvestigationPanel({ nodes, edges, rootId }: {
  nodes: CytoscapeNode[]; edges: CytoscapeEdge[]; rootId: string
}) {
  const [target, setTarget] = useState('')
  const [edgeId, setEdgeId] = useState('')
  const [recordId, setRecordId] = useState('')
  const byId = new Map(nodes.map(n => [n.data.id, n.data]))
  const name = (id: string) => String(byId.get(id)?.properties.name ?? byId.get(id)?.properties.fullAddress ?? id)
  const selectedTarget = byId.has(target) ? target : ''
  const path = selectedTarget ? shortestPath(nodes, edges, rootId, selectedTarget) : null
  const comparison = selectedTarget && byId.get(rootId)?.entityType === 'company' && byId.get(selectedTarget)?.entityType === 'company'
    ? sharedConnections(edges, rootId, selectedTarget) : null
  const selectedEdge = edges.find(e => e.data.id === edgeId)?.data
  const evidence = evidenceIds(selectedEdge?.properties.evidence)
  const activeRecord = selectedEdge?.properties.synthetic === true && evidence.includes(recordId) ? recordId : ''
  const sourceRecord = useQuery({
    queryKey: ['fixture-evidence', rootId, edgeId, activeRecord],
    queryFn: () => entitiesApi.getFixtureEvidence(activeRecord),
    enabled: Boolean(activeRecord), retry: false, staleTime: 0,
  })

  return <section className="p-4 border-t border-gray-200 space-y-4" aria-label="Investigation workspace">
    <h2 className="text-sm font-semibold text-gray-900">Investigation workspace</h2>
    <p className="text-xs text-gray-500">Uses only the loaded depth and enabled relationship filters. Paths traverse either direction; arrows retain the recorded relationship direction.</p>
    <label className="block text-xs font-medium text-gray-700">Explore connection to
      <select value={selectedTarget} onChange={e => setTarget(e.target.value)} className="mt-1 w-full rounded border border-gray-300 p-2 text-sm">
        <option value="">Choose an entity</option>
        {nodes.filter(n => n.data.id !== rootId).map(n => <option key={n.data.id} value={n.data.id}>{name(n.data.id)}</option>)}
      </select>
    </label>
    {selectedTarget && <div aria-live="polite" className="text-xs space-y-2">
      <h3 className="font-semibold">Shortest path in this view</h3>
      {path ? <>
        <p>{path.edges.length} hops · one shortest path</p>
        <ol className="list-decimal pl-4 space-y-2">
          {path.nodes.map((id, index) => <li key={id} className="break-words">{name(id)}
            {path.edges[index] && <button onClick={() => setEdgeId(path.edges[index])} className="block text-blue-700 underline mt-1">Inspect connecting relationship</button>}
          </li>)}
        </ol>
      </> : <p>No connection in this filtered view. Increase depth or enable more relationship types; this does not establish database-wide disconnection.</p>}
    </div>}
    {comparison && <div className="text-xs space-y-2">
      <h3 className="font-semibold">Company comparison</h3>
      <p>Recorded shared directors: {comparison.directors.length}</p>
      {comparison.directors.map(id => <p key={id} className="break-words">{name(id)}</p>)}
      <p>Recorded shared addresses: {comparison.addresses.length}</p>
      {comparison.addresses.map(id => <p key={id} className="break-words">{name(id)}</p>)}
      <p className="text-gray-500">Shared connections are review aids, not evidence of wrongdoing. Counts apply only to this view.</p>
    </div>}
    <fieldset className="space-y-2">
      <legend className="text-xs font-medium text-gray-700">Relationship evidence</legend>
      <div className="max-h-64 overflow-y-auto space-y-2">
        {edges.map(({ data: e }) => <label key={e.id} className={`flex items-start gap-2 rounded-lg border p-3 cursor-pointer text-xs ${edgeId === e.id ? 'border-blue-500 bg-blue-50' : 'border-gray-200 hover:bg-gray-50'}`}>
          <input type="radio" name={`evidence-${rootId}`} checked={edgeId === e.id} onChange={() => { setEdgeId(e.id); setRecordId('') }} className="mt-1" />
          <span className="min-w-0 break-words"><span className="block font-medium">{name(e.source)}</span><span className="block my-1 text-gray-500">{e.label} →</span><span className="block">{name(e.target)}</span></span>
        </label>)}
      </div>
      {!edges.length && <p className="text-xs text-gray-500">No relationships match the current filters.</p>}
    </fieldset>
    {selectedEdge && <div className="text-xs space-y-2 break-words" aria-live="polite">
      <p>{name(selectedEdge.source)} → {selectedEdge.label} → {name(selectedEdge.target)}</p>
      <p>{selectedEdge.isInferred ? 'Inferred relationship' : 'Recorded relationship'}</p>
      {selectedEdge.properties.synthetic === true && <p className="font-semibold text-blue-700">Synthetic fixture evidence</p>}
      {Boolean(selectedEdge.properties.appointedDate) && <p>Appointment: {String(selectedEdge.properties.appointedDate)}</p>}
      <p>Source record references:</p>
      {evidence.length ? <ul className="list-disc pl-4">{evidence.map(id => <li key={id}>
        {selectedEdge.properties.synthetic === true ? <button className="text-blue-700 underline" onClick={() => setRecordId(id)}>Open {id}</button> : id}
      </li>)}</ul> : <p>No source record references supplied.</p>}
      {activeRecord && <section aria-label="Source record" className="border rounded p-3 space-y-2">
        <h3 className="font-semibold">Source record: {activeRecord}</h3>
        {sourceRecord.isFetching ? <p>Loading source record…</p> : sourceRecord.isError ? <p role="alert">Could not load this record. Access may be denied, the fixture may be unavailable, or integrity validation may have failed.</p> : sourceRecord.data && <>
          <p>Synthetic · sealed local fixture, not a government document</p>
          <p>{sourceRecord.data.filename} · data row {sourceRecord.data.dataRow}</p>
          <dl className="space-y-2">{Object.entries(sourceRecord.data.fields).map(([key, value]) => <div key={key}>
            <dt className="font-medium">{key}</dt><dd className="whitespace-pre-wrap">{value || '(empty)'}</dd>
          </div>)}</dl>
          <details><summary className="cursor-pointer">Integrity and provenance</summary>
            <p>SHA-256: {sourceRecord.data.fileSha256}</p><p>Batch: {sourceRecord.data.batchId}</p>
          </details>
        </>}
      </section>}
    </div>}
  </section>
}
