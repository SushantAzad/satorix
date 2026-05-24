import React, { useEffect } from 'react'
import { useParams, useNavigate, Link } from 'react-router-dom'
import { useQuery } from '@tanstack/react-query'
import { Download, Flag, FileText, ArrowLeft, Brain } from 'lucide-react'
import { entitiesApi } from '@shared/api/entities'
import { useEntityStore } from '@shared/store/entityStore'
import { RiskBadge } from '@shared/components/RiskBadge'
import { AlertBadge } from '@shared/components/AlertBadge'
import { MetricCard } from '@shared/components/MetricCard'
import { LoadingSpinner } from '@shared/components/LoadingSpinner'
import { NetworkGraph } from '../components/graph/NetworkGraph'
import { formatDistanceToNow, parseISO } from 'date-fns'

const FLAG_COLORS: Record<string, string> = {
  CIRP_ACTIVE: 'bg-red-100 text-red-700 border border-red-200',
  OFFSHORE_DIRECTOR: 'bg-orange-100 text-orange-700 border border-orange-200',
  DISQUALIFIED_DIRECTOR: 'bg-red-100 text-red-700 border border-red-200',
  ADDRESS_CLUSTERING: 'bg-amber-100 text-amber-700 border border-amber-200',
  ONGOING_REGULATORY: 'bg-amber-100 text-amber-700 border border-amber-200',
  STRESSED_PROJECT: 'bg-orange-100 text-orange-700 border border-orange-200',
  STRUCK_OFF: 'bg-gray-100 text-gray-700 border border-gray-200',
}

const EVENT_ICONS: Record<string, string> = { regulatory: '⚖️', alert: '🚨', event: '📅', prediction: '🤖', trend: '📈', default: '📌' }

function DataFreshnessPill({ source, lastSynced }: { source: string; lastSynced: string }) {
  return <span className="text-xs text-gray-400">Source: {source} · {lastSynced}</span>
}

export function EntityProfile() {
  const { entityType = '', entityId = '' } = useParams<{ entityType: string; entityId: string }>()
  const nav = useNavigate()
  const addRecent = useEntityStore(s => s.addRecentView)

  const { data: profile, isLoading, error } = useQuery({
    queryKey: ['entity', entityType, entityId],
    queryFn: () => entitiesApi.getProfile(entityType, entityId),
    staleTime: 60_000,
  })

  const { data: network, isLoading: netLoading } = useQuery({
    queryKey: ['network', entityType, entityId],
    queryFn: () => entitiesApi.getNetwork(entityType, entityId, 2),
    staleTime: 120_000,
    enabled: !!profile,
  })

  useEffect(() => {
    if (profile) {
      addRecent({ entityType, entityId, name: profile.name, riskScore: profile.riskScore, viewedAt: new Date().toISOString() })
    }
  }, [profile, entityType, entityId, addRecent])

  if (isLoading) return <div className="flex items-center justify-center min-h-screen"><LoadingSpinner label="Loading entity data..." /></div>

  if (error || !profile) return (
    <div className="flex flex-col items-center justify-center min-h-screen gap-4">
      <p className="text-gray-500">Unable to load entity data.</p>
      <button onClick={() => nav(-1)} className="px-4 py-2 text-sm border border-gray-300 rounded-lg hover:bg-gray-50">Go back</button>
    </div>
  )

  const entityTypeLabel = entityType.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase())
  const primaryId = (profile.properties.cin || profile.properties.din || profile.properties.projectId || entityId) as string

  return (
    <div className="min-h-screen bg-white">
      {/* Back link */}
      <div className="px-8 py-3 border-b border-gray-100">
        <button onClick={() => nav(-1)} className="flex items-center gap-1 text-sm text-gray-500 hover:text-gray-900 transition-colors">
          <ArrowLeft className="h-3.5 w-3.5" /><span>Back</span>
        </button>
      </div>

      {/* Section 1: Entity Header (sticky) */}
      <div className="sticky top-14 z-30 bg-white border-b border-gray-200 shadow-sm px-8 py-4">
        <div className="flex items-start justify-between gap-6">
          <div className="min-w-0">
            <div className="flex items-center gap-2 mb-1">
              <span className="px-2 py-0.5 bg-gray-100 text-gray-600 text-xs rounded-md font-medium">{entityTypeLabel}</span>
              {primaryId && primaryId !== entityId && <span className="text-xs text-gray-400 font-mono">{String(primaryId)}</span>}
            </div>
            <h1 className="text-2xl font-bold text-gray-900 leading-tight">{profile.name}</h1>
            {profile.riskFlags.length > 0 && (
              <div className="flex flex-wrap gap-1.5 mt-2">
                {profile.riskFlags.map(flag => (
                  <span key={flag} className={`px-2 py-0.5 text-xs rounded-md font-medium ${FLAG_COLORS[flag] ?? 'bg-gray-100 text-gray-600'}`}>
                    {flag.replace(/_/g, ' ')}
                  </span>
                ))}
              </div>
            )}
          </div>
          <div className="flex items-center gap-3 flex-shrink-0">
            <RiskBadge band={profile.riskBand} score={profile.riskScore} size="lg" />
            <div className="flex flex-col gap-2">
              <Link to={`/reports?entity=${entityType}/${entityId}`}
                className="flex items-center gap-1.5 px-3 py-1.5 bg-gray-900 text-white text-sm font-medium rounded-lg hover:bg-gray-800 transition-colors">
                <FileText className="h-3.5 w-3.5" /><span>Due Diligence</span>
              </Link>
              {entityType === 'company' && (
                <Link to={`/intelligence/${entityId}`}
                  className="flex items-center gap-1.5 px-3 py-1.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition-colors">
                  <Brain className="h-3.5 w-3.5" /><span>Intelligence</span>
                </Link>
              )}
              <div className="flex gap-2">
                <button className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 text-sm text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                  <Flag className="h-3.5 w-3.5" /><span>Flag</span>
                </button>
                <button className="flex items-center gap-1 px-3 py-1.5 border border-gray-300 text-sm text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
                  <Download className="h-3.5 w-3.5" /><span>Export</span>
                </button>
              </div>
            </div>
          </div>
        </div>
        <div className="flex items-center justify-between mt-2">
          <DataFreshnessPill source={profile.dataFreshness.source} lastSynced={profile.dataFreshness.lastSynced} />
          {profile.mlPredictions.cirpProbability !== undefined && (
            <span className={`text-xs font-medium px-2 py-1 rounded-md ${profile.mlPredictions.cirpProbability > 0.6 ? 'bg-red-50 text-red-700' : profile.mlPredictions.cirpProbability > 0.3 ? 'bg-amber-50 text-amber-700' : 'bg-green-50 text-green-700'}`}>
              CIRP Risk: {Math.round(profile.mlPredictions.cirpProbability * 100)}%
            </span>
          )}
        </div>
      </div>

      {/* Section 2: Intelligence Summary */}
      <div className="px-8 py-6 border-b border-gray-100">
        <div className="bg-gray-50 rounded-xl p-6">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-3">Intelligence Summary</p>
          <p className="text-base text-gray-700 leading-relaxed">{profile.intelligenceSummary || 'Intelligence summary is being generated. Please check back shortly.'}</p>
          <p className="text-xs text-gray-400 mt-3 text-right">Powered by Satorix AI</p>
        </div>
      </div>

      {/* Section 3: Metrics */}
      {profile.metrics.length > 0 && (
        <div className="px-8 py-6 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Key Metrics</p>
          <div className="flex gap-3 overflow-x-auto scrollbar-thin pb-2">
            {profile.metrics.map(m => <MetricCard key={m.label} metric={m} />)}
          </div>
        </div>
      )}

      {/* Section 4: Network Graph */}
      <div className="px-8 py-6 border-b border-gray-100">
        <div className="flex items-center justify-between mb-4">
          <div>
            <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider">Entity Network</p>
            <p className="text-xs text-gray-400 mt-0.5">2-degree connections · {network?.metadata?.entityCount ?? 0} entities · {network?.metadata?.relationshipCount ?? 0} relationships</p>
          </div>
          <Link to={`/network/${entityType}/${entityId}`} className="text-xs text-gray-500 hover:text-gray-900 border border-gray-300 px-2 py-1 rounded-lg transition-colors">
            Expand →
          </Link>
        </div>
        {netLoading ? (
          <div className="h-96 bg-gray-50 rounded-xl animate-pulse flex items-center justify-center">
            <span className="text-sm text-gray-400">Loading network...</span>
          </div>
        ) : network && (network.nodes?.length ?? 0) > 0 ? (
          <div className="h-96 border border-gray-200 rounded-xl overflow-hidden">
            <NetworkGraph nodes={network.nodes ?? []} edges={network.edges ?? []} />
          </div>
        ) : (
          <div className="h-48 bg-gray-50 rounded-xl flex items-center justify-center border border-gray-200">
            <p className="text-sm text-gray-400">Network data unavailable</p>
          </div>
        )}
      </div>

      {/* Section 5: Intelligence Feed */}
      {(profile.recentEvents.length > 0 || profile.activeAlerts.length > 0) && (
        <div className="px-8 py-6 border-b border-gray-100">
          <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Intelligence Feed</p>
          <div className="space-y-3">
            {profile.activeAlerts.slice(0, 3).map(a => (
              <div key={a.alertId} className="flex items-start gap-3 p-3 bg-red-50 border border-red-100 rounded-xl">
                <span className="text-lg flex-shrink-0">🚨</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <AlertBadge severity={a.severity} />
                    <span className="text-xs text-gray-400">{a.createdAt ? formatDistanceToNow(parseISO(a.createdAt), { addSuffix: true }) : ''}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-900">{a.title}</p>
                  <p className="text-xs text-gray-500 mt-0.5">{a.message}</p>
                </div>
              </div>
            ))}
            {profile.recentEvents.slice(0, 5).map(ev => (
              <div key={ev.eventId} className="flex items-start gap-3 p-3 border border-gray-100 rounded-xl hover:bg-gray-50 transition-colors">
                <span className="text-lg flex-shrink-0">{EVENT_ICONS[ev.eventType] ?? EVENT_ICONS.default}</span>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 mb-0.5">
                    <span className="text-xs text-gray-400 capitalize">{ev.eventType.replace('_', ' ')}</span>
                    <span className="text-gray-300">·</span>
                    <span className="text-xs text-gray-400">{ev.timestamp ? formatDistanceToNow(parseISO(ev.timestamp), { addSuffix: true }) : ''}</span>
                  </div>
                  <p className="text-sm font-medium text-gray-900">{ev.headline}</p>
                  {ev.description && <p className="text-xs text-gray-500 mt-0.5">{ev.description}</p>}
                </div>
              </div>
            ))}
          </div>
        </div>
      )}

      {/* Section 6: Related Intelligence */}
      <div className="px-8 py-6">
        <p className="text-xs font-semibold text-gray-400 uppercase tracking-wider mb-4">Related Intelligence</p>
        <div className="text-sm text-gray-400 italic">Use the Network Explorer for full relationship analysis →</div>
        <div className="mt-4">
          <Link to={`/network/${entityType}/${entityId}`}
            className="inline-flex items-center gap-2 px-4 py-2 border border-gray-300 text-sm text-gray-700 rounded-lg hover:bg-gray-50 transition-colors">
            Open Network Explorer
          </Link>
        </div>
      </div>
    </div>
  )
}
