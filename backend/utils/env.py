from dotenv import load_dotenv
import os

load_dotenv()

class EnvironmentVariables:
    HUBSPOT_CLIENT_ID = os.getenv("HUBSPOT_CLIENT_ID")
    HUBSPOT_CLIENT_SECRET = os.getenv("HUBSPOT_CLIENT_SECRET")
    HUBSPOT_REDIRECT_URI = os.getenv("HUBSPOT_REDIRECT_URI")
    REDIS_HOST = os.getenv("REDIS_HOST")
    REDIS_PORT = os.getenv("REDIS_PORT")

ENV = EnvironmentVariables()
