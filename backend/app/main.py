import os

if os.environ.get("ANTHROPIC_API_KEY_SECRET_ARN"):
    import boto3

    _sm = boto3.client("secretsmanager", region_name="us-east-2")
    for _key in [
        "ANTHROPIC_API_KEY",
        "OPENAI_API_KEY",
        "DATABASE_URL",
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        "LANGSMITH_API_KEY",
    ]:
        os.environ[_key] = _sm.get_secret_value(SecretId=os.environ[f"{_key}_SECRET_ARN"])["SecretString"]
else:
    from dotenv import load_dotenv
    load_dotenv()

    # Show app INFO logs in the local console. Lambda configures its own
    # logging (JSON at INFO, set in the CDK stack).
    import logging
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.main import api_router
from app.errors import register_error_handlers

app = FastAPI()

register_error_handlers(app)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://buzz-buddy.app",
        "https://www.buzz-buddy.app",
        "https://buzz-buddy-pi.vercel.app",
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

handler = Mangum(app)
