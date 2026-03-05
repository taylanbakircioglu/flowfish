"""
Flowfish Ingestion Service
Collects eBPF data from Inspektor Gadget and publishes to RabbitMQ

Version History:
- 1.1.1: SDN Gateway detection for custom pod network gateway IPs, fixed Pod-Network CIDR
- 1.1.0: Remote cluster kubectl discovery, increased memory limits
"""

__version__ = "1.1.1"

