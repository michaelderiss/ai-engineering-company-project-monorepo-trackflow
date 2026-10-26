from __future__ import annotations

import logging
import os
from urllib.parse import quote

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm

from services.api.auth import (
    change_user_password,
    create_password_reset_token,
    get_current_user,
    login_user,
    reset_user_password,
)
from services.api.database import get_user_by_email
from services.api.email import send_password_reset_email
from services.api.models import (
    ChangePasswordRequest,
    ForgotPasswordRequest,
    ResetPasswordRequest,
    Token,
    User,
)

router = APIRouter(prefix="/auth", tags=["auth"])
logger = logging.getLogger(__name__)
BACKOFFICE_URL = os.getenv("BACKOFFICE_URL", "http://localhost:3000").rstrip("/")


def _deliver_reset_email(recipient: str, reset_url: str) -> None:
    try:
        send_password_reset_email(recipient, reset_url)
    except Exception:
        logger.exception("Password reset delivery failed unexpectedly")


@router.post("/login", response_model=Token)
async def login(form_data: OAuth2PasswordRequestForm = Depends()) -> Token:
    return await login_user(form_data)


@router.get("/me", response_model=User)
async def me(current_user: User = Depends(get_current_user)) -> User:
    return current_user


@router.post("/forgot-password", status_code=status.HTTP_200_OK)
async def forgot_password(
    payload: ForgotPasswordRequest,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    user = get_user_by_email(payload.email)
    if user is not None and user.is_active:
        token, _ = create_password_reset_token(user)
        reset_url = f"{BACKOFFICE_URL}/reset-password?token={quote(token)}"
        background_tasks.add_task(_deliver_reset_email, user.email, reset_url)

    return {
        "message": "If that address is registered, you'll receive a password reset link."
    }


@router.post("/reset-password")
async def reset_password(payload: ResetPasswordRequest) -> dict[str, str]:
    if not reset_user_password(payload.token, payload.new_password):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="This password reset link is invalid, expired, or has already been used.",
        )
    return {"message": "Password updated successfully."}


@router.post("/change-password")
async def change_password(
    payload: ChangePasswordRequest,
    current_user: User = Depends(get_current_user),
) -> dict[str, str]:
    if not change_user_password(
        current_user,
        payload.current_password,
        payload.new_password,
    ):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="The current password is incorrect.",
        )
    return {"message": "Password updated successfully."}
