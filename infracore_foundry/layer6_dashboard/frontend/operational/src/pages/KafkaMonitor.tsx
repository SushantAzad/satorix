import { useQuery } from '@tanstack/react-query'
import axios from 'axios'
import TopicCard, { TopicCardProps } from '../components/TopicCard'

const KNOWN_TOPICS = [
  'layer1.raw.parquet.ready',
  'layer2.clean.ready',
  'layer3.ontology.changes',
  'layer3.alerts.created',
  'layer3.ingest.complete',
  'layer4.recompute.triggers',
  'layer4.cache.invalidate',
  'layer5.risk.scores.updated',
  'layer5.predictions.ready',
]

interface KafkaTopicData {
  name: string
  messages_per_sec: number
  consumer_group_lag: number
  partition_count: number
  retention: string
}

interface KafkaTopicsResponse {
  topics: KafkaTopicData[]
}

function buildFallback(): KafkaTopicsResponse {
  return {
    topics: KNOWN_TOPICS.map(name => ({
      name,
      messages_per_sec: 0,
      consumer_group_lag: 0,
      partition_count: 3,
      retention: '7d',
    })),
  }
}

export default function KafkaMonitor() {
  const { data, isLoading, isError } = useQuery<KafkaTopicsResponse>({
    queryKey: ['kafka-topics'],
    queryFn: async () => {
      const res = await axios.get<KafkaTopicsResponse>('/api/v1/operational/kafka-topics')
      return res.data
    },
    refetchInterval: 10_000,
  })

  const display = data ?? buildFallback()

  // Merge live data with known topics so all 9 always show
  const topicMap = new Map((display.topics ?? []).map(t => [t.name, t]))
  const cards: TopicCardProps[] = KNOWN_TOPICS.map(name => {
    const live = topicMap.get(name)
    return {
      name,
      messagesPerSec: live?.messages_per_sec ?? 0,
      consumerGroupLag: live?.consumer_group_lag ?? 0,
      partitionCount: live?.partition_count ?? 3,
      retention: live?.retention ?? '7d',
    }
  })

  return (
    <div className="p-8">
      <div className="mb-6">
        <h1 className="text-2xl font-bold text-gray-900">Kafka Topics</h1>
        <p className="text-sm text-gray-500 mt-1">9 topics · Auto-refresh every 10s</p>
      </div>

      {isError && (
        <div className="bg-amber-50 border border-amber-200 rounded-xl px-5 py-3.5 mb-6 text-sm text-amber-700">
          Could not reach Kafka metrics API — displaying fallback data.
        </div>
      )}

      {isLoading ? (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="h-36 bg-gray-800 rounded-xl animate-pulse" />
          ))}
        </div>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 xl:grid-cols-3 gap-4">
          {cards.map(card => (
            <TopicCard key={card.name} {...card} />
          ))}
        </div>
      )}
    </div>
  )
}
