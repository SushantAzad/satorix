import { useState } from 'react'
import { GitCommit } from 'lucide-react'
import SchemaDiff from '../components/SchemaDiff'

interface VersionEntry {
  version: string
  date: string
  author: string
  changes_added: number
  changes_removed: number
  changes_modified: number
  notes: string
}

interface DiffProperty {
  name: string
  type: string
  required: boolean
  change: 'added' | 'removed' | 'modified' | 'unchanged'
  old_value?: string
  new_value?: string
}

// Static mock schema version history — this data lives in the codebase
const MOCK_VERSIONS: VersionEntry[] = [
  {
    version: 'v2.4.0',
    date: '2025-04-28',
    author: 'Schema Steward',
    changes_added: 3,
    changes_removed: 0,
    changes_modified: 1,
    notes: 'Added beneficial_owner_depth, cin_verified_at, and pan_verified_at to company. Modified risk_score type to Float.',
  },
  {
    version: 'v2.3.1',
    date: '2025-04-10',
    author: 'Data Eng',
    changes_added: 0,
    changes_removed: 1,
    changes_modified: 2,
    notes: 'Removed deprecated legacy_id field. Fixed incorporation_date to be Date type across all types.',
  },
  {
    version: 'v2.3.0',
    date: '2025-03-22',
    author: 'Schema Steward',
    changes_added: 5,
    changes_removed: 0,
    changes_modified: 0,
    notes: 'New object type: contract. New properties for insolvency_proceeding: resolution_date, liquidation_value, committee_members.',
  },
  {
    version: 'v2.2.0',
    date: '2025-03-01',
    author: 'Data Eng',
    changes_added: 2,
    changes_removed: 0,
    changes_modified: 3,
    notes: 'Added director.disqualification_orders array. Added company.mca_last_verified.',
  },
  {
    version: 'v2.1.0',
    date: '2025-02-14',
    author: 'Schema Steward',
    changes_added: 8,
    changes_removed: 2,
    changes_modified: 1,
    notes: 'Initial CIRP-aware schema. Added insolvency_proceeding type.',
  },
  {
    version: 'v2.0.0',
    date: '2025-01-01',
    author: 'System',
    changes_added: 42,
    changes_removed: 0,
    changes_modified: 0,
    notes: 'Satorix v2 ontology baseline — full rewrite from v1.',
  },
]

// Diff data keyed by "fromVersion->toVersion"
const MOCK_DIFFS: Record<string, DiffProperty[]> = {
  'v2.3.1->v2.4.0': [
    { name: 'beneficial_owner_depth', type: 'Integer', required: false, change: 'added' },
    { name: 'cin_verified_at', type: 'DateTime', required: false, change: 'added' },
    { name: 'pan_verified_at', type: 'DateTime', required: false, change: 'added' },
    {
      name: 'risk_score',
      type: 'Float',
      required: false,
      change: 'modified',
      old_value: 'Integer',
      new_value: 'Float',
    },
    { name: 'name', type: 'String', required: true, change: 'unchanged' },
    { name: 'status', type: 'String', required: true, change: 'unchanged' },
  ],
  'v2.3.0->v2.3.1': [
    { name: 'legacy_id', type: 'String', required: false, change: 'removed' },
    {
      name: 'incorporation_date',
      type: 'Date',
      required: false,
      change: 'modified',
      old_value: 'String',
      new_value: 'Date',
    },
    {
      name: 'dissolution_date',
      type: 'Date',
      required: false,
      change: 'modified',
      old_value: 'String',
      new_value: 'Date',
    },
  ],
}

export default function SchemaVersions() {
  const [fromVersion, setFromVersion] = useState<string>('v2.3.1')
  const [toVersion, setToVersion] = useState<string>('v2.4.0')
  const [showDiff, setShowDiff] = useState(false)

  const versionOptions = MOCK_VERSIONS.map(v => v.version)

  const diffKey = `${fromVersion}->${toVersion}`
  const diff = MOCK_DIFFS[diffKey] ?? []

  function handleCompare() {
    if (fromVersion === toVersion) return
    setShowDiff(true)
  }

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Schema Versions</h1>
        <p className="text-sm text-gray-500 mt-1">Version history and schema comparison</p>
      </div>

      {/* Version history table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm mb-6">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900">Version History</h2>
        </div>
        <table className="w-full text-left">
          <thead>
            <tr className="border-b border-gray-50 bg-gray-50">
              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Version</th>
              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Date</th>
              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Author</th>
              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Changes</th>
              <th className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider">Notes</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-gray-50">
            {MOCK_VERSIONS.map((v, i) => (
              <tr key={v.version} className={i === 0 ? 'bg-blue-50/40' : 'hover:bg-gray-50'}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2">
                    <GitCommit size={14} className="text-gray-400" />
                    <span className="font-mono text-sm font-semibold text-gray-900">{v.version}</span>
                    {i === 0 && (
                      <span className="text-xs bg-blue-100 text-blue-700 px-1.5 py-0.5 rounded font-medium">
                        latest
                      </span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-sm text-gray-600">{v.date}</td>
                <td className="px-4 py-3 text-sm text-gray-600">{v.author}</td>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2 text-xs font-medium">
                    {v.changes_added > 0 && (
                      <span className="text-green-700">+{v.changes_added}</span>
                    )}
                    {v.changes_removed > 0 && (
                      <span className="text-red-600">-{v.changes_removed}</span>
                    )}
                    {v.changes_modified > 0 && (
                      <span className="text-amber-600">~{v.changes_modified}</span>
                    )}
                  </div>
                </td>
                <td className="px-4 py-3 text-xs text-gray-500 max-w-xs truncate">{v.notes}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Version comparison */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-6">
        <h2 className="font-semibold text-gray-900 mb-4">Compare Versions</h2>
        <div className="flex items-center gap-3 mb-5">
          <select
            value={fromVersion}
            onChange={e => { setFromVersion(e.target.value); setShowDiff(false) }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          >
            {versionOptions.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <span className="text-gray-400 text-sm">→</span>
          <select
            value={toVersion}
            onChange={e => { setToVersion(e.target.value); setShowDiff(false) }}
            className="text-sm border border-gray-200 rounded-lg px-3 py-2 bg-white focus:outline-none focus:ring-2 focus:ring-gray-900/10"
          >
            {versionOptions.map(v => (
              <option key={v} value={v}>{v}</option>
            ))}
          </select>
          <button
            onClick={handleCompare}
            disabled={fromVersion === toVersion}
            className="px-4 py-2 text-sm font-semibold bg-gray-900 text-white rounded-lg hover:bg-gray-700 disabled:opacity-40 disabled:cursor-not-allowed transition-colors"
          >
            Compare
          </button>
        </div>

        {showDiff && (
          <SchemaDiff
            fromVersion={fromVersion}
            toVersion={toVersion}
            diff={diff}
          />
        )}
      </div>
    </div>
  )
}
