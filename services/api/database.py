from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from passlib.context import CryptContext
from tinydb import Query, TinyDB
from tinydb.table import Document

from services.api.models import (
    SUPPLIERS_SEED,
    Profile,
    ProfileCreate,
    Role,
    Supplier,
    SupplierCreate,
    SupplierStatus,
    User,
    UserCreate,
    UserUpdate,
)

DB_PATH = Path(__file__).resolve().parent / "data" / "suppliers.json"
USER_DB_PATH = Path(__file__).resolve().parent / "data" / "users.json"
_pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def get_password_hash(password: str) -> str:
    return _pwd_context.hash(password)


def get_db() -> TinyDB:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return TinyDB(DB_PATH, indent=2, ensure_ascii=False)


def get_user_db() -> TinyDB:
    USER_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return TinyDB(USER_DB_PATH, indent=2, ensure_ascii=False)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _now_iso() -> str:
    return _now().isoformat()


def _supplier_from_document(document: Document) -> Supplier:
    payload = dict(document)
    updated_at = payload.pop("updated_at")
    return Supplier(id=document.doc_id, updated_at=updated_at, **payload)


def _seed_identity(supplier: dict) -> tuple[str, str]:
    return supplier["name"], supplier["country"]


def _profile_from_document(document: Document | None) -> Profile | None:
    if document is None:
        return None
    payload = dict(document)
    payload["id"] = document.doc_id
    return Profile(**payload)


def _user_from_document(document: Document | None, profile_document: Document | None = None) -> User | None:
    if document is None:
        return None
    payload = dict(document)
    payload["id"] = document.doc_id
    payload["profile"] = _profile_from_document(profile_document)
    return User(**payload)


def list_suppliers(country: str | None = None, category: str | None = None) -> list[Supplier]:
    with get_db() as db:
        query = Query()
        documents = db.all()
        if country:
            documents = [document for document in documents if document.get("country") == country]
        if category:
            documents = [
                document
                for document in documents
                if category in document.get("categories", [])
            ]
        return [_supplier_from_document(document) for document in documents]


def get_supplier_by_id(supplier_id: int) -> Supplier | None:
    with get_db() as db:
        document = db.get(doc_id=supplier_id)
        if document is None:
            return None
        return _supplier_from_document(document)


def create_supplier(payload: SupplierCreate) -> Supplier:
    supplier_data = payload.dict()
    supplier_data["updated_at"] = _now_iso()
    with get_db() as db:
        doc_id = db.insert(supplier_data)
        document = db.get(doc_id=doc_id)
        return _supplier_from_document(document)


def update_supplier_rate(supplier_id: int, rate_per_shipment: float) -> Supplier | None:
    with get_db() as db:
        document = db.get(doc_id=supplier_id)
        if document is None:
            return None
        db.update(
            {"rate_per_shipment": rate_per_shipment, "updated_at": _now_iso()},
            doc_ids=[supplier_id],
        )
        updated_document = db.get(doc_id=supplier_id)
        return _supplier_from_document(updated_document)


def update_supplier_status(supplier_id: int, status: SupplierStatus) -> Supplier | None:
    with get_db() as db:
        document = db.get(doc_id=supplier_id)
        if document is None:
            return None
        db.update({"status": status.value}, doc_ids=[supplier_id])
        updated_document = db.get(doc_id=supplier_id)
        return _supplier_from_document(updated_document)


def delete_supplier(supplier_id: int) -> bool:
    with get_db() as db:
        document = db.get(doc_id=supplier_id)
        if document is None:
            return False
        db.remove(doc_ids=[supplier_id])
        return True


def seed_suppliers() -> int:
    inserted = 0
    seed_keys = {_seed_identity(supplier) for supplier in SUPPLIERS_SEED}

    with get_db() as db:
        existing = {
            _seed_identity(document)
            for document in db.all()
            if _seed_identity(document) in seed_keys
        }

        for supplier in SUPPLIERS_SEED:
            if _seed_identity(supplier) in existing:
                continue
            db.insert({**supplier, "updated_at": _now_iso()})
            inserted += 1

    return inserted


def list_users() -> list[User]:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        users: list[User] = []
        for document in user_table.all():
            profile_document = profile_table.get(query.user_id == document.doc_id)
            user = _user_from_document(document, profile_document)
            if user is not None:
                users.append(user)
        return users


def get_user_by_id(user_id: int) -> User | None:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        document = user_table.get(doc_id=user_id)
        if document is None:
            return None
        profile_document = profile_table.get(query.user_id == user_id)
        return _user_from_document(document, profile_document)


def get_user_by_email(email: str) -> User | None:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        document = user_table.get(query.email == email)
        if document is None:
            return None
        profile_document = profile_table.get(query.user_id == document.doc_id)
        return _user_from_document(document, profile_document)


def create_user(payload: UserCreate) -> User:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        if user_table.get(query.email == payload.email):
            raise ValueError("A user with this email already exists.")

        created_at = _now_iso()
        user_document = {
            "email": payload.email,
            "hashed_password": get_password_hash(payload.password),
            "is_active": payload.is_active,
            "role": payload.role.value,
            "created_at": created_at,
            "updated_at": created_at,
        }
        user_id = user_table.insert(user_document)
        profile_document: dict | None = None
        if payload.profile is not None:
            profile_document = {
                "user_id": user_id,
                "display_name": payload.profile.display_name,
                "phone": payload.profile.phone,
                "address": payload.profile.address,
            }
            profile_table.insert(profile_document)
        stored_user = user_table.get(doc_id=user_id)
        stored_profile = profile_table.get(query.user_id == user_id)
        return _user_from_document(stored_user, stored_profile)


def update_user(user_id: int, payload: UserUpdate) -> User | None:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        document = user_table.get(doc_id=user_id)
        if document is None:
            return None

        updates: dict = {"updated_at": _now_iso()}
        if payload.email is not None:
            updates["email"] = payload.email
        if payload.password is not None:
            updates["hashed_password"] = get_password_hash(payload.password)
        if payload.role is not None:
            updates["role"] = payload.role.value
        if payload.is_active is not None:
            updates["is_active"] = payload.is_active

        user_table.update(updates, doc_ids=[user_id])

        if payload.profile is not None:
            existing_profile = profile_table.get(query.user_id == user_id)
            profile_data = {
                "user_id": user_id,
                "display_name": payload.profile.display_name,
                "phone": payload.profile.phone,
                "address": payload.profile.address,
            }
            if existing_profile is None:
                profile_table.insert(profile_data)
            else:
                profile_table.update(profile_data, doc_ids=[existing_profile.doc_id])

        updated_document = user_table.get(doc_id=user_id)
        updated_profile = profile_table.get(query.user_id == user_id)
        return _user_from_document(updated_document, updated_profile)


def delete_user(user_id: int) -> bool:
    with get_user_db() as db:
        user_table = db.table("users")
        profile_table = db.table("profiles")
        query = Query()
        user_document = user_table.get(doc_id=user_id)
        if user_document is None:
            return False
        user_table.remove(doc_ids=[user_id])
        profile_table.remove(query.user_id == user_id)
        return True


def create_profile_for_user(user_id: int, payload: ProfileCreate) -> Profile:
    with get_user_db() as db:
        profile_table = db.table("profiles")
        query = Query()
        if profile_table.get(query.user_id == user_id):
            raise ValueError("This user already has a profile.")
        profile_doc_id = profile_table.insert(
            {
                "user_id": user_id,
                "display_name": payload.display_name,
                "phone": payload.phone,
                "address": payload.address,
            }
        )
        document = profile_table.get(doc_id=profile_doc_id)
        return _profile_from_document(document)


def get_profile_for_user(user_id: int) -> Profile | None:
    with get_user_db() as db:
        profile_table = db.table("profiles")
        query = Query()
        document = profile_table.get(query.user_id == user_id)
        return _profile_from_document(document)


def update_profile_for_user(user_id: int, payload: ProfileCreate) -> Profile | None:
    with get_user_db() as db:
        profile_table = db.table("profiles")
        query = Query()
        document = profile_table.get(query.user_id == user_id)
        if document is None:
            return None
        profile_table.update(
            {
                "display_name": payload.display_name,
                "phone": payload.phone,
                "address": payload.address,
            },
            doc_ids=[document.doc_id],
        )
        updated_document = profile_table.get(doc_id=document.doc_id)
        return _profile_from_document(updated_document)


def seed_users() -> int:
    from os import getenv

    email = getenv("TRACKFLOW_ADMIN_EMAIL", "admin@trackflow.com")
    password = getenv("TRACKFLOW_ADMIN_PASSWORD", "admin123")
    with get_user_db() as db:
        user_table = db.table("users")
        if user_table.get(Query().email == email):
            return 0
        user_id = user_table.insert(
            {
                "email": email,
                "hashed_password": get_password_hash(password),
                "is_active": True,
                "role": Role.ADMIN.value,
                "created_at": _now_iso(),
                "updated_at": _now_iso(),
            }
        )
        profile_table = db.table("profiles")
        profile_table.insert(
            {
                "user_id": user_id,
                "display_name": "TrackFlow Admin",
                "phone": "+1-555-0000",
                "address": "Los Angeles, CA",
            }
        )
        return 1
