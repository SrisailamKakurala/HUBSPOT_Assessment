"""
Notion OAuth2 Integration Module
--------------------------------
Handles authorization, token exchange, and fetching Notion workspace items
for integration purposes.
"""

import json
import secrets
import base64
import asyncio
import urllib.parse
from typing import Any, Optional, Union

import httpx  # type: ignore
from fastapi import Request, HTTPException  # type: ignore
from fastapi.responses import HTMLResponse  # type: ignore

from integrations.integration_item import IntegrationItem
from utils.env import ENV
from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

# Environment configuration
CLIENT_ID: str = ENV.NOTION_CLIENT_ID
CLIENT_SECRET: str = ENV.NOTION_CLIENT_SECRET
REDIRECT_URI: str = ENV.NOTION_REDIRECT_URI

encoded_client_id_secret: str = base64.b64encode(
    f"{CLIENT_ID}:{CLIENT_SECRET}".encode()
).decode()

authorization_url: str = (
    f"https://api.notion.com/v1/oauth/authorize?"
    f"client_id={CLIENT_ID}&response_type=code&owner=user&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
)


async def authorize_notion(user_id: str, org_id: str) -> str:
    """
    Initiates the Notion OAuth2 authorization flow.

    Args:
        user_id (str): The user initiating the connection.
        org_id (str): The organization the integration belongs to.

    Returns:
        str: The Notion authorization URL.
    """
    state_data = {
        "state": secrets.token_urlsafe(32),
        "user_id": user_id,
        "org_id": org_id,
    }

    encoded_state = urllib.parse.quote(json.dumps(state_data))

    await add_key_value_redis(
        f"notion_state:{org_id}:{user_id}", json.dumps(state_data), expire=600
    )

    return f"{authorization_url}&state={encoded_state}"


async def oauth2callback_notion(request: Request) -> HTMLResponse:
    """
    Handles the OAuth2 callback from Notion after user authorization.

    Args:
        request (Request): The incoming FastAPI request.

    Returns:
        HTMLResponse: A response that closes the authorization popup.

    Raises:
        HTTPException: If state validation or token exchange fails.
    """
    if request.query_params.get("error"):
        raise HTTPException(
            status_code=400,
            detail=request.query_params.get("error_description", "OAuth error"),
        )

    code = request.query_params.get("code")
    encoded_state = request.query_params.get("state")

    if not code or not encoded_state:
        raise HTTPException(status_code=400, detail="Missing code or state parameter.")

    try:
        state_data = json.loads(urllib.parse.unquote(encoded_state))
    except (json.JSONDecodeError, ValueError):
        raise HTTPException(status_code=400, detail="Invalid state parameter.")

    original_state = state_data.get("state")
    user_id = state_data.get("user_id")
    org_id = state_data.get("org_id")

    if not all([original_state, user_id, org_id]):
        raise HTTPException(status_code=400, detail="Incomplete state data.")

    saved_state_json = await get_value_redis(f"notion_state:{org_id}:{user_id}")
    if not saved_state_json:
        raise HTTPException(status_code=400, detail="State not found in Redis.")

    try:
        saved_state = json.loads(saved_state_json)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Corrupted state in Redis.")

    if original_state != saved_state.get("state"):
        raise HTTPException(status_code=400, detail="State mismatch detected.")

    async with httpx.AsyncClient() as client:
        token_response, _ = await asyncio.gather(
            client.post(
                "https://api.notion.com/v1/oauth/token",
                data={
                    "grant_type": "authorization_code",
                    "code": code,
                    "redirect_uri": REDIRECT_URI,
                },
                headers={
                    "Authorization": f"Basic {encoded_client_id_secret}",
                    "Content-Type": "application/x-www-form-urlencoded",
                },
            ),
            delete_key_redis(f"notion_state:{org_id}:{user_id}"),
        )

    if token_response.status_code != 200:
        raise HTTPException(
            status_code=token_response.status_code, detail="Token exchange failed."
        )

    token_data = token_response.json()
    if "access_token" not in token_data:
        raise HTTPException(status_code=400, detail="No access token in response.")

    await add_key_value_redis(
        f"notion_credentials:{org_id}:{user_id}", json.dumps(token_data), expire=600
    )

    return HTMLResponse(
        content="""
        <html>
            <script>
                window.close();
            </script>
        </html>
        """
    )


async def get_notion_credentials(user_id: str, org_id: str) -> dict[str, Any]:
    """
    Retrieves stored Notion credentials from Redis.

    Args:
        user_id (str): The user ID.
        org_id (str): The organization ID.

    Returns:
        dict[str, Any]: The credentials dictionary.

    Raises:
        HTTPException: If credentials are missing or corrupted.
    """
    credentials = await get_value_redis(f"notion_credentials:{org_id}:{user_id}")
    if not credentials:
        raise HTTPException(status_code=400, detail="No credentials found.")

    try:
        parsed_credentials = json.loads(credentials)
    except json.JSONDecodeError:
        raise HTTPException(status_code=500, detail="Invalid credentials format.")

    await delete_key_redis(f"notion_credentials:{org_id}:{user_id}")
    return parsed_credentials


def _recursive_dict_search(data: Any, target_key: str) -> Optional[Any]:
    """
    Recursively searches for a key in a nested dictionary or list.

    Args:
        data (Any): The structure to search.
        target_key (str): The key to find.

    Returns:
        Optional[Any]: The value if found, otherwise None.
    """
    if isinstance(data, dict):
        if target_key in data:
            return data[target_key]
        for value in data.values():
            result = _recursive_dict_search(value, target_key)
            if result is not None:
                return result
    elif isinstance(data, list):
        for item in data:
            result = _recursive_dict_search(item, target_key)
            if result is not None:
                return result
    return None


def create_integration_item_metadata_object(
    response_json: dict[str, Any]
) -> IntegrationItem:
    """
    Creates an IntegrationItem object from a Notion API response.

    Args:
        response_json (dict): The Notion object metadata.

    Returns:
        IntegrationItem: A structured integration item.
    """
    properties = response_json.get("properties", {})
    name = _recursive_dict_search(properties, "content")

    parent_data = response_json.get("parent", {})
    parent_type = parent_data.get("type", "")
    parent_id = None if parent_type == "workspace" else parent_data.get(parent_type)

    if name is None:
        name = _recursive_dict_search(response_json, "content") or response_json.get(
            "object", "Unknown"
        )

    if isinstance(name, list) and name:
        name = (
            name[0].get("plain_text", "Untitled")
            if isinstance(name[0], dict)
            else str(name[0])
        )
    elif not isinstance(name, str):
        name = "Untitled"

    return IntegrationItem(
        id=response_json.get("id"),
        type=response_json.get("object", "unknown"),
        name=name,
        creation_time=response_json.get("created_time"),
        last_modified_time=response_json.get("last_edited_time"),
        parent_id=parent_id,
        parent_path_or_name=None,
        url=response_json.get("url"),
    )


async def get_items_notion(credentials: Union[str, dict[str, Any]]) -> list[IntegrationItem]:
    """
    Fetches all available Notion items for a user.

    Args:
        credentials (Union[str, dict]): The OAuth credentials.

    Returns:
        list[IntegrationItem]: A list of integration items.
    """
    if isinstance(credentials, str):
        credentials = json.loads(credentials)

    access_token = credentials.get("access_token")
    if not access_token:
        raise ValueError("No access token found in credentials.")

    async with httpx.AsyncClient() as client:
        try:
            response = await client.post(
                "https://api.notion.com/v1/search",
                headers={
                    "Authorization": f"Bearer {access_token}",
                    "Notion-Version": "2022-06-28",
                    "Content-Type": "application/json",
                },
                json={},
            )

            if response.status_code != 200:
                print(
                    f"Error fetching Notion items: {response.status_code} - {response.text}"
                )
                return []

            results = response.json().get("results", [])
            items: list[IntegrationItem] = []

            for result in results:
                try:
                    items.append(create_integration_item_metadata_object(result))
                except Exception as e:
                    print(f"Error processing Notion item: {e}")

            print("Fetched Notion items:")
            for item in items:
                print(f"ID: {item.id}")
                print(f"Name: {item.name}")
                print(f"Type: {item.type}")
                print(f"Created: {item.creation_time}")
                print(f"Modified: {item.last_modified_time}")
                print()

            return items

        except Exception as e:
            print(f"Exception while fetching Notion items: {e}")
            return []
