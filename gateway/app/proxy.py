import logging
from fastapi import Request, Response
import httpx

logger = logging.getLogger(__name__)

# Shared async client — reused across requests (connection pooling)
_client = httpx.AsyncClient(timeout=30.0)


async def proxy(request: Request, target_url: str) -> Response:
    """
    Forward the incoming request to `target_url`, preserving method,
    headers, query params, and body. Returns a FastAPI Response.
    """
    # Strip hop-by-hop headers that must not be forwarded
    excluded = {"host", "content-length", "transfer-encoding", "connection"}
    headers  = {k: v for k, v in request.headers.items() if k.lower() not in excluded}

    body = await request.body()

    try:
        upstream = await _client.request(
            method  = request.method,
            url     = target_url,
            headers = headers,
            content = body,
            params  = dict(request.query_params),
        )
    except httpx.ConnectError:
        logger.error("[gateway] Service unreachable: %s", target_url)
        return Response(content=b'{"detail":"Service unavailable"}', status_code=503, media_type="application/json")
    except httpx.TimeoutException:
        logger.error("[gateway] Timeout: %s", target_url)
        return Response(content=b'{"detail":"Service timeout"}', status_code=504, media_type="application/json")

    # Forward response as-is
    return Response(
        content    = upstream.content,
        status_code= upstream.status_code,
        headers    = dict(upstream.headers),
        media_type = upstream.headers.get("content-type"),
    )
