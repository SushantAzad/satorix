import type { CytoscapeNode, CytoscapeEdge } from '@shared/api/types'

// Paths describe connectivity, not ownership direction, within the loaded view.
export function shortestPath(nodes: CytoscapeNode[], edges: CytoscapeEdge[], source: string, target: string) {
  const ids = new Set(nodes.map(n => n.data.id))
  if (!ids.has(source) || !ids.has(target)) return null
  const adjacency = new Map<string, { node: string; edge: string }[]>()
  for (const { data: e } of edges) {
    if (!ids.has(e.source) || !ids.has(e.target)) continue
    for (const [a, b] of [[e.source, e.target], [e.target, e.source]]) {
      adjacency.set(a, [...(adjacency.get(a) ?? []), { node: b, edge: e.id }])
    }
  }
  const queue = [source]
  const previous = new Map<string, { node: string; edge: string }>()
  const seen = new Set([source])
  for (let i = 0; i < queue.length && !seen.has(target); i++) {
    for (const next of (adjacency.get(queue[i]) ?? []).sort((a, b) => a.node.localeCompare(b.node) || a.edge.localeCompare(b.edge))) {
      if (seen.has(next.node)) continue
      seen.add(next.node)
      previous.set(next.node, { node: queue[i], edge: next.edge })
      queue.push(next.node)
    }
  }
  if (!seen.has(target)) return null
  const pathNodes = [target], pathEdges: string[] = []
  while (pathNodes[0] !== source) {
    const step = previous.get(pathNodes[0])!
    pathNodes.unshift(step.node)
    pathEdges.unshift(step.edge)
  }
  return { nodes: pathNodes, edges: pathEdges }
}

export function evidenceIds(value: unknown): string[] {
  const values = Array.isArray(value) ? value : typeof value === 'string' ? value.split(',') : []
  return [...new Set(values.filter((v): v is string => typeof v === 'string').map(v => v.trim()).filter(Boolean))]
}

export function sharedConnections(edges: CytoscapeEdge[], left: string, right: string) {
  const neighbors = (company: string, type: string) => new Set(edges.flatMap(({ data: e }) => {
    if (e.linkType !== type || e.isInferred) return []
    if (type === 'DIRECTED' && e.target === company) return [e.source]
    if (type === 'REGISTERED_AT' && e.source === company) return [e.target]
    return []
  }))
  const shared = (type: string) => {
    const other = neighbors(right, type)
    return [...neighbors(left, type)].filter(id => other.has(id)).sort()
  }
  return { directors: shared('DIRECTED'), addresses: shared('REGISTERED_AT') }
}
