"""Regression coverage for connector exports used during API startup."""


def test_public_connector_exports_and_rest_registration():
    from layer1_ingestion.core.config import (
        _auto_register_connectors, get_connector_class,
    )
    from layer1_ingestion import connectors
    from layer1_ingestion.connectors.rest_api_connector import RestAPIConnector
    from layer1_ingestion.connectors.webhook_connector import WebhookReceiver

    _auto_register_connectors()
    for name in connectors.__all__:
        assert getattr(connectors, name) is not None
    assert connectors.RESTAPIConnector is RestAPIConnector
    assert get_connector_class("rest_api") is RestAPIConnector
    assert connectors.WebhookReceiver is WebhookReceiver
