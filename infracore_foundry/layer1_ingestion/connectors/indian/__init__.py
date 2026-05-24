"""Indian-specific data source connectors."""

from layer1_ingestion.connectors.indian.mca21_connector import MCA21Connector
from layer1_ingestion.connectors.indian.sebi_connector import SEBIConnector
from layer1_ingestion.connectors.indian.rbi_connector import RBIConnector
from layer1_ingestion.connectors.indian.tally_connector import TallyConnector
from layer1_ingestion.connectors.indian.gstn_connector import GSTNConnector
from layer1_ingestion.connectors.indian.ibbi_connector import IBBIConnector
from layer1_ingestion.connectors.indian.bse_nse_connector import BSENSEConnector
from layer1_ingestion.connectors.indian.rera_connector import RERAConnector
from layer1_ingestion.connectors.indian.epfo_connector import EPFOConnector
from layer1_ingestion.connectors.indian.msme_connector import MSMEConnector
from layer1_ingestion.connectors.indian.busy_accounting_connector import BUSYAccountingConnector
from layer1_ingestion.connectors.indian.traces_connector import TRACESConnector
from layer1_ingestion.connectors.indian.marg_erp_connector import MargERPConnector

__all__ = [
    "MCA21Connector",
    "SEBIConnector",
    "RBIConnector",
    "TallyConnector",
    "GSTNConnector",
    "IBBIConnector",
    "BSENSEConnector",
    "RERAConnector",
    "EPFOConnector",
    "MSMEConnector",
    "BUSYAccountingConnector",
    "TRACESConnector",
    "MargERPConnector",
]
