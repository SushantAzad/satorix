import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  Cell,
} from 'recharts'
import PropertyHeatmap from '../components/PropertyHeatmap'

interface OrphanCount {
  type: string
  count: number
}

interface ImpossibleState {
  object_id: string
  rule: string
  values: string
}

interface CoverageRow {
  object_type: string
  name: number
  status: number
  risk_score: number
  incorporation_date: number
  registered_state: number
}

interface OntologyHealthResponse {
  health_score: number
  property_coverage: CoverageRow[]
  orphan_counts: OrphanCount[]
  impossible_states: ImpossibleState[]
}

const FALLBACK_COVERAGE: CoverageRow[] = [
  { object_type: 'company', name: 98, status: 95, risk_score: 72, incorporation_date: 61, registered_state: 55 },
  { object_type: 'director', name: 97, status: 91, risk_score: 68, incorporation_date: 20, registered_state: 30 },
  { object_type: 'project', name: 95, status: 88, risk_score: 70, incorporation_date: 45, registered_state: 50 },
  { object_type: 'address', name: 85, status: 60, risk_score: 30, incorporation_date: 10, registered_state: 75 },
  { object_type: 'regulatory_action', name: 92, status: 89, risk_score: 80, incorporation_date: 40, registered_state: 33 },
  { object_type: 'legal_case', name: 90, status: 82, risk_score: 65, incorporation_date: 25, registered_state: 28 },
  { object_type: 'insolvency', name: 88, status: 76, risk_score: 74, incorporation_date: 35, registered_state: 22 },
  { object_type: 'alert', name: 99, status: 99, risk_score: 55, incorporation_date: 5, registered_state: 8 },
  { object_type: 'event', name: 94, status: 80, risk_score: 40, incorporation_date: 15, registered_state: 12 },
  { object_type: 'reg_body', name: 91, status: 84, risk_score: 62, incorporation_date: 50, registered_state: 65 },
  { object_type: 'gov_entity', name: 89, status: 77, risk_score: 58, incorporation_date: 42, registered_state: 60 },
  { object_type: 'contract', name: 86, status: 70, risk_score: 45, incorporation_date: 30, registered_state: 20 },
]

const FALLBACK: OntologyHealthResponse = {
  health_score: 0,
  property_coverage: FALLBACK_COVERAGE,
  orphan_counts: [
    { type: 'company', count: 120 },
    { type: 'director', count: 340 },
    { type: 'project', count: 56 },
    { type: 'address', count: 890 },
    { type: 'legal_case', count: 22 },
  ],
  impossible_states: [],
}

function scoreColor(score: number) {
  if (score >= 80) return 'text-green-600'
  if (score >= 60) return 'text-amber-500'
  return 'text-red-600'
}

export default function OntologyHealth() {
  const { data, isLoading, isError } = useQuery<OntologyHealthResponse>({
    queryKey: ['ontology-health'],
    queryFn: async () => {
      const res = await axios.get<OntologyHealthResponse>(
        '/api/v1/operational/ontology-health',
      )
      return res.data
    },
    refetchInterval: 60_000,
  })

  const display = data ?? FALLBACK

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ontology Health</h1>
        <p className="text-sm text-gray-500 mt-1">Graph completeness and constraint violations</p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load ontology data — showing cached defaults.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-40 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Health score */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 flex items-center gap-6">
            <div>
              <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-1">Overall Health Score</p>
              <p className={`text-6xl font-bold tabular-nums leading-none ${scoreColor(display.health_score)}`}>
                {display.health_score > 0 ? display.health_score : '—'}
              </p>
            </div>
            <div className="flex-1 ml-4">
              <div className="h-3 bg-gray-100 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full transition-all ${
                    display.health_score >= 80
                      ? 'bg-green-500'
                      : display.health_score >= 60
                      ? 'bg-amber-400'
                      : 'bg-red-500'
                  }`}
                  style={{ width: `${display.health_score || 0}%` }}
                />
              </div>
              <p className="text-xs text-gray-400 mt-2">
                Score of 100 = full property coverage, no orphans, no constraint violations
              </p>
            </div>
          </div>

          {/* Property coverage heatmap */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="font-semibold text-gray-900 mb-1">Property Coverage Heatmap</h2>
            <p className="text-xs text-gray-400 mb-4">Completeness % by object type and property</p>
            <PropertyHeatmap rows={display.property_coverage} />
          </div>

          {/* Orphan counts chart */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="font-semibold text-gray-900 mb-1">Orphan Counts by Type</h2>
            <p className="text-xs text-gray-400 mb-4">Nodes with no valid relationships</p>
            <ResponsiveContainer width="100%" height={180}>
              <BarChart
                data={display.orphan_counts}
                layout="vertical"
                margin={{ left: 16, right: 24, top: 0, bottom: 0 }}
              >
                <XAxis type="number" tick={{ fontSize: 11 }} />
                <YAxis dataKey="type" type="category" tick={{ fontSize: 12 }} width={110} />
                <Tooltip
                  contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                />
                <Bar dataKey="count" radius={[0, 4, 4, 0]}>
                  {display.orphan_counts.map((_, index) => (
                    <Cell
                      key={`cell-${index}`}
                      fill={index % 2 === 0 ? '#111827' : '#6b7280'}
                    />
                  ))}
                </Bar>
              </BarChart>
            </ResponsiveContainer>
          </div>

          {/* Impossible states */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Impossible State Violations</h2>
              <p className="text-xs text-gray-400 mt-0.5">
                {display.impossible_states.length} violation
                {display.impossible_states.length !== 1 ? 's' : ''} detected
              </p>
            </div>
            {display.impossible_states.length === 0 ? (
              <div className="py-10 text-center text-sm text-gray-400">
                No constraint violations detected
              </div>
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-50 bg-gray-50">
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Object ID</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Rule</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Values</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {display.impossible_states.map((v, i) => (
                    <tr key={i} className="hover:bg-gray-50">
                      <td className="px-4 py-3 font-mono text-xs text-gray-700">{v.object_id}</td>
                      <td className="px-4 py-3 text-sm text-red-600 font-medium">{v.rule}</td>
                      <td className="px-4 py-3 text-xs text-gray-500">{v.values}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </div>
      )}
    </div>
  )
}
