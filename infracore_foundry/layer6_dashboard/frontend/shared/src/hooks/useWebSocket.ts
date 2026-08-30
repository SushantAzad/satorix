import { useEffect, useRef, useCallback } from 'react'

export function useWebSocket(sessionId: string, onMessage: (data: Record<string, unknown>) => void) {
  const wsRef = useRef<WebSocket | null>(null)
  const reconnectTimer = useRef<ReturnType<typeof setTimeout>>()
  const WS_URL = (typeof import.meta !== 'undefined' && (import.meta as any).env?.VITE_WS_URL) || 'ws://localhost:8007'

  const connect = useCallback(() => {
    if ((import.meta as any).env?.VITE_LOCAL_SAFE_MODE !== 'false') return
    const token = localStorage.getItem('satorix_token')
    if (!token) return
    try {
      const ws = new WebSocket(`${WS_URL}/ws/${sessionId}?token=${token}`)
      ws.onopen = () => console.log('[WS] Connected')
      ws.onmessage = (e) => { try { onMessage(JSON.parse(e.data)) } catch {} }
      ws.onclose = () => { reconnectTimer.current = setTimeout(connect, 5000) }
      ws.onerror = () => ws.close()
      wsRef.current = ws
    } catch (e) {}
  }, [sessionId, onMessage, WS_URL])

  useEffect(() => { connect(); return () => { clearTimeout(reconnectTimer.current); wsRef.current?.close() } }, [connect])

  return { send: useCallback((data: Record<string, unknown>) => {
    if (wsRef.current?.readyState === WebSocket.OPEN) wsRef.current.send(JSON.stringify(data))
  }, []) }
}
