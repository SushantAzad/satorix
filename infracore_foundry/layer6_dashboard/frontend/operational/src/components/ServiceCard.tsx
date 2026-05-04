import clsx from 'clsx'

export interface ServiceCardProps {
  name: string
  port: number
  status: 'healthy' | 'degraded' | 'down' | 'unknown'
  responseTimeMs: number
  lastChecked: string
}

const statusDot: Record<ServiceCardProps['status'], string> = {
  healthy: 'bg-green-500',
  degraded: 'bg-amber-500',
  down: 'bg-red-500',
  unknown: 'bg-gray-400',
}

const statusText: Record<ServiceCardProps['status'], string> = {
  healthy: 'Healthy',
  degraded: 'Degraded',
  down: 'Down',
  unknown: 'Unknown',
}

const statusColor: Record<ServiceCardProps['status'], string> = {
  healthy: 'text-green-600',
  degraded: 'text-amber-600',
  down: 'text-red-600',
  unknown: 'text-gray-500',
}

export default function ServiceCard({ name, port, status, responseTimeMs, lastChecked }: ServiceCardProps) {
  return (
    <div className="bg-white rounded-xl border border-gray-200 shadow-sm p-4 flex flex-col gap-3 hover:shadow-md transition-shadow">
      <div className="flex items-start justify-between">
        <div>
          <p className="font-semibold text-gray-900 text-sm">{name}</p>
          <div className="flex items-center gap-1.5 mt-1">
            <span
              className={clsx('inline-block w-2 h-2 rounded-full flex-shrink-0', statusDot[status])}
            />
            <span className={clsx('text-xs font-medium', statusColor[status])}>
              {statusText[status]}
            </span>
          </div>
        </div>
        <span className="text-xs font-mono bg-gray-100 text-gray-500 px-2 py-0.5 rounded-md border border-gray-200">
          :{port}
        </span>
      </div>
      <div className="flex items-center justify-between text-xs text-gray-400 border-t border-gray-50 pt-2">
        <span>{responseTimeMs > 0 ? `${responseTimeMs}ms` : '—'}</span>
        <span className="truncate ml-2">{lastChecked}</span>
      </div>
    </div>
  )
}
