"""Debug admin user state in TinyDB."""
import json, os, sys
sys.path.insert(0, '.')

from pathlib import Path

db_path = Path('services/api/data/users.json')
if db_path.exists():
    with open(db_path) as f:
        raw = json.load(f)
    print('users.json exists and is valid JSON')
    print('Root keys:', list(raw.keys()) if isinstance(raw, dict) else 'list (root not dict)')
    if isinstance(raw, dict):
        users = raw.get('users', [])
        print(f'users table: {len(users)} records')
        for u in users:
            print(f'  doc_id={u.get("doc_id")!r} email={u.get("email")!r} is_active={u.get("is_active")!r}')
else:
    print('users.json DOES NOT EXIST')

# Try seeding
from services.api.database import seed_users, get_user_by_email, get_user_db
from tinydb import Query

result = seed_users()
print(f'\nseed_users() returned: {result}')

user = get_user_by_email('admin@trackflow.com')
if user:
    print(f'admin user: id={user.id} is_active={user.is_active} role={user.role}')
    print(f'  hashed_password[:20]={user.hashed_password[:20] if user.hashed_password else "MISSING"}')
else:
    print('admin user NOT FOUND after seeding')

# Direct TinyDB check
u_db = get_user_db()
q = Query()
all_users = u_db.table('users').all()
print(f'\nDirect TinyDB users table: {len(all_users)} records')
for u in all_users:
    print(f'  doc_id={u.doc_id!r} email={u.get("email")!r} is_active={u.get("is_active")!r}')