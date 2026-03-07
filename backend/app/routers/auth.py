from fastapi import APIRouter, Request
from app.services.auth_service import auth_service

router = APIRouter(prefix="/api/auth", tags=["Auth"])

@router.get("/client_id")
async def get_client_id(request: Request):
    """Fetch or create a client_id for the current IP."""
    ip = auth_service.get_ip(request)
    client_id = auth_service.get_or_create_client_id(ip)
    return {"client_id": client_id}
