"""
Client context — extracts and propagates client_id through every Layer 3 request.

Contract:
  - Every write operation MUST carry a client_id.
  - PLATFORM_GLOBAL is the canonical sentinel for publicly-sourced data
    (MCA21, IBBI, BSE/NSE, RERA, GSTN) that every tenant can read.
  - Private data (client's own ERP, CRM, files) carries the actual client_id.

How client_id flows into Layer 3:
  Layer 6 auth middleware extracts client_id from JWT
      → attaches X-Client-ID header to every upstream call
          → this FastAPI dependency reads it
              → passed into every store/query method
"""

from fastapi import Header
from typing import Optional

PLATFORM_GLOBAL = "PLATFORM_GLOBAL"


async def get_client_id(
    x_client_id: Optional[str] = Header(default=None),
) -> str:
    """
    FastAPI dependency — returns the caller's client_id.
    Falls back to PLATFORM_GLOBAL so unauthenticated read paths still work
    (they will only see platform-wide public data, which is correct).
    """
    return x_client_id.strip() if x_client_id else PLATFORM_GLOBAL
