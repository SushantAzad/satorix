import React, { useState } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { Download, Flag } from 'lucide-react'
import { apiClient } from '@shared/api/client'
import type { EntityProfile } from '@shared/api/types'

export function EntityActions({ entityType, entityId, profile }: {
  entityType: string; entityId: string; profile: EntityProfile
}) {
  const qc = useQueryClient()
  const [message, setMessage] = useState('')
  const [exportError, setExportError] = useState('')
  const path = `${encodeURIComponent(entityType)}/${encodeURIComponent(entityId)}`
  const queryKey = ['watchlist-check', entityType, entityId]
  const flag = useQuery({ queryKey,
    queryFn: () => apiClient.get(`/api/v1/watchlists/check/${path}`).then(r => r.data as { inWatchlist: boolean }),
  })
  const toggle = useMutation({
    mutationFn: async () => {
      const removing = flag.data?.inWatchlist === true
      if (removing) await apiClient.delete(`/api/v1/watchlists/${path}`)
      else await apiClient.post('/api/v1/watchlists/', {
        entity_type: entityType, entity_id: entityId, entity_name: profile.name,
        notes: 'Flagged for personal review from entity profile. Not a risk finding.',
      })
      return !removing
    },
    onSuccess: (inWatchlist) => {
      qc.setQueryData(queryKey, { inWatchlist })
      qc.invalidateQueries({ queryKey: ['watchlist'] })
      setMessage(inWatchlist ? 'Flagged in your personal watchlist. Risk score unchanged.' : 'Personal review flag removed.')
    },
    onError: () => { setMessage(''); qc.invalidateQueries({ queryKey }) },
  })

  function exportProfile() {
    setExportError('')
    try {
      const snapshot = {
        schema_version: 'entity-profile-export/v1', exported_at: new Date().toISOString(),
        entity_type: entityType, entity_id: entityId,
        notice: 'Snapshot of the displayed profile, not a complete due-diligence report or independent verification. Network graph and Gemini reports are not included.',
        profile,
      }
      const url = URL.createObjectURL(new Blob([JSON.stringify(snapshot, null, 2)], { type: 'application/json' }))
      const link = document.createElement('a')
      link.href = url
      link.download = `satorix-${entityType}-${entityId}`.replace(/[^a-zA-Z0-9_.-]/g, '_') + '.json'
      document.body.appendChild(link)
      try { link.click() } finally { link.remove(); setTimeout(() => URL.revokeObjectURL(url), 1000) }
      setMessage('Profile JSON download requested. Check your browser downloads.')
    } catch {
      setExportError('Could not export this profile. Please reload and retry.')
    }
  }

  return <div className="max-w-xs">
    <div className="flex gap-2">
      <button type="button" aria-pressed={flag.data?.inWatchlist === true}
        title="Toggle personal review flag in your watchlist; does not change recorded risk"
        disabled={!flag.data || flag.isError || toggle.isPending || flag.isFetching}
        onClick={() => { setMessage(''); toggle.mutate() }}
        className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 text-sm text-gray-700 rounded-lg hover:bg-gray-50 disabled:opacity-50 disabled:cursor-not-allowed">
        <Flag className="h-3.5 w-3.5" /><span>{toggle.isPending ? 'Saving…' : flag.data?.inWatchlist ? 'Unflag' : 'Flag'}</span>
      </button>
      <button type="button" title="Download displayed profile as JSON" onClick={exportProfile}
        className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 text-sm text-gray-700 rounded-lg hover:bg-gray-50">
        <Download className="h-3.5 w-3.5" /><span>Export</span>
      </button>
    </div>
    {message && <p role="status" className="text-xs text-gray-600 mt-2">{message}</p>}
    {(flag.isError || toggle.isError) && <p role="alert" className="text-xs text-red-600 mt-2">Could not load or save your personal flag. <button onClick={() => { toggle.reset(); flag.refetch() }}>Reload flag status</button></p>}
    {exportError && <p role="alert" className="text-xs text-red-600 mt-2">{exportError}</p>}
  </div>
}
