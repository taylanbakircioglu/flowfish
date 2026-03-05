"""Import router - placeholder"""
from fastapi import APIRouter, Depends
from utils.jwt_utils import require_permissions
router = APIRouter()

@router.post("/import")
async def import_data(current_user: dict = Depends(require_permissions("dependencies.export"))):
    return {"message": "Import - coming in Faz 2"}
