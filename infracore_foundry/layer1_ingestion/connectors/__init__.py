"""Data source connectors for file, database, API, and Indian government sources."""

from layer1_ingestion.connectors.base_connector import BaseConnector

# Generic connectors
from layer1_ingestion.connectors.csv_connector import CSVConnector
from layer1_ingestion.connectors.excel_connector import ExcelConnector
from layer1_ingestion.connectors.pdf_connector import PDFConnector
from layer1_ingestion.connectors.s3_connector import S3Connector
from layer1_ingestion.connectors.sftp_connector import SFTPConnector
from layer1_ingestion.connectors.ftp_connector import FTPConnector
from layer1_ingestion.connectors.rest_api_connector import RESTAPIConnector
from layer1_ingestion.connectors.webhook_connector import WebhookConnector
from layer1_ingestion.connectors.google_sheets_connector import GoogleSheetsConnector

# Database connectors
from layer1_ingestion.connectors.mysql_connector import MySQLConnector
from layer1_ingestion.connectors.postgresql_connector import PostgreSQLConnector
from layer1_ingestion.connectors.mssql_connector import MSSQLConnector
from layer1_ingestion.connectors.oracle_connector import OracleConnector
from layer1_ingestion.connectors.mongodb_connector import MongoDBConnector

# Cloud storage & file connectors
from layer1_ingestion.connectors.google_drive_connector import GoogleDriveConnector
from layer1_ingestion.connectors.azure_blob_connector import AzureBlobConnector
from layer1_ingestion.connectors.dropbox_connector import DropboxConnector
from layer1_ingestion.connectors.box_connector import BoxConnector
from layer1_ingestion.connectors.sharepoint_connector import SharePointConnector

# Communication & messaging connectors
from layer1_ingestion.connectors.email_connector import EmailConnector
from layer1_ingestion.connectors.whatsapp_connector import WhatsAppConnector
from layer1_ingestion.connectors.slack_connector import SlackConnector
from layer1_ingestion.connectors.telegram_connector import TelegramConnector
from layer1_ingestion.connectors.notion_connector import NotionConnector

# CRM & sales connectors
from layer1_ingestion.connectors.salesforce_connector import SalesforceConnector
from layer1_ingestion.connectors.hubspot_connector import HubSpotConnector
from layer1_ingestion.connectors.zoho_connector import ZohoConnector
from layer1_ingestion.connectors.pipedrive_connector import PipedriveConnector

# ERP & accounting connectors
from layer1_ingestion.connectors.sap_connector import SAPConnector
from layer1_ingestion.connectors.quickbooks_connector import QuickBooksConnector

# Support & project management connectors
from layer1_ingestion.connectors.freshdesk_connector import FreshdeskConnector
from layer1_ingestion.connectors.jira_connector import JiraConnector
from layer1_ingestion.connectors.zendesk_connector import ZendeskConnector

__all__ = [
    "BaseConnector",
    # Generic
    "CSVConnector", "ExcelConnector", "PDFConnector", "S3Connector",
    "SFTPConnector", "FTPConnector", "RESTAPIConnector", "WebhookConnector",
    "GoogleSheetsConnector",
    # Database
    "MySQLConnector", "PostgreSQLConnector", "MSSQLConnector",
    "OracleConnector", "MongoDBConnector",
    # Cloud storage
    "GoogleDriveConnector", "AzureBlobConnector", "DropboxConnector",
    "BoxConnector", "SharePointConnector",
    # Communication
    "EmailConnector", "WhatsAppConnector", "SlackConnector",
    "TelegramConnector", "NotionConnector",
    # CRM
    "SalesforceConnector", "HubSpotConnector", "ZohoConnector", "PipedriveConnector",
    # ERP & Accounting
    "SAPConnector", "QuickBooksConnector",
    # Support & PM
    "FreshdeskConnector", "JiraConnector", "ZendeskConnector",
]
