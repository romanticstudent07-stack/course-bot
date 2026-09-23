"""/security/csp-report — приёмник CSP violation reports (E2 ERRATA, report-uri).

Без initData (security: [] в miniapp-api-contract.yaml). Тело контракта — TODO в
исходнике, поэтому здесь только приём и логирование с ограничением размера.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Request, Response, status

router = APIRouter(tags=["security"])
logger = logging.getLogger("csp")

MAX_REPORT_BYTES = 16 * 1024


@router.post("/security/csp-report", status_code=status.HTTP_204_NO_CONTENT)
async def csp_report(request: Request) -> Response:
    body = await request.body()
    logger.warning("CSP violation report: %s", body[:MAX_REPORT_BYTES].decode("utf-8", "replace"))
    return Response(status_code=status.HTTP_204_NO_CONTENT)
