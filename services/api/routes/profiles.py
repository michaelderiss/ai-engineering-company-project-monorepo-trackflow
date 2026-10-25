from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.api.auth import get_current_user
from services.api.database import (
    create_profile_for_user,
    get_profile_for_user,
    update_profile_for_user,
)
from services.api.models import Profile, ProfileCreate, Role, User

router = APIRouter(prefix="/profiles", tags=["profiles"])


@router.post("", response_model=Profile, status_code=status.HTTP_201_CREATED)
def create_profile(
    payload: ProfileCreate,
    current_user: User = Depends(get_current_user),
) -> Profile:
    try:
        return create_profile_for_user(current_user.id, payload)
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc


@router.get("", response_model=list[Profile])
def list_profiles(current_user: User = Depends(get_current_user)) -> list[Profile]:
    if current_user.role != Role.ADMIN:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can list all profiles.",
        )
    return []


@router.get("/me", response_model=Profile)
def my_profile(current_user: User = Depends(get_current_user)) -> Profile:
    profile = get_profile_for_user(current_user.id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return profile


@router.get("/{profile_id}", response_model=Profile)
def get_profile_by_id(
    profile_id: int,
    current_user: User = Depends(get_current_user),
) -> Profile:
    profile = get_profile_for_user(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    if current_user.role != Role.ADMIN and profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to access this profile.",
        )
    return profile


@router.patch("/{profile_id}", response_model=Profile)
def patch_profile(
    profile_id: int,
    payload: ProfileCreate,
    current_user: User = Depends(get_current_user),
) -> Profile:
    profile = get_profile_for_user(profile_id)
    if profile is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    if current_user.role != Role.ADMIN and profile.user_id != current_user.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="You do not have permission to update this profile.",
        )
    updated = update_profile_for_user(profile_id, payload)
    if updated is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Profile not found.")
    return updated
