import React from 'react'

export function DataFreshness({ source, lastSynced }: { source: string; lastSynced: string }) {
  return (
    <span className="text-xs text-gray-400" title={`Last synced: ${lastSynced}`}>
      {source} · {lastSynced}
    </span>
  )
}
