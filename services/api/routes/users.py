from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from services.api.auth import get_current_user
from services.api.database import RecordConflictError, create_user, delete_user, get_user_by_id, list_users, update_user
from services.api.models import Role, User, UserCreate, UserUpdate
from services.api.response_schemas import DeleteResponse, UserCreatedResponse, UserResponse

router = APIRouter(prefix="/users", tags=["users"])


def _ensure_access(current_user: User, user_id: int) -> None:
    if current_user.role == Role.ADMIN or current_user.id == user_id:
        return
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="You do not have permission to access this user.",
    )


@router.post("", response_model=UserCreatedResponse, status_code=status.HTTP_201_CREATED)
def create_new_user(payload: UserCreate) -> UserCreatedResponse:
    try:
        return create_user(payload)
    except RecordConflictError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="A user with this email already exists.") from exc


@router.get("", response_model=list[UserResponse])
def get_all_users(current_user: User = Depends(get_current_user)) -> list[UserResponse]:
    return list_users()


@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, current_user: User = Depends(get_current_user)) -> UserResponse:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _ensure_access(current_user, user_id)
    return user


@router.patch("/{user_id}", response_model=UserResponse)
def patch_user(
    user_id: int,
    payload: UserUpdate,
    current_user: User = Depends(get_current_user),
) -> UserResponse:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _ensure_access(current_user, user_id)
    if current_user.role != Role.ADMIN and (payload.role is not None or payload.is_active is not None):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admins can change a user's role or active status.",
        )
    updated_user = update_user(user_id, payload)
    if updated_user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return updated_user


@router.delete("/{user_id}", response_model=DeleteResponse)
def remove_user(user_id: int, current_user: User = Depends(get_current_user)) -> DeleteResponse:
    user = get_user_by_id(user_id)
    if user is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    _ensure_access(current_user, user_id)
    deleted = delete_user(user_id)
    if not deleted:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found.")
    return {"deleted": True, "id": user_id}
