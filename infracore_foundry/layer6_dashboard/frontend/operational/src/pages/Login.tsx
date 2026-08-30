import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import { useAuth } from '@shared/hooks/useAuth'

export default function Login() {
  const { login } = useAuth()
  const nav = useNavigate()
  const [params] = useSearchParams()
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  return <form className="max-w-sm mx-auto mt-20 p-6 bg-white border rounded space-y-4" onSubmit={async e => {
    e.preventDefault(); setBusy(true); setError('')
    try { await login(email, password); const from = params.get('from') || '/imports'; nav(from.startsWith('/') && !from.startsWith('//') && !from.includes('\\') ? from : '/imports') }
    catch { setError('Sign-in failed. Check your credentials.') } finally { setBusy(false) }
  }}>
    <h1 className="text-xl font-semibold">Satorix Operations — Sign in</h1>
    <label className="block">Email<input className="border p-2 w-full" type="email" required value={email} onChange={e => setEmail(e.target.value)} /></label>
    <label className="block">Password<input className="border p-2 w-full" type="password" required value={password} onChange={e => setPassword(e.target.value)} /></label>
    {error && <p role="alert">{error}</p>}
    <button disabled={busy} className="bg-gray-900 text-white p-2 rounded">{busy ? 'Signing in…' : 'Sign in'}</button>
  </form>
}
