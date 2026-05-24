import { apiClient } from './client'

export interface RiskSignal {
  name: string
  feature: string
  value: number
  severity: 'critical' | 'high' | 'medium' | 'info'
}

export interface Prediction {
  entity_id?: string
  probability?: number
  risk_score?: number
  confidence?: number
  prediction_label?: string
  features_used?: string[]
  model_type?: string
  explanation?: string
}

export interface IntelligenceData {
  cin: string
  prediction: Prediction
  features: Record<string, number | null>
  risk_signals: RiskSignal[]
  trends: Record<string, unknown>
  benchmark: Record<string, unknown>
  correlations: Record<string, unknown>
  scenarios: Record<string, unknown>
  risk_score: Record<string, unknown>
  network_influence: Record<string, unknown>
}

export interface AskResponse {
  answer: string
  run_id?: string
  status?: string
}

export const intelligenceApi = {
  getCompanyIntelligence: async (cin: string): Promise<IntelligenceData> => {
    const res = await apiClient.get(`/api/v1/intelligence/${cin}`)
    return res.data
  },

  askQuestion: async (question: string, cin?: string): Promise<AskResponse> => {
    const res = await apiClient.post('/api/v1/intelligence/ask', { question, cin }, { timeout: 120000 })
    return res.data
  },
}
