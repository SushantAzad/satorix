import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { apiClient } from '@shared/api/client'

export default function CsvImport() {
  const [kind, setKind] = useState('company')
  const [source, setSource] = useState('Local CSV upload')
  const [synthetic, setSynthetic] = useState(true)
  const [csv, setCsv] = useState('')
  const [schema, setSchema] = useState<any>(null)
  const [mapping, setMapping] = useState<Record<string, string>>({})
  const [preview, setPreview] = useState<any>(null)
  const [result, setResult] = useState<any>(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const history = useQuery({ queryKey: ['imports'], queryFn: () => apiClient.get('/api/v1/imports/').then(r => r.data) })
  const invalidate = () => { setPreview(null); setResult(null) }
  async function inspect(text: string) {
    setBusy(true); setError(''); setSchema(null); invalidate()
    try {
      const r = await apiClient.post('/api/v1/imports/preview', { kind, source, synthetic, csv_text: text })
      setSchema(r.data)
      setMapping(Object.fromEntries(Object.keys(r.data.fields).map(k => [k, r.data.headers.includes(k) ? k : ''])))
    } catch (e: any) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Could not read CSV. Check permissions and format.') }
    finally { setBusy(false) }
  }
  async function validate() {
    setBusy(true); setError(''); invalidate()
    try {
      const r = await apiClient.post('/api/v1/imports/preview', { kind, source, synthetic, csv_text: csv, mapping })
      setPreview(r.data); history.refetch()
    } catch (e: any) { setError(typeof e.response?.data?.detail === 'string' ? e.response.data.detail : 'Validation failed') }
    finally { setBusy(false) }
  }
  async function commit() {
    setBusy(true); setError('')
    try {
      const r = await apiClient.post(`/api/v1/imports/${preview.import_id}/commit`, {}, { timeout: 150000 })
      setResult(r.data); setPreview(null); history.refetch()
    } catch { setError('Import response unavailable. Check recent imports; retry confirmation of this preview only after checking status.'); history.refetch() }
    finally { setBusy(false) }
  }
  return <div className="p-8 max-w-5xl space-y-5">
    <h1 className="text-2xl font-semibold">CSV Import</h1>
    <p>Import companies and directors first, then directorships. UTF-8 CSV, maximum 256 KB and 200 rows.</p>
    <p className="text-sm text-gray-600">IDs are stable internal identifiers (CIN/DIN may be used but are not verified). Blank optional cells preserve existing values. Unmapped columns are ignored. No risk scores are calculated. Registered address is a profile field; address graph links are not created here.</p>
    <fieldset disabled={busy} className="bg-white rounded border p-5 space-y-4">
      <button type="button" className="border rounded px-3 py-2" onClick={() => {
        const templates: Record<string, string> = {
          company: 'id,name,status,registeredAddress\nCSV-DEMO-C-001,SYNTHETIC CSV Demo Company,ACTIVE,Synthetic address\n',
          director: 'id,name\nCSV-DEMO-D-001,SYNTHETIC CSV Demo Director\n',
          directorship: 'director_id,company_id,appointed_date\nCSV-DEMO-D-001,CSV-DEMO-C-001,2025-01-01\n',
        }
        const url = URL.createObjectURL(new Blob([templates[kind]], { type: 'text/csv;charset=utf-8' }))
        const link = document.createElement('a'); link.href = url; link.download = `synthetic-${kind}-template.csv`; link.click()
        setTimeout(() => URL.revokeObjectURL(url), 1000)
      }}>Download synthetic template</button>
      <label className="block">Record type <select className="border rounded p-2 ml-3" value={kind} onChange={e => { setKind(e.target.value); setSchema(null); setCsv(''); invalidate() }}>
        <option value="company">Companies</option><option value="director">Directors</option><option value="directorship">Directorships</option>
      </select></label>
      <label className="block">Source name <input className="border rounded p-2 ml-3" maxLength={100} value={source} onChange={e => { setSource(e.target.value); invalidate() }} /></label>
      <label className="block"><input type="checkbox" checked={synthetic} onChange={e => { setSynthetic(e.target.checked); invalidate() }} /> Synthetic test data (new entities only; existing classification is preserved)</label>
      <label className="block">CSV file <input key={kind} type="file" accept=".csv,text/csv" className="ml-3" onChange={async e => {
        const file = e.target.files?.[0]; if (!file) return
        if (file.size > 256000) { setError('Maximum file size is 256 KB'); setSchema(null); invalidate(); return }
        try { const text = new TextDecoder('utf-8', { fatal: true }).decode(await file.arrayBuffer()); setCsv(text); await inspect(text) }
        catch { setError('File must be valid UTF-8 CSV'); setSchema(null); invalidate() }
      }} /></label>
      {schema && <><h2 className="font-semibold">Map columns</h2>{Object.entries(schema.fields).map(([field, required]) =>
        <label className="block" key={field}>{field}{required ? ' *' : ''}
          <select className="border rounded p-2 ml-3" value={mapping[field] || ''} onChange={e => { setMapping({ ...mapping, [field]: e.target.value }); invalidate() }}>
            <option value="">Not mapped</option>{schema.headers.map((h: string) => <option key={h}>{h}</option>)}
          </select></label>)}
        <button className="bg-gray-900 text-white rounded px-4 py-2" disabled={!source.trim()} onClick={validate}>Validate preview</button></>}
    </fieldset>
    {busy && <p role="status">Processing… keep this page open.</p>}
    {error && <p role="alert" className="text-red-700">{error}</p>}
    {preview && <section className="border rounded bg-white p-5 space-y-3">
      <h2 className="font-semibold">Preview: {preview.status}</h2>
      <p>{Array.isArray(preview.rows) ? preview.rows.length : preview.rows} rows · {preview.existing_entities ?? 0} existing entities will be compared and may be updated.</p>
      {preview.errors?.map((e: any, i: number) => <p className="text-red-700" key={i}>Row {e.row}: {e.message}</p>)}
      {(preview.preview_rows || (Array.isArray(preview.rows) ? preview.rows : [])).map((r: any) =>
        <div className="border-t pt-2 text-sm break-words" key={r.row}>Row {r.row}: {Object.entries(r.data).map(([k, v]) => `${k}: ${v}`).join(' · ')}</div>)}
      {preview.status === 'ready' && <button disabled={busy} className="bg-blue-700 text-white rounded px-4 py-2" onClick={commit}>Confirm import</button>}
      <p className="text-sm">Validation rejects the entire file if any row is invalid. Runtime failures can leave partially imported rows; results report this explicitly.</p>
    </section>}
    {result && <section className="border rounded p-5"><h2 className="font-semibold">Import {result.status}</h2>
      <p>Accepted: {result.accepted ?? 0} · Failed: {result.failed ?? 0}</p>
      {result.errors?.map((e: any, i: number) => <p key={i}>Row {e.row}: {e.message}</p>)}
      {result.results?.map((r: any) => <p key={r.row}>Row {r.row}: {r.id} — {r.status}</p>)}
      <p className="text-sm mt-3">{result.note}</p>
      <p className="text-sm">Open Search or refresh an existing profile to view the imported records.</p>
    </section>}
    <section><h2 className="font-semibold mb-3">Recent imports and previews</h2>
      {history.isError && <p>Could not load import history. Sign in with an administrator or data-steward account.</p>}
      {history.data?.map((j: any) => <details className="border rounded p-3 mb-2" key={j.import_id}>
        <summary>{j.source} · {j.kind} · {j.status} · {new Date(j.created_at).toLocaleString()}</summary>
        <p>Accepted: {j.result.accepted ?? '—'} · Failed: {j.result.failed ?? '—'}</p>
        {j.result.results?.map((r: any) => <p key={r.row}>Row {r.row}: {r.id} — {r.status}</p>)}
      </details>)}
    </section>
  </div>
}
