# Intelligence alerts and optional Gemini review

Alerts are rule-based, not real-time or AI-generated. Open `/alerts` and select **Run signal scan** after changing imported data. It scans only the signed-in private tenant (up to 5000 objects / 10000 links). It flags companies with recorded risk >=70 and directors/companies directly linked by recorded DIRECTED/OWNS relationships to such companies. Unknown scores are not zero; inferred links do not trigger exposure alerts. Association is not wrongdoing.

The PostgreSQL scan snapshot stores acknowledgements and last scan time. Repeat scans preserve acknowledgements for unchanged signals; changed evidence reopens a signal. Signals no longer present disappear from the current snapshot (this is not an audit-history system). Failed scans retain the previous snapshot. Filters, pagination and the notification bell use persisted state. No extra database or background worker is required.

## Gemini setup

1. Copy `.env.gemini.example` to `.env.gemini` in this directory. Enter `GEMINI_API_KEY` and a currently available `GEMINI_MODEL` from your Google AI Studio account. Never paste the key into chat or set a frontend/VITE variable. `.env.gemini` is ignored by Git.
2. Run `./scripts/start-focused.ps1 -EnableGemini` (PowerShell). Requires Docker Compose support for `gw_priority`. This explicitly adds external networking to Layer 6 only. The Python destination guard permits the Gemini hostname on port 443; this is defense in depth, NOT an OS sandbox against arbitrary native code. Other services retain their offline network.
3. Generate/open a due-diligence report. At the bottom, choose **Preview data to send**, inspect the exact evidence, give consent, then **Send to Gemini**. Both real and synthetic records are supported. Provider charges and data-processing terms apply.
4. The AI draft is saved as `gemini_ai_review` and included in JSON downloads. Scores are not modified. Each saved snapshot is enriched once; concurrent repeated requests reuse the stored draft. Reports still expire after 24 hours. Download copies to retain them.

Run `./scripts/start-focused.ps1` without the flag to recreate Layer 6 without Gemini networking/key injection. Safe mode is unchanged. Default focused Development remains offline. No live Gemini request is necessary to use local intelligence, alerts or reports.

Evidence is allowlisted and bounded to 20 nodes, 40 edges and 32KB. It includes names/identifiers, recorded scores, relation types and synthetic indicators, not entire source rows or arbitrary properties. Payload preview/hash binds consent to the sent snapshot. Names may contain sensitive or malicious text; prompts treat it as untrusted data. Output is an unverified AI draft rendered as text, never executed. Original local report limitations remain applicable to the original snapshot; the added AI section is not external verification. Failed/blocked/truncated provider output is not saved, and no automatic retry is performed. A manual retry after an uncertain failure can incur another charge.

Official protocol: [Gemini generateContent](https://ai.google.dev/api/generate-content), [API key authentication](https://ai.google.dev/api). The backend uses existing httpx, not an additional model SDK or database.
