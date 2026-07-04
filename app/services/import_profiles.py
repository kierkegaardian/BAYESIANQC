from __future__ import annotations

from datetime import datetime, timezone
from fnmatch import fnmatch
from pathlib import Path
from typing import Optional

from fastapi import HTTPException
from sqlmodel import Session, col, select

from app.import_db_models import ParserProfile
from app.import_models import ParserProfileIn, ParserProfileOut, ParserProfileStatus, ParserProfileUpdate
from app.rbac import UserContext
from app.storage import record_audit


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _clean_extensions(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        ext = value.strip().lower()
        if not ext:
            continue
        cleaned.append(ext if ext.startswith(".") else f".{ext}")
    return cleaned


def profile_out(profile: ParserProfile) -> ParserProfileOut:
    if profile.id is None:
        raise RuntimeError("Parser profile missing id")
    return ParserProfileOut(**profile.model_dump())


def list_profiles(session: Session, status: Optional[ParserProfileStatus]) -> list[ParserProfileOut]:
    query = select(ParserProfile).order_by(col(ParserProfile.name).asc(), col(ParserProfile.version).desc())
    if status is not None:
        query = query.where(ParserProfile.status == status)
    return [profile_out(row) for row in session.exec(query).all()]


def get_profile(session: Session, profile_id: int) -> ParserProfile:
    profile = session.exec(select(ParserProfile).where(ParserProfile.id == profile_id)).first()
    if profile is None:
        raise HTTPException(status_code=404, detail="Parser profile not found")
    return profile


def create_profile(session: Session, payload: ParserProfileIn, user: UserContext) -> ParserProfileOut:
    latest = session.exec(
        select(ParserProfile.version)
        .where(ParserProfile.name == payload.name)
        .order_by(col(ParserProfile.version).desc())
    ).first()
    profile = ParserProfile(
        name=payload.name,
        version=(latest or 0) + 1,
        profile_type=payload.profile_type,
        status=payload.status,
        source_id=payload.source_id,
        instrument=payload.instrument,
        file_extensions=_clean_extensions(payload.file_extensions),
        filename_patterns=payload.filename_patterns,
        signature=payload.signature,
        config=payload.config,
        created_by=user.actor,
        updated_by=user.actor,
    )
    session.add(profile)
    session.flush()
    out = profile_out(profile)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="create_parser_profile",
        entity_type="parser_profile",
        entity_id=str(out.id),
        before=None,
        after=out.model_dump(mode="json"),
        reason=None,
        commit=False,
    )
    session.commit()
    return out


def update_profile(session: Session, profile_id: int, payload: ParserProfileUpdate, user: UserContext) -> ParserProfileOut:
    current = get_profile(session, profile_id)
    before = profile_out(current).model_dump(mode="json")
    data = payload.model_dump(exclude_unset=True)
    reason = data.pop("reason", None)
    next_version = (
        session.exec(
            select(ParserProfile.version)
            .where(ParserProfile.name == current.name)
            .order_by(col(ParserProfile.version).desc())
        ).first()
        or current.version
    ) + 1
    merged = current.model_dump()
    merged.update(data)
    profile = ParserProfile(
        name=merged["name"],
        version=next_version,
        profile_type=merged["profile_type"],
        status=merged["status"],
        source_id=merged.get("source_id"),
        instrument=merged.get("instrument"),
        file_extensions=_clean_extensions(merged.get("file_extensions") or []),
        filename_patterns=merged.get("filename_patterns") or [],
        signature=merged.get("signature"),
        config=merged.get("config") or {},
        created_by=current.created_by,
        created_at=current.created_at,
        updated_at=utcnow(),
        updated_by=user.actor,
    )
    session.add(profile)
    session.flush()
    out = profile_out(profile)
    record_audit(
        session=session,
        actor=user.actor,
        actor_role=user.role,
        api_key_id=user.api_key_id,
        action="update_parser_profile",
        entity_type="parser_profile",
        entity_id=str(out.id),
        before=before,
        after=out.model_dump(mode="json"),
        reason=reason,
        commit=False,
    )
    session.commit()
    return out


def select_profile(
    session: Session,
    *,
    filename: str,
    source_id: Optional[str],
    explicit_profile_id: Optional[int],
    header_text: str,
) -> ParserProfile:
    if explicit_profile_id is not None:
        return get_profile(session, explicit_profile_id)
    ext = Path(filename).suffix.lower()
    profiles = session.exec(
        select(ParserProfile)
        .where(ParserProfile.status == ParserProfileStatus.ACTIVE)
        .order_by(col(ParserProfile.version).desc())
    ).all()
    best: tuple[int, ParserProfile] | None = None
    for profile in profiles:
        if profile.source_id and source_id and profile.source_id != source_id:
            continue
        if profile.source_id and source_id is None:
            continue
        score = 0
        if profile.source_id and profile.source_id == source_id:
            score += 4
        if ext and ext in profile.file_extensions:
            score += 2
        if any(fnmatch(filename, pattern) for pattern in profile.filename_patterns):
            score += 3
        if profile.signature:
            if profile.signature not in header_text:
                continue
            score += 4
        if score and (best is None or score > best[0]):
            best = (score, profile)
    if best is None:
        raise HTTPException(status_code=422, detail="No active parser profile matched the uploaded file")
    return best[1]
