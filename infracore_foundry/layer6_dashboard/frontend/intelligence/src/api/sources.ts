import { apiClient } from '@shared/api/client'

export interface DataSource {
  id: string
  source_name: string
  source_type: string
  client_id?: string
  status?: string
  last_sync?: string | null
  record_count?: number
  config?: Record<string, unknown>
  created_at?: string
}

export interface CreateSourcePayload {
  source_name: string
  source_type: string
  config: Record<string, unknown>
}

export interface TestResult {
  success: boolean
  message?: string
  record_count?: number
  schema_columns?: string[]
  error?: string
}

export const sourcesApi = {
  list: (): Promise<DataSource[]> =>
    apiClient.get('/api/v1/sources/').then(r => r.data ?? []),

  create: (payload: CreateSourcePayload): Promise<DataSource> =>
    apiClient.post('/api/v1/sources/', payload).then(r => r.data),

  test: (sourceId: string): Promise<TestResult> =>
    apiClient.post(`/api/v1/sources/${sourceId}/test`).then(r => r.data),

  health: (sourceId: string): Promise<DataSource> =>
    apiClient.get(`/api/v1/sources/${sourceId}/health`).then(r => r.data),

  sync: (sourceId: string): Promise<{ triggered: boolean }> =>
    apiClient.post(`/api/v1/sources/${sourceId}/sync`).then(r => r.data),

  delete: (sourceId: string): Promise<void> =>
    apiClient.delete(`/api/v1/sources/${sourceId}`).then(() => undefined),
}
