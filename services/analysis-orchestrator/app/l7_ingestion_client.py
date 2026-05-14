"""gRPC client for L7 Ingestion Service."""
import logging
import grpc
import sys
import os

logger = logging.getLogger(__name__)

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

try:
    from proto import l7_ingestion_service_pb2 as pb2
    from proto import l7_ingestion_service_pb2_grpc as pb2_grpc
    logger.info("L7 ingestion proto stubs loaded successfully")
except Exception as exc:
    pb2 = None
    pb2_grpc = None
    logger.warning("L7 ingestion proto stubs not available: %s", exc)


class L7IngestionClient:
    def __init__(self, host: str = "l7-ingestion-service", port: int = 5006):
        self._channel = grpc.insecure_channel(f"{host}:{port}")
        self._stub = pb2_grpc.L7DataIngestionStub(self._channel) if pb2_grpc else None

    def start_l7_collection(
        self,
        analysis_id: str,
        cluster_id: str,
        cluster_name: str,
        beyla_namespace: str,
        protocols: list = None,
        sampling_rate: float = 1.0,
        namespace_allow: list = None,
        namespace_deny: list = None,
        cluster_api_url: str = "",
        cluster_token: str = "",
        cluster_ca_cert: str = "",
        skip_tls_verify: bool = False,
        max_events_per_second: int = 5000,
        service_filter: str = "",
        http_methods: list = None,
        status_codes: list = None,
        path_pattern: str = "",
        exclude_paths: str = "/healthz, /readyz, /livez, /metrics",
    ) -> dict:
        if not self._stub:
            return {"success": False, "message": "L7 proto stubs not available"}
        try:
            request = pb2.StartL7CollectionRequest(
                analysis_id=str(analysis_id),
                cluster_id=str(cluster_id),
                cluster_name=cluster_name,
                beyla_namespace=beyla_namespace,
                protocols=protocols or ["http", "grpc"],
                sampling_rate=sampling_rate,
                namespace_allow=namespace_allow or [],
                namespace_deny=namespace_deny or [],
                cluster_api_url=cluster_api_url,
                cluster_token=cluster_token,
                cluster_ca_cert=cluster_ca_cert,
                skip_tls_verify=skip_tls_verify,
                max_events_per_second=max_events_per_second,
                service_filter=service_filter,
                http_methods=http_methods or [],
                status_codes=status_codes or [],
                path_pattern=path_pattern,
                exclude_paths=exclude_paths,
            )
            response = self._stub.StartL7Collection(request, timeout=30)
            return {"success": response.success, "message": response.message, "session_id": response.session_id}
        except grpc.RpcError as e:
            logger.error("start_l7_collection_error: %s", e)
            return {"success": False, "message": str(e)}

    def stop_l7_collection(self, analysis_id: str, cluster_id: str = "") -> dict:
        if not self._stub:
            return {"success": False, "message": "L7 proto stubs not available"}
        try:
            request = pb2.StopL7CollectionRequest(
                analysis_id=str(analysis_id),
                cluster_id=str(cluster_id),
            )
            response = self._stub.StopL7Collection(request, timeout=30)
            return {"success": response.success, "message": response.message, "total_events": response.total_events}
        except grpc.RpcError as e:
            logger.error("stop_l7_collection_error: %s", e)
            return {"success": False, "message": str(e)}

    def get_l7_collection_status(self, analysis_id: str, cluster_id: str = "") -> dict:
        if not self._stub:
            return {"status": "unavailable"}
        try:
            request = pb2.GetL7CollectionStatusRequest(
                analysis_id=str(analysis_id),
                cluster_id=str(cluster_id),
            )
            response = self._stub.GetL7CollectionStatus(request, timeout=10)
            return {
                "analysis_id": response.analysis_id,
                "cluster_id": response.cluster_id,
                "status": response.status,
                "events_published": response.events_published,
                "http_events": response.http_events,
                "grpc_events": response.grpc_events,
                "dns_events": response.dns_events,
                "error_message": response.error_message,
            }
        except grpc.RpcError as e:
            return {"status": "error", "error_message": str(e)}

    def list_l7_collection_statuses(self, analysis_id: str) -> dict:
        """List all L7 collection statuses for an analysis (all clusters).

        Returns dict with 'statuses' list and 'error' key (None on success).
        """
        if not self._stub:
            return {"statuses": [], "error": "L7 proto stubs not available"}
        try:
            request = pb2.ListL7StatusRequest(analysis_id=str(analysis_id))
            response = self._stub.ListL7CollectionStatus(request, timeout=10)
            return {
                "statuses": [
                    {
                        "analysis_id": s.analysis_id,
                        "cluster_id": s.cluster_id,
                        "status": s.status,
                        "events_published": s.events_published,
                        "http_events": s.http_events,
                        "grpc_events": s.grpc_events,
                        "dns_events": s.dns_events,
                        "error_message": s.error_message,
                    }
                    for s in response.statuses
                ],
                "error": None,
            }
        except grpc.RpcError as e:
            logger.error("list_l7_collection_statuses error: %s", e)
            return {"statuses": [], "error": str(e)}

    def health_check(self) -> dict:
        """Probe L7 Ingestion Service health."""
        if not self._stub:
            return {"status": "unavailable", "message": "L7 proto stubs not available"}
        try:
            request = pb2.HealthCheckRequest()
            response = self._stub.HealthCheck(request, timeout=5)
            return {"status": "healthy" if response.healthy else "unhealthy", "message": response.message}
        except grpc.RpcError as e:
            logger.error("l7_ingestion_health_check_error: %s", e)
            return {"status": "error", "message": str(e)}

    def close(self):
        if self._channel:
            self._channel.close()
