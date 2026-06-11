import { useState } from 'react'
import clsx from 'clsx'

interface CoverageRow {
  object_type: string
  name: number
  status: number
  risk_score: number
  incorporation_date: number
  registered_state: number
}

interface PropertyHeatmapProps {
  rows: CoverageRow[]
}

const PROPERTIES: { key: keyof Omit<CoverageRow, 'object_type'>; label: string }[] = [
  { key: 'name', label: 'name' },
  { key: 'status', label: 'status' },
  { key: 'risk_score', label: 'riskScore' },
  { key: 'incorporation_date', label: 'incorporationDate' },
  { key: 'registered_state', label: 'registeredState' },
]

function cellBg(val: number) {
  if (val >= 80) return 'bg-green-50 text-green-800'
  if (val >= 50) return 'bg-amber-50 text-amber-800'
  return 'bg-red-50 text-red-800'
}

export default function PropertyHeatmap({ rows }: PropertyHeatmapProps) {
  const [tooltip, setTooltip] = useState<{ x: number; y: number; text: string } | null>(null)

  return (
    <div className="relative overflow-x-auto scrollbar-thin">
      <table className="text-xs border-separate border-spacing-1">
        <thead>
          <tr>
            <th className="text-left pr-3 py-1 text-gray-400 font-medium w-36">Object Type</th>
            {PROPERTIES.map(p => (
              <th key={p.key} className="text-center px-2 py-1 text-gray-500 font-medium whitespace-nowrap">
                {p.label}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map(row => (
            <tr key={row.object_type}>
              <td className="pr-3 py-1 text-gray-600 font-medium whitespace-nowrap">{row.object_type}</td>
              {PROPERTIES.map(p => {
                const val = row[p.key] as number
                return (
                  <td
                    key={p.key}
                    className="px-2 py-1 text-center cursor-default"
                    onMouseEnter={e => {
                      const rect = (e.target as HTMLElement).getBoundingClientRect()
                      setTooltip({
                        x: rect.left + rect.width / 2,
                        y: rect.top,
                        text: `${row.object_type} · ${p.label}: ${val}%`,
                      })
                    }}
                    onMouseLeave={() => setTooltip(null)}
                  >
                    <div
                      className={clsx(
                        'rounded w-11 h-7 flex items-center justify-center font-semibold text-xs',
                        cellBg(val),
                      )}
                    >
                      {val}
                    </div>
                  </td>
                )
              })}
            </tr>
          ))}
        </tbody>
      </table>

      <div className="flex items-center gap-4 mt-3 text-xs text-gray-500">
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-green-400" />
          <span>80–100%</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-amber-400" />
          <span>50–79%</span>
        </div>
        <div className="flex items-center gap-1.5">
          <div className="w-3 h-3 rounded bg-red-400" />
          <span>0–49%</span>
        </div>
      </div>

      {tooltip && (
        <div
          className="fixed z-50 bg-gray-900 text-white text-xs rounded-lg px-3 py-1.5 pointer-events-none -translate-x-1/2 -translate-y-full"
          style={{ left: tooltip.x, top: tooltip.y - 6 }}
        >
          {tooltip.text}
        </div>
      )}
    </div>
  )
}
