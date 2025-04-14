from fastapi import APIRouter
from app.api.v1 import endpoints
from app.api.v1 import item_routes

api_router = APIRouter()
api_router.include_router(endpoints.router)
api_router.include_router(item_routes.router) 