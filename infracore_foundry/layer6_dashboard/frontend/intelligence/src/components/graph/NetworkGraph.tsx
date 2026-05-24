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

function sanitizeCytoscapeElements(
  nodes: CytoscapeNode[],
  edges: CytoscapeEdge[],
): { nodes: CytoscapeNode[]; edges: CytoscapeEdge[] } {
  const nodeIds = new Set(nodes.map((n) => n.data.id))
  const safeEdges = edges.filter((e) => {
    const sourceOk = nodeIds.has(e.data.source)
    const targetOk = nodeIds.has(e.data.target)
    if (!sourceOk || !targetOk) {
      console.warn(
        `Dropping edge ${e.data.id}: ` +
        `source=${e.data.source}(${sourceOk}) ` +
        `target=${e.data.target}(${targetOk})`,
      )
      return false
    }
    return true
  })
  return { nodes, edges: safeEdges }
}

class GraphErrorBoundary extends React.Component<
  { children: React.ReactNode },
  { hasError: boolean; error: string }
> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: '' }
  }
  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error: error.message }
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="flex flex-col items-center justify-center h-64 bg-gray-50 rounded-lg border border-gray-200 p-6">
          <p className="text-gray-500 text-sm mb-2">Network graph unavailable</p>
          <p className="text-gray-400 text-xs font-mono">{this.state.error}</p>
          <button
            onClick={() => this.setState({ hasError: false, error: '' })}
            className="mt-4 px-4 py-2 text-xs bg-gray-800 text-white rounded hover:bg-gray-700"
          >
            Retry
          </button>
        </div>
      )
    }
    return this.props.children
  }
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

function NetworkGraphInner({ nodes, edges, onNodeClick, height = 384 }: Props) {
  const cyRef = useRef<Cytoscape.Core | null>(null)

  const { nodes: safeNodes, edges: safeEdges } = sanitizeCytoscapeElements(nodes, edges)

  const elements = [
    ...safeNodes.map(n => ({ data: { ...n.data, isAnomalous: n.data.isAnomalous ? 1 : 0, size: n.data.size || 30 } })),
    ...safeEdges.map(e => ({ data: { ...e.data, isInferred: e.data.isInferred ? 1 : 0 } })),
  ]

  const handleCyInit = useCallback((cy: Cytoscape.Core) => {
    cyRef.current = cy
    cy.on('tap', 'node', (event) => {
      const node = event.target
      if (onNodeClick) onNodeClick(node.data())
    })
    cy.fit(undefined, 30)
  }, [onNodeClick])

  if (!safeNodes.length) return (
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

export function NetworkGraph(props: Props) {
  return (
    <GraphErrorBoundary>
      <NetworkGraphInner {...props} />
    </GraphErrorBoundary>
  )
}
