"""
Encryption utilities for sensitive data
Uses Fernet (AES-128-CBC) for symmetric encryption

SECURITY NOTES:
- ENCRYPTION_KEY must be set via environment variable
- Key should be generated with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
- Store key securely (Kubernetes Secret, HashiCorp Vault, etc.)
- Never commit encryption keys to version control
"""

import os
import base64
from typing import Optional
from cryptography.fernet import Fernet, InvalidToken
import structlog

logger = structlog.get_logger()

# Get encryption key from environment
# MUST be a valid Fernet key (32 url-safe base64-encoded bytes)
_ENCRYPTION_KEY = os.environ.get("FLOWFISH_ENCRYPTION_KEY")

# Lazy initialization of Fernet cipher
_cipher: Optional[Fernet] = None


def _get_cipher() -> Fernet:
    """Get or initialize Fernet cipher"""
    global _cipher
    
    if _cipher is None:
        if not _ENCRYPTION_KEY:
            # In development, generate a warning and use a default key
            # In production, this should NEVER happen
            logger.warning(
                "FLOWFISH_ENCRYPTION_KEY not set! Using temporary key. "
                "THIS IS INSECURE FOR PRODUCTION!"
            )
            # Generate a temporary key for development only
            _cipher = Fernet(Fernet.generate_key())
        else:
            try:
                _cipher = Fernet(_ENCRYPTION_KEY.encode())
            except Exception as e:
                logger.error("Invalid FLOWFISH_ENCRYPTION_KEY", error=str(e))
                raise ValueError(
                    "Invalid FLOWFISH_ENCRYPTION_KEY. "
                    "Generate with: python -c \"from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())\""
                )
    
    return _cipher


def encrypt_value(plaintext: str) -> str:
    """
    Encrypt a string value using Fernet (AES-128-CBC)
    
    Args:
        plaintext: The string to encrypt
        
    Returns:
        Base64-encoded encrypted string
    """
    if not plaintext:
        return ""
    
    cipher = _get_cipher()
    encrypted = cipher.encrypt(plaintext.encode('utf-8'))
    return encrypted.decode('utf-8')


def decrypt_value(ciphertext: str) -> str:
    """
    Decrypt a Fernet-encrypted string with backward compatibility.
    
    If decryption fails (e.g., data is plain text or wrong key),
    returns the original value as-is. This ensures:
    - Backward compatibility with existing unencrypted data
    - Graceful handling of encryption key changes
    - No application crashes on decrypt failure
    
    Args:
        ciphertext: Base64-encoded encrypted string (or plain text for legacy data)
        
    Returns:
        Decrypted plaintext string, or original value if decryption fails
    """
    if not ciphertext:
        return ""
    
    # Check if value looks like it could be Fernet encrypted
    # Fernet tokens start with 'gAAAAA' (base64 encoded version byte)
    if not ciphertext.startswith('gAAAAA'):
        # Likely plain text (legacy unencrypted data)
        logger.debug("Value doesn't appear to be encrypted, returning as-is")
        return ciphertext
    
    cipher = _get_cipher()
    try:
        decrypted = cipher.decrypt(ciphertext.encode('utf-8'))
        return decrypted.decode('utf-8')
    except InvalidToken:
        # Decryption failed - could be plain text or wrong key
        # Return original value as fallback for backward compatibility
        logger.warning(
            "Decryption failed, returning value as-is. "
            "This may indicate legacy unencrypted data or key mismatch."
        )
        return ciphertext
    except Exception as e:
        # Unexpected error - log and return original
        logger.error("Unexpected decryption error", error=str(e))
        return ciphertext


def encrypt_token(token: str) -> str:
    """Encrypt a service account token"""
    return encrypt_value(token)


def decrypt_token(encrypted_token: str) -> str:
    """Decrypt a service account token"""
    return decrypt_value(encrypted_token)


def encrypt_certificate(cert: str) -> str:
    """Encrypt a CA certificate"""
    return encrypt_value(cert)


def decrypt_certificate(encrypted_cert: str) -> str:
    """Decrypt a CA certificate"""
    return decrypt_value(encrypted_cert)


def encrypt_kubeconfig(kubeconfig: str) -> str:
    """Encrypt a kubeconfig file content"""
    return encrypt_value(kubeconfig)


def decrypt_kubeconfig(encrypted_kubeconfig: str) -> str:
    """Decrypt a kubeconfig file content"""
    return decrypt_value(encrypted_kubeconfig)


def is_encryption_configured() -> bool:
    """Check if encryption is properly configured"""
    return bool(_ENCRYPTION_KEY)


def generate_encryption_key() -> str:
    """Generate a new Fernet encryption key"""
    return Fernet.generate_key().decode()


# Aliases for backward compatibility
encrypt_data = encrypt_value
decrypt_data = decrypt_value

