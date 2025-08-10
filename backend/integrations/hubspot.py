"""
HubSpot Integration Module

Responsibilities:
- Build HubSpot OAuth2 authorization URL (with PKCE + state)
- Handle OAuth callback and exchange authorization code for tokens
- Store temporary state / verifiers in Redis
- Persist retrieved credentials in Redis (short TTL)
- Fetch HubSpot contacts and normalize into IntegrationItem objects
"""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
import asyncio
import logging
import urllib.parse
from typing import Any, Dict, List, Optional

import httpx # type: ignore
from fastapi import HTTPException, Request # type: ignore 
from fastapi.responses import HTMLResponse # type: ignore

from integrations.integration_item import IntegrationItem
from utils.env import ENV
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# --- Configuration ---
CLIENT_ID: str = ENV.HUBSPOT_CLIENT_ID
CLIENT_SECRET: str = ENV.HUBSPOT_CLIENT_SECRET
REDIRECT_URI: str = ENV.HUBSPOT_REDIRECT_URI

if not CLIENT_ID or not CLIENT_SECRET or not REDIRECT_URI:
    logger.warning("HubSpot ENV variables may be missing (CLIENT_ID/CLIENT_SECRET/REDIRECT_URI)")

# Base authorization URL (HubSpot region-agnostic endpoint)
# We'll URL-encode the redirect_uri and state when building the final URL
BASE_AUTH_URL = "https://app.hubspot.com/oauth/authorize"

# Scopes required for contacts + minimal platform access. Adjust if you need other scopes.
SCOPE = "crm.objects.contacts.read crm.objects.contacts.write crm.schemas.companies.read oauth"

# Token endpoint
TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"

# Redis key patterns
STATE_KEY = "hubspot_state:{org_id}:{user_id}"
VERIFIER_KEY = "hubspot_verifier:{org_id}:{user_id}"
CREDENTIALS_KEY = "hubspot_credentials:{org_id}:{user_id}"

# TTL for temporary data (seconds)
TEMP_TTL_SECONDS = 600


# ---------------------------
# Authorization (start flow)
# ---------------------------
async def authorize_hubspot(user_id: str, org_id: str) -> str:
    """
    Build a HubSpot OAuth2 authorization URL (PKCE + state), store state & verifier in Redis.

    Args:
        user_id: application user id initiating the flow
        org_id: organization id

    Returns:
        authorization URL (str) to redirect the user to
    """
    if not user_id or not org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or org_id")

    # state protects against CSRF - make it opaque and include user context
    state_data = {"state": secrets.token_urlsafe(32), "user_id": user_id, "org_id": org_id}
    # store state as JSON in redis; we will URL-encode when embedding in the auth URL
    encoded_state = base64.urlsafe_b64encode(json.dumps(state_data).encode("utf-8")).decode("utf-8").rstrip("=")

    # PKCE: code_verifier (random string 43-128 chars), and code_challenge derived with SHA256
    code_verifier = secrets.token_urlsafe(64)  # usually between 43 and 128 characters
    sha = hashlib.sha256()
    sha.update(code_verifier.encode("utf-8"))
    code_challenge = base64.urlsafe_b64encode(sha.digest()).decode("utf-8").rstrip("=")

    # Save state and verifier in Redis (temporary)
    try:
        await asyncio.gather(
            add_key_value_redis(STATE_KEY.format(org_id=org_id, user_id=user_id), json.dumps(state_data), expire=TEMP_TTL_SECONDS),
            add_key_value_redis(VERIFIER_KEY.format(org_id=org_id, user_id=user_id), code_verifier, expire=TEMP_TTL_SECONDS),
        )
    except Exception as e:
        logger.exception("Failed to save state/verifier to Redis: %s", e)
        raise HTTPException(status_code=500, detail="Internal error saving oauth state")

    # Build the authorization URL
    q = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPE,
        "state": encoded_state,
        "response_type": "code",
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    auth_url = f"{BASE_AUTH_URL}?{urllib.parse.urlencode(q, safe=' ')}"
    # urlencode will convert spaces to + by default; HubSpot accepts either; we can replace pluses with %20
    auth_url = auth_url.replace("+", "%20")
    logger.debug("Generated HubSpot auth URL for user=%s org=%s", user_id, org_id)
    return auth_url


# ---------------------------
# OAuth callback (exchange)
# ---------------------------
async def oauth2callback_hubspot(request: Request) -> HTMLResponse:
    """
    Exchange the authorization code returned by HubSpot for tokens and store them in Redis.

    Args:
        request: FastAPI request that includes 'code' and 'state' query params

    Returns:
        HTMLResponse that closes the popup window
    """
    if request.query_params.get("error"):
        detail = request.query_params.get("error_description") or request.query_params.get("error")
        raise HTTPException(status_code=400, detail=detail)

    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")
    if not code or not encoded_state:
        raise HTTPException(status_code=400, detail="Missing 'code' or 'state' in callback")

    # Decode state from URL-safe base64 (handle missing padding)
    try:
        padded = encoded_state + "=" * (-len(encoded_state) % 4)
        decoded_state_json = base64.urlsafe_b64decode(padded).decode("utf-8")
        state_data = json.loads(decoded_state_json)
    except Exception as exc:
        logger.exception("Invalid state param: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid state parameter")

    user_id = state_data.get("user_id")
    org_id = state_data.get("org_id")
    original_state = state_data.get("state")

    if not (user_id and org_id and original_state):
        raise HTTPException(status_code=400, detail="Invalid state payload")

    # Retrieve saved state & verifier from Redis
    try:
        saved_state_raw, code_verifier = await asyncio.gather(
            get_value_redis(STATE_KEY.format(org_id=org_id, user_id=user_id)),
            get_value_redis(VERIFIER_KEY.format(org_id=org_id, user_id=user_id)),
        )
    except Exception as e:
        logger.exception("Redis read error: %s", e)
        raise HTTPException(status_code=500, detail="Internal error reading state")

    if not saved_state_raw or not code_verifier:
        raise HTTPException(status_code=400, detail="State or PKCE verifier missing or expired")

    try:
        saved_state = json.loads(saved_state_raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted saved state")

    if original_state != saved_state.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch")

    # Exchange code for tokens
    token_payload = {
        "grant_type": "authorization_code",
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "code": code,
        "code_verifier": code_verifier,
    }

    # Always attempt token exchange and then clean up the temporary Redis keys
    token_response = None
    try:
        async with httpx.AsyncClient(timeout=15.0) as client:
            token_response = await client.post(TOKEN_URL, data=token_payload, headers={"Content-Type": "application/x-www-form-urlencoded"})
    except httpx.RequestError as e:
        logger.exception("Token exchange request failed: %s", e)
        # ensure we still delete the temporary keys below
        raise HTTPException(status_code=502, detail="Failed to reach HubSpot token endpoint")
    finally:
        # Remove temporary objects from Redis (best-effort)
        try:
            await asyncio.gather(
                delete_key_redis(STATE_KEY.format(org_id=org_id, user_id=user_id)),
                delete_key_redis(VERIFIER_KEY.format(org_id=org_id, user_id=user_id)),
            )
        except Exception:
            logger.exception("Failed to delete temp keys from Redis")

    # Check response
    if token_response is None or token_response.status_code != 200:
        text = token_response.text if token_response is not None else "no response"
        logger.error("HubSpot token exchange failed: status=%s body=%s", getattr(token_response, "status_code", None), text)
        raise HTTPException(status_code=token_response.status_code if token_response is not None else 502, detail=f"Token exchange failed: {text}")

    try:
        token_data = token_response.json()
    except Exception as e:
        logger.exception("Invalid token response JSON: %s", e)
        raise HTTPException(status_code=500, detail="Invalid token response format")

    if "access_token" not in token_data:
        logger.error("Token response missing access_token: %s", token_data)
        raise HTTPException(status_code=400, detail="Token response missing access_token")

    # Store credentials in Redis for the frontend to pick up (short TTL)
    try:
        await add_key_value_redis(CREDENTIALS_KEY.format(org_id=org_id, user_id=user_id), json.dumps(token_data), expire=TEMP_TTL_SECONDS)
    except Exception as e:
        logger.exception("Failed to save credentials to Redis: %s", e)
        raise HTTPException(status_code=500, detail="Failed to persist credentials")

    # Close popup (frontend monitors closure to continue)
    return HTMLResponse(content="<html><script>window.close();</script></html>", status_code=200)


# ---------------------------
# Credential retrieval
# ---------------------------
async def get_hubspot_credentials(user_id: str, org_id: str) -> Dict[str, Any]:
    """
    Return the cached HubSpot credentials (and delete them from Redis).

    Args:
        user_id: user id
        org_id: organization id

    Returns:
        Parsed credentials dict
    """
    try:
        raw = await get_value_redis(CREDENTIALS_KEY.format(org_id=org_id, user_id=user_id))
    except Exception as e:
        logger.exception("Redis read error: %s", e)
        raise HTTPException(status_code=500, detail="Internal error reading credentials")

    if not raw:
        raise HTTPException(status_code=404, detail="No credentials found")

    try:
        credentials = json.loads(raw)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted credentials in storage")

    # delete the stored item (one-time retrieval pattern)
    try:
        await delete_key_redis(CREDENTIALS_KEY.format(org_id=org_id, user_id=user_id))
    except Exception:
        logger.exception("Failed to delete credentials from Redis")

    return credentials


# ---------------------------
# Normalizer: HubSpot contact -> IntegrationItem
# ---------------------------
def create_integration_item_metadata_object(response_json: Dict[str, Any]) -> IntegrationItem:
    """
    Normalize a HubSpot contact JSON object into IntegrationItem.

    Args:
        response_json: single contact object returned by HubSpot's CRM API

    Returns:
        IntegrationItem
    """
    properties = response_json.get("properties", {}) or {}

    firstname = properties.get("firstname", "")
    lastname = properties.get("lastname", "")
    email = properties.get("email", "")
    name = (f"{firstname} {lastname}".strip()) or email or "Unnamed Contact"

    # HubSpot stores dates as epoch ms strings or ISO depending on endpoint/config - leave as-is
    created = properties.get("createdate")
    modified = properties.get("lastmodifieddate")

    return IntegrationItem(
        id=str(response_json.get("id")),
        type="Contact",
        name=name,
        creation_time=created,
        last_modified_time=modified,
        parent_id=None,
        parent_path_or_name=None,
        url=None,
    )


# ---------------------------
# Fetch HubSpot items (contacts)
# ---------------------------
async def get_items_hubspot(credentials: Any) -> List[IntegrationItem]:
    """
    Fetch HubSpot contacts using provided credentials (access_token).

    Args:
        credentials: dict or JSON string that contains access_token

    Returns:
        list of IntegrationItem
    """
    # Accept either string or dict
    if isinstance(credentials, str):
        try:
            credentials = json.loads(credentials)
        except json.JSONDecodeError:
            raise HTTPException(status_code=400, detail="Invalid credentials JSON")

    access_token = credentials.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access_token in credentials")

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {"Authorization": f"Bearer {access_token}"}
    params: Dict[str, Any] = {"limit": 100, "properties": "firstname,lastname,email,createdate,lastmodifieddate"}

    items: List[IntegrationItem] = []
    after: Optional[str] = None
    more = True

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            while more:
                if after:
                    params["after"] = after

                resp = await client.get(url, headers=headers, params=params)

                # handle forbidden (usually missing scope) explicitly
                if resp.status_code == 403:
                    logger.warning("HubSpot API returned 403: check scopes required: %s", SCOPE)
                    raise HTTPException(status_code=403, detail="Missing required HubSpot scopes")

                if resp.status_code != 200:
                    logger.error("HubSpot API error: status=%s body=%s", resp.status_code, resp.text)
                    raise HTTPException(status_code=502, detail=f"HubSpot API error: {resp.status_code}")

                data = resp.json()
                results = data.get("results", [])
                for contact in results:
                    try:
                        items.append(create_integration_item_metadata_object(contact))
                    except Exception:
                        logger.exception("Failed to normalize contact: %s", contact)

                # pagination
                paging = data.get("paging", {})
                next_page = paging.get("next", {})
                after = next_page.get("after")
                more = bool(after)
    except httpx.RequestError as e:
        logger.exception("HTTP request error while fetching HubSpot contacts: %s", e)
        raise HTTPException(status_code=502, detail="Network error calling HubSpot API")

    logger.info("Fetched %d HubSpot contacts", len(items))
    
    print("Fetched HubSpot contacts:")
    for item in items:
        print(f"ID: {item.id}")
        print(f"Name: {item.name}")
        print(f"Type: {item.type}")
        print(f"Created: {item.creation_time}")
        print(f"Modified: {item.last_modified_time}")
        print()  # Empty line between contacts
        
    return items
