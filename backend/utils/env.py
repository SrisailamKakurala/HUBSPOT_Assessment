from dotenv import load_dotenv
import os

load_dotenv()

class EnvironmentVariables:
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = os.getenv("REDIS_PORT")
    HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
    HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
    HUBSPOT_REDIRECT_URI = os.getenv("HUBSPOT_REDIRECT_URI")
    AIRTABLE_CLIENT_ID = os.getenv("AIRTABLE_CLIENT_ID")
    AIRTABLE_CLIENT_SECRET = os.getenv("AIRTABLE_CLIENT_SECRET")
    AIRTABLE_REDIRECT_URI = os.getenv("AIRTABLE_REDIRECT_URI")
    NOTION_CLIENT_ID = os.getenv("NOTION_CLIENT_ID")
    NOTION_CLIENT_SECRET = os.getenv("NOTION_CLIENT_SECRET")
    NOTION_REDIRECT_URI = os.getenv("NOTION_REDIRECT_URI")

ENV = EnvironmentVariables()
