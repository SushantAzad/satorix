import { create } from 'zustand'
import { persist } from 'zustand/middleware'

export interface RecentEntity { entityType: string; entityId: string; name: string; riskScore: number; viewedAt: string }

interface EntityState {
  recentViews: RecentEntity[]
  addRecentView: (entity: RecentEntity) => void
}

export const useEntityStore = create<EntityState>()(
  persist(
    (set) => ({
      recentViews: [],
      addRecentView: (entity) => set((s) => {
        const filtered = s.recentViews.filter(e => !(e.entityType === entity.entityType && e.entityId === entity.entityId))
        return { recentViews: [entity, ...filtered].slice(0, 20) }
      }),
    }),
    { name: 'satorix-entities' }
  )
)
