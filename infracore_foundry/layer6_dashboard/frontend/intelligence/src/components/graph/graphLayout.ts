// A label-aware deterministic grid makes small embedded graphs readable.
// Larger graphs keep a force layout. Run after element reconciliation and resize.
export function graphLayout(nodeCount: number) {
  return nodeCount <= 12
    ? { name: 'grid', fit: false, animate: false, padding: 50,
        avoidOverlap: true, avoidOverlapPadding: 70, nodeDimensionsIncludeLabels: true,
        cols: Math.ceil(Math.sqrt(nodeCount)), spacingFactor: 1.3 }
    : { name: 'cose', fit: false, animate: false, padding: 50,
        nodeDimensionsIncludeLabels: true, nodeRepulsion: () => 12000,
        idealEdgeLength: () => 180, componentSpacing: 100 };
}
