import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { Inbox } from 'lucide-react'
import PipelineFlow, { PipelineBatch } from '../components/PipelineFlow'

interface IngestionQueueResponse {
  batches: PipelineBatch[]
}

const FALLBACK: IngestionQueueResponse = { batches: [] }

export default function IngestionQueue() {
  const { data, isLoading, isError } = useQuery<IngestionQueueResponse>({
    queryKey: ['ingestion-queue'],
    queryFn: async () => {
      const res = await axios.get<IngestionQueueResponse>(
        '/api/v1/operational/ingestion-queue',
      )
      return res.data
    },
    refetchInterval: 15_000,
  })

  const display = data ?? FALLBACK
  const total = display.batches.length
  const stuck = display.batches.filter(b => b.duration_min > 30).length

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Ingestion Pipeline</h1>
        <p className="text-sm text-gray-500 mt-1">Active batches across pipeline stages · Auto-refresh every 15s</p>
      </div>

      {/* Summary pills */}
      <div className="flex gap-3 mb-6">
        <div className="bg-white border border-gray-200 rounded-lg px-4 py-2.5 flex items-center gap-2">
          <span className="text-sm text-gray-500">Active batches</span>
          <span className="font-bold text-gray-900 text-sm tabular-nums">{total}</span>
        </div>
        {stuck > 0 && (
          <div className="bg-amber-50 border border-amber-200 rounded-lg px-4 py-2.5 flex items-center gap-2">
            <span className="text-sm text-amber-700">Stuck (&gt;30m)</span>
            <span className="font-bold text-amber-700 text-sm tabular-nums">{stuck}</span>
          </div>
        )}
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load pipeline data.
        </div>
      )}

      {isLoading ? (
        <div className="h-48 bg-gray-100 rounded-xl animate-pulse" />
      ) : total === 0 ? (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm flex flex-col items-center justify-center py-20 text-gray-400">
          <Inbox size={40} className="mb-3 opacity-30" />
          <p className="text-sm">No active batches in pipeline</p>
          <p className="text-xs mt-1 text-gray-300">Batches will appear here when syncs are running</p>
        </div>
      ) : (
        <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-5">
          <PipelineFlow batches={display.batches} />
        </div>
      )}

      <div className="mt-5 text-xs text-gray-400">
        Batches with amber border have been in the same stage for more than 30 minutes.
      </div>
    </div>
  )
}
