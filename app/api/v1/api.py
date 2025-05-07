from fastapi import APIRouter
from app.api.v1 import endpoints
from app.api.v1 import item_routes
from app.api.dispatch import router as dispatch_router

api_router = APIRouter()
api_router.include_router(endpoints.router)
api_router.include_router(item_routes.router)
api_router.include_router(dispatch_router, prefix="/dispatch", tags=["dispatch"]) 