export type RiskBand = 'HIGH' | 'MEDIUM' | 'LOW' | 'NONE'
export type AlertSeverity = 'CRITICAL' | 'HIGH' | 'MEDIUM' | 'LOW'
export type EntityType = 'company' | 'director' | 'project' | 'address' | 'regulatory_action' | 'legal_case' | 'insolvency_proceeding' | 'alert' | 'event'

export interface User {
  id: string; email: string; name: string; role: string; client_id?: string
}

export interface SearchResult {
  entityId: string; entityType: EntityType; name: string; riskScore: number
  riskBand: RiskBand; riskFlags: string[]; description: string; matchScore: number
}

export interface MetricData {
  label: string; value: string | number | null; trend: 'up' | 'down' | 'stable' | null
  color: 'red' | 'amber' | 'green' | 'gray'; sparkline?: number[]; source?: string; unit?: string
}

export interface Alert {
  alertId: string; severity: AlertSeverity; alertType: string; title: string; message: string
  affectedEntityType: string; affectedEntityId: string; affectedEntityName?: string
  isActive: boolean; isAcknowledged: boolean; acknowledgedBy?: string; acknowledgedAt?: string
  createdAt: string; source: 'ML_MODEL' | 'RULE_ENGINE' | 'MANUAL'; confidence?: number
  shapExplanation?: ShapFeature[]
}

export interface ShapFeature {
  feature: string; value: number | string; shapValue: number; contribution: string
}

export interface EntityProfile {
  entityType: string; entityId: string; name: string; riskScore: number; riskBand: RiskBand
  riskFlags: string[]; properties: Record<string, unknown>; intelligenceSummary: string
  metrics: MetricData[]; activeAlerts: Alert[]; recentEvents: TimelineEvent[]
  mlPredictions: { cirpProbability?: number; projectCompletionProbability?: number; confidence?: number }
  trends?: TrendData[]; benchmark?: BenchmarkData; influenceScore?: number
  clusterInfo?: ClusterInfo; dataFreshness: { source: string; lastSynced: string }
}

export interface TimelineEvent {
  eventId: string; eventType: string; timestamp: string; headline: string
  description: string; severity?: AlertSeverity; source?: string; url?: string
}

export interface TrendData {
  metric: string; direction: 'improving' | 'deteriorating' | 'stable'; changePercent: number
  periods: number; values: number[]; dates: string[]
}

export interface BenchmarkData {
  sector: string; peerCount: number; percentileRank: number
  metrics: Record<string, { value: number; percentile: number; sectorMedian: number }>
}

export interface ClusterInfo { clusterId: string; clusterLabel: string; memberCount: number; dominantPattern: string }

export interface CytoscapeNode {
  data: {
    id: string; label: string; entityType: string; riskScore: number; riskBand: RiskBand
    riskFlags: string[]; betweennessCentrality: number; isAnomalous: boolean
    properties: Record<string, unknown>; size: number
  }
}

export interface CytoscapeEdge {
  data: {
    id: string; source: string; target: string; linkType: string
    isInferred: boolean; properties: Record<string, unknown>; label: string
  }
}

export interface NetworkGraph {
  nodes: CytoscapeNode[]; edges: CytoscapeEdge[]
  metadata: { entityCount: number; relationshipCount: number; maxDepth: number }
}

export interface WatchlistItem {
  id: string; entityType: string; entityId: string; entityName: string; addedAt: string; notes?: string
}

export interface Report {
  id: string; entityType: string; entityId: string; entityName?: string; reportType: string
  status: 'pending' | 'generating' | 'completed' | 'failed'; generatedAt?: string; content?: ReportContent
}

export interface ReportContent {
  executiveSummary: string; sections: ReportSection[]
}

export interface ReportSection {
  id: string; title: string; content: string; dataPoints?: DataPoint[]; edited?: boolean
}

export interface DataPoint { label: string; value: string; source: string; lastUpdated: string }
