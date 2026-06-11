interface DiffProperty {
  name: string
  type: string
  required: boolean
  change: 'added' | 'removed' | 'modified' | 'unchanged'
  old_value?: string
  new_value?: string
}

interface SchemaDiffProps {
  fromVersion: string
  toVersion: string
  diff: DiffProperty[]
}

export default function SchemaDiff({ fromVersion, toVersion, diff }: SchemaDiffProps) {
  if (diff.length === 0) {
    return (
      <div className="bg-gray-50 rounded-xl border border-gray-200 px-6 py-8 text-center text-sm text-gray-400">
        No differences between {fromVersion} and {toVersion}
      </div>
    )
  }

  const added = diff.filter(d => d.change === 'added')
  const removed = diff.filter(d => d.change === 'removed')
  const modified = diff.filter(d => d.change === 'modified')

  return (
    <div className="border border-gray-200 rounded-xl overflow-hidden">
      {/* Header */}
      <div className="bg-gray-50 px-4 py-3 flex items-center gap-4 border-b border-gray-200 text-xs">
        <span className="font-semibold text-gray-600">{fromVersion}</span>
        <span className="text-gray-400">→</span>
        <span className="font-semibold text-gray-900">{toVersion}</span>
        <div className="ml-auto flex gap-3">
          {added.length > 0 && (
            <span className="text-green-700 font-medium">+{added.length} added</span>
          )}
          {removed.length > 0 && (
            <span className="text-red-600 font-medium">-{removed.length} removed</span>
          )}
          {modified.length > 0 && (
            <span className="text-amber-600 font-medium">{modified.length} modified</span>
          )}
        </div>
      </div>

      <table className="w-full text-sm">
        <thead>
          <tr className="border-b border-gray-100 bg-white">
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Property</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Type</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Required</th>
            <th className="px-4 py-2.5 text-left text-xs font-semibold text-gray-400 uppercase tracking-wider">Change</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {diff.map((prop, i) => {
            const rowClass =
              prop.change === 'added'
                ? 'bg-green-50'
                : prop.change === 'removed'
                ? 'bg-red-50'
                : prop.change === 'modified'
                ? 'bg-amber-50'
                : ''

            return (
              <tr key={i} className={rowClass}>
                <td className="px-4 py-2.5">
                  <span
                    className={`font-mono text-sm ${
                      prop.change === 'removed' ? 'line-through text-red-400' : 'text-gray-800'
                    }`}
                  >
                    {prop.name}
                  </span>
                </td>
                <td className="px-4 py-2.5">
                  {prop.change === 'modified' && prop.old_value ? (
                    <div className="flex flex-col gap-0.5">
                      <span className="text-red-400 line-through text-xs">{prop.old_value}</span>
                      <span className="text-green-700 text-xs">{prop.new_value}</span>
                    </div>
                  ) : (
                    <span className="text-gray-600 font-mono text-xs">{prop.type}</span>
                  )}
                </td>
                <td className="px-4 py-2.5 text-xs text-gray-500">
                  {prop.required ? 'Yes' : 'No'}
                </td>
                <td className="px-4 py-2.5">
                  <span
                    className={`text-xs font-semibold capitalize ${
                      prop.change === 'added'
                        ? 'text-green-700'
                        : prop.change === 'removed'
                        ? 'text-red-600'
                        : prop.change === 'modified'
                        ? 'text-amber-600'
                        : 'text-gray-400'
                    }`}
                  >
                    {prop.change}
                  </span>
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
