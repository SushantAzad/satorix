import { apiClient } from './client'
import type { EntityProfile, SearchResult, NetworkGraph, WatchlistItem } from './types'

export const entitiesApi = {
  getFixtureEvidence: (recordId: string) => apiClient.get<{
    recordId: string; filename: string; dataRow: number; fileSha256: string
    batchId: string; source: string; synthetic: boolean; fields: Record<string, string>
  }>(`/api/v1/evidence/fixtures/${encodeURIComponent(recordId)}`).then(r => r.data),
  search: (q: string, limit = 10) =>
    apiClient.get('/api/v1/entities/search', { params: { q, limit } })
      .then(r => (Array.isArray(r.data) ? r.data : (r.data.results ?? [])) as SearchResult[]),
  getProfile: (entityType: string, entityId: string) =>
    apiClient.get<EntityProfile>(`/api/v1/entities/${entityType}/${entityId}`).then(r => r.data),
  getNetwork: (entityType: string, entityId: string, depth = 2) =>
    apiClient.get<NetworkGraph>(`/api/v1/network/${entityType}/${entityId}`, { params: { depth } }).then(r => r.data),
  getRecent: () => apiClient.get('/api/v1/entities/recent').then(r => r.data),
  getWatchlist: () => apiClient.get<WatchlistItem[]>('/api/v1/watchlists').then(r => r.data),
  addToWatchlist: (item: Omit<WatchlistItem, 'id' | 'addedAt'>) =>
    apiClient.post('/api/v1/watchlists', item).then(r => r.data),
  removeFromWatchlist: (entityType: string, entityId: string) =>
    apiClient.delete(`/api/v1/watchlists/${entityType}/${entityId}`).then(r => r.data),
  checkWatchlist: (entityType: string, entityId: string) =>
    apiClient.get(`/api/v1/watchlists/check/${entityType}/${entityId}`).then(r => r.data),
}
