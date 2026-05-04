import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import { Copy, Inbox } from 'lucide-react'
import DuplicateCard, { DuplicateCandidate } from '../components/DuplicateCard'
import DeadLetterItem, { DeadLetterRecord } from '../components/DeadLetterItem'
import clsx from 'clsx'

type TabType = 'duplicates' | 'dlq' | 'impossible'

interface ImpossibleState {
  object_id: string
  rule: string
  values: string
  object_type: string
}

interface DataQualityResponse {
  duplicate_candidates?: DuplicateCandidate[]
  dead_letter_queue?: DeadLetterRecord[]
  impossible_states?: ImpossibleState[]
}

const TABS: { key: TabType; label: string }[] = [
  { key: 'duplicates', label: 'Duplicate Candidates' },
  { key: 'dlq', label: 'Dead Letter Queue' },
  { key: 'impossible', label: 'Impossible States' },
]

export default function DataQuality() {
  const [activeTab, setActiveTab] = useState<TabType>('duplicates')
  const [resolvedDups, setResolvedDups] = useState<Set<string>>(new Set())
  const [resolvedDLQ, setResolvedDLQ] = useState<Set<string>>(new Set())

  const { data, isLoading, isError } = useQuery<DataQualityResponse>({
    queryKey: ['data-quality'],
    queryFn: async () => {
      const res = await axios.get<DataQualityResponse>('/api/v1/operational/ontology-health')
      return res.data
    },
    refetchInterval: 120_000,
  })

  const duplicates = (data?.duplicate_candidates ?? []).filter(d => !resolvedDups.has(d.id))
  const dlq = (data?.dead_letter_queue ?? []).filter(r => !resolvedDLQ.has(r.id))
  const impossibleStates = data?.impossible_states ?? []

  const counts: Record<TabType, number> = {
    duplicates: duplicates.length,
    dlq: dlq.length,
    impossible: impossibleStates.length,
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Data Quality</h1>
        <p className="text-sm text-gray-500 mt-1">Duplicates, dead letters, and constraint violations</p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-5 text-sm text-amber-700">
          Could not load data quality metrics.
        </div>
      )}

      {/* Tabs */}
      <div className="flex gap-1 bg-gray-100 rounded-xl p-1 mb-6 w-fit">
        {TABS.map(tab => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={clsx(
              'flex items-center gap-2 px-4 py-2 rounded-lg text-sm font-medium transition-colors',
              activeTab === tab.key
                ? 'bg-white text-gray-900 shadow-sm'
                : 'text-gray-500 hover:text-gray-700',
            )}
          >
            {tab.label}
            {counts[tab.key] > 0 && (
              <span
                className={clsx(
                  'text-xs font-bold w-5 h-5 rounded-full flex items-center justify-center',
                  activeTab === tab.key
                    ? 'bg-gray-900 text-white'
                    : 'bg-gray-300 text-gray-600',
                )}
              >
                {counts[tab.key] > 9 ? '9+' : counts[tab.key]}
              </span>
            )}
          </button>
        ))}
      </div>

      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => (
            <div key={i} className="h-32 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <>
          {/* Duplicate Candidates */}
          {activeTab === 'duplicates' && (
            <div className="space-y-4">
              {duplicates.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 bg-white rounded-xl border border-gray-200">
                  <Copy size={36} className="mb-3 opacity-30" />
                  <p className="text-sm">No duplicate candidates found</p>
                  <p className="text-xs mt-1 text-gray-300">The deduplication engine found no matches above threshold</p>
                </div>
              ) : (
                duplicates.map(candidate => (
                  <DuplicateCard
                    key={candidate.id}
                    candidate={candidate}
                    onResolved={id => setResolvedDups(s => new Set([...s, id]))}
                  />
                ))
              )}
            </div>
          )}

          {/* Dead Letter Queue */}
          {activeTab === 'dlq' && (
            <div className="space-y-4">
              {dlq.length === 0 ? (
                <div className="flex flex-col items-center justify-center py-20 text-gray-400 bg-white rounded-xl border border-gray-200">
                  <Inbox size={36} className="mb-3 opacity-30" />
                  <p className="text-sm">Dead letter queue is empty</p>
                  <p className="text-xs mt-1 text-gray-300">All records are processing cleanly</p>
                </div>
              ) : (
                dlq.map(record => (
                  <DeadLetterItem
                    key={record.id}
                    record={record}
                    onResolved={id => setResolvedDLQ(s => new Set([...s, id]))}
                  />
                ))
              )}
            </div>
          )}

          {/* Impossible States */}
          {activeTab === 'impossible' && (
            <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
              {impossibleStates.length === 0 ? (
                <div className="py-16 text-center text-gray-400 text-sm">
                  No constraint violations detected
                </div>
              ) : (
                <table className="w-full text-left">
                  <thead>
                    <tr className="border-b border-gray-100 bg-gray-50">
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Object ID</th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Object Type</th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Rule Violated</th>
                      <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Values</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-gray-50">
                    {impossibleStates.map((v, i) => (
                      <tr key={i} className="hover:bg-gray-50">
                        <td className="px-4 py-3 font-mono text-xs text-gray-700">{v.object_id}</td>
                        <td className="px-4 py-3 text-sm text-gray-600 capitalize">{v.object_type}</td>
                        <td className="px-4 py-3 text-sm text-red-600 font-medium">{v.rule}</td>
                        <td className="px-4 py-3 text-xs text-gray-500 font-mono">{v.values}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              )}
            </div>
          )}
        </>
      )}
    </div>
  )
}
