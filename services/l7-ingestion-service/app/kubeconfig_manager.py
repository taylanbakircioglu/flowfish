"""Temporary kubeconfig for remote cluster access (Fernet-decrypted credentials)."""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
import base64
from dataclasses import dataclass
from typing import List, Optional

from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)


def _decrypt_if_needed(value: str, encryption_key: str) -> str:
    if not value:
        return ""
    if not encryption_key:
        logger.warning("encryption_key_empty — treating value as plaintext")
        return value
    try:
        f = Fernet(
            encryption_key.encode() if isinstance(encryption_key, str) else encryption_key
        )
        return f.decrypt(value.encode() if isinstance(value, str) else value).decode()
    except Exception as exc:
        logger.error(
            "kubeconfig_decrypt_failed: %s — value will NOT be used as plaintext fallback",
            exc,
        )
        raise ValueError(f"Failed to decrypt credential: {exc}") from exc


def _sanitize_pem_certificate(cert: str) -> Optional[str]:
    if not cert:
        return None
    cert = cert.strip().replace("\r\n", "\n").replace("\r", "\n")
    if not cert.startswith("-----BEGIN"):
        clean_b64 = re.sub(r"\s+", "", cert)
        try:
            decoded = base64.b64decode(clean_b64)
            if decoded.startswith(b"\x30"):
                formatted_b64 = "\n".join(
                    [clean_b64[i : i + 64] for i in range(0, len(clean_b64), 64)]
                )
                cert = (
                    f"-----BEGIN CERTIFICATE-----\n{formatted_b64}\n"
                    f"-----END CERTIFICATE-----\n"
                )
        except Exception:
            return None
    blocks = re.findall(
        r"-----BEGIN CERTIFICATE-----[\s\S]*?-----END CERTIFICATE-----",
        cert,
    )
    if not blocks:
        return None
    sanitized: List[str] = []
    for block in blocks:
        lines = block.strip().split("\n")
        content_lines = [
            line.strip()
            for line in lines
            if line.strip() and not line.strip().startswith("-----")
        ]
        if content_lines:
            formatted_block = "-----BEGIN CERTIFICATE-----\n"
            formatted_block += "\n".join(content_lines)
            formatted_block += "\n-----END CERTIFICATE-----\n"
            sanitized.append(formatted_block)
    if not sanitized:
        return None
    return "\n".join(sanitized)


@dataclass
class KubeconfigManager:
    """Creates a temp kubeconfig; tracks CA file for cleanup."""

    api_server_url: str
    token_encrypted: str
    ca_cert_encrypted: str
    skip_tls_verify: bool
    encryption_key: str
    cluster_name: str = "remote-cluster"

    _kubeconfig_path: Optional[str] = None
    _ca_file_path: Optional[str] = None

    def write_kubeconfig(self) -> str:
        token = _decrypt_if_needed(self.token_encrypted, self.encryption_key)
        if not token:
            raise ValueError("cluster token is empty after decryption")

        ca_plain = _decrypt_if_needed(self.ca_cert_encrypted, self.encryption_key)

        kubeconfig: dict = {
            "apiVersion": "v1",
            "kind": "Config",
            "current-context": self.cluster_name,
            "clusters": [
                {
                    "name": self.cluster_name,
                    "cluster": {"server": self.api_server_url},
                }
            ],
            "contexts": [
                {
                    "name": self.cluster_name,
                    "context": {
                        "cluster": self.cluster_name,
                        "user": "flowfish-l7-reader",
                    },
                }
            ],
            "users": [
                {
                    "name": "flowfish-l7-reader",
                    "user": {"token": token},
                }
            ],
        }

        cluster_block = kubeconfig["clusters"][0]["cluster"]
        if self.skip_tls_verify:
            cluster_block["insecure-skip-tls-verify"] = True
        elif ca_plain:
            sanitized = _sanitize_pem_certificate(ca_plain)
            if sanitized:
                fd, ca_path = tempfile.mkstemp(suffix=".crt", prefix="flowfish-l7-ca-")
                os.chmod(fd, 0o600)
                with os.fdopen(fd, "w") as ca_file:
                    ca_file.write(sanitized)
                self._ca_file_path = ca_path
                cluster_block["certificate-authority"] = ca_path
            else:
                logger.warning("invalid_ca_falling_back_insecure_skip_tls")
                cluster_block["insecure-skip-tls-verify"] = True

        kc_fd, kc_path = tempfile.mkstemp(suffix=".kubeconfig", prefix="flowfish-l7-")
        os.chmod(kc_fd, 0o600)
        with os.fdopen(kc_fd, "w") as kc_file:
            json.dump(kubeconfig, kc_file)
        self._kubeconfig_path = kc_path
        logger.info(
            "wrote_temp_kubeconfig path=%s cluster=%s",
            self._kubeconfig_path,
            self.cluster_name,
        )
        return self._kubeconfig_path

    def cleanup(self) -> None:
        paths = [self._kubeconfig_path, self._ca_file_path]
        for p in paths:
            if p and os.path.isfile(p):
                try:
                    os.unlink(p)
                except OSError as e:
                    logger.warning("kubeconfig_cleanup_failed path=%s err=%s", p, e)
        self._kubeconfig_path = None
        self._ca_file_path = None


def cleanup_stale_temp_files() -> int:
    """Remove leftover flowfish-l7-* temp files from previous runs (e.g. after crash)."""
    cleaned = 0
    tmp_dir = tempfile.gettempdir()
    for fname in os.listdir(tmp_dir):
        if fname.startswith("flowfish-l7-") and (
            fname.endswith(".kubeconfig") or fname.endswith(".crt")
        ):
            fpath = os.path.join(tmp_dir, fname)
            try:
                os.unlink(fpath)
                cleaned += 1
            except OSError:
                pass
    if cleaned:
        logger.info("Cleaned %d stale temp kubeconfig/ca files on startup", cleaned)
    return cleaned
