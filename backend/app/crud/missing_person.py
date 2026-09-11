"""CRUD operations for missing_persons table."""
from typing import List, Optional
from uuid import UUID

from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.missing_person import MissingPerson
from app.schemas.missing_person import MissingPersonCreate, MissingPersonUpdate


# ── Missing Persons ──

async def create_report(
    db: AsyncSession, user_id: UUID, data: MissingPersonCreate
) -> MissingPerson:
    """Create a new missing person report. Status starts as PROCESSING."""
    person = MissingPerson(user_id=user_id, **data.model_dump())
    db.add(person)
    await db.flush()
    await db.refresh(person)
    return person


async def get_report_by_id(db: AsyncSession, report_id: UUID) -> Optional[MissingPerson]:
    """Get a single report with photos loaded."""
    result = await db.execute(
        select(MissingPerson)
        .options(selectinload(MissingPerson.photos))
        .where(MissingPerson.id == report_id)
    )
    return result.scalar_one_or_none()


async def list_reports_by_user(
    db: AsyncSession, user_id: UUID, page: int = 1, per_page: int = 20,
    status_filter: Optional[str] = None,
) -> tuple[List[MissingPerson], int]:
    """List reports for a specific user with pagination and optional status filter."""
    # Build base filters
    base_filter = [MissingPerson.user_id == user_id]
    if status_filter:
        base_filter.append(MissingPerson.status == status_filter)

    # Count total (with filter applied)
    count_stmt = select(func.count(MissingPerson.id)).where(*base_filter)
    count_result = await db.execute(count_stmt)
    total = count_result.scalar_one()

    # Fetch page (with filter applied)
    offset = (page - 1) * per_page
    result = await db.execute(
        select(MissingPerson)
        .options(selectinload(MissingPerson.photos))
        .where(*base_filter)
        .order_by(MissingPerson.created_at.desc())
        .offset(offset)
        .limit(per_page)
    )
    items = list(result.scalars().all())
    return items, total


async def list_all_reports(
    db: AsyncSession, status_filter: Optional[str] = None, page: int = 1, per_page: int = 50
) -> tuple[List[MissingPerson], int]:
    """List all reports across users with optional status filter."""
    stmt = select(MissingPerson).options(selectinload(MissingPerson.photos))
    count_stmt = select(func.count(MissingPerson.id))
    if status_filter:
        stmt = stmt.where(MissingPerson.status == status_filter)
        count_stmt = count_stmt.where(MissingPerson.status == status_filter)

    count_res = await db.execute(count_stmt)
    total = count_res.scalar_one()

    offset = (page - 1) * per_page
    result = await db.execute(
        stmt.order_by(MissingPerson.created_at.desc()).offset(offset).limit(per_page)
    )
    items = list(result.scalars().all())
    return items, total


async def list_active_reports(db: AsyncSession) -> List[MissingPerson]:
    """Get all ACTIVE reports (those being monitored on CCTV)."""
    result = await db.execute(
        select(MissingPerson)
        .where(MissingPerson.status == "ACTIVE")
        .order_by(MissingPerson.created_at.desc())
    )
    return list(result.scalars().all())


async def update_report(
    db: AsyncSession, report_id: UUID, data: MissingPersonUpdate
) -> Optional[MissingPerson]:
    """Update report fields."""
    person = await get_report_by_id(db, report_id)
    if not person:
        return None
    update_data = data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(person, field, value)
    await db.flush()
    await db.refresh(person)
    return person


async def update_report_status(
    db: AsyncSession, report_id: UUID, status: str
) -> Optional[MissingPerson]:
    """Change report status (PROCESSING → ACTIVE → FOUND/CLOSED)."""
    person = await get_report_by_id(db, report_id)
    if not person:
        return None
    person.status = status
    await db.flush()
    return person
