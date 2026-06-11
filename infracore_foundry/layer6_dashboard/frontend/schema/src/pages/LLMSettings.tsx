import { useState, useEffect } from 'react'
import axios from 'axios'
import { Activity, Copy, Play, RefreshCw, Zap } from 'lucide-react'
import clsx from 'clsx'

const API = '/api/v1/operational/llm'

interface ProviderStatus {
  provider: string
  model: string
  healthy: boolean
  latency_ms: number | null
  available_models: string[]
  error: string | null
}

interface ModelEntry {
  name: string
  size_gb: number | null
  family: string
}

interface ModelsResponse {
  provider: string
  current_model: string
  available_models: ModelEntry[]
  error?: string
}

interface TestResult {
  provider: string
  model: string
  response: string | null
  latency_ms: number
  tokens_used?: number
  error?: string
}

const RAM_RECOMMENDATIONS = [
  { ram: '4-8 GB',   model: 'phi4-mini:3.8b', pull: 'ollama pull phi4-mini',  note: 'Lightweight, fast' },
  { ram: '8-16 GB',  model: 'qwen3:8b',        pull: 'ollama pull qwen3:8b',   note: 'Default · Recommended' },
  { ram: '16-32 GB', model: 'qwen3:14b',        pull: 'ollama pull qwen3:14b',  note: 'Better extraction quality' },
  { ram: '32 GB+',   model: 'qwen3:30b',        pull: 'ollama pull qwen3:30b',  note: 'Best for complex documents' },
]

function StatusDot({ healthy }: { healthy: boolean | null }) {
  if (healthy === null) return <span className="w-2.5 h-2.5 rounded-full bg-gray-300 flex-shrink-0" />
  return (
    <span
      className={clsx(
        'w-2.5 h-2.5 rounded-full flex-shrink-0',
        healthy ? 'bg-green-500' : 'bg-red-500',
      )}
    />
  )
}

export default function LLMSettings() {
  const [status, setStatus] = useState<ProviderStatus | null>(null)
  const [statusLoading, setStatusLoading] = useState(false)
  const [models, setModels] = useState<ModelsResponse | null>(null)
  const [testPrompt, setTestPrompt] = useState(
    'Explain what CIRP means in Indian corporate law in 2 sentences.',
  )
  const [testResult, setTestResult] = useState<TestResult | null>(null)
  const [testLoading, setTestLoading] = useState(false)
  const [copiedCmd, setCopiedCmd] = useState<string | null>(null)

  useEffect(() => {
    fetchStatus()
    fetchModels()
    const interval = setInterval(fetchStatus, 30_000)
    return () => clearInterval(interval)
  }, [])

  async function fetchStatus() {
    setStatusLoading(true)
    try {
      const res = await axios.get<ProviderStatus>(`${API}/status`)
      setStatus(res.data)
    } catch {
      setStatus(null)
    } finally {
      setStatusLoading(false)
    }
  }

  async function fetchModels() {
    try {
      const res = await axios.get<ModelsResponse>(`${API}/models`)
      setModels(res.data)
    } catch {
      setModels(null)
    }
  }

  async function runTest() {
    setTestLoading(true)
    setTestResult(null)
    try {
      const res = await axios.post<TestResult>(`${API}/test`, { prompt: testPrompt }, { timeout: 180_000 })
      setTestResult(res.data)
    } catch (err) {
      const msg = axios.isAxiosError(err) ? err.response?.data?.detail ?? err.message : String(err)
      setTestResult({ provider: '?', model: '?', response: null, latency_ms: 0, error: String(msg) })
    } finally {
      setTestLoading(false)
    }
  }

  function copyToClipboard(text: string) {
    navigator.clipboard.writeText(text).then(() => {
      setCopiedCmd(text)
      setTimeout(() => setCopiedCmd(null), 1500)
    })
  }

  return (
    <div className="p-8 max-w-4xl">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">LLM Provider</h1>
        <p className="text-sm text-gray-500 mt-1">
          Configure and test the inference provider used across Layers 4, 5, and 6
        </p>
      </div>

      {/* ── 1. Provider Status Card ─────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-5">
        <div className="flex items-center justify-between mb-4">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">Provider Status</p>
          <button
            onClick={fetchStatus}
            disabled={statusLoading}
            className="flex items-center gap-1.5 text-xs text-gray-500 hover:text-gray-900 border border-gray-200 rounded-lg px-2.5 py-1.5 hover:bg-gray-50 disabled:opacity-40 transition-colors"
          >
            <RefreshCw size={12} className={statusLoading ? 'animate-spin' : ''} />
            {statusLoading ? 'Checking…' : 'Run Health Check'}
          </button>
        </div>

        {status ? (
          <div className="flex items-center gap-4">
            <div
              className={clsx(
                'w-14 h-14 rounded-2xl flex items-center justify-center flex-shrink-0',
                status.healthy ? 'bg-green-50 border-2 border-green-200' : 'bg-red-50 border-2 border-red-200',
              )}
            >
              <Activity
                size={24}
                className={status.healthy ? 'text-green-600' : 'text-red-500'}
              />
            </div>
            <div className="flex-1">
              <div className="flex items-center gap-2 mb-1">
                <StatusDot healthy={status.healthy} />
                <span className="text-sm font-semibold text-gray-900 capitalize">
                  {status.provider}
                </span>
                <span className="text-xs text-gray-400 font-mono">{status.model}</span>
                {status.healthy && (
                  <span className="px-1.5 py-0.5 bg-green-50 text-green-700 text-xs font-medium rounded">
                    Healthy
                  </span>
                )}
                {!status.healthy && (
                  <span className="px-1.5 py-0.5 bg-red-50 text-red-700 text-xs font-medium rounded">
                    Unhealthy
                  </span>
                )}
              </div>
              {status.latency_ms !== null && (
                <p className="text-xs text-gray-400">Response time: {status.latency_ms}ms</p>
              )}
              {status.error && (
                <p className="text-xs text-red-600 mt-1 font-mono">{status.error}</p>
              )}
            </div>
          </div>
        ) : (
          <div className="flex items-center gap-3 text-sm text-gray-400">
            <StatusDot healthy={null} />
            {statusLoading ? 'Checking provider health…' : 'Click "Run Health Check" to check status'}
          </div>
        )}
      </section>

      {/* ── 2. Provider Cards ───────────────────────────────────────────── */}
      <section className="mb-5">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-3">
          Active Provider
          <span className="ml-2 font-normal text-gray-400 normal-case">
            — switch via LLM_PROVIDER env var; restart required in production
          </span>
        </p>
        <div className="grid grid-cols-2 gap-4">
          {/* Anthropic */}
          <div
            className={clsx(
              'rounded-xl border-2 p-5 transition-colors',
              status?.provider === 'anthropic'
                ? 'border-gray-900 bg-gray-50'
                : 'border-gray-200 bg-white',
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Zap size={16} className="text-orange-500" />
                <span className="text-sm font-semibold text-gray-900">Anthropic</span>
              </div>
              {status?.provider === 'anthropic' && (
                <span className="text-xs px-2 py-0.5 bg-gray-900 text-white rounded-full">Active</span>
              )}
            </div>
            <p className="text-xs font-mono text-gray-500 mb-1">
              {status?.provider === 'anthropic' ? status.model : 'claude-sonnet-4-6'}
            </p>
            <p className="text-xs text-gray-400 mb-4">Production · Highest quality · Requires API key</p>
            <div className="text-xs font-mono bg-gray-100 rounded-lg px-3 py-2 text-gray-600">
              LLM_PROVIDER=anthropic
            </div>
          </div>

          {/* Ollama */}
          <div
            className={clsx(
              'rounded-xl border-2 p-5 transition-colors',
              status?.provider === 'ollama'
                ? 'border-gray-900 bg-gray-50'
                : 'border-gray-200 bg-white',
            )}
          >
            <div className="flex items-center justify-between mb-3">
              <div className="flex items-center gap-2">
                <Activity size={16} className="text-blue-500" />
                <span className="text-sm font-semibold text-gray-900">Ollama (Local)</span>
              </div>
              {status?.provider === 'ollama' && (
                <span className="text-xs px-2 py-0.5 bg-gray-900 text-white rounded-full">Active</span>
              )}
            </div>
            <p className="text-xs font-mono text-gray-500 mb-1">
              {status?.provider === 'ollama'
                ? status.model
                : models?.current_model ?? 'qwen3:8b'}
            </p>
            <p className="text-xs text-gray-400 mb-4">Free · No API key · Works offline</p>
            <div className="text-xs font-mono bg-gray-100 rounded-lg px-3 py-2 text-gray-600">
              LLM_PROVIDER=ollama
            </div>
          </div>
        </div>
      </section>

      {/* ── 3. Test Panel ───────────────────────────────────────────────── */}
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm p-6 mb-5">
        <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-4">Test Completion</p>
        <textarea
          value={testPrompt}
          onChange={e => setTestPrompt(e.target.value)}
          rows={3}
          className="w-full text-sm border border-gray-200 rounded-lg px-3 py-2.5 resize-none focus:outline-none focus:ring-2 focus:ring-gray-900/10 placeholder-gray-300 mb-3"
          placeholder="Enter a test prompt…"
        />
        <button
          onClick={runTest}
          disabled={testLoading || !testPrompt.trim()}
          className="flex items-center gap-2 px-4 py-2 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
        >
          <Play size={13} />
          {testLoading ? 'Running…' : 'Run Test'}
        </button>
        {testLoading && (
          <p className="text-xs text-gray-400 mt-2">
            Ollama loads the model into RAM on first request — this may take 30–90 seconds.
          </p>
        )}

        {testResult && (
          <div className="mt-4">
            <div className="flex items-center gap-3 text-xs text-gray-400 mb-2">
              <span className="font-medium text-gray-600 capitalize">{testResult.provider}</span>
              <span className="font-mono">{testResult.model}</span>
              <span>{testResult.latency_ms}ms</span>
              {testResult.tokens_used !== undefined && <span>{testResult.tokens_used} tokens</span>}
            </div>
            {testResult.error ? (
              <pre className="text-xs font-mono text-red-700 bg-red-50 border border-red-200 rounded-xl p-4 whitespace-pre-wrap">
                {testResult.error}
              </pre>
            ) : (
              <pre className="text-xs font-mono text-gray-800 bg-gray-50 border border-gray-100 rounded-xl p-4 whitespace-pre-wrap leading-relaxed">
                {testResult.response}
              </pre>
            )}
          </div>
        )}
      </section>

      {/* ── 4. Model Recommendations Table ─────────────────────────────── */}
      <section className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
        <div className="px-6 py-4 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider">
            Ollama Model Recommendations
          </p>
        </div>
        <table className="w-full text-sm">
          <thead>
            <tr className="border-b border-gray-100 text-xs text-gray-400 font-medium">
              <th className="text-left px-6 py-3">RAM Available</th>
              <th className="text-left px-6 py-3">Recommended Model</th>
              <th className="text-left px-6 py-3">Note</th>
              <th className="text-left px-6 py-3">Pull Command</th>
            </tr>
          </thead>
          <tbody>
            {RAM_RECOMMENDATIONS.map((row, i) => (
              <tr
                key={row.model}
                className={clsx(
                  'border-b border-gray-50 last:border-b-0',
                  status?.model === row.model ? 'bg-green-50' : i % 2 === 0 ? 'bg-white' : 'bg-gray-50/40',
                )}
              >
                <td className="px-6 py-3 text-gray-700 font-medium">{row.ram}</td>
                <td className="px-6 py-3">
                  <div className="flex items-center gap-2">
                    <span className="font-mono text-gray-800">{row.model}</span>
                    {status?.model === row.model && (
                      <span className="text-xs px-1.5 py-0.5 bg-green-100 text-green-700 rounded font-medium">
                        Active
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-6 py-3 text-gray-400 text-xs">{row.note}</td>
                <td className="px-6 py-3">
                  <div className="flex items-center gap-2">
                    <code className="text-xs font-mono text-gray-600 bg-gray-100 px-2 py-1 rounded">
                      {row.pull}
                    </code>
                    <button
                      onClick={() => copyToClipboard(row.pull)}
                      className="p-1 text-gray-400 hover:text-gray-700 transition-colors"
                      title="Copy command"
                    >
                      <Copy size={12} />
                    </button>
                    {copiedCmd === row.pull && (
                      <span className="text-xs text-green-600 font-medium">Copied!</span>
                    )}
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>

        {/* Locally available models (if Ollama) */}
        {models && models.provider === 'ollama' && models.available_models.length > 0 && (
          <div className="px-6 py-4 border-t border-gray-100 bg-gray-50">
            <p className="text-xs font-semibold text-gray-500 uppercase tracking-wider mb-2">
              Locally Available
            </p>
            <div className="flex flex-wrap gap-2">
              {models.available_models.map(m => (
                <span
                  key={m.name}
                  className={clsx(
                    'text-xs font-mono px-2.5 py-1 rounded-lg border',
                    m.name === models.current_model
                      ? 'bg-gray-900 text-white border-gray-900'
                      : 'bg-white text-gray-600 border-gray-200',
                  )}
                >
                  {m.name}
                  {m.size_gb ? ` · ${m.size_gb}GB` : ''}
                </span>
              ))}
            </div>
          </div>
        )}
      </section>
    </div>
  )
}
