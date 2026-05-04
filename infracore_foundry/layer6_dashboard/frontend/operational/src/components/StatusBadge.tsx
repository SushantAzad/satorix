import clsx from 'clsx'

type StatusType =
  | 'healthy'
  | 'degraded'
  | 'down'
  | 'running'
  | 'completed'
  | 'failed'
  | 'pending'
  | 'unknown'

interface StatusBadgeProps {
  status: StatusType
  className?: string
}

const statusConfig: Record<StatusType, { label: string; className: string }> = {
  healthy: { label: 'Healthy', className: 'bg-green-50 text-green-700 border-green-200' },
  degraded: { label: 'Degraded', className: 'bg-amber-50 text-amber-700 border-amber-200' },
  down: { label: 'Down', className: 'bg-red-50 text-red-700 border-red-200' },
  running: { label: 'Running', className: 'bg-blue-50 text-blue-700 border-blue-200' },
  completed: { label: 'Completed', className: 'bg-green-50 text-green-700 border-green-200' },
  failed: { label: 'Failed', className: 'bg-red-50 text-red-700 border-red-200' },
  pending: { label: 'Pending', className: 'bg-gray-50 text-gray-600 border-gray-200' },
  unknown: { label: 'Unknown', className: 'bg-gray-50 text-gray-500 border-gray-200' },
}

export default function StatusBadge({ status, className }: StatusBadgeProps) {
  const config = statusConfig[status] ?? statusConfig.unknown
  return (
    <span
      className={clsx(
        'inline-flex items-center px-2 py-0.5 rounded-md text-xs font-medium border',
        config.className,
        className,
      )}
    >
      {config.label}
    </span>
  )
}
