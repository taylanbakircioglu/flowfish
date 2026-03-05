"""Anomalies router - placeholder"""
from fastapi import APIRouter, Depends
from utils.jwt_utils import require_permissions
router = APIRouter()

@router.get("/anomalies")
async def get_anomalies(current_user: dict = Depends(require_permissions("anomalies.view"))):
    return {"message": "Anomaly detection - coming in Faz 2"}
