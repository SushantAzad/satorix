import { useState, useRef } from 'react'
import axios from 'axios'
import { Play, Clock, ChevronDown } from 'lucide-react'

interface FunctionDef {
  name: string
  description: string
  endpoint: string
  method: 'GET' | 'POST'
  params: { key: string; label: string; placeholder: string; required: boolean }[]
}

const FUNCTIONS: FunctionDef[] = [
  {
    name: 'computeGroupRiskScore',
    description: 'Compute the corporate group risk score for a company',
    endpoint: '/api/v1/companies/:cin/group-risk-score',
    method: 'GET',
    params: [
      { key: 'cin', label: 'CIN', placeholder: 'L17110MH1973PLC019786', required: true },
    ],
  },
  {
    name: 'computeBeneficialOwnershipChain',
    description: 'Trace beneficial ownership chain up to max_depth levels',
    endpoint: '/api/v1/companies/:cin/beneficial-ownership',
    method: 'GET',
    params: [
      { key: 'cin', label: 'CIN', placeholder: 'L17110MH1973PLC019786', required: true },
      { key: 'max_depth', label: 'Max Depth', placeholder: '5', required: false },
    ],
  },
  {
    name: 'assessCIRPContagionRisk',
    description: 'Assess CIRP contagion risk spread from a company',
    endpoint: '/api/v1/companies/:cin/cirp-contagion',
    method: 'GET',
    params: [
      { key: 'cin', label: 'CIN', placeholder: 'L17110MH1973PLC019786', required: true },
    ],
  },
  {
    name: 'predictProjectCompletionProbability',
    description: 'ML prediction of project completion probability',
    endpoint: '/api/v1/projects/:projectId/completion-probability',
    method: 'GET',
    params: [
      { key: 'projectId', label: 'Project ID', placeholder: 'proj_001', required: true },
    ],
  },
  {
    name: 'searchEntities',
    description: 'Full-text and semantic search across all entity types',
    endpoint: '/api/v1/search',
    method: 'GET',
    params: [
      { key: 'query', label: 'Query', placeholder: 'Reliance Industries Ltd', required: true },
    ],
  },
  {
    name: 'generateNarrative',
    description: 'Generate Claude-powered narrative for an entity',
    endpoint: '/api/v1/narratives',
    method: 'POST',
    params: [
      {
        key: 'entity_type',
        label: 'Entity Type',
        placeholder: 'company',
        required: true,
      },
      {
        key: 'entity_id',
        label: 'Entity ID',
        placeholder: 'L17110MH1973PLC019786',
        required: true,
      },
    ],
  },
]

interface ExecutionRecord {
  id: string
  functionName: string
  params: Record<string, string>
  result: unknown
  durationMs: number
  status: 'success' | 'error'
  timestamp: string
}

function buildUrl(fn: FunctionDef, params: Record<string, string>): string {
  let url = fn.endpoint
  for (const [k, v] of Object.entries(params)) {
    url = url.replace(`:${k}`, encodeURIComponent(v))
  }
  // Add remaining params as query string for GET
  if (fn.method === 'GET') {
    const qs = fn.params
      .filter(p => !fn.endpoint.includes(`:${p.key}`) && params[p.key])
      .map(p => `${p.key}=${encodeURIComponent(params[p.key])}`)
      .join('&')
    if (qs) url += `?${qs}`
  }
  return url
}

export default function FunctionTester() {
  const [selectedFn, setSelectedFn] = useState<FunctionDef>(FUNCTIONS[0])
  const [params, setParams] = useState<Record<string, string>>({})
  const [executing, setExecuting] = useState(false)
  const [result, setResult] = useState<unknown | null>(null)
  const [resultStatus, setResultStatus] = useState<'success' | 'error' | null>(null)
  const [lastDuration, setLastDuration] = useState<number | null>(null)
  const [history, setHistory] = useState<ExecutionRecord[]>([])

  function handleSelectFn(name: string) {
    const fn = FUNCTIONS.find(f => f.name === name)!
    setSelectedFn(fn)
    setParams({})
    setResult(null)
    setResultStatus(null)
    setLastDuration(null)
  }

  async function handleExecute() {
    // Validate required params
    for (const p of selectedFn.params) {
      if (p.required && !params[p.key]) return
    }
    setExecuting(true)
    setResult(null)
    const start = Date.now()
    try {
      const url = buildUrl(selectedFn, params)
      let res
      if (selectedFn.method === 'POST') {
        res = await axios.post(url, params)
      } else {
        res = await axios.get(url)
      }
      const duration = Date.now() - start
      setResult(res.data)
      setResultStatus('success')
      setLastDuration(duration)
      setHistory(h =>
        [
          {
            id: crypto.randomUUID(),
            functionName: selectedFn.name,
            params: { ...params },
            result: res.data,
            durationMs: duration,
            status: 'success' as const,
            timestamp: new Date().toLocaleTimeString(),
          },
          ...h,
        ].slice(0, 5),
      )
    } catch (err) {
      const duration = Date.now() - start
      const msg = axios.isAxiosError(err)
        ? err.response?.data ?? err.message
        : String(err)
      setResult(msg)
      setResultStatus('error')
      setLastDuration(duration)
      setHistory(h =>
        [
          {
            id: crypto.randomUUID(),
            functionName: selectedFn.name,
            params: { ...params },
            result: msg,
            durationMs: duration,
            status: 'error' as const,
            timestamp: new Date().toLocaleTimeString(),
          },
          ...h,
        ].slice(0, 5),
      )
    } finally {
      setExecuting(false)
    }
  }

  const canExecute =
    !executing && selectedFn.params.filter(p => p.required).every(p => params[p.key])

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Function Tester</h1>
        <p className="text-sm text-gray-500 mt-1">Execute Layer 3/5 API functions interactively</p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-5 gap-6">
        {/* Left: form */}
        <div className="lg:col-span-2 space-y-4">
          {/* Function selector */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <label className="block text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Function
            </label>
            <div className="relative">
              <select
                value={selectedFn.name}
                onChange={e => handleSelectFn(e.target.value)}
                className="w-full appearance-none text-sm border border-gray-200 rounded-lg px-3 py-2.5 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/10 pr-8"
              >
                {FUNCTIONS.map(f => (
                  <option key={f.name} value={f.name}>
                    {f.name}
                  </option>
                ))}
              </select>
              <ChevronDown size={14} className="absolute right-3 top-1/2 -translate-y-1/2 text-gray-400 pointer-events-none" />
            </div>
            <p className="text-xs text-gray-400 mt-2">{selectedFn.description}</p>
            <p className="text-xs font-mono text-gray-300 mt-1">
              {selectedFn.method} {selectedFn.endpoint}
            </p>
          </div>

          {/* Parameters */}
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Parameters</p>
            <div className="space-y-3">
              {selectedFn.params.map(param => (
                <div key={param.key}>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    {param.label}
                    {param.required && <span className="text-red-400 ml-1">*</span>}
                  </label>
                  <input
                    type="text"
                    placeholder={param.placeholder}
                    value={params[param.key] ?? ''}
                    onChange={e =>
                      setParams(p => ({ ...p, [param.key]: e.target.value }))
                    }
                    className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-gray-900/10 placeholder-gray-300"
                  />
                </div>
              ))}
            </div>

            <button
              onClick={handleExecute}
              disabled={!canExecute}
              className="mt-4 w-full flex items-center justify-center gap-2 py-2.5 text-sm font-semibold bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
            >
              <Play size={14} />
              {executing ? 'Executing…' : 'Execute'}
            </button>
          </div>

          {/* Recent executions */}
          {history.length > 0 && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">Recent Executions</p>
              <div className="space-y-2">
                {history.map(h => (
                  <div
                    key={h.id}
                    className="flex items-center justify-between text-xs border border-gray-100 rounded-lg px-3 py-2 hover:bg-gray-50 cursor-pointer"
                    onClick={() => {
                      setResult(h.result)
                      setResultStatus(h.status)
                      setLastDuration(h.durationMs)
                    }}
                  >
                    <div>
                      <p className="font-medium text-gray-700">{h.functionName}</p>
                      <p className="text-gray-400">{h.timestamp}</p>
                    </div>
                    <div className="flex items-center gap-2 text-right">
                      <span
                        className={`font-semibold ${
                          h.status === 'success' ? 'text-green-600' : 'text-red-600'
                        }`}
                      >
                        {h.status}
                      </span>
                      <span className="text-gray-400 flex items-center gap-0.5">
                        <Clock size={10} />
                        {h.durationMs}ms
                      </span>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>

        {/* Right: result */}
        <div className="lg:col-span-3">
          <div className="bg-white rounded-xl border border-gray-200 shadow-sm h-full flex flex-col">
            <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100">
              <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Response</p>
              {lastDuration !== null && (
                <div className="flex items-center gap-3">
                  <span
                    className={`text-xs font-semibold ${
                      resultStatus === 'success' ? 'text-green-600' : 'text-red-600'
                    }`}
                  >
                    {resultStatus === 'success' ? '200 OK' : 'Error'}
                  </span>
                  <span className="text-xs text-gray-400 flex items-center gap-1">
                    <Clock size={11} />
                    {lastDuration}ms
                  </span>
                </div>
              )}
            </div>

            <div className="flex-1 overflow-auto scrollbar-thin p-5">
              {result === null && !executing && (
                <div className="flex flex-col items-center justify-center h-full text-gray-300 py-16">
                  <Play size={32} className="mb-3 opacity-40" />
                  <p className="text-sm">Select a function and execute to see the response</p>
                </div>
              )}

              {executing && (
                <div className="flex items-center justify-center h-full text-gray-400 py-16">
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 border-2 border-gray-300 border-t-gray-700 rounded-full animate-spin" />
                    <span className="text-sm">Executing…</span>
                  </div>
                </div>
              )}

              {result !== null && !executing && (
                <pre
                  className={`text-xs font-mono leading-relaxed whitespace-pre-wrap break-all rounded-xl p-4 ${
                    resultStatus === 'error'
                      ? 'bg-red-50 text-red-700 border border-red-200'
                      : 'bg-gray-50 text-gray-800 border border-gray-100'
                  }`}
                >
                  {typeof result === 'string'
                    ? result
                    : JSON.stringify(result, null, 2)}
                </pre>
              )}
            </div>
          </div>
        </div>
      </div>
    </div>
  )
}
