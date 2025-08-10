"""
Airtable Integration Module
Handles OAuth 2.0 authorization, token exchange, and metadata retrieval from Airtable.
"""

import json
import secrets
import asyncio
import base64
import hashlib
from typing import Any, Optional

import requests
import httpx # type: ignore
from fastapi import Request, HTTPException # type: ignore
from fastapi.responses import HTMLResponse # type: ignore

from integrations.integration_item import IntegrationItem
from utils.env import ENV
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

# --- Config ---
CLIENT_ID: str = ENV.AIRTABLE_CLIENT_ID
CLIENT_SECRET: str = ENV.AIRTABLE_CLIENT_SECRET
REDIRECT_URI: str = ENV.AIRTABLE_REDIRECT_URI

encoded_client_id_secret: str = base64.b64encode(
    f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
).decode()
authorization_url: str = (
    f"https://airtable.com/oauth2/v1/authorize"
    f"?client_id={CLIENT_ID}"
    f"&response_type=code"
    f"&owner=user"
    f"&redirect_uri={REDIRECT_URI}"
)
scope: str = (
    "data.records:read data.records:write "
    "data.recordComments:read data.recordComments:write "
    "schema.bases:read schema.bases:write"
)


# --- OAuth Authorization ---
async def authorize_airtable(user_id: str, org_id: str) -> str:
    """
    Generate the Airtable OAuth authorization URL with PKCE and state parameters.

    Args:
        user_id (str): ID of the user initiating authorization.
        org_id (str): ID of the organization.

    Returns:
        str: Fully constructed Airtable authorization URL.
    """
    if not user_id or not org_id:
        raise HTTPException(status_code=400, detail="Missing user_id or org_id")

    # Prepare state
    state_data = {
        "state": secrets.token_urlsafe(32),
        "user_id": user_id,
        "org_id": org_id,
    }
    encoded_state = base64.urlsafe_b64encode(
        json.dumps(state_data).encode("utf-8")
    ).decode("utf-8")

    # Prepare PKCE
    code_verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(code_verifier.encode("utf-8"))
    code_challenge = (
        base64.urlsafe_b64encode(m.digest()).decode("utf-8").replace("=", "")
    )

    # Save temporary state in Redis
    await asyncio.gather(
        add_key_value_redis(
            f"airtable_state:{org_id}:{user_id}", json.dumps(state_data), expire=600
        ),
        add_key_value_redis(
            f"airtable_verifier:{org_id}:{user_id}", code_verifier, expire=600
        ),
    )

    # Build URL
    auth_url = (
        f"{authorization_url}"
        f"&state={encoded_state}"
        f"&code_challenge={code_challenge}"
        f"&code_challenge_method=S256"
        f"&scope={scope}"
    )
    return auth_url


# --- OAuth Callback ---
async def oauth2callback_airtable(request: Request) -> HTMLResponse:
    """
    Handle Airtable OAuth 2.0 callback and exchange code for access tokens.

    Args:
        request (Request): FastAPI request object containing query params.

    Returns:
        HTMLResponse: Script to close the OAuth popup window.
    """
    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail=request.query_params.get("error_description")
            or request.query_params.get("error"),
        )

    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")

    if not code or not encoded_state:
        raise HTTPException(status_code=400, detail="Missing code or state in callback")

    try:
        state_data = json.loads(
            base64.urlsafe_b64decode(encoded_state).decode("utf-8")
        )
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid state encoding")

    user_id = state_data.get("user_id")
    org_id = state_data.get("org_id")
    original_state = state_data.get("state")

    if not user_id or not org_id or not original_state:
        raise HTTPException(status_code=400, detail="Invalid state data")

    saved_state, code_verifier = await asyncio.gather(
        get_value_redis(f"airtable_state:{org_id}:{user_id}"),
        get_value_redis(f"airtable_verifier:{org_id}:{user_id}"),
    )

    if (
        not saved_state
        or not code_verifier
        or original_state != json.loads(saved_state).get("state")
    ):
        raise HTTPException(status_code=400, detail="State verification failed")

    async with httpx.AsyncClient() as client:
        try:
            response, _, _ = await asyncio.gather(
                client.post(
                    "https://airtable.com/oauth2/v1/token",
                    data={
                        "grant_type": "authorization_code",
                        "code": code,
                        "redirect_uri": REDIRECT_URI,
                        "client_id": CLIENT_ID,
                        "code_verifier": code_verifier.decode("utf-8"),
                    },
                    headers={
                        "Authorization": f"Basic {encoded_client_id_secret}",
                        "Content-Type": "application/x-www-form-urlencoded",
                    },
                ),
                delete_key_redis(f"airtable_state:{org_id}:{user_id}"),
                delete_key_redis(f"airtable_verifier:{org_id}:{user_id}"),
            )
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"Airtable token request failed: {e}")

    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Airtable token exchange failed: {response.text}",
        )

    await add_key_value_redis(
        f"airtable_credentials:{org_id}:{user_id}",
        json.dumps(response.json()),
        expire=600,
    )

    return HTMLResponse(
        content="<html><script>window.close();</script></html>",
        status_code=200,
    )


# --- Credential Retrieval ---
async def get_airtable_credentials(user_id: str, org_id: str) -> dict[str, Any]:
    """
    Retrieve stored Airtable OAuth credentials from Redis.

    Args:
        user_id (str): ID of the user.
        org_id (str): ID of the organization.

    Returns:
        dict: Airtable OAuth credentials.
    """
    credentials = await get_value_redis(f"airtable_credentials:{org_id}:{user_id}")
    if not credentials:
        raise HTTPException(status_code=404, detail="No Airtable credentials found")

    await delete_key_redis(f"airtable_credentials:{org_id}:{user_id}")

    try:
        return json.loads(credentials)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted Airtable credentials")


# --- Integration Item Creation ---
def create_integration_item_metadata_object(
    response_json: dict[str, Any],
    item_type: str,
    parent_id: Optional[str] = None,
    parent_name: Optional[str] = None,
) -> IntegrationItem:
    """
    Create an IntegrationItem object from Airtable API response.

    Args:
        response_json (dict): API response JSON.
        item_type (str): Type of item ("Base" or "Table").
        parent_id (Optional[str]): Parent ID if applicable.
        parent_name (Optional[str]): Parent name if applicable.

    Returns:
        IntegrationItem: Created integration item metadata.
    """
    parent_id = None if parent_id is None else f"{parent_id}_Base"
    return IntegrationItem(
        id=f"{response_json.get('id', '')}_{item_type}",
        name=response_json.get("name"),
        type=item_type,
        parent_id=parent_id,
        parent_path_or_name=parent_name,
    )


# --- Airtable API Fetching ---
def fetch_items(
    access_token: str,
    url: str,
    aggregated_response: list[dict[str, Any]],
    offset: Optional[str] = None,
) -> None:
    """
    Recursively fetch Airtable bases with pagination.

    Args:
        access_token (str): Airtable API access token.
        url (str): API endpoint URL.
        aggregated_response (list): List to store fetched items.
        offset (Optional[str]): Pagination offset.
    """
    params = {"offset": offset} if offset else {}
    headers = {"Authorization": f"Bearer {access_token}"}

    response = requests.get(url, headers=headers, params=params)
    if response.status_code != 200:
        raise HTTPException(
            status_code=response.status_code,
            detail=f"Airtable API request failed: {response.text}",
        )

    data = response.json()
    results = data.get("bases", [])
    next_offset = data.get("offset")

    aggregated_response.extend(results)

    if next_offset:
        fetch_items(access_token, url, aggregated_response, next_offset)


# --- Main Data Retrieval ---
async def get_items_airtable(credentials: str) -> list[IntegrationItem]:
    """
    Retrieve Airtable bases and tables from API using stored credentials.

    Args:
        credentials (str): JSON string containing access_token.

    Returns:
        list[IntegrationItem]: List of normalized integration items.
    """
    try:
        credentials_dict = json.loads(credentials)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid credentials format")

    access_token = credentials_dict.get("access_token")
    if not access_token:
        raise HTTPException(status_code=400, detail="Missing access token in credentials")

    bases_url = "https://api.airtable.com/v0/meta/bases"
    integration_items: list[IntegrationItem] = []
    base_responses: list[dict[str, Any]] = []

    fetch_items(access_token, bases_url, base_responses)

    for base in base_responses:
        integration_items.append(create_integration_item_metadata_object(base, "Base"))

        tables_url = f"https://api.airtable.com/v0/meta/bases/{base.get('id')}/tables"
        tables_response = requests.get(
            tables_url, headers={"Authorization": f"Bearer {access_token}"}
        )

        if tables_response.status_code == 200:
            tables_data = tables_response.json().get("tables", [])
            for table in tables_data:
                integration_items.append(
                    create_integration_item_metadata_object(
                        table, "Table", base.get("id"), base.get("name")
                    )
                )
        else:
            raise HTTPException(
                status_code=tables_response.status_code,
                detail=f"Failed to fetch tables: {tables_response.text}",
            )
            
    print("Fetched Airtable items:")
    for item in integration_items:
        print(f"ID: {item.id}")
        print(f"Name: {item.name}")
        print(f"Type: {item.type}")
        print(f"Parent Name: {item.parent_path_or_name}")
        print(f"Created: {item.creation_time}")
        print(f"Modified: {item.last_modified_time}")
        print()  # Empty line between items

    return integration_items
