"""
Factory for creating appropriate Gadget client based on protocol
"""

from typing import Dict, Any
import structlog

from .abstract_gadget_client import AbstractGadgetClient, Protocol, AuthMethod
from .kubectl_gadget_client import KubectlGadgetClient
from app.constants import GADGET_DEFAULT_VERSION

logger = structlog.get_logger()


class GadgetClientFactory:
    """
    Factory for creating Gadget clients
    
    Currently supports:
    - kubectl-gadget CLI (primary, v0.46.0+)
    
    Note: gRPC, HTTP, and Agent protocols have been removed.
    All communication with Inspektor Gadget is done via kubectl-gadget CLI.
    """
    
    @staticmethod
    def create_client(config: Dict[str, Any]) -> AbstractGadgetClient:
        """
        Create kubectl-gadget client
        
        Args:
            config: Client configuration dict containing:
                - kubeconfig: Path to kubeconfig file (optional)
                - context: Kubernetes context (optional)
                - gadget_namespace: Namespace where gadget is deployed
                - gadget_image_version: Gadget version
                - gadget_registry: OCI registry for gadget images
                - gadget_image_prefix: Prefix for gadget images
                - timeout_seconds: Command timeout
        
        Returns:
            KubectlGadgetClient instance
        
        Raises:
            ValueError: If protocol is not supported
        """
        protocol = config.get('protocol', 'kubectl').lower()
        
        logger.info("Creating Gadget client",
                   protocol=protocol)
        
        # All protocols now use kubectl-gadget CLI
        if protocol in ('kubectl', 'kubectl-gadget', 'cli', 'grpc', 'http', 'agent'):
            # Note: grpc, http, agent are deprecated and redirected to kubectl
            if protocol in ('grpc', 'http', 'agent'):
                logger.warning(
                    f"Protocol '{protocol}' is deprecated, using kubectl-gadget instead",
                    requested_protocol=protocol
                )
            
            return KubectlGadgetClient(
                kubeconfig=config.get('kubeconfig'),
                context=config.get('context'),
                kubectl_path=config.get('kubectl_path', 'kubectl'),
                gadget_namespace=config.get('gadget_namespace'),  # REQUIRED - from request
                gadget_image_version=config.get('gadget_image_version', GADGET_DEFAULT_VERSION),
                gadget_registry=config.get('gadget_registry', ''),
                gadget_image_prefix=config.get('gadget_image_prefix', 'gadget-'),
                timeout_seconds=config.get('timeout_seconds', 30)
            )
        
        else:
            raise ValueError(f"Unsupported protocol: {protocol}. Use 'kubectl' or 'kubectl-gadget'.")
    
    @staticmethod
    def create_from_collection_request(request) -> AbstractGadgetClient:
        """
        Create client from gRPC StartCollectionRequest
        
        Args:
            request: StartCollectionRequest from proto
        
        Returns:
            AbstractGadgetClient implementation
        """
        protocol = request.gadget_protocol or 'kubectl'
        
        config = {
            'endpoint': request.gadget_endpoint,
            'protocol': protocol,
            'auth_method': request.gadget_auth_method,
            'use_tls': request.use_tls,
            'verify_tls': request.verify_ssl,
            'api_key': request.gadget_api_key if request.gadget_api_key else None,
            'token': request.gadget_token if request.gadget_token else None,
            'client_cert': request.gadget_client_cert if request.gadget_client_cert else None,
            'client_key': request.gadget_client_key if request.gadget_client_key else None,
            'ca_cert': request.gadget_ca_cert if request.gadget_ca_cert else None,
            # kubectl-gadget specific
            'kubeconfig': getattr(request, 'kubeconfig', None),
            'context': getattr(request, 'context', None),
            'gadget_namespace': request.gadget_namespace,  # REQUIRED - from proto
        }
        
        return GadgetClientFactory.create_client(config)

