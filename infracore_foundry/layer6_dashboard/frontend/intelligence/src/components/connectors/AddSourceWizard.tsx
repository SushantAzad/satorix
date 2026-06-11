import React, { useState, useCallback } from 'react'
import { useMutation, useQueryClient } from '@tanstack/react-query'
import { X, Check, ChevronRight, Loader2, AlertCircle, Search } from 'lucide-react'
import { CONNECTORS, CONNECTOR_CATEGORIES, CONNECTOR_MAP } from '../../lib/connectorMetadata'
import type { FieldDef } from '../../lib/connectorMetadata'
import { sourcesApi } from '../../api/sources'
import type { CreateSourcePayload } from '../../api/sources'

// ── Step types ───────────────────────────────────────────────────────────────

type Step = 'choose' | 'configure' | 'test' | 'save'

const STEPS: { id: Step; label: string }[] = [
  { id: 'choose', label: 'Choose Type' },
  { id: 'configure', label: 'Configure' },
  { id: 'test', label: 'Test' },
  { id: 'save', label: 'Name & Save' },
]

interface Props {
  onClose: () => void
}

// ── Field renderer ───────────────────────────────────────────────────────────

function Field({ def, value, onChange }: {
  def: FieldDef
  value: string
  onChange: (v: string) => void
}) {
  const base = 'w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 placeholder-gray-400 focus:outline-none focus:border-gray-400 focus:bg-white transition-all'

  return (
    <div className="space-y-1">
      <label className="block text-xs font-medium text-gray-700">
        {def.label}
        {def.required && <span className="text-red-500 ml-1">*</span>}
      </label>
      {def.type === 'select' ? (
        <select value={value} onChange={e => onChange(e.target.value)} className={base}>
          {def.options?.map(o => <option key={o.value} value={o.value}>{o.label}</option>)}
        </select>
      ) : def.type === 'textarea' ? (
        <textarea
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={def.placeholder}
          rows={4}
          className={`${base} resize-none font-mono text-xs`}
        />
      ) : (
        <input
          type={def.type === 'password' ? 'password' : def.type === 'number' ? 'number' : def.type === 'url' ? 'url' : 'text'}
          value={value}
          onChange={e => onChange(e.target.value)}
          placeholder={def.placeholder ?? (def.defaultValue !== undefined ? String(def.defaultValue) : '')}
          className={base}
        />
      )}
      {def.helpText && <p className="text-xs text-gray-400">{def.helpText}</p>}
    </div>
  )
}

// ── Main wizard ──────────────────────────────────────────────────────────────

export function AddSourceWizard({ onClose }: Props) {
  const qc = useQueryClient()

  const [step, setStep] = useState<Step>('choose')
  const [selectedType, setSelectedType] = useState<string | null>(null)
  const [config, setConfig] = useState<Record<string, string>>({})
  const [sourceName, setSourceName] = useState('')
  const [categoryFilter, setCategoryFilter] = useState<string>('all')
  const [typeSearch, setTypeSearch] = useState('')
  const [testResult, setTestResult] = useState<{ success: boolean; message?: string } | null>(null)
  const [createdSourceId, setCreatedSourceId] = useState<string | null>(null)

  const connectorDef = selectedType ? CONNECTOR_MAP[selectedType] : null

  // ── Mutations ──────────────────────────────────────────────────────────────

  const createMut = useMutation({
    mutationFn: (payload: CreateSourcePayload) => sourcesApi.create(payload),
    onSuccess: (data) => {
      setCreatedSourceId(data.id)
      qc.invalidateQueries({ queryKey: ['sources'] })
    },
  })

  const testMut = useMutation({
    mutationFn: (id: string) => sourcesApi.test(id),
    onSuccess: (result) => setTestResult(result),
    onError: (err: unknown) => {
      const msg = err instanceof Error ? err.message : 'Connection test failed'
      setTestResult({ success: false, message: msg })
    },
  })

  // ── Step navigation ────────────────────────────────────────────────────────

  const handleChooseNext = useCallback(() => {
    if (!selectedType) return
    const def = CONNECTOR_MAP[selectedType]
    const defaults: Record<string, string> = {}
    def.fields.forEach(f => {
      defaults[f.key] = f.defaultValue !== undefined ? String(f.defaultValue) : ''
    })
    setConfig(defaults)
    setStep('configure')
  }, [selectedType])

  const handleConfigureNext = useCallback(() => {
    const def = CONNECTOR_MAP[selectedType!]
    const missing = def.fields.filter(f => f.required && !config[f.key]?.trim())
    if (missing.length > 0) return  // Field-level validation shown inline
    setStep('test')
  }, [selectedType, config])

  const handleTestStep = useCallback(async () => {
    if (!sourceName.trim()) return
    setTestResult(null)
    try {
      const payload: CreateSourcePayload = {
        source_name: `__test__${Date.now()}`,
        source_type: selectedType!,
        config: Object.fromEntries(Object.entries(config).filter(([, v]) => v.trim() !== '')),
      }
      const created = await createMut.mutateAsync(payload)
      setCreatedSourceId(created.id)
      await testMut.mutateAsync(created.id)
    } catch {
      // error shown via testResult
    }
  }, [sourceName, selectedType, config, createMut, testMut])

  const handleSave = useCallback(async () => {
    if (!createdSourceId || !sourceName.trim()) return
    // Rename the source to the user's chosen name by creating a fresh one
    // (Layer 1 doesn't have PATCH /sources yet — create with correct name)
    await sourcesApi.delete(createdSourceId).catch(() => undefined)
    const payload: CreateSourcePayload = {
      source_name: sourceName.trim(),
      source_type: selectedType!,
      config: Object.fromEntries(Object.entries(config).filter(([, v]) => v.trim() !== '')),
    }
    await createMut.mutateAsync(payload)
    qc.invalidateQueries({ queryKey: ['sources'] })
    onClose()
  }, [createdSourceId, sourceName, selectedType, config, createMut, qc, onClose])

  // ── Filtered connector list ────────────────────────────────────────────────

  const visibleConnectors = CONNECTORS.filter(c => {
    if (categoryFilter !== 'all' && c.category !== categoryFilter) return false
    if (typeSearch && !c.displayName.toLowerCase().includes(typeSearch.toLowerCase()) &&
        !c.description.toLowerCase().includes(typeSearch.toLowerCase())) return false
    return true
  })

  const currentStepIndex = STEPS.findIndex(s => s.id === step)

  // ── Config validation ──────────────────────────────────────────────────────

  const missingFields = connectorDef?.fields.filter(f => f.required && !config[f.key]?.trim()) ?? []

  // ── Render ─────────────────────────────────────────────────────────────────

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/40">
      <div className="relative w-full max-w-2xl bg-white rounded-2xl shadow-2xl overflow-hidden flex flex-col max-h-[90vh]">

        {/* Header */}
        <div className="flex items-center justify-between px-6 py-4 border-b border-gray-100">
          <h2 className="text-base font-semibold text-gray-900">Add Data Source</h2>
          <button onClick={onClose} className="p-1 rounded-lg hover:bg-gray-100 transition-colors">
            <X className="h-4 w-4 text-gray-500" />
          </button>
        </div>

        {/* Step indicator */}
        <div className="flex items-center px-6 py-3 bg-gray-50 border-b border-gray-100 gap-2">
          {STEPS.map((s, i) => (
            <React.Fragment key={s.id}>
              <div className={`flex items-center gap-1.5 text-xs font-medium ${
                i < currentStepIndex ? 'text-green-600' :
                i === currentStepIndex ? 'text-gray-900' :
                'text-gray-400'
              }`}>
                <span className={`w-5 h-5 rounded-full flex items-center justify-center text-[10px] font-bold ${
                  i < currentStepIndex ? 'bg-green-100 text-green-600' :
                  i === currentStepIndex ? 'bg-gray-900 text-white' :
                  'bg-gray-200 text-gray-400'
                }`}>
                  {i < currentStepIndex ? <Check className="h-3 w-3" /> : i + 1}
                </span>
                <span className="hidden sm:block">{s.label}</span>
              </div>
              {i < STEPS.length - 1 && <ChevronRight className="h-3 w-3 text-gray-300 flex-shrink-0" />}
            </React.Fragment>
          ))}
        </div>

        {/* Body */}
        <div className="flex-1 overflow-y-auto">

          {/* STEP 1 — Choose Type */}
          {step === 'choose' && (
            <div className="p-6 space-y-4">
              <div className="flex gap-3">
                <div className="relative flex-1">
                  <Search className="absolute left-3 top-1/2 -translate-y-1/2 h-3.5 w-3.5 text-gray-400" />
                  <input
                    value={typeSearch}
                    onChange={e => setTypeSearch(e.target.value)}
                    placeholder="Search connectors..."
                    className="w-full pl-8 pr-3 h-8 border border-gray-200 rounded-lg text-sm bg-gray-50 focus:bg-white focus:outline-none focus:border-gray-400"
                  />
                </div>
                <select
                  value={categoryFilter}
                  onChange={e => setCategoryFilter(e.target.value)}
                  className="h-8 border border-gray-200 rounded-lg text-xs bg-gray-50 focus:outline-none px-2"
                >
                  <option value="all">All categories</option>
                  {CONNECTOR_CATEGORIES.map(c => <option key={c} value={c}>{c}</option>)}
                </select>
              </div>

              <div className="grid grid-cols-2 gap-2">
                {visibleConnectors.map(c => (
                  <button
                    key={c.type}
                    onClick={() => setSelectedType(c.type)}
                    className={`flex items-start gap-3 p-3 rounded-xl border text-left transition-all ${
                      selectedType === c.type
                        ? 'border-gray-900 bg-gray-50 ring-1 ring-gray-900'
                        : 'border-gray-200 hover:border-gray-300 hover:bg-gray-50'
                    }`}
                  >
                    <span className="text-xl flex-shrink-0 mt-0.5">{c.icon}</span>
                    <div className="min-w-0">
                      <p className="text-sm font-medium text-gray-900 leading-tight">{c.displayName}</p>
                      <p className="text-xs text-gray-400 mt-0.5 leading-tight line-clamp-2">{c.description}</p>
                    </div>
                  </button>
                ))}
              </div>

              {visibleConnectors.length === 0 && (
                <p className="text-sm text-gray-400 text-center py-8">No connectors match your search.</p>
              )}
            </div>
          )}

          {/* STEP 2 — Configure */}
          {step === 'configure' && connectorDef && (
            <div className="p-6 space-y-4">
              <div className="flex items-center gap-3 pb-2 border-b border-gray-100">
                <span className="text-2xl">{connectorDef.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{connectorDef.displayName}</p>
                  <p className="text-xs text-gray-400">{connectorDef.description}</p>
                </div>
              </div>
              {connectorDef.fields.map(f => (
                <Field
                  key={f.key}
                  def={f}
                  value={config[f.key] ?? ''}
                  onChange={v => setConfig(prev => ({ ...prev, [f.key]: v }))}
                />
              ))}
              {missingFields.length > 0 && (
                <p className="text-xs text-amber-600 flex items-center gap-1.5">
                  <AlertCircle className="h-3.5 w-3.5" />
                  Fill in required fields: {missingFields.map(f => f.label).join(', ')}
                </p>
              )}
            </div>
          )}

          {/* STEP 3 — Test */}
          {step === 'test' && connectorDef && (
            <div className="p-6 space-y-6">
              <div className="flex items-center gap-3 pb-2 border-b border-gray-100">
                <span className="text-2xl">{connectorDef.icon}</span>
                <div>
                  <p className="text-sm font-semibold text-gray-900">{connectorDef.displayName}</p>
                  <p className="text-xs text-gray-400">Give this source a name, then test the connection.</p>
                </div>
              </div>

              <div className="space-y-1">
                <label className="block text-xs font-medium text-gray-700">
                  Source Name <span className="text-red-500">*</span>
                </label>
                <input
                  value={sourceName}
                  onChange={e => setSourceName(e.target.value)}
                  placeholder={`e.g. ${connectorDef.displayName} - Production`}
                  className="w-full rounded-lg border border-gray-200 bg-gray-50 px-3 py-2 text-sm text-gray-900 focus:outline-none focus:border-gray-400 focus:bg-white"
                />
              </div>

              <button
                onClick={handleTestStep}
                disabled={!sourceName.trim() || testMut.isPending || createMut.isPending}
                className="w-full h-10 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 transition-colors disabled:opacity-50 disabled:cursor-not-allowed flex items-center justify-center gap-2"
              >
                {(testMut.isPending || createMut.isPending) ? (
                  <><Loader2 className="h-4 w-4 animate-spin" />Testing connection...</>
                ) : (
                  'Test Connection'
                )}
              </button>

              {testResult && (
                <div className={`rounded-xl p-4 flex items-start gap-3 ${
                  testResult.success ? 'bg-green-50 border border-green-200' : 'bg-red-50 border border-red-200'
                }`}>
                  {testResult.success ? (
                    <Check className="h-4 w-4 text-green-600 flex-shrink-0 mt-0.5" />
                  ) : (
                    <AlertCircle className="h-4 w-4 text-red-500 flex-shrink-0 mt-0.5" />
                  )}
                  <div>
                    <p className={`text-sm font-medium ${testResult.success ? 'text-green-700' : 'text-red-700'}`}>
                      {testResult.success ? 'Connection successful' : 'Connection failed'}
                    </p>
                    {testResult.message && (
                      <p className="text-xs mt-0.5 text-gray-600">{testResult.message}</p>
                    )}
                  </div>
                </div>
              )}
            </div>
          )}

          {/* STEP 4 — Save */}
          {step === 'save' && (
            <div className="p-6 space-y-4">
              <div className="rounded-xl bg-green-50 border border-green-200 p-4 flex items-start gap-3">
                <Check className="h-5 w-5 text-green-600 flex-shrink-0 mt-0.5" />
                <div>
                  <p className="text-sm font-semibold text-green-700">Source ready to save</p>
                  <p className="text-xs text-green-600 mt-0.5">
                    "{sourceName}" will be added to your data sources and synced on the next scheduled run.
                  </p>
                </div>
              </div>

              <div className="rounded-xl border border-gray-100 p-4 space-y-2">
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Connector type</span>
                  <span className="font-medium text-gray-900">{connectorDef?.displayName}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Source name</span>
                  <span className="font-medium text-gray-900">{sourceName}</span>
                </div>
                <div className="flex justify-between text-xs">
                  <span className="text-gray-500">Category</span>
                  <span className="font-medium text-gray-900">{connectorDef?.category}</span>
                </div>
              </div>
            </div>
          )}
        </div>

        {/* Footer */}
        <div className="flex items-center justify-between px-6 py-4 border-t border-gray-100 bg-white">
          <button
            onClick={() => {
              const prev = STEPS[currentStepIndex - 1]
              if (prev) setStep(prev.id)
              else onClose()
            }}
            className="text-sm text-gray-500 hover:text-gray-900 transition-colors"
          >
            {currentStepIndex === 0 ? 'Cancel' : 'Back'}
          </button>

          <div className="flex items-center gap-3">
            {step === 'choose' && (
              <button
                onClick={handleChooseNext}
                disabled={!selectedType}
                className="h-9 px-5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
              >
                Continue <ChevronRight className="h-3.5 w-3.5" />
              </button>
            )}
            {step === 'configure' && (
              <button
                onClick={handleConfigureNext}
                disabled={missingFields.length > 0}
                className="h-9 px-5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
              >
                Continue <ChevronRight className="h-3.5 w-3.5" />
              </button>
            )}
            {step === 'test' && (
              <button
                onClick={() => setStep('save')}
                disabled={!testResult?.success && !createdSourceId}
                className="h-9 px-5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-1.5"
              >
                {testResult?.success ? 'Continue' : 'Skip & Continue'}
                <ChevronRight className="h-3.5 w-3.5" />
              </button>
            )}
            {step === 'save' && (
              <button
                onClick={handleSave}
                disabled={createMut.isPending}
                className="h-9 px-5 rounded-xl bg-gray-900 text-white text-sm font-medium hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors flex items-center gap-2"
              >
                {createMut.isPending ? <Loader2 className="h-4 w-4 animate-spin" /> : <Check className="h-4 w-4" />}
                Save Source
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
