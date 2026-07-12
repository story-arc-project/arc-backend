from fastapi import APIRouter

admin_router = APIRouter()

@admin_router.get("/status")
async def admin_status():
    return {"status": "ok", "message": "Admin route is accessible."}