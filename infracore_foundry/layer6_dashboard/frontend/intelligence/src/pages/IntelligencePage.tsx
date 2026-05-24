import React, { useState } from 'react'
import { useParams, Link } from 'react-router-dom'
import { useQuery, useMutation } from '@tanstack/react-query'
import { Brain, TrendingUp, AlertTriangle, BarChart2, Send, Loader2, ChevronDown, ChevronUp } from 'lucide-react'
import { intelligenceApi, type RiskSignal } from '@shared/api/intelligence'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'

// ── Severity colours ──────────────────────────────────────────────────────────
const SEV_STYLES: Record<string, string> = {
  critical: 'bg-red-50 border-red-200 text-red-800',
  high:     'bg-orange-50 border-orange-200 text-orange-800',
  medium:   'bg-amber-50 border-amber-200 text-amber-800',
  info:     'bg-blue-50 border-blue-200 text-blue-800',
}

const SEV_DOT: Record<string, string> = {
  critical: 'bg-red-500',
  high:     'bg-orange-500',
  medium:   'bg-amber-500',
  info:     'bg-blue-400',
}

// ── Sub-components ────────────────────────────────────────────────────────────

function RiskSignalCard({ signal }: { signal: RiskSignal }) {
  const val = signal.value
  const formatted = Number.isInteger(val) ? val.toString() : val?.toFixed(2) ?? '—'
  return (
    <div className={`border rounded-lg p-3 flex items-center justify-between gap-3 ${SEV_STYLES[signal.severity] || SEV_STYLES.info}`}>
      <div className="flex items-center gap-2">
        <div className={`w-2 h-2 rounded-full flex-shrink-0 ${SEV_DOT[signal.severity] || SEV_DOT.info}`} />
        <span className="text-sm font-medium">{signal.name}</span>
      </div>
      <span className="text-sm font-mono font-semibold">{formatted}</span>
    </div>
  )
}

function FeatureTable({ features }: { features: Record<string, number | null> }) {
  const [expanded, setExpanded] = useState(false)
  const entries = Object.entries(features).filter(([, v]) => v !== null && v !== undefined)
  const visible = expanded ? entries : entries.slice(0, 8)

  if (!entries.length) return <p className="text-sm text-gray-400">No features computed yet.</p>

  return (
    <div>
      <div className="divide-y divide-gray-100">
        {visible.map(([key, val]) => (
          <div key={key} className="flex justify-between items-center py-1.5 text-sm">
            <span className="text-gray-600 font-mono text-xs">{key}</span>
            <span className="font-medium text-gray-900">
              {typeof val === 'number' ? (Number.isInteger(val) ? val : val.toFixed(4)) : String(val)}
            </span>
          </div>
        ))}
      </div>
      {entries.length > 8 && (
        <button
          onClick={() => setExpanded(e => !e)}
          className="mt-2 text-xs text-blue-600 hover:underline flex items-center gap-1"
        >
          {expanded ? <><ChevronUp className="h-3 w-3" />Show less</> : <><ChevronDown className="h-3 w-3" />Show {entries.length - 8} more</>}
        </button>
      )}
    </div>
  )
}

function PredictionPanel({ prediction }: { prediction: Record<string, unknown> }) {
  if (!prediction || !Object.keys(prediction).length) {
    return <p className="text-sm text-gray-400">No prediction data available.</p>
  }
  const prob = typeof prediction.probability === 'number' ? prediction.probability : null
  const score = typeof prediction.risk_score === 'number' ? prediction.risk_score : null
  const confidence = typeof prediction.confidence === 'number' ? prediction.confidence : null

  return (
    <div className="space-y-3">
      {prob !== null && (
        <div>
          <div className="flex justify-between text-sm mb-1">
            <span className="text-gray-600">CIRP Risk Probability</span>
            <span className="font-semibold text-red-700">{(prob * 100).toFixed(1)}%</span>
          </div>
          <div className="h-2 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full transition-all ${prob > 0.6 ? 'bg-red-500' : prob > 0.3 ? 'bg-amber-500' : 'bg-green-500'}`}
              style={{ width: `${Math.min(prob * 100, 100)}%` }}
            />
          </div>
        </div>
      )}
      {score !== null && (
        <div className="flex justify-between text-sm">
          <span className="text-gray-600">Risk Score</span>
          <span className="font-semibold">{score}/100</span>
        </div>
      )}
      {confidence !== null && (
        <div className="flex justify-between text-sm">
          <span className="text-gray-600">Model Confidence</span>
          <span className="font-medium">{(confidence * 100).toFixed(0)}%</span>
        </div>
      )}
      {prediction.explanation && (
        <p className="text-xs text-gray-500 italic mt-2">{String(prediction.explanation)}</p>
      )}
      {prediction.model_type && (
        <p className="text-xs text-gray-400">Model: {String(prediction.model_type)}</p>
      )}
    </div>
  )
}

// ── Ask Intelligence ──────────────────────────────────────────────────────────

function AskIntelligence({ cin }: { cin?: string }) {
  const [question, setQuestion] = useState('')
  const [answer, setAnswer] = useState<string | null>(null)

  const { mutate, isPending } = useMutation({
    mutationFn: () => intelligenceApi.askQuestion(question, cin),
    onSuccess: (data) => setAnswer(data.answer),
    onError: () => setAnswer('[Could not reach the intelligence engine. Please try again.]'),
  })

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (question.trim().length >= 5) mutate()
  }

  const EXAMPLE_QUESTIONS = cin
    ? [
        `What is the financial health of this company?`,
        `Are there any CIRP risk signals I should know about?`,
        `Who are the key directors and what is their risk profile?`,
      ]
    : [
        'What are the top risk signals for companies in this sector?',
        'Which companies have the highest CIRP probability?',
      ]

  return (
    <div className="space-y-4">
      <form onSubmit={handleSubmit} className="flex gap-2">
        <input
          type="text"
          value={question}
          onChange={e => setQuestion(e.target.value)}
          placeholder="Ask anything about this company…"
          className="flex-1 text-sm border border-gray-200 rounded-lg px-3 py-2 focus:outline-none focus:ring-2 focus:ring-blue-500"
          disabled={isPending}
        />
        <button
          type="submit"
          disabled={isPending || question.trim().length < 5}
          className="flex items-center gap-1.5 px-4 py-2 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
        >
          {isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Send className="h-4 w-4" />}
          Ask
        </button>
      </form>

      {/* Example questions */}
      {!answer && !isPending && (
        <div className="flex flex-wrap gap-2">
          {EXAMPLE_QUESTIONS.map(q => (
            <button
              key={q}
              onClick={() => setQuestion(q)}
              className="text-xs text-blue-600 bg-blue-50 px-2 py-1 rounded-full hover:bg-blue-100 transition-colors"
            >
              {q}
            </button>
          ))}
        </div>
      )}

      {isPending && (
        <div className="flex items-center gap-2 text-sm text-gray-500">
          <Loader2 className="h-4 w-4 animate-spin text-blue-500" />
          Reasoning across the knowledge graph…
        </div>
      )}

      {answer && (
        <div className="bg-gray-50 border border-gray-200 rounded-lg p-4">
          <div className="flex items-center gap-1.5 text-xs font-semibold text-gray-500 mb-2">
            <Brain className="h-3.5 w-3.5" />
            Intelligence Answer
          </div>
          <p className="text-sm text-gray-800 whitespace-pre-wrap leading-relaxed">{answer}</p>
          <button
            onClick={() => { setAnswer(null); setQuestion('') }}
            className="mt-3 text-xs text-gray-400 hover:text-gray-600"
          >
            Ask another question
          </button>
        </div>
      )}
    </div>
  )
}

// ── Main page ─────────────────────────────────────────────────────────────────

export function IntelligencePage() {
  const { cin } = useParams<{ cin?: string }>()

  const { data, isLoading, error } = useQuery({
    queryKey: ['intelligence', cin],
    queryFn: () => intelligenceApi.getCompanyIntelligence(cin!),
    enabled: !!cin,
    staleTime: 120_000,
    retry: 1,
  })

  // If no CIN param — show the standalone ask interface
  if (!cin) {
    return (
      <div className="max-w-3xl mx-auto px-6 py-10">
        <div className="flex items-center gap-3 mb-8">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
            <Brain className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Intelligence</h1>
            <p className="text-sm text-gray-500">Ask any question about companies in the knowledge graph</p>
          </div>
        </div>
        <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
          <AskIntelligence />
        </div>
      </div>
    )
  }

  if (isLoading) return <div className="flex justify-center py-20"><LoadingSpinner /></div>

  if (error || !data) {
    return (
      <div className="max-w-2xl mx-auto px-6 py-10 text-center">
        <AlertTriangle className="h-8 w-8 text-amber-500 mx-auto mb-3" />
        <p className="text-gray-600">Intelligence data unavailable for <code className="bg-gray-100 px-1 rounded">{cin}</code></p>
        <Link to={`/entity/company/${cin}`} className="mt-4 inline-block text-sm text-blue-600 hover:underline">
          Back to entity profile
        </Link>
      </div>
    )
  }

  const criticalSignals = data.risk_signals.filter(s => s.severity === 'critical' || s.severity === 'high')
  const infoSignals = data.risk_signals.filter(s => s.severity === 'medium' || s.severity === 'info')

  return (
    <div className="max-w-6xl mx-auto px-6 py-8">
      {/* Header */}
      <div className="flex items-center justify-between mb-8">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 bg-blue-600 rounded-xl flex items-center justify-center">
            <Brain className="h-5 w-5 text-white" />
          </div>
          <div>
            <h1 className="text-xl font-bold text-gray-900">Intelligence</h1>
            <p className="text-sm text-gray-500 font-mono">{cin}</p>
          </div>
        </div>
        <Link
          to={`/entity/company/${cin}`}
          className="text-sm text-blue-600 hover:underline"
        >
          Entity Profile
        </Link>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Left column */}
        <div className="lg:col-span-2 space-y-6">

          {/* Ask Intelligence */}
          <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <Brain className="h-4 w-4 text-blue-600" />
              <h2 className="font-semibold text-gray-900">Ask the Intelligence Engine</h2>
            </div>
            <AskIntelligence cin={cin} />
          </div>

          {/* Risk Signals */}
          {data.risk_signals.length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
              <div className="flex items-center gap-2 mb-4">
                <AlertTriangle className="h-4 w-4 text-amber-500" />
                <h2 className="font-semibold text-gray-900">Risk Signals</h2>
                <span className="ml-auto text-xs text-gray-400">{data.risk_signals.length} signals</span>
              </div>
              {criticalSignals.length > 0 && (
                <div className="space-y-2 mb-3">
                  {criticalSignals.map(s => <RiskSignalCard key={s.feature} signal={s} />)}
                </div>
              )}
              {infoSignals.length > 0 && (
                <div className="space-y-2">
                  {infoSignals.map(s => <RiskSignalCard key={s.feature} signal={s} />)}
                </div>
              )}
            </div>
          )}

          {/* Feature table */}
          <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <BarChart2 className="h-4 w-4 text-gray-500" />
              <h2 className="font-semibold text-gray-900">Intelligence Features</h2>
            </div>
            <FeatureTable features={data.features} />
          </div>
        </div>

        {/* Right column */}
        <div className="space-y-6">
          {/* CIRP Prediction */}
          <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
            <div className="flex items-center gap-2 mb-4">
              <TrendingUp className="h-4 w-4 text-red-500" />
              <h2 className="font-semibold text-gray-900">Risk Prediction</h2>
            </div>
            <PredictionPanel prediction={data.prediction} />
          </div>

          {/* Benchmark */}
          {data.benchmark && Object.keys(data.benchmark).length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
              <h2 className="font-semibold text-gray-900 mb-3">Sector Benchmark</h2>
              <div className="space-y-2">
                {Object.entries(data.benchmark).slice(0, 6).map(([key, val]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                    <span className="font-medium">{typeof val === 'number' ? val.toFixed(2) : String(val)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Network influence */}
          {data.network_influence && Object.keys(data.network_influence).length > 0 && (
            <div className="bg-white border border-gray-200 rounded-xl p-6 shadow-sm">
              <h2 className="font-semibold text-gray-900 mb-3">Network Influence</h2>
              <div className="space-y-2">
                {Object.entries(data.network_influence).slice(0, 5).map(([key, val]) => (
                  <div key={key} className="flex justify-between text-sm">
                    <span className="text-gray-500 capitalize">{key.replace(/_/g, ' ')}</span>
                    <span className="font-medium">{typeof val === 'number' ? val.toFixed(4) : String(val)}</span>
                  </div>
                ))}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
