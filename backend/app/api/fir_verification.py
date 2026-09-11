"""FIR (First Information Report) verification admin endpoints."""
import logging
from datetime import datetime, timezone
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user, get_db
from app.crud.missing_person import get_report_by_id
from app.models.face_embedding import FaceEmbedding
from app.models.missing_person import MissingPerson
from app.models.user import User
from app.schemas.missing_person import MissingPersonResponse
from app.services.fir_validation import fir_validator

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/fir", tags=["fir-verification"])


# ── Request/Response Schemas ──

class FIRVerifyRequest(BaseModel):
    """Admin approves a FIR."""
    notes: Optional[str] = Field(None, max_length=500)


class FIRRejectRequest(BaseModel):
    """Admin rejects a FIR with reason."""
    reason: str = Field(..., min_length=5, max_length=500, description="Reason for rejection")


class FIRValidateResponse(BaseModel):
    """Response from FIR number format validation."""
    fir_number: str
    is_valid: bool
    message: str
    confidence: float
    pattern_matched: Optional[str] = None


# ── Endpoints ──

@router.get("/pending", response_model=list[MissingPersonResponse])
async def list_pending_fir_reviews(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    List all reports pending FIR verification.
    Used by admins/operators to review and approve/reject FIR details.
    """
    result = await db.execute(
        select(MissingPerson)
        .where(MissingPerson.status == "PENDING_FIR_REVIEW")
        .order_by(MissingPerson.created_at.asc())
    )
    reports = result.scalars().all()
    return list(reports)


@router.post("/verify/{report_id}", response_model=MissingPersonResponse)
async def verify_fir(
    report_id: UUID,
    body: Optional[FIRVerifyRequest] = None,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin approves a FIR — transitions report from PENDING_FIR_REVIEW to ACTIVE.
    Activates face embeddings for CCTV matching.
    """
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    
    if report.status != "PENDING_FIR_REVIEW":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is in '{report.status}' status. Only PENDING_FIR_REVIEW reports can be verified.",
        )
    
    # Update report status
    report.status = "ACTIVE"
    report.fir_status = "VERIFIED"
    report.fir_verified_by = current_user.id
    report.fir_verified_at = datetime.now(timezone.utc)
    report.updated_at = datetime.now(timezone.utc)
    
    # Ensure embeddings are active for CCTV matching
    await db.execute(
        update(FaceEmbedding)
        .where(FaceEmbedding.person_id == report_id)
        .values(is_active=True, updated_at=datetime.now(timezone.utc))
    )
    
    await db.flush()
    await db.refresh(report)
    
    logger.info(f"FIR verified for report {report_id} by user {current_user.id}")
    
    full_report = await get_report_by_id(db, report.id)
    return full_report or report


@router.post("/reject/{report_id}", response_model=MissingPersonResponse)
async def reject_fir(
    report_id: UUID,
    body: FIRRejectRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Admin rejects a FIR — transitions report to FIR_REJECTED.
    User will be notified to resubmit with correct FIR details.
    Deactivates face embeddings to stop CCTV matching.
    """
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Report not found",
        )
    
    if report.status not in ("PENDING_FIR_REVIEW", "ACTIVE"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Report is in '{report.status}' status. Cannot reject FIR for this report.",
        )
    
    # Update report status
    report.status = "FIR_REJECTED"
    report.fir_status = "REJECTED"
    report.fir_rejection_reason = body.reason
    report.fir_verified_by = current_user.id
    report.fir_verified_at = datetime.now(timezone.utc)
    report.updated_at = datetime.now(timezone.utc)
    
    # Deactivate embeddings to stop CCTV matching
    await db.execute(
        update(FaceEmbedding)
        .where(FaceEmbedding.person_id == report_id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    
    await db.flush()
    await db.refresh(report)
    
    logger.info(f"FIR rejected for report {report_id} by user {current_user.id}: {body.reason}")
    
    full_report = await get_report_by_id(db, report.id)
    return full_report or report


@router.get("/validate/{fir_number}", response_model=FIRValidateResponse)
async def validate_fir_number(
    fir_number: str,
    current_user: User = Depends(get_current_user),
):
    """
    Check if a FIR number matches known Indian police format patterns.
    Useful for real-time validation in the report form.
    """
    result = fir_validator.validate_fir_number(fir_number)
    return FIRValidateResponse(
        fir_number=fir_number,
        is_valid=result.is_valid,
        message=result.message,
        confidence=result.confidence,
    )
