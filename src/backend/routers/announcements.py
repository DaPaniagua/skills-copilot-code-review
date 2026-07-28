"""
Announcement endpoints for the High School Management System API
"""

from fastapi import APIRouter, HTTPException, Query
from typing import Optional, List, Dict, Any
from pydantic import BaseModel
from bson import ObjectId
from datetime import date

from ..database import announcements_collection, teachers_collection

router = APIRouter(
    prefix="/announcements",
    tags=["announcements"]
)


class AnnouncementCreate(BaseModel):
    message: str
    expiration_date: str  # ISO date string YYYY-MM-DD
    start_date: Optional[str] = None  # ISO date string YYYY-MM-DD (optional)


class AnnouncementUpdate(BaseModel):
    message: Optional[str] = None
    expiration_date: Optional[str] = None
    start_date: Optional[str] = None


def serialize_announcement(ann: dict) -> dict:
    """Convert MongoDB document to JSON-serializable dict"""
    ann["id"] = str(ann["_id"])
    del ann["_id"]
    return ann


def is_active(ann: dict) -> bool:
    """Determine if an announcement is currently active"""
    today = date.today().isoformat()
    if ann.get("expiration_date", "") < today:
        return False
    start = ann.get("start_date")
    if start and start > today:
        return False
    return True


def _require_teacher(teacher_username: str):
    """Validate that the requesting user exists. Raises 401 if not found."""
    teacher = teachers_collection.find_one({"_id": teacher_username})
    if not teacher:
        raise HTTPException(status_code=401, detail="Authentication required")
    return teacher


@router.get("/active", response_model=List[Dict[str, Any]])
def get_active_announcements() -> List[Dict[str, Any]]:
    """
    Get all currently active announcements (public endpoint).

    An announcement is active when:
    - Its expiration_date is today or in the future
    - Its start_date is absent, null, or today/in the past
    """
    today = date.today().isoformat()
    query = {
        "expiration_date": {"$gte": today},
        "$or": [
            {"start_date": None},
            {"start_date": {"$exists": False}},
            {"start_date": {"$lte": today}},
        ],
    }
    return [serialize_announcement(a) for a in announcements_collection.find(query)]


@router.get("", response_model=List[Dict[str, Any]])
def get_all_announcements(
    teacher_username: str = Query(..., description="Authenticated teacher username")
) -> List[Dict[str, Any]]:
    """
    Get all announcements including expired ones.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)
    result = []
    for ann in announcements_collection.find():
        serialized = serialize_announcement(ann)
        serialized["is_active"] = is_active(serialized)
        result.append(serialized)
    return result


@router.post("", response_model=Dict[str, Any])
def create_announcement(
    body: AnnouncementCreate,
    teacher_username: str = Query(..., description="Authenticated teacher username"),
) -> Dict[str, Any]:
    """
    Create a new announcement.
    Requires teacher authentication.
    - expiration_date is required (YYYY-MM-DD)
    - start_date is optional (YYYY-MM-DD); defaults to immediately active
    """
    _require_teacher(teacher_username)

    doc = {
        "message": body.message,
        "expiration_date": body.expiration_date,
        "start_date": body.start_date,
        "created_by": teacher_username,
    }
    result = announcements_collection.insert_one(doc)
    doc["id"] = str(result.inserted_id)
    del doc["_id"]
    doc["is_active"] = is_active(doc)
    return doc


@router.put("/{announcement_id}", response_model=Dict[str, Any])
def update_announcement(
    announcement_id: str,
    body: AnnouncementUpdate,
    teacher_username: str = Query(..., description="Authenticated teacher username"),
) -> Dict[str, Any]:
    """
    Update an existing announcement by ID.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    existing = announcements_collection.find_one({"_id": obj_id})
    if not existing:
        raise HTTPException(status_code=404, detail="Announcement not found")

    updates: Dict[str, Any] = {}
    if body.message is not None:
        updates["message"] = body.message
    if body.expiration_date is not None:
        updates["expiration_date"] = body.expiration_date
    # Allow explicitly setting start_date to None to clear it
    if "start_date" in body.model_fields_set:
        updates["start_date"] = body.start_date

    if updates:
        announcements_collection.update_one({"_id": obj_id}, {"$set": updates})

    updated = announcements_collection.find_one({"_id": obj_id})
    serialized = serialize_announcement(updated)
    serialized["is_active"] = is_active(serialized)
    return serialized


@router.delete("/{announcement_id}")
def delete_announcement(
    announcement_id: str,
    teacher_username: str = Query(..., description="Authenticated teacher username"),
) -> Dict[str, Any]:
    """
    Delete an announcement by ID.
    Requires teacher authentication.
    """
    _require_teacher(teacher_username)

    try:
        obj_id = ObjectId(announcement_id)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid announcement ID")

    result = announcements_collection.delete_one({"_id": obj_id})
    if result.deleted_count == 0:
        raise HTTPException(status_code=404, detail="Announcement not found")

    return {"message": "Announcement deleted successfully"}
