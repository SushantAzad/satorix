const assert = require('node:assert/strict')
const fs = require('node:fs')
const path = require('node:path')
const ts = require('typescript')
const Module = require('node:module')
const cytoscape = require('cytoscape')
const source = fs.readFileSync(path.join(__dirname, '../src/components/graph/graphLayout.ts'), 'utf8')
const helper = new Module(__filename)
helper._compile(ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS } }).outputText, __filename)
const { graphLayout } = helper.exports
for (const count of [1, 4, 9, 12]) {
  const cy = cytoscape({ headless: true, styleEnabled: true,
    elements: Array.from({ length: count }, (_, i) => ({ data: { id: String(i), label: 'SYNTHETIC RISK LAB Long company name ' + i } })),
    style: [{ selector: 'node', style: { width: 40, height: 40, label: 'data(label)', 'text-wrap': 'wrap', 'text-max-width': 160 } }]
  })
  cy.layout(graphLayout(count)).run()
  const nodes = cy.nodes()
  for (let i = 0; i < count; i++) for (let j = i + 1; j < count; j++) {
    const a = nodes[i].boundingBox(), b = nodes[j].boundingBox()
    assert.ok(a.x2 <= b.x1 || b.x2 <= a.x1 || a.y2 <= b.y1 || b.y2 <= a.y1, 'Node/label boxes overlap')
  }
  cy.destroy()
}
assert.equal(graphLayout(13).name, 'cose')
console.log('Graph layouts: small-network bounding boxes do not overlap; large graphs use force layout')
