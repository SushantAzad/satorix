import clsx from 'clsx'
import { ArrowRight } from 'lucide-react'

export interface BatchCard {
  batch_id: string
  source: string
  record_count: number
  duration_min: number
}

export type PipelineStage = 'source_synced' | 'l1_parquet' | 'l2_cleaned' | 'l3_ingested' | 'intelligence_updated'

export interface PipelineBatch {
  batch_id: string
  source: string
  record_count: number
  duration_min: number
  stage: PipelineStage
}

interface PipelineFlowProps {
  batches: PipelineBatch[]
}

const stages: { key: PipelineStage; label: string }[] = [
  { key: 'source_synced', label: 'Source Synced' },
  { key: 'l1_parquet', label: 'L1 Parquet' },
  { key: 'l2_cleaned', label: 'L2 Cleaned' },
  { key: 'l3_ingested', label: 'L3 Ingested' },
  { key: 'intelligence_updated', label: 'Intelligence Updated' },
]

export default function PipelineFlow({ batches }: PipelineFlowProps) {
  const batchesByStage = stages.reduce<Record<PipelineStage, PipelineBatch[]>>(
    (acc, s) => {
      acc[s.key] = batches.filter(b => b.stage === s.key)
      return acc
    },
    {} as Record<PipelineStage, PipelineBatch[]>,
  )

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <div className="flex items-start gap-0 min-w-max">
        {stages.map((stage, idx) => (
          <div key={stage.key} className="flex items-start">
            {/* Stage column */}
            <div className="flex flex-col" style={{ minWidth: '180px' }}>
              {/* Stage header */}
              <div className="bg-gray-900 text-white text-xs font-semibold px-4 py-2.5 rounded-t-lg text-center tracking-wide">
                {stage.label}
              </div>
              {/* Batch cards */}
              <div className="border-x border-b border-gray-200 rounded-b-lg bg-gray-50 min-h-[100px] p-2 space-y-1.5">
                {batchesByStage[stage.key].length === 0 ? (
                  <div className="text-xs text-gray-300 text-center mt-3">—</div>
                ) : (
                  batchesByStage[stage.key].map(batch => {
                    const stuck = batch.duration_min > 30
                    return (
                      <div
                        key={batch.batch_id}
                        className={clsx(
                          'bg-white rounded-lg border p-2 text-xs',
                          stuck ? 'border-amber-400 shadow-amber-100 shadow-sm' : 'border-gray-200',
                        )}
                      >
                        <p className="font-mono text-gray-500 truncate">
                          {batch.batch_id.slice(0, 12)}…
                        </p>
                        <p className="font-medium text-gray-800 truncate">{batch.source}</p>
                        <div className="flex justify-between text-gray-400 mt-0.5">
                          <span>{batch.record_count.toLocaleString()} rows</span>
                          <span className={clsx(stuck ? 'text-amber-500 font-semibold' : '')}>
                            {batch.duration_min}m
                          </span>
                        </div>
                        {stuck && (
                          <p className="text-amber-500 font-semibold mt-0.5">Stuck</p>
                        )}
                      </div>
                    )
                  })
                )}
              </div>
            </div>

            {/* Arrow between stages */}
            {idx < stages.length - 1 && (
              <div className="flex items-center self-start mt-2.5 px-1 text-gray-400">
                <ArrowRight size={16} />
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  )
}
