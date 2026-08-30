"""Static, offline inventory. Never imports application code or contacts an endpoint."""
import ast,json,os,re
from pathlib import Path
from urllib.parse import urlsplit
ROOT=Path(__file__).resolve().parents[1]
UNKNOWN='UNKNOWN OR REQUIRES MANUAL REVIEW'
READ='EXTERNAL READ ONLY'
EFFECT='EXTERNAL WITH POTENTIAL SIDE EFFECTS'
LOCAL='LOCAL ONLY BUT REQUIRES CONFIGURATION'
SAFE='SAFE LOCAL'
# Endpoint patterns are descriptive inventory entries, never probe targets.
endpoints={
'azure_blob':'https://{account_name}.blob.core.windows.net (Azure SDK)',
'box':'api.box.com; upload.box.com; api.box.com/oauth2/token',
'csv':'config.file_path; HTTP(S) supported outside safe mode',
'excel':'config.file_path (local workbook; network-share paths require review)',
'pdf':'config.file_path (local PDF/OCR; file provenance requires review)',
'dropbox':'api.dropbox.com/oauth2/token; api.dropboxapi.com; content.dropboxapi.com',
'email':'configured IMAP server; graph.microsoft.com; login.microsoftonline.com',
'freshdesk':'https://{domain}.freshdesk.com/api/v2',
'ftp':'configured FTP/FTPS host, usually port 21',
'google_drive':'www.googleapis.com/drive/v3; Google OAuth SDK endpoints',
'google_sheets':'Google Sheets/Drive SDK and Google OAuth endpoints (SDK-resolved)',
'hubspot':'api.hubapi.com',
'bse_nse':'api.bseindia.com; www.nseindia.com; api.sandbox.co.in',
'busy_accounting':'local export file path; busywin.com URL is an XML namespace, not a request',
'epfo':'api.sandbox.co.in; unifiedportal-mem.epfindia.gov.in',
'gstn':'api.sandbox.co.in (GST APIs)',
'ibbi':'ibbi.gov.in/api/public; api.sandbox.co.in',
'marg_erp':'local export file path / directory',
'mca21':'api.sandbox.co.in; www.mca.gov.in and discovered document hrefs',
'msme':'api.sandbox.co.in; udyamregistration.gov.in',
'rbi':'www.rbi.org.in (HTML scraping)',
'rera':'api.sandbox.co.in; maharera.maharashtra.gov.in; rera.karnataka.gov.in; rera.delhi.gov.in; www.tnrera.in; gujrera.gujarat.gov.in; hrera.in; up-rera.in; hira.wb.gov.in; tsrera.telangana.gov.in; rera.rajasthan.gov.in',
'sebi':'www.sebi.gov.in (HTML scraping)',
'tally':'http://{host}:{port} (XML POST to configured ERP)',
 'traces':'api.sandbox.co.in (tax/TRACES lookup)',
'jira':'configured https://{tenant}.atlassian.net/rest/api/3 or other base_url',
'mongodb':'configured MongoDB URI (may be remote/Atlas)',
'mssql':'configured MSSQL host/port/database/query',
'mysql':'configured MySQL host/port/database/query',
'oracle':'configured Oracle DSN/host/service/query',
'postgresql':'configured PostgreSQL host/port/database/query',
'notion':'api.notion.com/v1',
'pipedrive':'https://{domain}/v1',
'quickbooks':'quickbooks.api.intuit.com; sandbox-quickbooks.api.intuit.com; oauth.platform.intuit.com',
'rest_api':'arbitrary configured base_url, endpoint, OAuth token_url and pagination links',
's3':'AWS S3 SDK default endpoints or configured endpoint; AWS credential provider chain',
'salesforce':'simple_salesforce SDK: configured login domain and returned instance URL',
'sap':'local SAP IDOC/CSV/ALV/BEx exports; mounted SFTP/network shares require review (no live SAP OData client found)',
'sftp':'configured SSH/SFTP host (Paramiko)',
'sharepoint':'graph.microsoft.com; login.microsoftonline.com',
'slack':'slack.com/api',
 'telegram':'api.telegram.org/bot{token} (polling/offsets)',
'whatsapp':'graph.facebook.com/v18.0 plus inbound webhook handling',
'webhook':'inbound HTTP webhook receiver; local MinIO persistence; no outgoing callback client identified in this module',
'zendesk':'https://{subdomain}.zendesk.com/api/v2',
'zoho':'accounts.zoho.com/.com.au/.eu/.in; www.zohoapis.com/.com.au/.eu/.in'
}
items=[]
for p in sorted((ROOT/'layer1_ingestion/connectors').rglob('*connector.py')):
    key=p.stem.removesuffix('_connector') if hasattr(str,'removesuffix') else p.stem[:-10]
    if key=='base':continue
    source=p.read_text(encoding='utf-8-sig')
    classification=UNKNOWN
    behavior='Configured destination, credentials and server semantics require manual review; not certified read-only.'
    if key in ('rbi','sebi','bse_nse','freshdesk','jira','slack','zendesk','pipedrive','hubspot','notion'):
        classification=READ;behavior='Repository implements data retrieval/search (some POST queries); still exposes requests/credentials and may consume quota or server audit state.'
    if key in ('box','dropbox','email','google_drive','google_sheets','sharepoint','quickbooks','zoho','salesforce','azure_blob','s3','telegram','whatsapp'):
        classification=EFFECT;behavior='Remote authenticated access, token/authentication activity, cloud SDK activity or stateful polling; potential quota, audit and provider-side effects. No claim that messages/payments are sent.'
    if key in ('excel','pdf','busy_accounting','marg_erp','sap'):
        classification=LOCAL;behavior='File parser; supplied file/directory may refer to an unapproved mounted share or real data. Disabled until fixture provenance approved.'
    if key=='webhook':classification=LOCAL;behavior='Inbound receiver writes local storage and can initiate ingestion; disabled by HTTP middleware.'
    credential_keys=sorted(set(re.findall(r'config\.get\([\"\x27]([^\"\x27]+)',source)))
    credential_keys=[k for k in credential_keys if any(w in k.lower() for w in ('token','key','secret','password','credential','username','user','client_id'))]
    noauth=key in ('csv','excel','pdf','sap','busy_accounting','marg_erp','rbi','sebi')
    items.append(dict(name=key,files=[p.relative_to(ROOT).as_posix()],endpoint=endpoints.get(key,'DYNAMIC / manual review required'),classification=classification,legacy_default='Available when registered; connector construction/test/schema discovery/extraction or scheduled active-source processing triggers it. Import registration alone is not proof of a network request. Existing source registry was not reused or inspected.',trigger='Connector constructor, test_connection, detect_schema, extract/incremental extraction; API or source-health/sync DAG. Webhook: inbound HTTP.' if key=='webhook' else 'Configured source test/schema discovery/extraction, API sync or scheduled source processing.',behavior=behavior,credentials='No external credentials needed for approved local fixture branch.' if noauth else 'Required or configuration-dependent; keys: '+(', '.join(credential_keys) or 'SDK/configured authentication'),could_contact_external=key not in ('excel','pdf','sap','busy_accounting','marg_erp','webhook'),government_public_production='Government/regulatory/exchange or third-party government-data gateway' if '/indian/' in p.as_posix() and key not in ('busy_accounting','marg_erp','tally') else 'Configured production/third-party systems or unapproved file shares possible; do not assume sandbox from a name.',disabled='YES; only CSV under local_safe/fixtures is approved. CSV HTTP/other file paths remain denied.' if key=='csv' else 'YES',control='LOCAL_SAFE_MODE defaults true; BaseConnector check_connector rejects before subclass initialization. Inbound webhooks and mutating APIs rejected by safe launcher. Internal Docker network.',recommended_action='Keep disabled. Review the precise source and credentials and obtain explicit approval before enabling. Use local_safe/fixtures/companies.csv for fixture testing.'))

def add(name,files,endpoint,kind,trigger,behavior,control,default='Available in legacy configuration; see trigger.',credentials='Depends on integration; safe configuration supplies only documented dummy local credentials.'):
    items.append(dict(name=name,files=files,endpoint=endpoint,classification=kind,legacy_default=default,trigger=trigger,behavior=behavior,credentials=credentials,could_contact_external=kind!=SAFE,government_public_production='Remote/production possible unless exact destinations are pinned locally.',disabled='YES for all external/unapproved behavior in safe entrypoint; local operations explicitly noted.',control=control,recommended_action='Use only isolated safe startup. Do not run legacy scripts or enable external configuration.'))
add('Anthropic provider including inference health check',['shared/llm/provider.py','layer4_graph_intelligence/query_builder/query_parser.py','layer5_analytics_ai/rag/document_embedder.py'],'Anthropic SDK endpoint (api.anthropic.com unless SDK overrides)',EFFECT,'LLM complete/tool calls, query parsing, embeddings, provider health_check (sends ping inference).','Sends prompts/data; may incur billing.','Provider constructors/factory fail closed; direct query parser disabled; embedding path returns None; /llm HTTP blocked.','LLM_PROVIDER=anthropic is legacy default; key-dependent.','ANTHROPIC_API_KEY; omitted/cleared in safe mode.')
add('Ollama remote/local provider and model pull',['shared/llm/provider.py','docker-compose.yml','layer6_dashboard/backend/api/routes/operational.py'],'OLLAMA_BASE_URL; legacy localhost:11434 or ollama:11434; model registry resolved by Ollama',UNKNOWN,'Provider chat/status/models/test; ollama-init startup pulls qwen3:8b.','Inference and external model downloads; remote base URL possible.','Ollama and init omitted; direct provider ctor and factory denied; /llm routes denied.','Legacy ollama-init automatically pulls model.','No credentials required by default; remote endpoint still unapproved.')
add('Hugging Face / SentenceTransformers download',['layer5_analytics_ai/models/trainers/entity_similarity.py'],'sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2; SDK-resolved Hugging Face download hosts',EFFECT,'Lazy similarity model initialization/training; may download weights.','Downloads model artifacts and optional telemetry.','Guard before SentenceTransformer; HF offline/telemetry flags; no model training DAG.','Lazy automatic download if cached model absent.')
for layer in ('layer1_ingestion','layer2_pipeline','layer4_graph_intelligence','layer5_analytics_ai'):
    files=[p.relative_to(ROOT).as_posix() for p in (ROOT/layer/'airflow').rglob('*.py')]
    add(layer+' Airflow DAGs/plugins',files,'Persisted source destinations and local databases/Kafka/MinIO; may reach connectors/LLMs',UNKNOWN,'Airflow scheduler/Celery execution; L1 extraction six-hourly, health every30min, schema hourly; L2 every15min; L4 nightly; L5 daily/weekly jobs.','Scheduled extraction, database writes, training and downstream events.','All Airflow services omitted from safe config and legacy entrypoints quarantined; existing state/queues not reused.','DAG definitions have schedules; paused-at-creation does not disable already-unpaused persisted DAGs.')
add('Kafka background processing and downstream writes',['layer1_ingestion/streaming/streaming_worker.py','layer4_graph_intelligence/network/network_cache.py','layer5_analytics_ai/streaming/risk_delta_stream.py','layer5_analytics_ai/streaming/alert_trigger_stream.py','layer5_analytics_ai/streaming/trend_update_stream.py','layer6_dashboard/backend/websocket/kafka_consumer.py'],'KAFKA_BOOTSTRAP_SERVERS; configured L3 API',UNKNOWN,'Worker process or API lifespan starts consumers; existing queue events can trigger writes.','Processes messages, local storage/API actions, downstream events.','Streaming worker omitted and guarded; L4/L5/L6 lifespan consumers suppressed; fresh Kafka volume.')
localfiles=[]
for layer in ('layer1_ingestion','layer2_pipeline','layer3_ontology','layer4_graph_intelligence','layer5_analytics_ai','layer6_dashboard/backend'):
    localfiles += [p.relative_to(ROOT).as_posix() for p in (ROOT/layer/'core').glob('*.py') if p.name!='__init__.py']
add('Application infrastructure clients',localfiles,'POSTGRES_HOST/POSTGRES_URL; NEO4J_URI; REDIS_URL; ELASTICSEARCH_URL; MINIO_ENDPOINT; KAFKA_BOOTSTRAP_SERVERS',LOCAL,'Imports, API lifespans, health endpoints and requests.','Database/object-store reads and writes; any configurable host can otherwise be external.','Fixed service-name endpoints in isolated Compose; fresh data volumes; synthetic credentials; Python destination/port policy. Local functionality remains enabled.')
add('Internal HTTP calls / agents / reports / workflows',['layer5_analytics_ai/agents/tool_registry.py','layer5_analytics_ai/agents/agents/entity_resolution.py','layer5_analytics_ai/analytics/report_generator.py','layer5_analytics_ai/llm/context_builder.py','layer5_analytics_ai/llm/workflows/extraction.py','layer5_analytics_ai/streaming/alert_trigger_stream.py','layer6_dashboard/backend/core/layer_clients.py','layer6_dashboard/backend/aggregators/operational.py'],'LAYER1_API_URL through LAYER5_API_URL; local health URLs',LOCAL,'API aggregation, agent tool execution, report generation and service health polling.','Reads plus some POST/write actions; configured URL can otherwise send tokens/data remotely.','Exact internal hosts/ports; mutating APIs and LLM paths blocked; no source sync consumers; no remote health probes.')
add('Browser HTTP and WebSocket clients',['layer6_dashboard/frontend/shared/src/api/client.ts','layer6_dashboard/frontend/shared/src/hooks/useWebSocket.ts','layer6_dashboard/frontend/intelligence/vite.config.ts','layer6_dashboard/frontend/operational/vite.config.ts','layer6_dashboard/frontend/schema/vite.config.ts'],'VITE_API_URL/VITE_WS_URL and proxy targets; safe browser same-origin /api only',UNKNOWN,'Browser app load/user navigation, Axios requests, token-bearing WebSocket connect/reconnect, Vite dev startup.','Can expose browser tokens to configured remote URL. Browser networking is outside Docker.','Safe default same-origin API plus URL interceptor; WebSocket hook disabled; separate safe Vite entrypoint ignores dotenv/config; self-only CSP and fixed backend proxy.')
add('Infrastructure startup downloads/update checks',['docker-compose.yml'],'Neo4j plugin distribution; Elasticsearch GeoIP downloader; MinIO update mechanism; Ollama registry',EFFECT,'Legacy Neo4j APOC installation, Elasticsearch ingest downloads, model init and possible update checks.','Downloads; implementation-specific telemetry/update traffic not fully audited.','NEO4J_PLUGINS=[]; ingest.geoip.downloader.enabled=false; MINIO_UPDATE=off; Ollama omitted; internal network, DNS upstream disabled.')
add('Build/package registries and startup installers',['docker-compose.yml','requirements.txt','layer1_ingestion/api/Dockerfile','layer2_pipeline/api/Dockerfile','layer3_ontology/Dockerfile','layer4_graph_intelligence/Dockerfile','layer5_analytics_ai/Dockerfile','layer6_dashboard/backend/Dockerfile','layer6_dashboard/frontend/package.json','scripts/start-phase-a.ps1','Makefile'],'Docker image registries; OS package mirrors; PyPI/dependency indexes; npm registry and transitive install scripts',EFFECT,'docker build/pull; apt/pip/npm install; legacy frontend startup npm install.','Downloads and executes packages; may authenticate registry credentials.','Safe compose has no build directives and pull_policy=never; safe start --no-build --pull never checks local images; cached modules read-only; no npm lifecycle scripts. Legacy startup script throws; default Compose override inert.')
add('CI remote templates and repository workflows',['../.gitlab-ci.yml'],'GitLab Security/SAST.gitlab-ci.yml and analyzer image registries',UNKNOWN,'Push/CI pipeline on external runner.','Downloads/runs analyzer; runner behavior outside local Compose.','Not executed or pushed. Local mode does not control remote CI; explicit approval required.')
add('Legacy smoke/system/mock-data scripts',['scripts/generate_all_mock_data.py','scripts/smoke-phase-a.py','system_test.py','Makefile'],'Configured or hardcoded local infrastructure; may point at existing real data',UNKNOWN,'Manual command or test execution.','Writes mock entities/events to existing databases/Kafka; generic tests may instantiate real integrations.','Not executed in this audit. New stdlib safety tests and CSV fixture only; legacy launch quarantined.')
add('Passive XML namespace and UI link literals',['layer1_ingestion/parsers/xbrl_parser.py','layer1_ingestion/connectors/indian/busy_accounting_connector.py','layer6_dashboard/frontend/shared/src/components/LoadingSpinner.tsx','layer6_dashboard/frontend/schema/src/pages/ObjectTypes.tsx'],'xbrl.org; mca.gov.in/xbrl/taxonomy; busywin.com; w3.org SVG namespace; localhost:7474 UI link',SAFE,'Namespace comparison/rendering; explicit local Neo4j link navigation.','A URL literal is not necessarily an HTTP request. Untrusted XML/file behavior still requires containment.','No external request inferred from namespace constants; local fixture only and internal networking.')
# Evidence index: retain paths and matching line numbers/categories, never full source lines/secret values.
pattern=re.compile(r'\b(requests|httpx|aiohttp|urllib|boto3|botocore|gspread|anthropic|openai|grpc|paramiko|imaplib|smtplib|BeautifulSoup|SentenceTransformer|from_pretrained|KafkaConsumer|KafkaProducer|AsyncGraphDatabase|create_engine|create_async_engine|Minio|Elasticsearch|WebSocket|fetch|axios|subprocess|Popen|load_dotenv)\b|https?://|schedule_interval|create_task|\bDAG\(')
excluded={'.git','node_modules','__pycache__','.pytest_cache','.venv','venv','dist','.agents','.codex'}
evidence=[];filecount=0;errors=[]
for current,dirs,files in os.walk(ROOT.parent):
    dirs[:]=[d for d in dirs if d not in excluded]
    for filename in files:
        p=Path(current)/filename
        if 'local_safe' in p.parts or filename.startswith('.env') or filename=='compose.local-safe.json':continue
        if p.suffix.lower() not in ('.py','.ts','.tsx','.js','.mjs','.json','.yml','.yaml','.sh','.ps1','.toml','.txt','.md') and filename not in ('Dockerfile','Makefile'):continue
        try:
            text=p.read_text(encoding='utf-8-sig')
            filecount+=1
            matches=[{'line':n,'signals':sorted(set(m.group(0) for m in pattern.finditer(line)))} for n,line in enumerate(text.splitlines(),1) if pattern.search(line)]
            if matches:evidence.append({'file':os.path.relpath(p,ROOT).replace('\\','/'),'matches':matches})
        except (UnicodeError,OSError) as e:errors.append({'file':str(p.relative_to(ROOT.parent)),'error_type':type(e).__name__})
# Config values never copied: only variable names and presence, even for URL variables.
envfiles=[]
for p in ROOT.glob('.env*'):
    entries=[]
    for line in p.read_text(encoding='utf-8-sig').splitlines():
        m=re.match(r'\s*([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.*)',line)
        if m:entries.append({'key':m.group(1),'nonempty':bool(m.group(2).strip().strip('\"\x27')),'safe_mode_action':'Not loaded; safe Compose supplies explicit local-only values.'})
    envfiles.append({'file':p.name,'entries':entries})
output={'scope':'Static first-party repository audit; dependency internals, binary artifacts, persisted DB source configs, external server behavior and remote CI are not certified. Unknowns disabled.', 'scanned_text_files':filecount,'read_errors':errors,'integrations':items,'environment_presence_only':envfiles,'network_evidence':evidence}
(ROOT/'local_safe/inventory.json').write_text(json.dumps(output,indent=2,ensure_ascii=False)+'\n',encoding='utf-8')
lines=['# Integration inventory','', 'Generated by local_safe/build_inventory.py without importing application code or making network requests. Paths are relative to infracore_foundry. See inventory.json for line-number evidence and environment-key presence (no secret values).','']
for entry in items:
    lines += ['## '+entry['name'],'']
    for key in ('classification','files','endpoint','legacy_default','trigger','behavior','credentials','government_public_production','disabled','control','recommended_action'):
        value=entry[key]
        if isinstance(value,list):value=', '.join('`'+x+'`' for x in value)
        lines.append('- **'+key.replace('_',' ')+'**: '+str(value))
    lines.append('')
(ROOT/'local_safe/INTEGRATIONS.md').write_text('\n'.join(lines),encoding='utf-8')
print('Inventory:',len(items),'integration records;',filecount,'text files scanned;',len(evidence),'evidence files;',len(errors),'read errors')
