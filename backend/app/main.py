import os

if os.environ.get("ANTHROPIC_API_KEY_SECRET_ARN"):
    import boto3

    _sm = boto3.client("secretsmanager", region_name="us-east-2")
    for _key in [
        "ANTHROPIC_API_KEY",
        # "OPENAI_API_KEY",  # TODO: no secret created yet, not implemented
        "SUPABASE_URL",
        "SUPABASE_SECRET_KEY",
        # "LANGCHAIN_API_KEY",  # TODO: no secret created yet, not implemented
    ]:
        os.environ[_key] = _sm.get_secret_value(SecretId=os.environ[f"{_key}_SECRET_ARN"])["SecretString"]
else:
    from dotenv import load_dotenv
    load_dotenv()

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from mangum import Mangum

from app.api.main import api_router

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "https://buzz-buddy-pi.vercel.app"],
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

# @app.get("/health")
# def health():
#     return {"status": "ok"}

handler = Mangum(app)
