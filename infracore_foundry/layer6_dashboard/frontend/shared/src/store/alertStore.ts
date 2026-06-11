import { create } from 'zustand'
import type { Alert } from '../api/types'

interface AlertState {
  alerts: Alert[]; unacknowledgedCount: number
  setAlerts: (alerts: Alert[]) => void
  addAlert: (alert: Alert) => void
  acknowledgeAlert: (alertId: string) => void
}

export const useAlertStore = create<AlertState>((set) => ({
  alerts: [], unacknowledgedCount: 0,
  setAlerts: (alerts) => set({ alerts, unacknowledgedCount: alerts.filter(a => !a.isAcknowledged).length }),
  addAlert: (alert) => set((s) => ({ alerts: [alert, ...s.alerts].slice(0, 100), unacknowledgedCount: s.unacknowledgedCount + (alert.isAcknowledged ? 0 : 1) })),
  acknowledgeAlert: (alertId) => set((s) => ({ alerts: s.alerts.map(a => a.alertId === alertId ? { ...a, isAcknowledged: true } : a), unacknowledgedCount: Math.max(0, s.unacknowledgedCount - 1) })),
}))
