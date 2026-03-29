"""
Protocol abstraction layer for Inspektor Gadget communication

Uses kubectl-gadget CLI for all communication with Inspektor Gadget v0.46.0+
"""

from .abstract_gadget_client import AbstractGadgetClient, TraceConfig, HealthStatus
from .kubectl_gadget_client import KubectlGadgetClient
from .client_factory import GadgetClientFactory

__all__ = [
    "AbstractGadgetClient",
    "TraceConfig",
    "HealthStatus",
    "KubectlGadgetClient",
    "GadgetClientFactory",
]

