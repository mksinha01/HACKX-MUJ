"""Missing person reports API endpoints: Atomic multipart submission, photos, sightings, and timeline."""
import asyncio
import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional
from uuid import UUID, uuid4

import aiofiles
from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Query,
    UploadFile,
    status,
)
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.api.deps import get_current_user, get_db
from app.config import settings
from app.crud.missing_person import (
    create_report,
    get_report_by_id,
    list_all_reports,
    list_reports_by_user,
    update_report,
    update_report_status,
)
from app.crud.sighting import get_person_timeline, list_sightings_for_person
from app.models.face_embedding import FaceEmbedding
from app.models.missing_person import MissingPerson
from app.models.photo import Photo
from app.models.user import User
from app.schemas.missing_person import (
    MissingPersonCreate,
    MissingPersonListResponse,
    MissingPersonResponse,
    MissingPersonUpdate,
    PhotoResponse,
)
from app.schemas.photo import PhotoUploadResponse
from app.schemas.sighting import PersonTimeline, SightingResponse, TimelineEntry
from app.services.face_processing import process_person_photo
from app.utils.file_storage import save_upload_file

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])


async def _save_face_crop(cropped_bytes: bytes) -> str:
    """Saves cropped face bytes to uploads/faces/ and returns relative URL."""
    faces_dir = Path(settings.UPLOAD_DIR) / "faces"
    faces_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid4().hex}.jpg"
    filepath = faces_dir / filename
    async with aiofiles.open(filepath, "wb") as f:
        await f.write(cropped_bytes)
    return f"/uploads/faces/{filename}"


@router.post(
    "/",
    response_model=MissingPersonResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_missing_person_report(
    # Atomic multipart payload
    report_data: Optional[str] = Form(
        None,
        description="JSON string containing report metadata (MissingPersonCreate)",
    ),
    full_name: Optional[str] = Form(None),
    age: Optional[int] = Form(None),
    gender: Optional[str] = Form(None),
    height_cm: Optional[int] = Form(None),
    description: Optional[str] = Form(None),
    last_seen_location: Optional[str] = Form(None),
    last_seen_time: Optional[datetime] = Form(None),
    contact_info: Optional[str] = Form(None),
    # FIR fields — required
    fir_number: Optional[str] = Form(None, description="FIR number from police station"),
    fir_police_station: Optional[str] = Form(None, description="Police station name"),
    fir_date: Optional[datetime] = Form(None, description="Date FIR was filed"),
    photos: List[UploadFile] = File(
        default=[],
        description="1-5 photo files of the missing person",
    ),
    fir_document: Optional[UploadFile] = File(
        None,
        description="Scanned FIR document (PDF, JPEG, or PNG)",
    ),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Atomic multipart submission for creating a missing person report with FIR verification.
    Accepts metadata, photos, and FIR details in a single HTTP request.
    Performs face detection, landmark alignment, 512-D ArcFace embedding generation,
    and FIR validation (format check + police station cross-reference).
    
    Status lifecycle:
      PROCESSING → PENDING_FIR_REVIEW → ACTIVE (when FIR verified)
      PROCESSING → REJECTED_NO_FACE (no valid face detected)
      PROCESSING → FIR_REJECTED (invalid FIR details)
    """
    # 1. Parse report metadata
    if report_data:
        try:
            parsed = json.loads(report_data)
            create_payload = MissingPersonCreate(**parsed)
        except Exception as e:
            raise HTTPException(
                status_code=422,
                detail=f"Invalid report_data JSON format: {str(e)}",
            )
    elif full_name:
        create_payload = MissingPersonCreate(
            full_name=full_name,
            age=age,
            gender=gender,
            height_cm=height_cm,
            description=description,
            last_seen_location=last_seen_location,
            last_seen_time=last_seen_time,
            contact_info=contact_info,
            fir_number=fir_number or "",
            fir_police_station=fir_police_station or "",
            fir_date=fir_date,
        )
    else:
        raise HTTPException(
            status_code=422,
            detail="Missing report metadata (provide report_data JSON or individual form fields)",
        )

    # 2. Run FIR validation
    from app.services.fir_validation import fir_validator
    
    fir_doc_bytes = None
    fir_doc_filename = None
    if fir_document and fir_document.filename:
        fir_doc_bytes = await fir_document.read()
        fir_doc_filename = fir_document.filename
    
    fir_result = fir_validator.run_full_validation(
        fir_number=create_payload.fir_number,
        police_station=create_payload.fir_police_station,
        fir_date=create_payload.fir_date,
        document_bytes=fir_doc_bytes,
        document_filename=fir_doc_filename,
    )
    
    # Save FIR document if provided
    fir_doc_path = None
    if fir_doc_bytes and fir_doc_filename:
        await fir_document.seek(0)
        fir_doc_path = await save_upload_file(
            file=fir_document,
            subfolder="evidence",
            upload_dir=settings.UPLOAD_DIR,
        )

    # 3. Create base report with status PROCESSING
    report = await create_report(db, user_id=current_user.id, data=create_payload)
    
    # Set FIR fields on the report
    report.fir_number = create_payload.fir_number
    report.fir_police_station = create_payload.fir_police_station
    report.fir_date = create_payload.fir_date
    report.fir_document_path = fir_doc_path

    # Check if FIR was rejected at format level
    if fir_result["overall_status"] == "REJECTED":
        report.status = "FIR_REJECTED"
        report.fir_status = "REJECTED"
        report.fir_rejection_reason = fir_result["message"]
        await db.flush()
        await db.refresh(report)
        full_report = await get_report_by_id(db, report.id)
        return full_report or report

    # 4. Process photos if provided
    active_embeddings_count = 0

    for idx, photo_file in enumerate(photos):
        try:
            # Read photo content
            content = await photo_file.read()
            if not content:
                continue

            # Save original photo
            await photo_file.seek(0)
            photo_url = await save_upload_file(
                file=photo_file,
                subfolder="photos",
                upload_dir=settings.UPLOAD_DIR,
            )

            is_primary = idx == 0
            photo_record = Photo(
                id=uuid4(),
                person_id=report.id,
                original_path=photo_url,
                is_primary=is_primary,
                processing_status="PENDING",
            )
            db.add(photo_record)
            await db.flush()

            # Attempt face processing
            try:
                crop_bytes, normed_emb, det_score = await asyncio.to_thread(process_person_photo, content)
                face_url = await _save_face_crop(crop_bytes)

                photo_record.face_crop_path = face_url
                photo_record.processing_status = "SUCCESS"

                # Store embedding
                embedding_record = FaceEmbedding(
                    id=uuid4(),
                    person_id=report.id,
                    photo_id=photo_record.id,
                    embedding=normed_emb.tobytes(),
                    model_version="arcface_r50",
                    quality_score=det_score,
                    is_active=True,
                )
                db.add(embedding_record)
                active_embeddings_count += 1

            except Exception as fe:
                logger.warning(f"Face processing failed for photo {photo_file.filename}: {fe}")
                photo_record.processing_status = "NO_FACE"

            await db.flush()

        except Exception as pe:
            logger.error(f"Error handling photo upload {photo_file.filename}: {pe}")

    # 5. Determine final status based on face processing + FIR validation
    if photos:
        if active_embeddings_count > 0:
            # Face found — check FIR status
            if fir_result["auto_approved"]:
                report.status = "ACTIVE"
                report.fir_status = "VERIFIED"
            else:
                report.status = "PENDING_FIR_REVIEW"
                report.fir_status = "PENDING"
        else:
            report.status = "REJECTED_NO_FACE"
            report.fir_status = create_payload.fir_number and "PENDING" or "PENDING"
    else:
        # If no photos were attached yet, report remains in PROCESSING status
        report.status = "PROCESSING"

    await db.flush()
    await db.refresh(report)

    # Reload with photos
    full_report = await get_report_by_id(db, report.id)
    return full_report or report


@router.get("/", response_model=MissingPersonListResponse)
async def list_my_reports(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(20, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List reports created by current user with optional status filter and pagination."""
    items, total = await list_reports_by_user(
        db=db,
        user_id=current_user.id,
        page=page,
        per_page=limit,
        status_filter=status_filter,
    )

    return MissingPersonListResponse(
        items=items,
        total=total,
        page=page,
        per_page=limit,
    )


@router.get("/all", response_model=MissingPersonListResponse)
async def list_all_missing_persons(
    status_filter: Optional[str] = Query(None, alias="status"),
    page: int = Query(1, ge=1),
    limit: int = Query(50, ge=1, le=100),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all missing persons across users for dashboard overview. Requires authentication."""
    items, total = await list_all_reports(
        db=db,
        status_filter=status_filter,
        page=page,
        per_page=limit,
    )
    return MissingPersonListResponse(
        items=items,
        total=total,
        page=page,
        per_page=limit,
    )


@router.get("/{report_id}", response_model=MissingPersonResponse)
async def get_report_detail(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Retrieve full details of a specific report including photos. Requires authentication."""
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Missing person report not found",
        )
    return report


@router.put("/{report_id}", response_model=MissingPersonResponse)
async def update_report_details(
    report_id: UUID,
    data: MissingPersonUpdate,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Update metadata for an existing report."""
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Missing person report not found",
        )
    if report.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to modify this report",
        )

    updated = await update_report(db, report_id, data)
    return updated


@router.delete("/{report_id}", status_code=status.HTTP_200_OK)
async def close_missing_person_report(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Soft-delete / close a missing person report.
    Sets report status to CLOSED and deactivates all embeddings (is_active=False)
    so Edge Agents receive tombstones on incremental sync.
    """
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Missing person report not found",
        )
    if report.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to close this report",
        )

    # Set status CLOSED
    report.status = "CLOSED"
    report.updated_at = datetime.now(timezone.utc)

    # Deactivate embeddings for tombstone sync
    await db.execute(
        update(FaceEmbedding)
        .where(FaceEmbedding.person_id == report_id)
        .values(is_active=False, updated_at=datetime.now(timezone.utc))
    )
    await db.flush()

    return {"status": "success", "message": f"Report {report_id} closed."}


@router.post("/{report_id}/photos", response_model=PhotoResponse)
async def upload_additional_photo(
    report_id: UUID,
    file: UploadFile = File(...),
    is_primary: bool = Form(False),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload an additional photo to an existing report, performing face extraction."""
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Missing person report not found",
        )
    if report.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to add photos to this report",
        )

    content = await file.read()
    await file.seek(0)
    photo_url = await save_upload_file(
        file=file,
        subfolder="photos",
        upload_dir=settings.UPLOAD_DIR,
    )

    photo_record = Photo(
        id=uuid4(),
        person_id=report_id,
        original_path=photo_url,
        is_primary=is_primary,
        processing_status="PENDING",
    )
    db.add(photo_record)
    await db.flush()

    # Process face
    try:
        crop_bytes, normed_emb, det_score = await asyncio.to_thread(process_person_photo, content)
        face_url = await _save_face_crop(crop_bytes)

        photo_record.face_crop_path = face_url
        photo_record.processing_status = "SUCCESS"

        embedding_record = FaceEmbedding(
            id=uuid4(),
            person_id=report_id,
            photo_id=photo_record.id,
            embedding=normed_emb.tobytes(),
            model_version="arcface_r50",
            quality_score=det_score,
            is_active=True,
        )
        db.add(embedding_record)

        if report.status in ("PROCESSING", "REJECTED_NO_FACE"):
            report.status = "ACTIVE"

    except Exception as fe:
        logger.warning(f"Face processing failed: {fe}")
        photo_record.processing_status = "NO_FACE"

    await db.flush()
    await db.refresh(photo_record)
    return photo_record


@router.get("/{report_id}/sightings", response_model=List[SightingResponse])
async def get_report_sightings(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """List all sightings for a specific missing person. Requires authentication."""
    return await list_sightings_for_person(db, report_id)


@router.get("/{report_id}/timeline", response_model=PersonTimeline)
async def get_report_timeline(
    report_id: UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Get chronological sighting timeline ("last seen" tracking) across CCTV cameras.
    """
    report = await get_report_by_id(db, report_id)
    if not report:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Missing person report not found",
        )

    raw_entries = await get_person_timeline(db, report_id)
    entries = [
        TimelineEntry(
            sighting_id=UUID(e["sighting_id"]),
            camera_name=e["camera_name"],
            camera_location=e["camera_location"],
            latitude=e["latitude"],
            longitude=e["longitude"],
            detected_at=e["detected_at"],
            similarity_score=e["similarity_score"],
            status=e["status"],
        )
        for e in raw_entries
    ]

    last_camera = entries[-1].camera_name if entries else None
    last_time = entries[-1].detected_at if entries else None

    return PersonTimeline(
        person_id=report.id,
        person_name=report.full_name,
        entries=entries,
        last_seen_camera=last_camera,
        last_seen_time=last_time,
    )
