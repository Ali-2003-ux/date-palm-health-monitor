#!/usr/bin/env python
"""Create an admin (or agronomist) account from the CLI.

Usage:
    python scripts/create_admin.py admin@farm.com "StrongPass123!" "Site Admin" [--role agronomist]

Uses the same settings (.env) as the API, so run it with DATABASE_URL
pointing at the target database. Passwords are read from the argument or
interactively when omitted.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.core.logging import get_logger, setup_logging
from backend.core.security import hash_password
from backend.db.session import get_session_factory
from backend.models import User, UserRole

logger = get_logger(__name__)


def main() -> int:
    setup_logging()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("email", help="Account email address")
    parser.add_argument("password", nargs="?", help="Password (prompted if omitted)")
    parser.add_argument("full_name", nargs="?", default="Administrator")
    parser.add_argument(
        "--role",
        choices=[UserRole.ADMIN.value, UserRole.AGRONOMIST.value],
        default=UserRole.ADMIN.value,
    )
    args = parser.parse_args()

    password = args.password or getpass.getpass("Password: ")
    if len(password) < 8:
        print("Password must be at least 8 characters.", file=sys.stderr)
        return 2

    with get_session_factory()() as session:
        existing = (
            session.query(User).filter(User.email == args.email.lower()).one_or_none()
        )
        if existing is not None:
            print(
                f"User {args.email} already exists with role "
                f"{existing.role.value}; nothing to do.",
                file=sys.stderr,
            )
            return 1

        user = User(
            email=args.email,
            hashed_password=hash_password(password),
            full_name=args.full_name,
            role=UserRole(args.role),
        )
        session.add(user)
        session.commit()
        print(f"Created {args.role} account: {user.email} (id={user.id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
