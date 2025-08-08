# hubspot.py

import datetime
import json
import secrets
from fastapi import Request, HTTPException # type: ignore
from fastapi.responses import HTMLResponse # type: ignore
import httpx # type: ignore
import asyncio
import base64
import hashlib

import requests
from integrations.integration_item import IntegrationItem
from utils.env import ENV

from redis_client import add_key_value_redis, get_value_redis, delete_key_redis

CLIENT_ID = ENV.HUBSPOT_CLIENT_ID
CLIENT_SECRET = ENV.HUBSPOT_CLIENT_SECRET
REDIRECT_URI = ENV.HUBSPOT_REDIRECT_URI

encoded_client_id_secret = base64.b64encode(f'{CLIENT_ID}:{CLIENT_SECRET}'.encode()).decode()
authorization_url = f'https://hubspot.com/oauth2/v1/authorize?client_id={CLIENT_ID}&response_type=code&owner=user&redirect_uri=http%3A%2F%2Flocalhost%3A8000%2Fintegrations%2Fhubspot%2Foauth2callback'
scope = 'crm.objects.contacts.read crm.objects.contacts.write crm.schemas.contacts.read'

async def authorize_hubspot(user_id, org_id):
    state_data = {
        'state': secrets.token_urlsafe(32),
        'user_id': user_id,
        'org_id': org_id
    }
    encoded_state = json.dumps(state_data)

    code_verifier = secrets.token_urlsafe(32)
    m = hashlib.sha256()
    m.update(code_verifier.encode('utf-8'))
    code_challenge = base64.urlsafe_b64encode(m.digest()).decode('utf-8').replace('=', '')

    auth_url = f'{authorization_url}&state={encoded_state}&code_challenge={code_challenge}&code_challenge_method=S256&scope={scope}'
    await asyncio.gather(
        add_key_value_redis(f'hubspot_state:{org_id}:{user_id}', json.dumps(state_data), expire=600),
        add_key_value_redis(f'hubspot_verifier:{org_id}:{user_id}', code_verifier, expire=600),
    )

    return auth_url

async def oauth2callback_hubspot(request: Request):
    if request.query_params.get('error'):
        raise HTTPException(status_code=400, detail=request.query_params.get('error_description'))
    code = request.query_params.get('code')
    encoded_state = request.query_params.get('state')
    state_data = json.loads(base64.urlsafe_b64decode(encoded_state).decode('utf-8'))

    original_state = state_data.get('state')
    user_id = state_data.get('user_id')
    org_id = state_data.get('org_id')

    saved_state, code_verifier = await asyncio.gather(
        get_value_redis(f'hubspot_state:{org_id}:{user_id}'),
        get_value_redis(f'hubspot_verifier:{org_id}:{user_id}'),
    )

    if not saved_state or original_state != json.loads(saved_state).get('state'):
        raise HTTPException(status_code=400, detail='State does not match.')

    async with httpx.AsyncClient() as client:
        response, _, _ = await asyncio.gather(
            client.post(
                'https://hubspot.com/oauth2/v1/token',
                data={
                    'grant_type': 'authorization_code',
                    'code': code,
                    'redirect_uri': REDIRECT_URI,
                    'client_id': CLIENT_ID,
                    'code_verifier': code_verifier.decode('utf-8'),
                },
                headers={
                    'Authorization': f'Basic {encoded_client_id_secret}',
                    'Content-Type': 'application/x-www-form-urlencoded',
                }
            ),
            delete_key_redis(f'hubspot_state:{org_id}:{user_id}'),
            delete_key_redis(f'hubspot_verifier:{org_id}:{user_id}'),
        )

    await add_key_value_redis(f'hubspot_credentials:{org_id}:{user_id}', json.dumps(response.json()), expire=600)
    
    close_window_script = """
    <html>
        <script>
            window.close();
        </script>
    </html>
    """
    return HTMLResponse(content=close_window_script)

async def get_hubspot_credentials(user_id, org_id):
    credentials = await get_value_redis(f'hubspot_credentials:{org_id}:{user_id}')
    if not credentials:
        raise HTTPException(status_code=400, detail='No credentials found.')
    credentials = json.loads(credentials)
    await delete_key_redis(f'hubspot_credentials:{org_id}:{user_id}')

    return credentials

def create_integration_item_metadata_object(response_json: dict) -> IntegrationItem:
    """Creates IntegrationItem from a HubSpot contact object"""
    properties = response_json.get("properties", {})
    
    name = f"{properties.get('firstname', '')} {properties.get('lastname', '')}".strip()
    if not name:
        name = properties.get("email", "Unnamed Contact")

    return IntegrationItem(
        id=response_json.get("id"),
        type="Contact",
        name=name,
        creation_time=properties.get("createdate"),
        last_modified_time=properties.get("lastmodifieddate"),
        parent_id=None,
        parent_path_or_name=None,
        url=f"https://app.hubspot.com/contacts/{response_json.get('id')}",
    )

async def get_items_hubspot(credentials) -> list[IntegrationItem]:
    """Fetches HubSpot contacts and returns list of IntegrationItem objects"""
    credentials = json.loads(credentials)
    access_token = credentials.get("access_token")

    url = "https://api.hubapi.com/crm/v3/objects/contacts"
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
    }
    params = {
        "limit": 50,
        "properties": "firstname,lastname,email,createdate,lastmodifieddate",
    }

    list_of_integration_item_metadata = []
    has_more = True
    after = None

    while has_more:
        if after:
            params["after"] = after

        response = requests.get(url, headers=headers, params=params)
        if response.status_code != 200:
            print(f"Error fetching contacts: {response.status_code} - {response.text}")
            break

        data = response.json()
        contacts = data.get("results", [])
        for contact in contacts:
            list_of_integration_item_metadata.append(
                create_integration_item_metadata_object(contact)
            )

        paging = data.get("paging", {})
        next_page = paging.get("next", {})
        after = next_page.get("after")
        has_more = after is not None

    print("Fetched HubSpot contacts:")
    for item in list_of_integration_item_metadata:
        print(vars(item))  # Show each IntegrationItem's fields

    return list_of_integration_item_metadata