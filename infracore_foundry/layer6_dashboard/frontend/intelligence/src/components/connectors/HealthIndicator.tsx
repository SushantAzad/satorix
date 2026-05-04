import React from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'

export function HealthIndicator() {
  const { data: sources } = useQuery({
    queryKey: ['source-health-indicator'],
    queryFn: () => apiClient.get('/api/v1/sources').then(r => r.data as any[]).catch(() => []),
    staleTime: 120_000,
    refetchInterval: 120_000,
  })

  if (!sources?.length) return null

  const healthy = sources.filter((s: any) => s.status === 'active' || s.status === 'healthy')
  const failed = sources.filter((s: any) => s.consecutive_failures > 0)

  return (
    <div className="fixed bottom-0 inset-x-0 h-8 bg-gray-50 border-t border-gray-200 flex items-center px-6 gap-4 z-30">
      {healthy.slice(0, 4).map((s: any) => (
        <span key={s.id} className="flex items-center gap-1 text-xs text-gray-500">
          <span className="w-1.5 h-1.5 rounded-full bg-green-500 flex-shrink-0" />
          {s.source_name}: synced
        </span>
      ))}
      {failed.map((s: any) => (
        <span key={s.id} className="flex items-center gap-1 text-xs text-amber-600">
          <span className="w-1.5 h-1.5 rounded-full bg-amber-500 flex-shrink-0" />
          {s.source_name}: sync failed
        </span>
      ))}
    </div>
  )
}
