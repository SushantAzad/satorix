import { apiClient } from './client'
import type { EntityProfile, SearchResult, NetworkGraph, WatchlistItem } from './types'

export const entitiesApi = {
  search: (q: string, limit = 10) =>
    apiClient.get<SearchResult[]>('/api/v1/entities/search', { params: { q, limit } }).then(r => r.data),
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
