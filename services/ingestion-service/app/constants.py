"""
Central constants for the ingestion service.
Version numbers and defaults should be defined here, not scattered in code.

IMPORTANT: Gadget OCI images MUST match the Inspektor Gadget DaemonSet version!
Using 'latest' can cause CO-RE eBPF compatibility issues if versions mismatch.
Example error: "bad CO-RE relocation: invalid func unknown" when gadget v0.47.0
images run on IG v0.48.0 DaemonSet.
"""

# Inspektor Gadget DaemonSet version deployed in cluster
INSPEKTOR_GADGET_VERSION = "v0.48.0"

# Gadget OCI image tag - MUST match DaemonSet version for CO-RE compatibility
# All gadget images (trace_dns, trace_sni, trace_tcp, top_tcp, etc.) will use this tag
# DO NOT use 'latest' - it causes version mismatch issues
GADGET_DEFAULT_VERSION = INSPEKTOR_GADGET_VERSION  # Always sync with DaemonSet version

