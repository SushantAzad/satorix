import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'
import axios from 'axios'
import { CheckCircle2, AlertTriangle } from 'lucide-react'
import ServiceCard, { ServiceCardProps } from '../components/ServiceCard'
import DAGTable, { DAGRow } from '../components/DAGTable'

interface SystemHealthResponse {
  services: Array<{
    name: string
    port: number
    status: 'healthy' | 'degraded' | 'down' | 'unknown'
    response_time_ms: number
    last_checked: string
  }>
  dags: DAGRow[]
}

const KNOWN_SERVICES: Array<{ name: string; port: number }> = [
  { name: 'postgres', port: 5432 },
  { name: 'redis', port: 6379 },
  { name: 'kafka', port: 9092 },
  { name: 'elasticsearch', port: 9200 },
  { name: 'neo4j-browser', port: 7474 },
  { name: 'minio', port: 9000 },
  { name: 'airflow', port: 8080 },
  { name: 'layer1-api', port: 8001 },
  { name: 'layer2-api', port: 8002 },
  { name: 'layer3-api', port: 8003 },
  { name: 'layer4-api', port: 8004 },
  { name: 'layer5-api', port: 8005 },
  { name: 'neo4j-bolt', port: 7687 },
  { name: 'minio-console', port: 9001 },
]

function buildFallback(): SystemHealthResponse {
  return {
    services: KNOWN_SERVICES.map(s => ({
      name: s.name,
      port: s.port,
      status: 'unknown' as const,
      response_time_ms: 0,
      last_checked: '—',
    })),
    dags: [],
  }
}

export default function SystemHealth() {
  const { data, isLoading, isError, refetch } = useQuery<SystemHealthResponse>({
    queryKey: ['system-health'],
    queryFn: async () => {
      const res = await axios.get<SystemHealthResponse>(
        '/api/v1/operational/system-health',
      )
      return res.data
    },
    refetchInterval: 30_000,
  })

  useEffect(() => {
    const id = setInterval(() => refetch(), 30_000)
    return () => clearInterval(id)
  }, [refetch])

  const display = data ?? buildFallback()
  const allHealthy = display.services.every(s => s.status === 'healthy')
  const anyDown = display.services.some(s => s.status === 'down')

  const serviceMap = new Map(display.services.map(s => [s.name, s]))
  const cards: ServiceCardProps[] = KNOWN_SERVICES.map(ks => {
    const live = serviceMap.get(ks.name)
    return {
      name: ks.name,
      port: ks.port,
      status: live?.status ?? 'unknown',
      responseTimeMs: live?.response_time_ms ?? 0,
      lastChecked: live?.last_checked ?? '—',
    }
  })

  return (
    <div className="p-8">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">System Health</h1>
        <p className="text-sm text-gray-500 mt-1">14 services monitored · Auto-refresh every 30s</p>
      </div>

      {/* Overall status banner */}
      {!isLoading && !isError && (
        <div
          className={`flex items-center gap-3 px-5 py-3.5 rounded-xl mb-6 border ${
            allHealthy
              ? 'bg-green-50 border-green-200 text-green-800'
              : anyDown
              ? 'bg-red-50 border-red-200 text-red-800'
              : 'bg-amber-50 border-amber-200 text-amber-800'
          }`}
        >
          {allHealthy ? (
            <CheckCircle2 size={18} className="text-green-600 flex-shrink-0" />
          ) : (
            <AlertTriangle size={18} className="flex-shrink-0" />
          )}
          <span className="font-semibold text-sm">
            {allHealthy
              ? 'All Systems Operational'
              : anyDown
              ? 'One or more services are down'
              : 'One or more services are degraded'}
          </span>
          {isLoading && (
            <span className="ml-auto text-xs opacity-60">Refreshing…</span>
          )}
        </div>
      )}

      {isLoading && (
        <div className="grid grid-cols-3 gap-4 mb-8">
          {Array.from({ length: 14 }).map((_, i) => (
            <div key={i} className="h-24 bg-gray-100 rounded-xl animate-pulse" />
          ))}
        </div>
      )}

      {isError && (
        <div className="bg-red-50 border border-red-200 rounded-xl px-5 py-4 mb-6 text-sm text-red-700">
          Could not reach API — showing last known state. Service statuses may be stale.
        </div>
      )}

      {/* Services grid */}
      {!isLoading && (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4 mb-8">
          {cards.map(card => (
            <ServiceCard key={card.name} {...card} />
          ))}
        </div>
      )}

      {/* DAG table */}
      <div className="bg-white rounded-xl border border-gray-200 shadow-sm">
        <div className="px-6 py-4 border-b border-gray-100">
          <h2 className="font-semibold text-gray-900 text-base">Airflow DAGs</h2>
          <p className="text-xs text-gray-400 mt-0.5">Pipeline schedules and success rates</p>
        </div>
        <DAGTable dags={display.dags} />
      </div>
    </div>
  )
}
