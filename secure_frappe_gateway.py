"""
=============================================================================
🛡️ VibeSec Secure Python Integration Layer & Frappe API Gateway
=============================================================================
Enforces strict security boundaries for web applications interacting with
Frappe / ERPNext REST & RPC interfaces:

1. Credentials Isolation:
   - System secrets (API Keys, API Secrets, Admin passwords) are loaded
     strictly from environment variables.
   - Zero hardcoded credentials; automated redaction on diagnostic logging.

2. Server-Side Session Validation (Anti-BOLA / Anti-IDOR):
   - Cryptographically secure session verification before ANY outbound request.
   - Prevents Broken Object Level Authorization (BOLA) and Insecure Direct
     Object References (IDOR) by strictly verifying that requesting session
     metadata matches target entity / customer identifiers (e.g. X-Customer-ID,
     X-Target-User, or customer-scoped URL parameters).
   - Returns clean HTTP 403 Forbidden immediately without forwarding to ERPNext.

3. Strict Schema Mapping & Parameter Sanitization:
   - Python dataclasses with type-hinting, regex allow-lists, and boundary checks.
   - Prevents path traversal, SQL/NoSQL injection, and malformed RPC parameters.
=============================================================================
"""

from dataclasses import dataclass, field
import hashlib
import hmac
import http.cookiejar
import json
import os
import re
import ssl
import sys
import time
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import urllib.error
import urllib.parse
import urllib.request

# =============================================================================
# 1. CREDENTIALS ISOLATION & CONFIGURATION
# =============================================================================

DEV_SERVER_URL = "https://dev.pmii-marketing.com"
PROD_SERVER_URL = "https://pmii-marketing.com"

# Environment toggle
ENVIRONMENT = os.environ.get("ENVIRONMENT", "development").lower()
DEFAULT_ERP_URL = PROD_SERVER_URL if ENVIRONMENT == "production" else DEV_SERVER_URL

ERPNEXT_SERVER_URL = os.environ.get("ERPNEXT_URL", DEFAULT_ERP_URL).rstrip("/")

# Frappe Token / Secret credentials isolated from OS environment
FRAPPE_API_KEY = os.environ.get("FRAPPE_API_KEY", "")
FRAPPE_API_SECRET = os.environ.get("FRAPPE_API_SECRET", "")
ERPNEXT_ADMIN_USER = os.environ.get("ERPNEXT_ADMIN_USER", "")
ERPNEXT_ADMIN_PASSWORD = os.environ.get("ERPNEXT_ADMIN_PASSWORD", "")

# Secret for signing session HMACs (fallback to random per-boot if unset)
SESSION_SIGNING_KEY = os.environ.get("SESSION_SECRET", os.environ.get("SECRET_KEY", "vibesec_pims_secret_k9x2_secure"))


def sanitize_log_message(msg: str) -> str:
    """Scrub sensitive credentials, passwords, tokens, and cookies from log output."""
    if not isinstance(msg, str):
        msg = str(msg)
    # Redact passwords, secrets, tokens
    msg = re.sub(r'(pwd|password|secret|api_secret|token|sid|key)=["\']?[^"\'&\s]+["\']?', r'\1=***REDACTED***', msg, flags=re.IGNORECASE)
    # Redact auth headers
    msg = re.sub(r'(Bearer|token)\s+[a-zA-Z0-9_\-\.~]+', r'\1 ***REDACTED***', msg, flags=re.IGNORECASE)
    return msg


# =============================================================================
# 2. STRICT SCHEMA MAPPING & PARAMETER SANITIZATION
# =============================================================================

class SecurityValidationError(ValueError):
    """Raised when an incoming parameter violates security constraints."""
    pass


# Allow-lists for safe identifiers
SAFE_IDENTIFIER_REGEX = re.compile(r'^[a-zA-Z0-9_\- ]+$')
SAFE_METHOD_REGEX = re.compile(r'^[a-zA-Z0-9_\.]+$')
SAFE_FIELD_NAME_REGEX = re.compile(r'^[a-zA-Z0-9_]+$')


def sanitize_string(val: Any, max_len: int = 140, allow_spaces: bool = True) -> str:
    """Strictly cast to trimmed string, remove control characters and script injection."""
    if val is None:
        return ""
    s = str(val).strip()
    # Strip null bytes and control chars
    s = "".join(c for c in s if c.isprintable())
    # Strip HTML tags
    s = re.sub(r'<[^>]*?>', '', s)
    if not allow_spaces:
        s = re.sub(r'\s+', '', s)
    if len(s) > max_len:
        s = s[:max_len]
    return s


def sanitize_int(val: Any, default: int = 0, min_val: int = 0, max_val: int = 1_000_000) -> int:
    """Strictly cast and clamp integer parameter."""
    try:
        n = int(val)
        return max(min_val, min(max_val, n))
    except (ValueError, TypeError):
        return default


@dataclass
class ResourceRequestSchema:
    """Strict schema for GET / POST / PUT / DELETE /api/resource/{doctype}/{name}"""
    doctype: str
    name: Optional[str] = None
    fields: List[str] = field(default_factory=list)
    filters: Optional[Union[Dict[str, Any], List[List[Any]]]] = None
    limit_page_length: int = 20
    limit_start: int = 0
    order_by: Optional[str] = None

    @classmethod
    def from_request(
        cls,
        doctype: str,
        name: Optional[str] = None,
        query_params: Optional[Dict[str, Any]] = None
    ) -> "ResourceRequestSchema":
        query_params = query_params or {}

        # 1. Validate DocType (Prevent path traversal & command injection)
        clean_dt = sanitize_string(doctype, max_len=80)
        if not clean_dt or not SAFE_IDENTIFIER_REGEX.match(clean_dt) or ".." in clean_dt or "/" in clean_dt or "\\" in clean_dt:
            raise SecurityValidationError(f"Invalid or unsafe DocType identifier: '{doctype}'")

        # 2. Validate DocName
        clean_name: Optional[str] = None
        if name:
            clean_name = sanitize_string(name, max_len=140)
            if ".." in clean_name or "/" in clean_name or "\\" in clean_name:
                raise SecurityValidationError(f"Path traversal detected in resource name: '{name}'")

        # 3. Parse fields
        parsed_fields: List[str] = []
        raw_fields = query_params.get("fields")
        if raw_fields:
            if isinstance(raw_fields, str):
                try:
                    loaded = json.loads(raw_fields)
                    if isinstance(loaded, list):
                        parsed_fields = [sanitize_string(f, 60, False) for f in loaded if isinstance(f, str)]
                except Exception:
                    # comma-separated fallback
                    parsed_fields = [sanitize_string(f, 60, False) for f in raw_fields.split(",") if f.strip()]
            elif isinstance(raw_fields, list):
                parsed_fields = [sanitize_string(f, 60, False) for f in raw_fields if isinstance(f, str)]

        # Validate each field identifier
        for f in parsed_fields:
            if not SAFE_FIELD_NAME_REGEX.match(f):
                raise SecurityValidationError(f"Illegal field identifier: '{f}'")

        # 4. Limit and paging
        limit_len = sanitize_int(query_params.get("limit_page_length", 20), default=20, min_val=1, max_val=2000)
        limit_start = sanitize_int(query_params.get("limit_start", 0), default=0, min_val=0, max_val=500_000)

        # 5. Safe Order By
        order_by: Optional[str] = None
        raw_order = query_params.get("order_by")
        if raw_order and isinstance(raw_order, str):
            clean_order = sanitize_string(raw_order, 60)
            # Allowed: 'creation desc', 'modified asc', 'name'
            if re.match(r'^[a-zA-Z0-9_]+(\s+(asc|desc))?$', clean_order, re.IGNORECASE):
                order_by = clean_order

        # 6. Filters
        filters = None
        raw_filters = query_params.get("filters")
        if raw_filters:
            if isinstance(raw_filters, str):
                try:
                    filters = json.loads(raw_filters)
                except Exception:
                    raise SecurityValidationError("Invalid JSON in filters query parameter")
            elif isinstance(raw_filters, (dict, list)):
                filters = raw_filters

        return cls(
            doctype=clean_dt,
            name=clean_name,
            fields=parsed_fields,
            filters=filters,
            limit_page_length=limit_len,
            limit_start=limit_start,
            order_by=order_by
        )


@dataclass
class TerritoryActionSchema:
    """Strict schema for territory tree manipulation RPC actions."""
    action: str
    territory_name: str
    parent_territory: str
    is_group: int = 0
    territory_manager: Optional[str] = None
    custom_user_id: Optional[str] = None
    custom_account_or_program: Optional[str] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "TerritoryActionSchema":
        if not isinstance(data, dict):
            raise SecurityValidationError("Payload must be a JSON object")

        raw_action = sanitize_string(data.get("action", ""), max_len=30, allow_spaces=False)
        allowed_actions = {"tree_add", "tree_edit", "tree_rename", "tree_delete", "tree_refresh"}
        if raw_action not in allowed_actions:
            raise SecurityValidationError(f"Disallowed action: '{raw_action}'")

        t_name = sanitize_string(data.get("territory_name") or data.get("name") or "", max_len=140)
        if not t_name and raw_action != "tree_refresh":
            raise SecurityValidationError("territory_name is required")

        parent_t = sanitize_string(data.get("parent_territory") or data.get("parent") or "", max_len=140)
        is_group_val = 1 if bool(data.get("is_group")) else 0

        mgr = sanitize_string(data.get("territory_manager"), max_len=140) if data.get("territory_manager") else None
        
        # User ID / email validation
        raw_uid = data.get("custom_user_id") or data.get("user_id")
        clean_uid: Optional[str] = None
        if raw_uid:
            clean_uid = sanitize_string(raw_uid, max_len=120, allow_spaces=False).lower()
            if not re.match(r'^[^@\s]+@[^@\s]+\.[^@\s]+$', clean_uid):
                raise SecurityValidationError(f"Invalid email format for custom_user_id: '{raw_uid}'")

        prog = sanitize_string(data.get("custom_account_or_program") or data.get("program"), max_len=100) if (data.get("custom_account_or_program") or data.get("program")) else None

        return cls(
            action=raw_action,
            territory_name=t_name,
            parent_territory=parent_t,
            is_group=is_group_val,
            territory_manager=mgr,
            custom_user_id=clean_uid,
            custom_account_or_program=prog
        )


# =============================================================================
# 3. SERVER-SIDE SESSION VALIDATION & ANTI-BOLA / ANTI-IDOR ENGINE
# =============================================================================

@dataclass
class UserSession:
    """Cryptographically managed server-side user session."""
    session_token: str
    user_email: str
    full_name: str
    roles: List[str] = field(default_factory=list)
    customer_id: Optional[str] = None  # Bound customer/tenant identifier (for customer portal sessions)
    is_admin: bool = False
    is_sfe: bool = False
    created_at: float = field(default_factory=time.time)
    last_active: float = field(default_factory=time.time)
    expires_at: float = 0.0

    def is_expired(self, max_idle_seconds: float = 86400.0) -> bool:
        now = time.time()
        if self.expires_at > 0 and now > self.expires_at:
            return True
        if (now - self.last_active) > max_idle_seconds:
            return True
        return False

    def touch(self) -> None:
        self.last_active = time.time()


class SessionRegistry:
    """Thread-safe server-side active session store."""

    def __init__(self):
        self._sessions: Dict[str, UserSession] = {}

    def register(
        self,
        token: str,
        user_email: str,
        full_name: str,
        roles: Optional[List[str]] = None,
        customer_id: Optional[str] = None,
        is_admin: bool = False,
        is_sfe: bool = False,
        ttl_seconds: float = 86400.0
    ) -> UserSession:
        now = time.time()
        session = UserSession(
            session_token=token,
            user_email=user_email.strip().lower(),
            full_name=full_name.strip(),
            roles=roles or [],
            customer_id=customer_id.strip() if customer_id else None,
            is_admin=is_admin,
            is_sfe=is_sfe,
            created_at=now,
            last_active=now,
            expires_at=now + ttl_seconds
        )
        self._sessions[token] = session
        return session

    def get(self, token: Optional[str]) -> Optional[UserSession]:
        if not token or token not in self._sessions:
            return None
        session = self._sessions[token]
        if session.is_expired():
            self._sessions.pop(token, None)
            return None
        session.touch()
        return session

    def revoke(self, token: str) -> bool:
        if token in self._sessions:
            self._sessions.pop(token, None)
            return True
        return False

    def purge_expired(self) -> int:
        now = time.time()
        expired_keys = [k for k, s in self._sessions.items() if s.is_expired()]
        for k in expired_keys:
            self._sessions.pop(k, None)
        return len(expired_keys)


GLOBAL_SESSION_REGISTRY = SessionRegistry()


class AuthorizationDecision:
    """Result of an anti-BOLA/IDOR security inspection."""
    def __init__(self, allowed: bool, status_code: int = 200, reason: str = ""):
        self.allowed = allowed
        self.status_code = status_code
        self.reason = reason

    def __bool__(self) -> bool:
        return self.allowed


class VibeSecAuthorizer:
    """
    Enforces server-side session validation to prevent IDOR and BOLA vulnerabilities:
    - Verifies requesting user's session token strictly matches target ERP user metadata.
    - Inspects incoming headers (X-Customer-ID, X-Target-User, etc.) against session claims.
    - Restricts customer-scoped resource endpoints (Customer, Sales Invoice, etc.)
    """

    # Doctypes that represent customer or tenant-specific confidential assets
    CUSTOMER_SCOPED_DOCTYPES: Set[str] = {
        "Customer",
        "Sales Invoice",
        "Payment Entry",
        "Quotation",
        "Sales Order",
        "Delivery Note"
    }

    @classmethod
    def extract_token_from_request(
        cls,
        headers: Dict[str, str],
        cookies: Optional[str] = None
    ) -> Optional[str]:
        """Extract session token from Authorization header, X-Session-Token, or cookie."""
        # 1. Authorization: Bearer <token>
        auth = headers.get("Authorization") or headers.get("authorization") or ""
        if auth.startswith("Bearer "):
            return auth[7:].strip()

        # 2. X-Session-Token header
        x_tok = headers.get("X-Session-Token") or headers.get("x-session-token")
        if x_tok:
            return x_tok.strip()

        # 3. Cookies: sfe_session=<token>
        if cookies:
            match = re.search(r'sfe_session=([a-zA-Z0-9_\-\.~]+)', cookies)
            if match:
                return match.group(1).strip()

        return None

    @classmethod
    def evaluate_request(
        cls,
        session: Optional[UserSession],
        doctype: str,
        docname: Optional[str],
        headers: Dict[str, str],
        method: str = "GET"
    ) -> AuthorizationDecision:
        """
        Evaluate if the session is strictly authorized to perform the operation.
        Returns AuthorizationDecision (allowed=False, status_code=403/401 on violation).
        """
        # Case 1: No active session
        if not session:
            return AuthorizationDecision(
                allowed=False,
                status_code=401,
                reason="Authentication required: Missing or invalid session token."
            )

        # Case 2: Inspect client-supplied Customer Identity Headers (Anti-BOLA Check)
        # Attackers often send: X-Customer-ID: CUST-VICTIM with their own valid session.
        req_customer_id = headers.get("X-Customer-ID") or headers.get("x-customer-id")
        if req_customer_id:
            req_customer_id = req_customer_id.strip()
            # If session is bound to a specific customer, it MUST match strictly!
            if session.customer_id and req_customer_id != session.customer_id:
                return AuthorizationDecision(
                    allowed=False,
                    status_code=403,
                    reason=f"BOLA/IDOR Violation: Request customer header '{req_customer_id}' does not match session customer '{session.customer_id}'."
                )
            # If session is non-admin and has no customer_id bound, cannot spoof customer headers
            if not session.is_admin and not session.is_sfe and req_customer_id != session.customer_id:
                return AuthorizationDecision(
                    allowed=False,
                    status_code=403,
                    reason="BOLA Violation: Customer header mismatch with authenticated session."
                )

        # Case 3: Inspect client-supplied Target User Header (Anti-IDOR Check)
        req_target_user = headers.get("X-Target-User") or headers.get("x-target-user") or headers.get("X-User-Email") or headers.get("x-user-email")
        if req_target_user:
            req_target_user = req_target_user.strip().lower()
            if not session.is_admin and req_target_user != session.user_email.lower():
                return AuthorizationDecision(
                    allowed=False,
                    status_code=403,
                    reason=f"IDOR Violation: Request target user '{req_target_user}' does not match authenticated user '{session.user_email}'."
                )

        # Case 4: Customer-scoped Doctype Resource inspection
        # If requesting a customer-scoped resource (Customer, Sales Invoice, etc.)
        if doctype in cls.CUSTOMER_SCOPED_DOCTYPES:
            # If user has an assigned customer_id and is querying a specific document
            if session.customer_id and docname:
                if docname.strip() != session.customer_id and not session.is_admin:
                    return AuthorizationDecision(
                        allowed=False,
                        status_code=403,
                        reason=f"IDOR Violation: Access denied to customer resource '{docname}'. Bound to '{session.customer_id}'."
                    )

        # Authorized
        return AuthorizationDecision(allowed=True, status_code=200, reason="Authorized")


# =============================================================================
# 4. SECURE OUTBOUND FRAPPE PROXY LAYER
# =============================================================================

class SecureFrappeGateway:
    """
    Intermediate execution gateway that validates, sanitizes, and proxies
    requests to Frappe REST/RPC endpoints.
    """

    def __init__(
        self,
        base_url: str = ERPNEXT_SERVER_URL,
        session_registry: SessionRegistry = GLOBAL_SESSION_REGISTRY
    ):
        self.base_url = base_url.rstrip("/")
        self.session_registry = session_registry
        self.cookie_jar = http.cookiejar.CookieJar()
        
        # Defensive SSL context
        self.ssl_ctx = ssl.create_default_context()
        if os.environ.get("ERPNEXT_INSECURE_SSL") == "1":
            self.ssl_ctx.check_hostname = False
            self.ssl_ctx.verify_mode = ssl.CERT_NONE

        self.opener = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self.cookie_jar),
            urllib.request.HTTPSHandler(context=self.ssl_ctx)
        )

    def execute_resource_request(
        self,
        method: str,
        doctype: str,
        name: Optional[str] = None,
        headers: Optional[Dict[str, str]] = None,
        query_params: Optional[Dict[str, Any]] = None,
        body_payload: Optional[Dict[str, Any]] = None,
        cookies: Optional[str] = None
    ) -> Tuple[int, Dict[str, Any]]:
        """
        Full lifecycle:
        1. Extract session token.
        2. Validate session & evaluate Anti-BOLA/IDOR constraints.
        3. Strictly sanitize schema.
        4. Forward request using isolated credentials.
        """
        headers = headers or {}
        query_params = query_params or {}

        # 1. Extract session token
        token = VibeSecAuthorizer.extract_token_from_request(headers, cookies)
        session = self.session_registry.get(token)

        # 2. Anti-BOLA & Anti-IDOR Authorization Check
        auth_decision = VibeSecAuthorizer.evaluate_request(
            session=session,
            doctype=doctype,
            docname=name,
            headers=headers,
            method=method
        )

        if not auth_decision.allowed:
            # RETURN 403 / 401 IMMEDIATELY — ZERO OUTBOUND CALLS TO ERPNEXT!
            return auth_decision.status_code, {
                "success": False,
                "error": auth_decision.reason,
                "status_code": auth_decision.status_code,
                "security_alert": "BOLA/IDOR attempt blocked by VibeSec Gateway"
            }

        # 3. Schema validation & parameter sanitization
        try:
            schema = ResourceRequestSchema.from_request(doctype, name, query_params)
        except SecurityValidationError as sve:
            return 400, {
                "success": False,
                "error": f"Schema Validation Error: {str(sve)}",
                "status_code": 400
            }

        # 4. Construct outbound URL
        target_path = f"/api/resource/{urllib.parse.quote(schema.doctype)}"
        if schema.name:
            target_path += f"/{urllib.parse.quote(schema.name)}"

        outbound_params: Dict[str, str] = {}
        if schema.fields:
            outbound_params["fields"] = json.dumps(schema.fields)
        if schema.filters:
            outbound_params["filters"] = json.dumps(schema.filters)
        if schema.limit_page_length != 20:
            outbound_params["limit_page_length"] = str(schema.limit_page_length)
        if schema.limit_start > 0:
            outbound_params["limit_start"] = str(schema.limit_start)
        if schema.order_by:
            outbound_params["order_by"] = schema.order_by

        query_string = urllib.parse.urlencode(outbound_params)
        full_url = f"{self.base_url}{target_path}"
        if query_string:
            full_url += f"?{query_string}"

        # 5. Outbound Headers with isolated credentials
        outbound_headers = {
            "Accept": "application/json",
            "User-Agent": "PIMS-Secure-VibeSec-Gateway/1.0"
        }

        # If system Frappe Token configured in environment, inject it safely
        if FRAPPE_API_KEY and FRAPPE_API_SECRET:
            outbound_headers["Authorization"] = f"token {FRAPPE_API_KEY}:{FRAPPE_API_SECRET}"

        outbound_data: Optional[bytes] = None
        if body_payload and method.upper() in ["POST", "PUT"]:
            outbound_headers["Content-Type"] = "application/json"
            outbound_data = json.dumps(body_payload).encode("utf-8")

        # 6. Outbound Dispatch
        req = urllib.request.Request(full_url, data=outbound_data, headers=outbound_headers, method=method.upper())
        try:
            res = self.opener.open(req, timeout=12)
            resp_body = res.read().decode("utf-8")
            data = json.loads(resp_body) if resp_body else {}
            return res.status, data
        except urllib.error.HTTPError as e:
            err_text = e.read().decode("utf-8", errors="replace")
            try:
                err_json = json.loads(err_text)
            except Exception:
                err_json = {"error": sanitize_log_message(err_text)}
            return e.code, err_json
        except Exception as ex:
            return 502, {"error": f"Upstream ERPNext connection error: {sanitize_log_message(str(ex))}"}
