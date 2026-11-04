from fastapi import APIRouter

from app.api.routes import chat, admin

api_router = APIRouter()
api_router.include_router(chat.router)
api_router.include_router(admin.router)