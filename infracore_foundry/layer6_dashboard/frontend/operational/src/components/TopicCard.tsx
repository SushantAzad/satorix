import clsx from 'clsx'

export interface TopicCardProps {
  name: string
  messagesPerSec: number
  consumerGroupLag: number
  partitionCount: number
  retention: string
}

export default function TopicCard({ name, messagesPerSec, consumerGroupLag, partitionCount, retention }: TopicCardProps) {
  const isLagHigh = consumerGroupLag > 1000
  const isActive = messagesPerSec > 0

  return (
    <div className="bg-gray-900 text-white rounded-xl border border-gray-800 shadow-sm p-4 flex flex-col gap-3 hover:border-gray-700 transition-colors">
      <div>
        <p className="text-xs text-gray-400 font-medium uppercase tracking-wider truncate">{name}</p>
      </div>

      <div className="grid grid-cols-2 gap-3">
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Messages/sec</p>
          <p className={clsx('text-lg font-semibold tabular-nums', isActive ? 'text-green-400' : 'text-gray-500')}>
            {messagesPerSec.toFixed(1)}
          </p>
        </div>
        <div>
          <p className="text-xs text-gray-500 mb-0.5">Consumer Lag</p>
          <p className={clsx('text-lg font-semibold tabular-nums', isLagHigh ? 'text-red-400' : 'text-gray-300')}>
            {consumerGroupLag.toLocaleString()}
          </p>
        </div>
      </div>

      <div className="flex items-center justify-between text-xs border-t border-gray-800 pt-2.5 mt-auto">
        <span className="text-gray-500">
          <span className="text-gray-400 font-medium">{partitionCount}</span> partitions
        </span>
        <span className="text-gray-500">
          ret: <span className="text-gray-400 font-medium">{retention}</span>
        </span>
        {isLagHigh && (
          <span className="text-red-400 text-xs font-medium">High Lag</span>
        )}
      </div>
    </div>
  )
}
