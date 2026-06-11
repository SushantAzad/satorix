import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import {
  LineChart,
  Line,
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  PieChart,
  Pie,
  Cell,
  Legend,
} from 'recharts'
import { Bell } from 'lucide-react'

interface DailyAlert {
  date: string
  critical: number
  high: number
  medium: number
  low: number
}

interface AlertByType {
  type: string
  count: number
}

interface TopEntity {
  entity_id: string
  entity_name: string
  entity_type: string
  alert_count: number
}

interface AlertAnalyticsResponse {
  daily_alerts: DailyAlert[]
  alerts_by_type: AlertByType[]
  acknowledged: number
  unacknowledged: number
  top_entities: TopEntity[]
}

const FALLBACK: AlertAnalyticsResponse = {
  daily_alerts: [],
  alerts_by_type: [
    { type: 'CIRP_CONTAGION', count: 0 },
    { type: 'DIRECTOR_PROLIFERATION', count: 0 },
    { type: 'REGULATORY_ACTION', count: 0 },
    { type: 'FINANCIAL_STRESS', count: 0 },
    { type: 'OWNERSHIP_CHANGE', count: 0 },
  ],
  acknowledged: 0,
  unacknowledged: 0,
  top_entities: [],
}

const SEVERITY_COLORS = {
  critical: '#ef4444',
  high: '#f97316',
  medium: '#f59e0b',
  low: '#6b7280',
}

const DONUT_COLORS = ['#22c55e', '#f59e0b']

export default function AlertAnalytics() {
  const { data, isLoading, isError } = useQuery<AlertAnalyticsResponse>({
    queryKey: ['alert-analytics'],
    queryFn: async () => {
      const res = await axios.get<AlertAnalyticsResponse>(
        '/api/v1/operational/alert-analytics?days=30',
      )
      return res.data
    },
    refetchInterval: 120_000,
  })

  const display = data ?? FALLBACK
  const donutData = [
    { name: 'Acknowledged', value: display.acknowledged },
    { name: 'Unacknowledged', value: display.unacknowledged },
  ]
  const totalAlerts = display.acknowledged + display.unacknowledged

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Alert Volume Analytics</h1>
        <p className="text-sm text-gray-500 mt-1">Last 30 days · Auto-refresh every 2 min</p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load alert analytics.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-52 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-6">
          {/* Daily alerts line chart */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="font-semibold text-gray-900 mb-1">Daily Alert Volume</h2>
            <p className="text-xs text-gray-400 mb-4">Stacked by severity over 30 days</p>
            {display.daily_alerts.length === 0 ? (
              <div className="flex flex-col items-center justify-center h-40 text-gray-300">
                <Bell size={32} className="mb-2 opacity-50" />
                <p className="text-sm">No alert data for this period</p>
              </div>
            ) : (
              <ResponsiveContainer width="100%" height={200}>
                <LineChart data={display.daily_alerts} margin={{ left: 0, right: 16 }}>
                  <XAxis dataKey="date" tick={{ fontSize: 10 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                  <Legend wrapperStyle={{ fontSize: 12 }} />
                  <Line type="monotone" dataKey="critical" stroke={SEVERITY_COLORS.critical} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="high" stroke={SEVERITY_COLORS.high} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="medium" stroke={SEVERITY_COLORS.medium} strokeWidth={2} dot={false} />
                  <Line type="monotone" dataKey="low" stroke={SEVERITY_COLORS.low} strokeWidth={1.5} dot={false} />
                </LineChart>
              </ResponsiveContainer>
            )}
          </div>

          {/* Bottom row: type bar + donut */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            {/* Alerts by type */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <h2 className="font-semibold text-gray-900 mb-1">Alerts by Type</h2>
              <p className="text-xs text-gray-400 mb-4">Total count per alert type</p>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={display.alerts_by_type}
                  margin={{ left: 0, right: 16 }}
                >
                  <XAxis dataKey="type" tick={{ fontSize: 9 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                  />
                  <Bar dataKey="count" fill="#111827" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>

            {/* Acknowledged donut */}
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
              <h2 className="font-semibold text-gray-900 mb-1">Acknowledgement Ratio</h2>
              <p className="text-xs text-gray-400 mb-4">
                {totalAlerts.toLocaleString()} total alerts
              </p>
              {totalAlerts === 0 ? (
                <div className="flex flex-col items-center justify-center h-40 text-gray-300">
                  <p className="text-sm">No data</p>
                </div>
              ) : (
                <ResponsiveContainer width="100%" height={200}>
                  <PieChart>
                    <Pie
                      data={donutData}
                      cx="50%"
                      cy="50%"
                      innerRadius={55}
                      outerRadius={80}
                      paddingAngle={3}
                      dataKey="value"
                    >
                      {donutData.map((_, index) => (
                        <Cell key={`cell-${index}`} fill={DONUT_COLORS[index]} />
                      ))}
                    </Pie>
                    <Tooltip
                      contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    />
                    <Legend wrapperStyle={{ fontSize: 12 }} />
                  </PieChart>
                </ResponsiveContainer>
              )}
            </div>
          </div>

          {/* Top entities table */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
            <div className="px-6 py-4 border-b border-gray-100">
              <h2 className="font-semibold text-gray-900">Top 10 Entities by Alert Count</h2>
              <p className="text-xs text-gray-400 mt-0.5">Most flagged entities in the last 30 days</p>
            </div>
            {display.top_entities.length === 0 ? (
              <div className="py-12 text-center text-gray-400 text-sm">
                No entity data available
              </div>
            ) : (
              <table className="w-full text-left">
                <thead>
                  <tr className="border-b border-gray-50 bg-gray-50">
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">#</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Entity Name</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Type</th>
                    <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Alert Count</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-gray-50">
                  {display.top_entities.slice(0, 10).map((entity, i) => (
                    <tr key={entity.entity_id} className="hover:bg-gray-50">
                      <td className="px-4 py-3 text-sm text-gray-400 tabular-nums">{i + 1}</td>
                      <td className="px-4 py-3">
                        <p className="font-medium text-sm text-gray-900">{entity.entity_name}</p>
                        <p className="text-xs font-mono text-gray-400">{entity.entity_id}</p>
                      </td>
                      <td className="px-4 py-3 text-sm text-gray-500 capitalize">{entity.entity_type}</td>
                      <td className="px-4 py-3">
                        <span className="font-bold text-gray-900 tabular-nums">{entity.alert_count}</span>
                      </td>
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
