"""
Authentication router - Simplified for MVP
"""

from datetime import datetime, timedelta
from fastapi import APIRouter, HTTPException, status, Request
from pydantic import BaseModel
from typing import Optional
import structlog
import jwt
import json

from database.postgresql import database
from config import settings
from services.activity_service import activity_service, ActivityService

logger = structlog.get_logger()

router = APIRouter()

# JWT secret
JWT_SECRET = getattr(settings, 'SECRET_KEY', 'super-secret-key-change-me-in-production')

# Pydantic schemas
class LoginRequest(BaseModel):
    username: str
    password: str
    client_ip: str | None = None  # Optional: sent from frontend
    two_factor_code: str | None = None  # Optional: 2FA code

class LoginResponse(BaseModel):
    access_token: str
    token_type: str
    expires_in: int
    user: dict
    requires_2fa: bool = False
    two_fa_sent: bool = False

async def check_2fa_required(user_id: int) -> tuple[bool, bool]:
    """
    Check if 2FA is required for a user.
    Returns (is_required, user_has_2fa_enabled)
    """
    try:
        # Check global 2FA settings
        settings_query = """
            SELECT value FROM system_settings 
            WHERE key = 'security_policies'
        """
        settings_row = await database.fetch_one(settings_query)
        
        global_2fa_enabled = False
        global_2fa_required = False
        
        if settings_row:
            settings_value = settings_row['value']
            if isinstance(settings_value, str):
                settings_value = json.loads(settings_value)
            global_2fa_enabled = settings_value.get('two_factor_enabled', False)
            global_2fa_required = settings_value.get('two_factor_required_for_all', False)
        
        # If 2FA is not enabled globally, skip
        if not global_2fa_enabled:
            return False, False
        
        # Check user's 2FA setting
        user_query = "SELECT two_factor_enabled FROM users WHERE id = :user_id"
        user_row = await database.fetch_one(user_query, {"user_id": user_id})
        
        user_2fa_enabled = False
        if user_row and user_row['two_factor_enabled']:
            user_2fa_enabled = True
        
        # 2FA is required if: globally required OR user has it enabled
        is_required = global_2fa_required or user_2fa_enabled
        
        return is_required, user_2fa_enabled
        
    except Exception as e:
        logger.error("Error checking 2FA requirement", error=str(e))
        return False, False


async def send_2fa_code_internal(user_id: int, email: str, username: str) -> bool:
    """Send 2FA code to user's email"""
    try:
        import secrets
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        
        # Generate 6-digit code
        code = ''.join([str(secrets.randbelow(10)) for _ in range(6)])
        
        # Get expiry from settings
        settings_query = """
            SELECT value FROM system_settings 
            WHERE key = 'security_policies'
        """
        settings_row = await database.fetch_one(settings_query)
        expiry_minutes = 5
        if settings_row:
            settings_value = settings_row['value']
            if isinstance(settings_value, str):
                settings_value = json.loads(settings_value)
            expiry_minutes = settings_value.get('two_factor_code_expiry_minutes', 5)
        
        expires_at = datetime.utcnow() + timedelta(minutes=expiry_minutes)
        
        # Store code
        store_query = """
            INSERT INTO two_factor_codes (user_id, code, expires_at, created_at)
            VALUES (:user_id, :code, :expires_at, NOW())
            ON CONFLICT (user_id) DO UPDATE SET
                code = :code, expires_at = :expires_at, created_at = NOW(), attempts = 0
        """
        await database.execute(store_query, {
            "user_id": user_id,
            "code": code,
            "expires_at": expires_at
        })
        
        # Get SMTP settings
        smtp_query = """
            SELECT value FROM system_settings 
            WHERE key = 'smtp_settings'
        """
        smtp_row = await database.fetch_one(smtp_query)
        
        if not smtp_row:
            logger.warning("SMTP not configured for 2FA")
            return False
        
        smtp_settings = smtp_row['value']
        if isinstance(smtp_settings, str):
            smtp_settings = json.loads(smtp_settings)
        
        if not smtp_settings.get('enabled'):
            logger.warning("Email notifications disabled")
            return False
        
        # Create email
        msg = MIMEMultipart('alternative')
        msg['From'] = f"{smtp_settings.get('from_name', 'Flowfish')} <{smtp_settings.get('from_email')}>"
        msg['To'] = email
        msg['Subject'] = f"Flowfish Login Verification: {code}"
        
        html_body = f"""
<!DOCTYPE html>
<html>
<head>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f5f5f5; padding: 20px; }}
        .container {{ max-width: 500px; margin: 0 auto; background: white; border-radius: 12px; padding: 40px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); }}
        .logo {{ text-align: center; margin-bottom: 30px; }}
        .logo h1 {{ color: #0891b2; margin: 0; font-size: 28px; }}
        .code-box {{ background: linear-gradient(135deg, #667eea 0%, #764ba2 100%); color: white; font-size: 32px; letter-spacing: 8px; text-align: center; padding: 20px; border-radius: 8px; margin: 30px 0; font-weight: bold; }}
        .message {{ color: #666; line-height: 1.6; }}
        .expiry {{ background: #fff3cd; color: #856404; padding: 12px; border-radius: 6px; margin-top: 20px; text-align: center; }}
        .footer {{ margin-top: 30px; text-align: center; color: #999; font-size: 12px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="logo"><h1>🐟 Flowfish</h1></div>
        <p class="message">Hello <strong>{username}</strong>,</p>
        <p class="message">Your login verification code is:</p>
        <div class="code-box">{code}</div>
        <div class="expiry">⏱️ This code expires in <strong>{expiry_minutes} minutes</strong></div>
        <p class="message" style="margin-top: 20px;">If you didn't attempt to log in, please contact your administrator immediately.</p>
        <div class="footer"><p>© 2026 Flowfish - Kubernetes Observability Platform</p></div>
    </div>
</body>
</html>
        """
        
        msg.attach(MIMEText(html_body, 'html'))
        
        # Send email
        if smtp_settings.get('use_ssl'):
            server = smtplib.SMTP_SSL(smtp_settings['host'], smtp_settings['port'])
        else:
            server = smtplib.SMTP(smtp_settings['host'], smtp_settings['port'])
            if smtp_settings.get('use_tls'):
                server.starttls()
        
        if smtp_settings.get('username') and smtp_settings.get('password'):
            server.login(smtp_settings['username'], smtp_settings['password'])
        
        server.send_message(msg)
        server.quit()
        
        logger.info("2FA code sent for login", user_id=user_id)
        return True
        
    except Exception as e:
        logger.error("Failed to send 2FA code", error=str(e))
        return False


async def verify_2fa_code_internal(user_id: int, code: str) -> tuple[bool, str]:
    """Verify 2FA code. Returns (success, error_message)"""
    try:
        # Get stored code
        query = """
            SELECT code, expires_at, attempts 
            FROM two_factor_codes 
            WHERE user_id = :user_id
        """
        row = await database.fetch_one(query, {"user_id": user_id})
        
        if not row:
            return False, "No verification code found. Please request a new code."
        
        # Check expiry
        expires_at = row['expires_at']
        if expires_at.tzinfo:
            expires_at = expires_at.replace(tzinfo=None)
        
        if datetime.utcnow() > expires_at:
            return False, "Verification code expired. Please request a new code."
        
        # Check max attempts
        max_attempts = 3
        if row['attempts'] >= max_attempts:
            return False, "Too many failed attempts. Please request a new code."
        
        # Verify code
        if row['code'] != code:
            # Increment attempts
            await database.execute(
                "UPDATE two_factor_codes SET attempts = attempts + 1 WHERE user_id = :user_id",
                {"user_id": user_id}
            )
            remaining = max_attempts - row['attempts'] - 1
            return False, f"Invalid verification code. {remaining} attempts remaining."
        
        # Code is valid - delete it
        await database.execute(
            "DELETE FROM two_factor_codes WHERE user_id = :user_id",
            {"user_id": user_id}
        )
        
        return True, ""
        
    except Exception as e:
        logger.error("2FA verification error", error=str(e))
        return False, "Verification failed. Please try again."


@router.post("/auth/login", response_model=LoginResponse)
async def login(login_data: LoginRequest, request: Request):
    """User login with username and password, with optional 2FA"""
    try:
        # Get client IP - priority order:
        # 1. Frontend-provided IP (most reliable in complex proxy setups)
        # 2. X-Real-IP header
        # 3. X-Forwarded-For header (first IP)
        # 4. Direct connection IP
        
        client_ip = "0.0.0.0"
        
        if login_data.client_ip:
            client_ip = login_data.client_ip
        elif request.headers.get("X-Real-IP"):
            client_ip = request.headers.get("X-Real-IP")
        elif request.headers.get("X-Forwarded-For"):
            client_ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
        elif request.client:
            client_ip = request.client.host
        
        logger.info("Login attempt", username=login_data.username, ip=client_ip)
        
        # Query user from database with 2FA status
        query = """
            SELECT id, username, email, is_active, two_factor_enabled 
            FROM users 
            WHERE username = :username AND is_active = true
        """
        user = await database.fetch_one(query, {"username": login_data.username})
        
        if not user:
            logger.warning("User not found", username=login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Verify password using bcrypt hash from database
        password_valid = False
        try:
            from passlib.context import CryptContext
            pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
            
            pwd_query = "SELECT password_hash FROM users WHERE id = :user_id"
            pwd_row = await database.fetch_one(pwd_query, {"user_id": user["id"]})
            
            if pwd_row and pwd_row['password_hash']:
                # Truncate password to 72 bytes (bcrypt limit)
                password_truncated = login_data.password[:72]
                password_valid = pwd_context.verify(password_truncated, pwd_row['password_hash'])
        except Exception as e:
            logger.warning("Password verification error", error=str(e))
        
        if not password_valid:
            logger.warning("Invalid password", username=login_data.username)
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid username or password"
            )
        
        # Check if 2FA is required
        tfa_required, user_has_2fa = await check_2fa_required(user["id"])
        
        if tfa_required:
            # If 2FA code is provided, verify it
            if login_data.two_factor_code:
                success, error_msg = await verify_2fa_code_internal(user["id"], login_data.two_factor_code)
                if not success:
                    raise HTTPException(
                        status_code=status.HTTP_401_UNAUTHORIZED,
                        detail=error_msg
                    )
                # 2FA verified, continue with login
            else:
                # No 2FA code provided, send one and return
                if user["email"]:
                    sent = await send_2fa_code_internal(user["id"], user["email"], user["username"])
                    if sent:
                        return LoginResponse(
                            access_token="",
                            token_type="bearer",
                            expires_in=0,
                            user={"id": user["id"], "username": user["username"]},
                            requires_2fa=True,
                            two_fa_sent=True
                        )
                    else:
                        raise HTTPException(
                            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                            detail="Failed to send verification code. Please contact administrator."
                        )
                else:
                    raise HTTPException(
                        status_code=status.HTTP_400_BAD_REQUEST,
                        detail="2FA is required but no email is configured for this user."
                    )
        
        # Update last_login_at and last_login_ip
        await database.execute(
            "UPDATE users SET last_login_at = NOW(), last_login_ip = :ip WHERE id = :user_id",
            {"user_id": user["id"], "ip": client_ip}
        )
        
        # Get user roles
        roles_query = """
            SELECT r.name FROM roles r
            JOIN user_roles ur ON r.id = ur.role_id
            WHERE ur.user_id = :user_id
        """
        roles_result = await database.fetch_all(roles_query, {"user_id": user["id"]})
        roles = [r["name"] for r in roles_result] if roles_result else ["Super Admin"]
        
        # Create JWT token
        token_payload = {
            "user_id": user["id"],
            "username": user["username"],
            "roles": roles,
            "type": "access",  # Required for token verification
            "exp": datetime.utcnow() + timedelta(hours=8),
            "iat": datetime.utcnow()
        }
        
        access_token = jwt.encode(token_payload, JWT_SECRET, algorithm="HS256")
        
        logger.info("Login successful", username=user["username"])
        
        # Log activity
        await activity_service.log_activity(
            user_id=user["id"],
            username=user["username"],
            action=ActivityService.ACTION_LOGIN,
            resource_type=ActivityService.RESOURCE_SESSION,
            resource_id=str(user["id"]),
            resource_name=user["username"],
            ip_address=client_ip,
            user_agent=request.headers.get("User-Agent")
        )
        
        return LoginResponse(
            access_token=access_token,
            token_type="bearer",
            expires_in=28800,  # 8 hours
            user={
                "id": user["id"],
                "username": user["username"],
                "email": user["email"],
                "roles": roles
            },
            requires_2fa=False,
            two_fa_sent=False
        )
            
    except HTTPException:
        raise
    except Exception as e:
        logger.error("Login error", error=str(e), exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Authentication service error: {str(e)}"
        )

@router.get("/auth/me")
async def get_current_user_info():
    """Get current user information (requires authentication)"""
    # TODO: Implement JWT verification middleware
    return {
        "message": "Authentication middleware not yet implemented",
        "status": "coming_soon"
    }
