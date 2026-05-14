"""OTLP HTTP receiver - receives traces and metrics from Beyla."""
import gzip
import io
import logging
from fastapi import APIRouter, Request, Response

from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (
    ExportTraceServiceRequest,
)

from app.event_transformer import transform_spans

logger = logging.getLogger(__name__)

router = APIRouter()

_buffer = None
_metrics_received = 0
_traces_received = 0
_MAX_BODY_BYTES = 50 * 1024 * 1024  # 50 MB hard limit per request
_DECOMPRESS_CHUNK = 64 * 1024


class _DecompressionTooLarge(Exception):
    pass


def set_buffer(buffer):
    global _buffer
    _buffer = buffer


def _decompress_if_gzip(body: bytes, headers) -> bytes:
    """Decompress a gzip-encoded body with a hard ceiling.

    A naive `gzip.decompress(body)` is vulnerable to gzip bombs: a
    50 MB compressed payload can expand to many gigabytes and OOM the
    pod before our `len(body) > _MAX_BODY_BYTES` post-check ever
    fires. Stream the decompression instead so we abort the moment
    the inflated stream crosses the same ceiling.
    """
    if headers.get("content-encoding", "").lower() != "gzip":
        return body
    out = bytearray()
    with gzip.GzipFile(fileobj=io.BytesIO(body)) as gz:
        while True:
            chunk = gz.read(_DECOMPRESS_CHUNK)
            if not chunk:
                break
            out.extend(chunk)
            if len(out) > _MAX_BODY_BYTES:
                raise _DecompressionTooLarge(
                    f"gzip payload expanded past {_MAX_BODY_BYTES} bytes"
                )
    return bytes(out)


def _is_protobuf(content_type: str) -> bool:
    ct = content_type.lower()
    return "protobuf" in ct or "octet-stream" in ct


@router.post("/v1/traces")
async def receive_traces(request: Request):
    """Standard OTLP HTTP receiver endpoint for Beyla traces."""
    body = await request.body()
    if len(body) > _MAX_BODY_BYTES:
        return Response(status_code=413, content="Payload too large")
    content_type = request.headers.get("content-type", "")

    try:
        body = _decompress_if_gzip(body, request.headers)
    except _DecompressionTooLarge:
        return Response(status_code=413, content="Decompressed payload too large")
    except Exception:
        return Response(status_code=400, content="Invalid gzip payload")

    try:
        global _traces_received
        req = ExportTraceServiceRequest()
        if _is_protobuf(content_type):
            req.ParseFromString(body)
        else:
            from google.protobuf.json_format import Parse
            Parse(body.decode("utf-8"), req)

        events = transform_spans(req.resource_spans)
        for event in events:
            await _buffer.add(event)

        _traces_received += 1
        if _traces_received <= 5 or _traces_received % 1000 == 0:
            logger.info("OTLP traces received: spans=%d events=%d total_requests=%d",
                        sum(len(ss.spans) for rs in req.resource_spans for ss in rs.scope_spans),
                        len(events), _traces_received)

        return Response(status_code=200)
    except Exception as e:
        logger.error("otlp_parse_error: %s", e)
        return Response(status_code=400, content="Parse error")


@router.post("/v1/metrics")
async def receive_metrics(request: Request):
    """Accept OTLP metrics from Beyla. Currently acknowledged but not stored."""
    global _metrics_received
    try:
        await request.body()
    except Exception:
        pass
    _metrics_received += 1
    if _metrics_received == 1 or _metrics_received % 10000 == 0:
        logger.info("OTLP metrics from Beyla (accepted, not stored) total=%d", _metrics_received)
    return Response(status_code=200)
