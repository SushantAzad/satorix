import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import {
  BarChart,
  Bar,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
} from 'recharts'
import StatusBadge from '../components/StatusBadge'
import clsx from 'clsx'

interface MLModel {
  name: string
  version: string
  last_trained: string
  predictions_today: number
  auc_roc: number
  status: 'healthy' | 'degraded' | 'unknown'
  model_status: 'Active' | 'Training' | 'Fallback'
}

interface LLMUsage {
  workflow: string
  calls: number
  tokens: number
}

interface LLMMetrics {
  calls_today: number
  cache_hit_rate: number
  avg_latency_ms: number
  usage_by_workflow: LLMUsage[]
}

interface ModelPerformanceResponse {
  models: MLModel[]
  llm: LLMMetrics
}

const FALLBACK: ModelPerformanceResponse = {
  models: [
    {
      name: 'cirp_precursor',
      version: 'v2.1.0',
      last_trained: '2025-04-28',
      predictions_today: 0,
      auc_roc: 0,
      status: 'unknown',
      model_status: 'Active',
    },
    {
      name: 'project_completion',
      version: 'v1.3.2',
      last_trained: '2025-04-20',
      predictions_today: 0,
      auc_roc: 0,
      status: 'unknown',
      model_status: 'Active',
    },
    {
      name: 'regulatory_likelihood',
      version: 'v1.0.5',
      last_trained: '2025-04-15',
      predictions_today: 0,
      auc_roc: 0,
      status: 'unknown',
      model_status: 'Active',
    },
  ],
  llm: {
    calls_today: 0,
    cache_hit_rate: 0,
    avg_latency_ms: 0,
    usage_by_workflow: [
      { workflow: 'narrative', calls: 0, tokens: 0 },
      { workflow: 'report', calls: 0, tokens: 0 },
      { workflow: 'agent', calls: 0, tokens: 0 },
    ],
  },
}

const MODEL_STATUS_COLORS: Record<string, string> = {
  Active: 'bg-green-50 text-green-700 border-green-200',
  Training: 'bg-blue-50 text-blue-700 border-blue-200',
  Fallback: 'bg-amber-50 text-amber-700 border-amber-200',
}

export default function ModelPerformance() {
  const { data, isLoading, isError } = useQuery<ModelPerformanceResponse>({
    queryKey: ['model-performance'],
    queryFn: async () => {
      const res = await axios.get<ModelPerformanceResponse>(
        '/api/v1/operational/model-performance',
      )
      return res.data
    },
    refetchInterval: 60_000,
  })

  const display = data ?? FALLBACK

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">ML Model Performance</h1>
        <p className="text-sm text-gray-500 mt-1">Model health, scores, and LLM usage metrics</p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load model metrics.
        </div>
      )}

      {isLoading ? (
        <div className="space-y-4">
          {[1, 2, 3].map(i => <div key={i} className="h-36 bg-gray-100 rounded-xl animate-pulse" />)}
        </div>
      ) : (
        <div className="space-y-6">
          {/* ML Models */}
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
            {display.models.map(model => (
              <div key={model.name} className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
                <div className="flex items-start justify-between mb-4">
                  <div>
                    <p className="font-semibold text-gray-900 text-sm">{model.name}</p>
                    <p className="text-xs text-gray-400 mt-0.5">{model.version}</p>
                  </div>
                  <span
                    className={clsx(
                      'text-xs font-medium px-2 py-0.5 rounded-md border',
                      MODEL_STATUS_COLORS[model.model_status] ?? 'bg-gray-50 text-gray-600 border-gray-200',
                    )}
                  >
                    {model.model_status}
                  </span>
                </div>

                <div className="space-y-3">
                  <div>
                    <div className="flex justify-between text-xs mb-1">
                      <span className="text-gray-500">AUC-ROC</span>
                      <span
                        className={clsx(
                          'font-semibold tabular-nums',
                          model.auc_roc >= 0.8
                            ? 'text-green-600'
                            : model.auc_roc > 0
                            ? 'text-amber-500'
                            : 'text-gray-400',
                        )}
                      >
                        {model.auc_roc > 0 ? model.auc_roc.toFixed(3) : '—'}
                      </span>
                    </div>
                    <div className="h-1.5 bg-gray-100 rounded-full overflow-hidden">
                      <div
                        className={clsx(
                          'h-full rounded-full',
                          model.auc_roc >= 0.8 ? 'bg-green-500' : 'bg-amber-400',
                        )}
                        style={{ width: `${model.auc_roc * 100}%` }}
                      />
                    </div>
                  </div>

                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Predictions today</span>
                    <span className="font-semibold text-gray-800 tabular-nums">
                      {model.predictions_today.toLocaleString()}
                    </span>
                  </div>

                  <div className="flex justify-between text-xs">
                    <span className="text-gray-500">Last trained</span>
                    <span className="text-gray-600">{model.last_trained}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* LLM Section */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
            <h2 className="font-semibold text-gray-900 mb-4">LLM Usage (Claude)</h2>

            <div className="grid grid-cols-3 gap-4 mb-6">
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">API Calls Today</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">
                  {display.llm.calls_today.toLocaleString()}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">Cache Hit Rate</p>
                <p
                  className={clsx(
                    'text-2xl font-bold tabular-nums',
                    display.llm.cache_hit_rate >= 60 ? 'text-green-600' : 'text-amber-500',
                  )}
                >
                  {display.llm.cache_hit_rate > 0 ? `${display.llm.cache_hit_rate}%` : '—'}
                </p>
              </div>
              <div className="bg-gray-50 rounded-lg p-4">
                <p className="text-xs text-gray-500 mb-1">Avg Latency</p>
                <p className="text-2xl font-bold text-gray-900 tabular-nums">
                  {display.llm.avg_latency_ms > 0 ? `${display.llm.avg_latency_ms}ms` : '—'}
                </p>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
                Token Usage by Workflow
              </p>
              <ResponsiveContainer width="100%" height={140}>
                <BarChart data={display.llm.usage_by_workflow} margin={{ left: 0, right: 16 }}>
                  <XAxis dataKey="workflow" tick={{ fontSize: 12 }} />
                  <YAxis tick={{ fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{ fontSize: 12, borderRadius: 8, border: '1px solid #e5e7eb' }}
                    formatter={(val: number) => [val.toLocaleString(), 'tokens']}
                  />
                  <Bar dataKey="tokens" fill="#111827" radius={[4, 4, 0, 0]} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}
