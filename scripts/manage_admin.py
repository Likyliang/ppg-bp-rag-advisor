from __future__ import annotations

import argparse
import getpass
import json

from sqlalchemy import select

from app.admin.db import session_scope
from app.admin.integration_service import generate_master_key
from app.admin.models import AdminUser
from app.admin.security import VALID_ROLES, hash_password


def _password(value: str = "") -> str:
    password = value or getpass.getpass("Password (12+ chars): ")
    confirmation = value or getpass.getpass("Confirm password: ")
    if password != confirmation:
        raise SystemExit("passwords do not match")
    return password


def create_user(args) -> None:
    if args.role not in VALID_ROLES:
        raise SystemExit(f"invalid role: {args.role}")
    with session_scope() as db:
        if db.scalar(select(AdminUser).where(AdminUser.username == args.username)):
            raise SystemExit("username already exists")
        row = AdminUser(
            username=args.username,
            password_hash=hash_password(_password(args.password)),
            role=args.role,
        )
        db.add(row)
        db.flush()
        print(json.dumps({"id": row.id, "username": row.username, "role": row.role}, ensure_ascii=False))


def list_users(_args) -> None:
    with session_scope() as db:
        rows = db.scalars(select(AdminUser).order_by(AdminUser.username)).all()
        print(
            json.dumps(
                [{"id": row.id, "username": row.username, "role": row.role, "active": row.active} for row in rows],
                ensure_ascii=False,
                indent=2,
            )
        )


def reset_password(args) -> None:
    with session_scope() as db:
        row = db.scalar(select(AdminUser).where(AdminUser.username == args.username))
        if row is None:
            raise SystemExit("username not found")
        row.password_hash = hash_password(_password(args.password))
        db.flush()
        print(json.dumps({"username": row.username, "password_reset": True}, ensure_ascii=False))


def main() -> None:
    parser = argparse.ArgumentParser(description="Manage local internal-admin credentials.")
    sub = parser.add_subparsers(dest="command", required=True)

    create = sub.add_parser("create-user")
    create.add_argument("username")
    create.add_argument("--role", default="admin", choices=sorted(VALID_ROLES))
    create.add_argument("--password", default="", help="Avoid on shared shells; prompt is safer.")
    create.set_defaults(func=create_user)

    listing = sub.add_parser("list-users")
    listing.set_defaults(func=list_users)

    reset = sub.add_parser("reset-password")
    reset.add_argument("username")
    reset.add_argument("--password", default="", help="Avoid on shared shells; prompt is safer.")
    reset.set_defaults(func=reset_password)

    master = sub.add_parser("generate-master-key")
    master.set_defaults(func=lambda _args: print(generate_master_key()))

    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
