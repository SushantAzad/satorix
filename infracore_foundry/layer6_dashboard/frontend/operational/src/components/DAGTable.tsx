import {
  useReactTable,
  getCoreRowModel,
  flexRender,
  createColumnHelper,
} from '@tanstack/react-table'
import StatusBadge from './StatusBadge'

export interface DAGRow {
  dag_id: string
  last_run: string
  next_run: string
  status: 'running' | 'completed' | 'failed' | 'pending' | 'unknown'
  records_last_run: number
  success_rate_7d: number
}

interface DAGTableProps {
  dags: DAGRow[]
}

const columnHelper = createColumnHelper<DAGRow>()

const columns = [
  columnHelper.accessor('dag_id', {
    header: 'DAG Name',
    cell: info => (
      <span className="font-mono text-sm text-gray-800">{info.getValue()}</span>
    ),
  }),
  columnHelper.accessor('last_run', {
    header: 'Last Run',
    cell: info => <span className="text-sm text-gray-600">{info.getValue()}</span>,
  }),
  columnHelper.accessor('next_run', {
    header: 'Next Run',
    cell: info => <span className="text-sm text-gray-600">{info.getValue()}</span>,
  }),
  columnHelper.accessor('status', {
    header: 'Status',
    cell: info => <StatusBadge status={info.getValue()} />,
  }),
  columnHelper.accessor('records_last_run', {
    header: 'Records (Last Run)',
    cell: info => (
      <span className="text-sm tabular-nums text-gray-700">
        {info.getValue().toLocaleString()}
      </span>
    ),
  }),
  columnHelper.accessor('success_rate_7d', {
    header: '7-Day Success Rate',
    cell: info => {
      const val = info.getValue()
      const color = val >= 90 ? 'bg-green-500' : val >= 70 ? 'bg-amber-500' : 'bg-red-500'
      return (
        <div className="flex items-center gap-2">
          <div className="flex-1 h-1.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full ${color}`}
              style={{ width: `${val}%` }}
            />
          </div>
          <span className="text-xs tabular-nums text-gray-500 w-9 text-right">{val}%</span>
        </div>
      )
    },
  }),
]

export default function DAGTable({ dags }: DAGTableProps) {
  const table = useReactTable({
    data: dags,
    columns,
    getCoreRowModel: getCoreRowModel(),
  })

  if (dags.length === 0) {
    return (
      <div className="text-center py-10 text-gray-400 text-sm">
        No DAG data available
      </div>
    )
  }

  return (
    <div className="overflow-x-auto scrollbar-thin">
      <table className="w-full text-left">
        <thead>
          <tr className="border-b border-gray-100">
            {table.getHeaderGroups().map(headerGroup =>
              headerGroup.headers.map(header => (
                <th
                  key={header.id}
                  className="px-4 py-3 text-xs font-semibold text-gray-500 uppercase tracking-wider whitespace-nowrap"
                >
                  {flexRender(header.column.columnDef.header, header.getContext())}
                </th>
              )),
            )}
          </tr>
        </thead>
        <tbody className="divide-y divide-gray-50">
          {table.getRowModel().rows.map(row => (
            <tr key={row.id} className="hover:bg-gray-50 transition-colors">
              {row.getVisibleCells().map(cell => (
                <td key={cell.id} className="px-4 py-3">
                  {flexRender(cell.column.columnDef.cell, cell.getContext())}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}
