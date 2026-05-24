import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { ChevronDown, ChevronRight, ExternalLink, Layers } from 'lucide-react'
import clsx from 'clsx'

const NEO4J_BROWSER_URL = 'http://localhost:7474'

const NEO4J_LABEL_MAP: Record<string, string> = {
  company: 'Company',
  director: 'Director',
  project: 'Project',
  address: 'Address',
  regulatory_action: 'RegulatoryAction',
  legal_case: 'LegalCase',
  insolvency_proceeding: 'InsolvencyProceeding',
  alert: 'Alert',
  event: 'Event',
  regulatory_body: 'RegulatoryBody',
  government_entity: 'GovernmentEntity',
  contract: 'Contract',
}

const OBJECT_TYPES = [
  'company',
  'director',
  'project',
  'address',
  'regulatory_action',
  'legal_case',
  'insolvency_proceeding',
  'alert',
  'event',
  'regulatory_body',
  'government_entity',
  'contract',
]

interface PropertyDef {
  property_name: string
  type: string
  required: boolean
  completeness_pct: number
  source: string
}

interface ObjectTypeData {
  name: string
  display_name: string
  property_count: number | null
  instance_count: number | null
  last_modified: string
  properties: PropertyDef[]
}

interface OntologyHealthResponse {
  object_types?: ObjectTypeData[]
  [key: string]: unknown
}

function buildFallback(): ObjectTypeData[] {
  return OBJECT_TYPES.map(name => ({
    name,
    display_name: name
      .replace(/_/g, ' ')
      .replace(/\b\w/g, c => c.toUpperCase()),
    property_count: null,
    instance_count: null,
    last_modified: '—',
    properties: [],
  }))
}

function coverageColor(pct: number) {
  if (pct >= 80) return 'text-green-600'
  if (pct >= 50) return 'text-amber-500'
  return 'text-red-600'
}

export default function ObjectTypes() {
  const [expandedType, setExpandedType] = useState<string | null>(null)

  const { data, isLoading, isError } = useQuery<OntologyHealthResponse>({
    queryKey: ['ontology-health'],
    queryFn: async () => {
      const res = await axios.get<OntologyHealthResponse>('/api/v1/operational/ontology-health')
      return res.data
    },
  })

  const types: ObjectTypeData[] =
    data?.object_types && data.object_types.length > 0
      ? data.object_types
      : buildFallback()

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Object Types</h1>
        <p className="text-sm text-gray-500 mt-1">
          {OBJECT_TYPES.length} object types in the Satorix ontology
        </p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load live schema data — showing structural defaults.
        </div>
      )}

      <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        {isLoading ? (
          <div className="p-8 text-center text-sm text-gray-400">Loading object types…</div>
        ) : types.length === 0 ? (
          <div className="flex flex-col items-center py-16 text-gray-400">
            <Layers size={36} className="mb-3 opacity-30" />
            <p className="text-sm">No object types found</p>
          </div>
        ) : (
          <table className="w-full text-left">
            <thead>
              <tr className="border-b border-gray-100 bg-gray-50">
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider w-6" />
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Object Type</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Display Name</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Properties</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Instances</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Last Modified</th>
                <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Neo4j</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-gray-50">
              {types.map(ot => (
                <>
                  <tr
                    key={ot.name}
                    className="hover:bg-gray-50 cursor-pointer transition-colors"
                    onClick={() => setExpandedType(t => (t === ot.name ? null : ot.name))}
                  >
                    <td className="px-4 py-3 text-gray-400">
                      {expandedType === ot.name ? (
                        <ChevronDown size={14} />
                      ) : (
                        <ChevronRight size={14} />
                      )}
                    </td>
                    <td className="px-4 py-3">
                      <span className="font-mono text-sm font-medium text-gray-900">{ot.name}</span>
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-600">{ot.display_name}</td>
                    <td className="px-4 py-3 text-sm tabular-nums text-gray-700">
                      {ot.property_count != null ? ot.property_count : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm tabular-nums text-gray-700">
                      {ot.instance_count != null ? ot.instance_count.toLocaleString() : '—'}
                    </td>
                    <td className="px-4 py-3 text-sm text-gray-500">{ot.last_modified}</td>
                    <td className="px-4 py-3">
                      <a
                        href={`${NEO4J_BROWSER_URL}/browser/?cmd=edit&arg=MATCH (n:${NEO4J_LABEL_MAP[ot.name] ?? ot.display_name.replace(/\s/g, '')}) RETURN n LIMIT 25`}
                        target="_blank"
                        rel="noreferrer"
                        onClick={e => e.stopPropagation()}
                        className="inline-flex items-center gap-1 text-xs text-gray-400 hover:text-gray-700 transition-colors"
                      >
                        <ExternalLink size={12} />
                        View
                      </a>
                    </td>
                  </tr>
                  {expandedType === ot.name && (
                    <tr key={`${ot.name}-expand`}>
                      <td colSpan={7} className="bg-gray-50 px-8 py-4 border-t border-gray-100">
                        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                          Properties — {ot.display_name}
                        </p>
                        {ot.properties.length === 0 ? (
                          <p className="text-xs text-gray-400">No property data available from API</p>
                        ) : (
                          <table className="text-xs w-full max-w-3xl">
                            <thead>
                              <tr className="text-gray-400 border-b border-gray-200">
                                <th className="text-left pb-2 pr-6 font-semibold">Property Name</th>
                                <th className="text-left pb-2 pr-6 font-semibold">Type</th>
                                <th className="text-left pb-2 pr-6 font-semibold">Required</th>
                                <th className="text-left pb-2 pr-6 font-semibold">Completeness</th>
                                <th className="text-left pb-2 font-semibold">Source</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-gray-100">
                              {ot.properties.map(prop => (
                                <tr key={prop.property_name}>
                                  <td className="py-2 pr-6 font-mono text-gray-800">{prop.property_name}</td>
                                  <td className="py-2 pr-6 text-gray-500">{prop.type}</td>
                                  <td className="py-2 pr-6">
                                    {prop.required ? (
                                      <span className="text-gray-800 font-medium">Yes</span>
                                    ) : (
                                      <span className="text-gray-400">No</span>
                                    )}
                                  </td>
                                  <td className="py-2 pr-6">
                                    <div className="flex items-center gap-2">
                                      <div className="w-16 h-1.5 bg-gray-200 rounded-full overflow-hidden">
                                        <div
                                          className={clsx(
                                            'h-full rounded-full',
                                            prop.completeness_pct >= 80
                                              ? 'bg-green-500'
                                              : prop.completeness_pct >= 50
                                              ? 'bg-amber-400'
                                              : 'bg-red-400',
                                          )}
                                          style={{ width: `${prop.completeness_pct}%` }}
                                        />
                                      </div>
                                      <span className={clsx('font-semibold tabular-nums', coverageColor(prop.completeness_pct))}>
                                        {prop.completeness_pct}%
                                      </span>
                                    </div>
                                  </td>
                                  <td className="py-2 text-gray-500">{prop.source}</td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        )}
                      </td>
                    </tr>
                  )}
                </>
              ))}
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}
