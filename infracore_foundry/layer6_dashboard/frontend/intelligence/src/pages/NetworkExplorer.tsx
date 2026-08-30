import React, { useState } from 'react'
import { useParams, useNavigate } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { entitiesApi } from '@shared/api/entities'
import { RiskBadge } from '@shared/components/RiskBadge'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'
import { NetworkGraph } from '../components/graph/NetworkGraph'
import { InvestigationPanel } from '../components/graph/InvestigationPanel'
import { RelationshipExposure } from '../components/RelationshipExposure'
import type { CytoscapeNode } from '@shared/api/types'

export function NetworkExplorer() {
  const { entityType = '', entityId = '' } = useParams<{ entityType: string; entityId: string }>()
  const nav = useNavigate()
  const [depth, setDepth] = useState(2)
  const [selectedNode, setSelectedNode] = useState<CytoscapeNode['data'] | null>(null)
  const [showRelTypes, setShowRelTypes] = useState({ DIRECTED: true, REGISTERED_AT: true, OWNS: true, SUBJECT_OF: true, inferred: true })

  const { data: profile } = useQuery({
    queryKey: ['entity-brief', entityType, entityId],
    queryFn: () => entitiesApi.getProfile(entityType, entityId),
    staleTime: 300_000,
  })

  const { data: network, isLoading } = useQuery({
    queryKey: ['network-explorer', entityType, entityId, depth],
    queryFn: () => entitiesApi.getNetwork(entityType, entityId, depth),
    staleTime: 120_000,
  })

  const filteredEdges = network?.edges.filter(e => {
    const lt = e.data.linkType
    if (!showRelTypes.inferred && e.data.isInferred) return false
    if (lt === 'DIRECTED' && !showRelTypes.DIRECTED) return false
    if (lt === 'REGISTERED_AT' && !showRelTypes.REGISTERED_AT) return false
    if (lt === 'OWNS' && !showRelTypes.OWNS) return false
    if (lt === 'SUBJECT_OF' && !showRelTypes.SUBJECT_OF) return false
    return true
  }) ?? []

  return (
    <div className="flex h-[calc(100vh-56px)] overflow-hidden bg-white">
      {/* Left panel */}
      <div className="w-80 border-r border-gray-200 flex flex-col overflow-y-auto flex-shrink-0">
        <div className="p-4 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">Exploring</p>
          <p className="font-semibold text-gray-900 truncate">{profile?.name ?? entityId}</p>
          {profile && <div className="mt-2"><p className="text-xs text-gray-500">Own recorded risk{profile.properties.synthetic === true ? ' · synthetic' : ''}</p><RiskBadge band={profile.riskBand} score={profile.riskScore} size="sm" /></div>}
        </div>

        <div className="p-4 border-b border-gray-100">
          <p className="text-xs font-medium text-gray-500 mb-2">Depth</p>
          <div className="flex gap-2">
            {[1, 2, 3].map(d => (
              <button key={d} onClick={() => setDepth(d)}
                className={`flex-1 py-1.5 text-sm rounded-lg border transition-colors ${depth === d ? 'bg-gray-900 text-white border-gray-900' : 'border-gray-200 text-gray-700 hover:bg-gray-50'}`}>
                {d}
              </button>
            ))}
          </div>
        </div>

        <div className="p-4 border-b border-gray-100">
          <p className="text-xs font-medium text-gray-500 mb-3">Relationship Types</p>
          <div className="space-y-2">
            {(Object.keys(showRelTypes) as Array<keyof typeof showRelTypes>).map((key) => (
              <label key={key} className="flex items-center gap-2 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showRelTypes[key]}
                  onChange={e => setShowRelTypes(s => ({ ...s, [key]: e.target.checked }))}
                  className="rounded"
                />
                <span className="text-sm text-gray-700">{key === 'inferred' ? 'Inferred (dashed)' : key}</span>
              </label>
            ))}
          </div>
        </div>

        {network && <InvestigationPanel key={`${entityType}:${entityId}:${depth}`} nodes={network.nodes} edges={filteredEdges} rootId={`${entityType}:${entityId}`} />}

        <div className="p-4"><RelationshipExposure entityType={entityType} entityId={entityId} /></div>
        <div className="p-4">
          <div className="space-y-1.5 text-xs">
            <p className="font-medium text-gray-500 mb-2">Legend · entity’s own recorded risk</p>
            <p className="text-gray-500">Node colors do not include relationship exposure.</p>
            <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-red-500" /><span className="text-gray-600">HIGH RISK</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-amber-500" /><span className="text-gray-600">MEDIUM RISK</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 rounded-sm bg-green-500" /><span className="text-gray-600">LOW RISK</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-blue-500" /><span className="text-gray-600">DIRECTED edge</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-slate-500" /><span className="text-gray-600">REGISTERED_AT edge · address rectangles</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-green-500" /><span className="text-gray-600">OWNS edge</span></div>
            <div className="flex items-center gap-2"><div className="w-3 h-3 bg-red-500" /><span className="text-gray-600">SUBJECT_OF edge</span></div>
          </div>
        </div>
      </div>

      {/* Main graph */}
      <div className="flex-1 relative overflow-hidden">
        {isLoading ? (
          <div className="flex items-center justify-center h-full">
            <LoadingSpinner label="Loading network..." />
          </div>
        ) : network ? (
          <NetworkGraph
            nodes={network.nodes}
            edges={filteredEdges}
            onNodeClick={setSelectedNode}
            height={window.innerHeight - 56}
          />
        ) : (
          <div className="flex items-center justify-center h-full text-gray-400">No network data</div>
        )}
        {network && (
          <div className="absolute top-4 right-4 bg-white border border-gray-200 rounded-xl px-3 py-2 shadow-sm text-xs text-gray-500">
            {network.nodes.length} entities · {filteredEdges.length} visible relationships
          </div>
        )}
      </div>

      {/* Right panel: selected node */}
      {selectedNode && (
        <div className="w-72 border-l border-gray-200 flex flex-col overflow-y-auto flex-shrink-0">
          <div className="p-4 border-b border-gray-100">
            <div className="flex items-center justify-between mb-2">
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Selected</p>
              <button onClick={() => setSelectedNode(null)} className="text-gray-400 hover:text-gray-900 text-lg leading-none">×</button>
            </div>
            <p className="font-semibold text-gray-900 break-words">{String(selectedNode.properties.name ?? selectedNode.properties.fullAddress ?? selectedNode.label)}</p>
            <p className="text-xs text-gray-400 capitalize mt-0.5">{selectedNode.entityType}</p>
            <div className="mt-2"><p className="text-xs text-gray-500">Own recorded risk</p><RiskBadge band={selectedNode.riskBand} score={selectedNode.riskScore} size="sm" /></div>
            <RelationshipExposure entityType={selectedNode.entityType} entityId={selectedNode.id.slice(selectedNode.id.indexOf(':') + 1)} />
            {selectedNode.riskFlags.length > 0 && (
              <div className="flex flex-wrap gap-1 mt-2">
                {selectedNode.riskFlags.map((f: string) => (
                  <span key={f} className="px-1.5 py-0.5 bg-red-50 text-red-700 text-xs rounded">{f.replace(/_/g, ' ')}</span>
                ))}
              </div>
            )}
          </div>
          <div className="p-4">
            <button
              onClick={() => {
                const idPart = selectedNode.id.slice(selectedNode.id.indexOf(':') + 1)
                nav(`/entity/${selectedNode.entityType}/${encodeURIComponent(String(idPart))}`)
              }}
              className="w-full py-2 bg-gray-900 text-white text-sm rounded-lg hover:bg-gray-800 transition-colors">
              View Full Profile →
            </button>
          </div>
        </div>
      )}
    </div>
  )
}
