import axios from 'axios'
import { useState } from 'react'
import clsx from 'clsx'

export interface DuplicateCandidate {
  id: string
  similarity_score: number
  entity_a: {
    id: string
    name: string
    [key: string]: string | number | boolean
  }
  entity_b: {
    id: string
    name: string
    [key: string]: string | number | boolean
  }
  matching_fields: string[]
  differing_fields: string[]
}

interface DuplicateCardProps {
  candidate: DuplicateCandidate
  onResolved: (id: string) => void
}

const COMPARE_FIELDS = ['name', 'cin', 'pan', 'registered_address', 'incorporation_date', 'status']

export default function DuplicateCard({ candidate, onResolved }: DuplicateCardProps) {
  const [loading, setLoading] = useState<null | 'merge' | 'not-dup' | 'skip'>(null)

  async function handleMerge() {
    setLoading('merge')
    try {
      await axios.post('/api/v1/entities/merge', {
        entity_a_id: candidate.entity_a.id,
        entity_b_id: candidate.entity_b.id,
      })
      onResolved(candidate.id)
    } catch {
      setLoading(null)
    }
  }

  function handleNotDup() {
    setLoading('not-dup')
    setTimeout(() => onResolved(candidate.id), 300)
  }

  function handleSkip() {
    onResolved(candidate.id)
  }

  const score = Math.round(candidate.similarity_score * 100)

  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3.5 border-b border-gray-100 bg-gray-50">
        <div className="flex items-center gap-3">
          <span className="text-sm font-semibold text-gray-700">Duplicate Candidate</span>
          <span
            className={clsx(
              'text-xs font-bold px-2.5 py-0.5 rounded-full',
              score >= 90
                ? 'bg-red-100 text-red-700'
                : score >= 75
                ? 'bg-amber-100 text-amber-700'
                : 'bg-gray-100 text-gray-600',
            )}
          >
            {score}% similar
          </span>
        </div>
        <div className="flex gap-2">
          <button
            onClick={handleMerge}
            disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-semibold bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-50 transition-colors"
          >
            {loading === 'merge' ? 'Merging…' : 'Merge'}
          </button>
          <button
            onClick={handleNotDup}
            disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-semibold bg-white text-gray-700 border border-gray-200 rounded-lg hover:bg-gray-50 disabled:opacity-50 transition-colors"
          >
            Not Duplicate
          </button>
          <button
            onClick={handleSkip}
            disabled={loading !== null}
            className="px-3 py-1.5 text-xs font-medium text-gray-400 hover:text-gray-600 disabled:opacity-50 transition-colors"
          >
            Skip
          </button>
        </div>
      </div>

      {/* Comparison table */}
      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100">
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider w-32">Property</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Entity A
              <span className="font-mono text-gray-300 ml-2 normal-case font-normal">{candidate.entity_a.id}</span>
            </th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">
              Entity B
              <span className="font-mono text-gray-300 ml-2 normal-case font-normal">{candidate.entity_b.id}</span>
            </th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {COMPARE_FIELDS.map(field => {
            const valA = String(candidate.entity_a[field] ?? '—')
            const valB = String(candidate.entity_b[field] ?? '—')
            const matches = valA === valB && valA !== '—'
            const differs = valA !== valB && valA !== '—' && valB !== '—'

            return (
              <tr
                key={field}
                className={
                  matches ? 'bg-green-50' : differs ? 'bg-amber-50' : ''
                }
              >
                <td className="px-4 py-2 text-xs font-medium text-gray-500">{field}</td>
                <td className="px-4 py-2 text-xs text-gray-700">{valA}</td>
                <td className="px-4 py-2 text-xs text-gray-700">{valB}</td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
