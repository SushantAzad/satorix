import React, { useCallback, useRef } from 'react'
import CytoscapeComponent from 'react-cytoscapejs'
import Cytoscape from 'cytoscape'
import type { CytoscapeNode, CytoscapeEdge } from '@shared/api/types'

interface Props {
  nodes: CytoscapeNode[]
  edges: CytoscapeEdge[]
  onNodeClick?: (data: CytoscapeNode['data']) => void
  height?: number
}

const STYLESHEET = [
  { selector: 'node', style: {
    label: 'data(label)', 'text-valign': 'bottom' as const, 'text-margin-y': 6,
    'font-size': 10, 'font-family': 'system-ui, sans-serif', color: '#374151',
    'text-max-width': '80px', 'text-wrap': 'ellipsis' as const, 'text-overflow-wrap': 'whitespace' as const,
    width: 'data(size)', height: 'data(size)',
    'background-color': '#9ca3af', 'border-width': 2, 'border-color': '#e5e7eb',
  }},
  { selector: 'node[riskBand = "HIGH"]', style: { 'background-color': '#ef4444', 'border-color': '#dc2626' } },
  { selector: 'node[riskBand = "MEDIUM"]', style: { 'background-color': '#f59e0b', 'border-color': '#d97706' } },
  { selector: 'node[riskBand = "LOW"]', style: { 'background-color': '#22c55e', 'border-color': '#16a34a' } },
  { selector: 'node[isAnomalous = 1]', style: { 'border-width': 4, 'border-color': '#dc2626' } },
  { selector: 'node[entityType = "director"]', style: { shape: 'diamond' as const } },
  { selector: 'node[entityType = "regulatory_action"]', style: { shape: 'triangle' as const, 'background-color': '#ef4444' } },
  { selector: 'node[entityType = "project"]', style: { shape: 'hexagon' as const, 'background-color': '#3b82f6' } },
  { selector: 'edge', style: {
    width: 1.5, 'line-color': '#d1d5db', 'target-arrow-color': '#d1d5db',
    'target-arrow-shape': 'triangle' as const, 'curve-style': 'bezier' as const, 'font-size': 9, color: '#9ca3af',
  }},
  { selector: 'edge[linkType = "DIRECTED"]', style: { 'line-color': '#3b82f6', 'target-arrow-color': '#3b82f6' } },
  { selector: 'edge[linkType = "OWNS"]', style: { 'line-color': '#22c55e', 'target-arrow-color': '#22c55e' } },
  { selector: 'edge[linkType = "SUBJECT_OF"]', style: { 'line-color': '#ef4444', 'target-arrow-color': '#ef4444' } },
  { selector: 'edge[isInferred = 1]', style: { 'line-style': 'dashed' as const, 'line-color': '#f59e0b', 'target-arrow-color': '#f59e0b' } },
  { selector: ':selected', style: { 'border-width': 3, 'border-color': '#111827', 'border-opacity': 1 } },
]

export function NetworkGraph({ nodes, edges, onNodeClick, height = 384 }: Props) {
  const cyRef = useRef<Cytoscape.Core | null>(null)

  const elements = [
    ...nodes.map(n => ({ data: { ...n.data, isAnomalous: n.data.isAnomalous ? 1 : 0, size: n.data.size || 30 } })),
    ...edges.map(e => ({ data: { ...e.data, isInferred: e.data.isInferred ? 1 : 0 } })),
  ]

  const handleCyInit = useCallback((cy: Cytoscape.Core) => {
    cyRef.current = cy
    cy.on('tap', 'node', (event) => {
      const node = event.target
      if (onNodeClick) onNodeClick(node.data())
    })
    cy.fit(undefined, 30)
  }, [onNodeClick])

  if (!nodes.length) return (
    <div className="flex items-center justify-center text-gray-400 text-sm" style={{ height }}>No network data available</div>
  )

  return (
    <CytoscapeComponent
      elements={elements}
      stylesheet={STYLESHEET as any}
      layout={{ name: 'cose', padding: 40, nodeRepulsion: 8000, idealEdgeLength: 80, animate: false } as any}
      style={{ width: '100%', height }}
      cy={handleCyInit}
    />
  )
}
