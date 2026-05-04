import axios from 'axios'
import { useState } from 'react'

export interface DeadLetterRecord {
  id: string
  source: string
  pipeline: string
  error_rule: string
  error_message: string
  timestamp: string
  record_preview: string
}

interface DeadLetterItemProps {
  record: DeadLetterRecord
  onResolved: (id: string) => void
}

export default function DeadLetterItem({ record, onResolved }: DeadLetterItemProps) {
  const [loading, setLoading] = useState<null | 'reprocess' | 'discard'>(null)

  async function handleReprocess() {
    setLoading('reprocess')
    try {
      await axios.post(`/api/v1/dead-letter/${record.id}/reprocess`)
      onResolved(record.id)
    } catch {
      setLoading(null)
    }
  }

  async function handleDiscard() {
    setLoading('discard')
    try {
      await axios.delete(`/api/v1/dead-letter/${record.id}`)
      onResolved(record.id)
    } catch {
      setLoading(null)
    }
  }

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
      <div className="flex items-start justify-between gap-4">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 flex-wrap mb-2">
            <span className="font-semibold text-sm text-gray-900">{record.source}</span>
            <span className="text-gray-300">·</span>
            <span className="text-xs text-gray-500">{record.pipeline}</span>
            <span
              className="text-xs font-semibold px-2 py-0.5 rounded-md bg-red-50 text-red-700 border border-red-200"
            >
              {record.error_rule}
            </span>
          </div>
          <p className="text-sm text-red-600 mb-2">{record.error_message}</p>
          <pre className="text-xs text-gray-400 bg-gray-50 rounded-lg px-3 py-2 font-mono overflow-x-auto scrollbar-thin whitespace-pre-wrap break-all max-h-24">
            {record.record_preview}
          </pre>
          <p className="text-xs text-gray-400 mt-2">{record.timestamp}</p>
        </div>
        <div className="flex flex-col gap-2 flex-shrink-0">
          <button
            onClick={handleReprocess}
            disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-semibold bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors whitespace-nowrap"
          >
            {loading === 'reprocess' ? 'Processing…' : 'Correct & Reprocess'}
          </button>
          <button
            onClick={handleDiscard}
            disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-semibold bg-white text-red-600 border border-red-200 rounded-lg hover:bg-red-50 disabled:opacity-50 transition-colors"
          >
            {loading === 'discard' ? 'Discarding…' : 'Discard'}
          </button>
        </div>
      </div>
    </div>
  )
}
