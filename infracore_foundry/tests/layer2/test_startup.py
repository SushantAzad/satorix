"""Ensure Layer 2 initializes its database before accepting requests."""
from unittest.mock import patch

import pytest

from layer2_pipeline.api.app import app, lifespan


@pytest.mark.asyncio
async def test_database_lifecycle():
    with patch("layer2_pipeline.api.app.init_db") as init_db, \
            patch("layer2_pipeline.api.app.close_db") as close_db:
        async with lifespan(app):
            init_db.assert_called_once_with()
            close_db.assert_not_called()
        close_db.assert_called_once_with()
