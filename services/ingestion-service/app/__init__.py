"""
Flowfish Ingestion Service
Collects eBPF data from Inspektor Gadget and publishes to RabbitMQ

Version History:
- 1.1.1: SDN Gateway detection for 10.194.x.1/x.2 IPs, fixed Pod-Network CIDR
- 1.1.0: Remote cluster kubectl discovery, increased memory limits
"""

__version__ = "1.1.1"

