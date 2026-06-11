export type FieldType = 'text' | 'password' | 'url' | 'number' | 'select' | 'textarea' | 'file'

export interface FieldDef {
  key: string
  label: string
  type: FieldType
  required: boolean
  placeholder?: string
  helpText?: string
  options?: { value: string; label: string }[]
  defaultValue?: string | number
}

export interface ConnectorDef {
  type: string
  displayName: string
  category: string
  icon: string
  description: string
  fields: FieldDef[]
}

export const CONNECTOR_CATEGORIES = [
  'Indian Government',
  'Files & Storage',
  'Databases',
  'Cloud Storage',
  'CRM & Sales',
  'ERP & Accounting',
  'Communication',
  'Support & PM',
]

export const CONNECTORS: ConnectorDef[] = [
  // ── Indian Government ────────────────────────────────────────────────────
  {
    type: 'mca21',
    displayName: 'MCA21 / ROC',
    category: 'Indian Government',
    icon: '🏛️',
    description: 'Ministry of Corporate Affairs — company, director, and charge data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true, placeholder: 'sk_live_...' },
      { key: 'sandbox_api_secret', label: 'API Secret', type: 'password', required: true },
      { key: 'environment', label: 'Environment', type: 'select', required: true, defaultValue: 'production',
        options: [{ value: 'sandbox', label: 'Sandbox (test)' }, { value: 'production', label: 'Production' }] },
    ],
  },
  {
    type: 'gstn',
    displayName: 'GSTN',
    category: 'Indian Government',
    icon: '🧾',
    description: 'GST Network — taxpayer and return filing data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
      { key: 'sandbox_api_secret', label: 'API Secret', type: 'password', required: true },
    ],
  },
  {
    type: 'ibbi',
    displayName: 'IBBI / CIRP',
    category: 'Indian Government',
    icon: '⚖️',
    description: 'Insolvency and Bankruptcy Board — CIRP and liquidation proceedings',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
    ],
  },
  {
    type: 'bse_nse',
    displayName: 'BSE / NSE',
    category: 'Indian Government',
    icon: '📈',
    description: 'Stock exchange filings, announcements, and listed entity data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
    ],
  },
  {
    type: 'rera',
    displayName: 'RERA',
    category: 'Indian Government',
    icon: '🏗️',
    description: 'Real Estate Regulatory Authority — project and promoter registrations',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
      { key: 'state_code', label: 'State Code', type: 'text', required: false, placeholder: 'MH (blank = all states)' },
    ],
  },
  {
    type: 'epfo',
    displayName: 'EPFO',
    category: 'Indian Government',
    icon: '👷',
    description: 'Employee Provident Fund Organisation — establishment and compliance data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
    ],
  },
  {
    type: 'msme',
    displayName: 'MSME / Udyam',
    category: 'Indian Government',
    icon: '🏭',
    description: 'Udyam registration and MSME certification data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
    ],
  },
  {
    type: 'traces',
    displayName: 'TRACES / TDS',
    category: 'Indian Government',
    icon: '📋',
    description: 'CBDT TDS reconciliation — Form 26AS and deductor data',
    fields: [
      { key: 'sandbox_api_key', label: 'Sandbox.co.in API Key', type: 'password', required: true },
    ],
  },

  // ── Files & Storage ──────────────────────────────────────────────────────
  {
    type: 'csv',
    displayName: 'CSV File',
    category: 'Files & Storage',
    icon: '📄',
    description: 'Upload or reference comma-separated value files',
    fields: [
      { key: 'file_path', label: 'File Path or URL', type: 'text', required: true, placeholder: '/data/export.csv or https://...' },
      { key: 'delimiter', label: 'Delimiter', type: 'select', required: false, defaultValue: ',',
        options: [{ value: ',', label: 'Comma (,)' }, { value: ';', label: 'Semicolon (;)' }, { value: '\t', label: 'Tab' }, { value: '|', label: 'Pipe (|)' }] },
      { key: 'encoding', label: 'Encoding', type: 'select', required: false, defaultValue: 'utf-8',
        options: [{ value: 'utf-8', label: 'UTF-8' }, { value: 'latin-1', label: 'Latin-1' }, { value: 'cp1252', label: 'Windows-1252' }] },
    ],
  },
  {
    type: 'excel',
    displayName: 'Excel / XLSX',
    category: 'Files & Storage',
    icon: '📊',
    description: 'Microsoft Excel workbooks (.xlsx, .xls)',
    fields: [
      { key: 'file_path', label: 'File Path or URL', type: 'text', required: true, placeholder: '/data/report.xlsx' },
      { key: 'sheet_name', label: 'Sheet Name', type: 'text', required: false, placeholder: 'Sheet1 (blank = first sheet)' },
    ],
  },
  {
    type: 'pdf',
    displayName: 'PDF Document',
    category: 'Files & Storage',
    icon: '📕',
    description: 'Extract structured data from PDF files using OCR',
    fields: [
      { key: 'file_path', label: 'File Path or URL', type: 'text', required: true },
      { key: 'use_ocr', label: 'Enable OCR', type: 'select', required: false, defaultValue: 'false',
        options: [{ value: 'false', label: 'Text extraction only' }, { value: 'true', label: 'OCR (scanned PDFs)' }] },
    ],
  },
  {
    type: 's3',
    displayName: 'Amazon S3',
    category: 'Files & Storage',
    icon: '☁️',
    description: 'AWS S3 bucket — CSV, Excel, JSON, PDF files',
    fields: [
      { key: 'bucket_name', label: 'Bucket Name', type: 'text', required: true },
      { key: 'prefix', label: 'Key Prefix / Path', type: 'text', required: false, placeholder: 'exports/2024/' },
      { key: 'aws_access_key_id', label: 'AWS Access Key ID', type: 'password', required: true },
      { key: 'aws_secret_access_key', label: 'AWS Secret Access Key', type: 'password', required: true },
      { key: 'region', label: 'AWS Region', type: 'text', required: false, defaultValue: 'ap-south-1' },
    ],
  },
  {
    type: 'sftp',
    displayName: 'SFTP',
    category: 'Files & Storage',
    icon: '🔒',
    description: 'Secure FTP server — pull files on a schedule',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true, placeholder: 'sftp.example.com' },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 22 },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: false },
      { key: 'private_key', label: 'Private Key (PEM)', type: 'textarea', required: false, placeholder: '-----BEGIN OPENSSH PRIVATE KEY-----' },
      { key: 'remote_path', label: 'Remote Path', type: 'text', required: false, defaultValue: '/' },
      { key: 'file_pattern', label: 'File Pattern', type: 'text', required: false, placeholder: '*.csv' },
    ],
  },
  {
    type: 'ftp',
    displayName: 'FTP',
    category: 'Files & Storage',
    icon: '📁',
    description: 'FTP / FTPS server file transfer',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 21 },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
      { key: 'use_tls', label: 'Use FTPS (TLS)', type: 'select', required: false, defaultValue: 'false',
        options: [{ value: 'false', label: 'Plain FTP' }, { value: 'true', label: 'FTPS (TLS)' }] },
      { key: 'remote_path', label: 'Remote Path', type: 'text', required: false, defaultValue: '/' },
      { key: 'file_pattern', label: 'File Pattern', type: 'text', required: false, placeholder: '*.csv' },
    ],
  },
  {
    type: 'rest_api',
    displayName: 'REST API',
    category: 'Files & Storage',
    icon: '🔌',
    description: 'Generic REST API with optional auth and pagination',
    fields: [
      { key: 'base_url', label: 'Base URL', type: 'url', required: true, placeholder: 'https://api.example.com/v1' },
      { key: 'endpoint', label: 'Endpoint Path', type: 'text', required: true, placeholder: '/records' },
      { key: 'auth_type', label: 'Auth Type', type: 'select', required: false, defaultValue: 'none',
        options: [{ value: 'none', label: 'None' }, { value: 'bearer', label: 'Bearer Token' }, { value: 'basic', label: 'Basic Auth' }, { value: 'api_key', label: 'API Key (Header)' }] },
      { key: 'auth_value', label: 'Token / Password / API Key', type: 'password', required: false },
      { key: 'auth_username', label: 'Username (Basic Auth)', type: 'text', required: false },
    ],
  },

  // ── Databases ────────────────────────────────────────────────────────────
  {
    type: 'postgresql',
    displayName: 'PostgreSQL',
    category: 'Databases',
    icon: '🐘',
    description: 'PostgreSQL relational database',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true, placeholder: 'localhost' },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 5432 },
      { key: 'database', label: 'Database', type: 'text', required: true },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
      { key: 'query', label: 'Extract Query (SQL)', type: 'textarea', required: false, placeholder: 'SELECT * FROM table WHERE ...' },
    ],
  },
  {
    type: 'mysql',
    displayName: 'MySQL / MariaDB',
    category: 'Databases',
    icon: '🐬',
    description: 'MySQL or MariaDB relational database',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 3306 },
      { key: 'database', label: 'Database', type: 'text', required: true },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
    ],
  },
  {
    type: 'mssql',
    displayName: 'SQL Server (MSSQL)',
    category: 'Databases',
    icon: '🗄️',
    description: 'Microsoft SQL Server',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 1433 },
      { key: 'database', label: 'Database', type: 'text', required: true },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
    ],
  },
  {
    type: 'oracle',
    displayName: 'Oracle Database',
    category: 'Databases',
    icon: '🔴',
    description: 'Oracle Database (thin mode — no Oracle Client needed)',
    fields: [
      { key: 'host', label: 'Host', type: 'text', required: true },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 1521 },
      { key: 'service_name', label: 'Service Name / SID', type: 'text', required: true },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
    ],
  },
  {
    type: 'mongodb',
    displayName: 'MongoDB',
    category: 'Databases',
    icon: '🍃',
    description: 'MongoDB Atlas or self-hosted cluster',
    fields: [
      { key: 'connection_string', label: 'Connection String', type: 'password', required: true, placeholder: 'mongodb+srv://user:pass@cluster.mongodb.net/db' },
      { key: 'database', label: 'Database', type: 'text', required: true },
      { key: 'collection', label: 'Collection', type: 'text', required: false, placeholder: 'Blank = all collections' },
    ],
  },

  // ── Cloud Storage ────────────────────────────────────────────────────────
  {
    type: 'google_drive',
    displayName: 'Google Drive',
    category: 'Cloud Storage',
    icon: '📂',
    description: 'Google Drive files and folders',
    fields: [
      { key: 'service_account_json', label: 'Service Account JSON', type: 'textarea', required: true, placeholder: '{"type": "service_account", ...}' },
      { key: 'folder_id', label: 'Folder ID', type: 'text', required: false, placeholder: 'Blank = My Drive root' },
      { key: 'file_types', label: 'File Types', type: 'text', required: false, placeholder: 'csv,xlsx,pdf (blank = all)' },
    ],
  },
  {
    type: 'google_sheets',
    displayName: 'Google Sheets',
    category: 'Cloud Storage',
    icon: '📋',
    description: 'Google Sheets spreadsheet data',
    fields: [
      { key: 'service_account_json', label: 'Service Account JSON', type: 'textarea', required: true },
      { key: 'spreadsheet_id', label: 'Spreadsheet ID', type: 'text', required: true, placeholder: 'From the URL: /spreadsheets/d/<ID>' },
      { key: 'sheet_name', label: 'Sheet / Tab Name', type: 'text', required: false, placeholder: 'Sheet1' },
    ],
  },
  {
    type: 'azure_blob',
    displayName: 'Azure Blob Storage',
    category: 'Cloud Storage',
    icon: '🔷',
    description: 'Microsoft Azure Blob Storage container',
    fields: [
      { key: 'connection_string', label: 'Connection String', type: 'password', required: true, placeholder: 'DefaultEndpointsProtocol=https;AccountName=...' },
      { key: 'container_name', label: 'Container Name', type: 'text', required: true },
      { key: 'blob_prefix', label: 'Blob Prefix', type: 'text', required: false, placeholder: 'exports/2024/' },
    ],
  },
  {
    type: 'dropbox',
    displayName: 'Dropbox',
    category: 'Cloud Storage',
    icon: '📦',
    description: 'Dropbox Business or personal account',
    fields: [
      { key: 'access_token', label: 'Access Token', type: 'password', required: false, helpText: 'Long-lived access token or use refresh token flow' },
      { key: 'refresh_token', label: 'Refresh Token', type: 'password', required: false },
      { key: 'app_key', label: 'App Key', type: 'text', required: false },
      { key: 'app_secret', label: 'App Secret', type: 'password', required: false },
      { key: 'folder_path', label: 'Folder Path', type: 'text', required: false, placeholder: '/Reports (blank = root)' },
    ],
  },
  {
    type: 'box',
    displayName: 'Box',
    category: 'Cloud Storage',
    icon: '📫',
    description: 'Box enterprise cloud storage',
    fields: [
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { key: 'access_token', label: 'Access Token', type: 'password', required: true },
      { key: 'folder_id', label: 'Folder ID', type: 'text', required: false, placeholder: '0 = root' },
    ],
  },
  {
    type: 'sharepoint',
    displayName: 'SharePoint / OneDrive',
    category: 'Cloud Storage',
    icon: '🔗',
    description: 'Microsoft SharePoint or OneDrive for Business',
    fields: [
      { key: 'tenant_id', label: 'Tenant ID', type: 'text', required: true },
      { key: 'client_id', label: 'Client ID (Azure App)', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { key: 'site_url', label: 'Site URL', type: 'url', required: true, placeholder: 'https://yourorg.sharepoint.com/sites/Finance' },
      { key: 'folder_path', label: 'Folder Path', type: 'text', required: false, placeholder: 'Documents/Reports' },
    ],
  },

  // ── CRM & Sales ──────────────────────────────────────────────────────────
  {
    type: 'salesforce',
    displayName: 'Salesforce',
    category: 'CRM & Sales',
    icon: '☁️',
    description: 'Salesforce CRM — Accounts, Contacts, Opportunities, Cases',
    fields: [
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
      { key: 'security_token', label: 'Security Token', type: 'password', required: true },
      { key: 'domain', label: 'Domain', type: 'select', required: false, defaultValue: 'login',
        options: [{ value: 'login', label: 'Production (login.salesforce.com)' }, { value: 'test', label: 'Sandbox (test.salesforce.com)' }] },
      { key: 'objects', label: 'Objects to Sync', type: 'text', required: false, placeholder: 'Account,Contact (blank = all)' },
    ],
  },
  {
    type: 'hubspot',
    displayName: 'HubSpot',
    category: 'CRM & Sales',
    icon: '🧲',
    description: 'HubSpot CRM — contacts, deals, companies',
    fields: [
      { key: 'api_key', label: 'Private App Token', type: 'password', required: true },
    ],
  },
  {
    type: 'zoho',
    displayName: 'Zoho CRM',
    category: 'CRM & Sales',
    icon: '🟠',
    description: 'Zoho CRM — leads, contacts, accounts, deals',
    fields: [
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { key: 'refresh_token', label: 'Refresh Token', type: 'password', required: true },
      { key: 'dc', label: 'Data Center', type: 'select', required: false, defaultValue: 'IN',
        options: [{ value: 'IN', label: 'India (zohoapis.in)' }, { value: 'US', label: 'US (zohoapis.com)' }, { value: 'EU', label: 'EU (zohoapis.eu)' }] },
    ],
  },
  {
    type: 'pipedrive',
    displayName: 'Pipedrive',
    category: 'CRM & Sales',
    icon: '🚿',
    description: 'Pipedrive — deals, organizations, people',
    fields: [
      { key: 'api_token', label: 'API Token', type: 'password', required: true },
    ],
  },

  // ── ERP & Accounting ─────────────────────────────────────────────────────
  {
    type: 'sap',
    displayName: 'SAP ERP',
    category: 'ERP & Accounting',
    icon: '🏢',
    description: 'SAP S/4HANA or ECC via OData / RFC',
    fields: [
      { key: 'host', label: 'SAP Host', type: 'text', required: true, placeholder: 'sap.company.com' },
      { key: 'client', label: 'Client (Mandant)', type: 'number', required: true, placeholder: '100' },
      { key: 'username', label: 'Username', type: 'text', required: true },
      { key: 'password', label: 'Password', type: 'password', required: true },
      { key: 'system_id', label: 'System ID (SID)', type: 'text', required: false, placeholder: 'PRD' },
      { key: 'entities', label: 'Entities', type: 'text', required: false, placeholder: 'vendor,customer (blank = all)' },
    ],
  },
  {
    type: 'tally',
    displayName: 'Tally ERP / Prime',
    category: 'ERP & Accounting',
    icon: '📒',
    description: 'Tally accounting software via XML API',
    fields: [
      { key: 'host', label: 'Tally Host', type: 'text', required: false, defaultValue: 'localhost' },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 9000 },
      { key: 'company_name', label: 'Company Name', type: 'text', required: false, placeholder: 'Blank = primary company' },
    ],
  },
  {
    type: 'quickbooks',
    displayName: 'QuickBooks Online',
    category: 'ERP & Accounting',
    icon: '💚',
    description: 'Intuit QuickBooks Online — accounts, invoices, vendors',
    fields: [
      { key: 'client_id', label: 'Client ID', type: 'text', required: true },
      { key: 'client_secret', label: 'Client Secret', type: 'password', required: true },
      { key: 'refresh_token', label: 'Refresh Token', type: 'password', required: true },
      { key: 'realm_id', label: 'Realm ID (Company ID)', type: 'text', required: true },
      { key: 'environment', label: 'Environment', type: 'select', required: false, defaultValue: 'production',
        options: [{ value: 'sandbox', label: 'Sandbox' }, { value: 'production', label: 'Production' }] },
    ],
  },
  {
    type: 'busy',
    displayName: 'BUSY Accounting',
    category: 'ERP & Accounting',
    icon: '💼',
    description: 'BUSY accounting software — XML/Excel export files',
    fields: [
      { key: 'export_directory', label: 'Export Directory Path', type: 'text', required: true, placeholder: '/exports/busy/' },
      { key: 'company_name', label: 'Company Name Filter', type: 'text', required: false },
    ],
  },
  {
    type: 'marg_erp',
    displayName: 'Marg ERP',
    category: 'ERP & Accounting',
    icon: '💊',
    description: 'Marg ERP for pharma/retail — sales, stock, party exports',
    fields: [
      { key: 'export_directory', label: 'Export Directory Path', type: 'text', required: true, placeholder: '/exports/marg/' },
      { key: 'company_id', label: 'Company ID', type: 'text', required: false },
    ],
  },

  // ── Communication ────────────────────────────────────────────────────────
  {
    type: 'email',
    displayName: 'Email (IMAP)',
    category: 'Communication',
    icon: '✉️',
    description: 'IMAP mailbox — extract attachments and structured data',
    fields: [
      { key: 'host', label: 'IMAP Host', type: 'text', required: true, placeholder: 'imap.gmail.com' },
      { key: 'port', label: 'Port', type: 'number', required: false, defaultValue: 993 },
      { key: 'username', label: 'Email Address', type: 'text', required: true },
      { key: 'password', label: 'App Password', type: 'password', required: true },
      { key: 'mailbox', label: 'Mailbox / Folder', type: 'text', required: false, defaultValue: 'INBOX' },
    ],
  },
  {
    type: 'slack',
    displayName: 'Slack',
    category: 'Communication',
    icon: '💬',
    description: 'Slack workspace — channels and message history',
    fields: [
      { key: 'bot_token', label: 'Bot OAuth Token', type: 'password', required: true, placeholder: 'xoxb-...' },
      { key: 'channel_ids', label: 'Channel IDs', type: 'text', required: false, placeholder: 'C012AB3CD, C098ZY (blank = all public)' },
    ],
  },
  {
    type: 'notion',
    displayName: 'Notion',
    category: 'Communication',
    icon: '📝',
    description: 'Notion workspace — pages and databases',
    fields: [
      { key: 'api_key', label: 'Integration Token', type: 'password', required: true, placeholder: 'secret_...' },
      { key: 'database_id', label: 'Database ID', type: 'text', required: false, helpText: 'Leave blank to sync all shared databases' },
    ],
  },

  // ── Support & PM ─────────────────────────────────────────────────────────
  {
    type: 'jira',
    displayName: 'Jira',
    category: 'Support & PM',
    icon: '🔵',
    description: 'Atlassian Jira — issues, projects, sprints',
    fields: [
      { key: 'base_url', label: 'Base URL', type: 'url', required: true, placeholder: 'https://yourorg.atlassian.net' },
      { key: 'email', label: 'Email', type: 'text', required: true },
      { key: 'api_token', label: 'API Token', type: 'password', required: true },
      { key: 'project_keys', label: 'Project Keys', type: 'text', required: false, placeholder: 'PROJ,INFRA (blank = all)' },
    ],
  },
  {
    type: 'freshdesk',
    displayName: 'Freshdesk',
    category: 'Support & PM',
    icon: '🌿',
    description: 'Freshdesk support tickets and agents',
    fields: [
      { key: 'domain', label: 'Domain', type: 'text', required: true, placeholder: 'yourcompany' },
      { key: 'api_key', label: 'API Key', type: 'password', required: true },
    ],
  },
  {
    type: 'zendesk',
    displayName: 'Zendesk',
    category: 'Support & PM',
    icon: '🎫',
    description: 'Zendesk Support — tickets, users, organizations',
    fields: [
      { key: 'subdomain', label: 'Subdomain', type: 'text', required: true, placeholder: 'yourcompany' },
      { key: 'email', label: 'Email', type: 'text', required: true },
      { key: 'api_token', label: 'API Token', type: 'password', required: true },
    ],
  },
]

export const CONNECTOR_MAP: Record<string, ConnectorDef> = Object.fromEntries(
  CONNECTORS.map(c => [c.type, c])
)
