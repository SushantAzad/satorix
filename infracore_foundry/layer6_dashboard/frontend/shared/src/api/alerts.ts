import { apiClient } from './client'
import type { Alert } from './types'

export interface AlertListResponse {
  alerts: Alert[]; total: number; unacknowledged: number; critical_count: number; high_count: number; matching?: number; last_scan?: string
}

export const alertsApi = {
  scan: () => apiClient.post('/api/v1/alerts/scan').then(r => r.data),
  list: (params?: { severity?: string; acknowledged?: boolean; limit?: number; offset?: number }) =>
    apiClient.get<AlertListResponse>('/api/v1/alerts', { params }).then(r => r.data),
  getSummary: () => apiClient.get('/api/v1/alerts/summary').then(r => r.data),
  getDetail: (alertId: string) => apiClient.get<Alert>(`/api/v1/alerts/${alertId}`).then(r => r.data),
  acknowledge: (alertId: string) => apiClient.patch(`/api/v1/alerts/${alertId}/acknowledge`, {}).then(r => r.data),
}
