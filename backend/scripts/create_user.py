"""Create (or reset the password of) a user, e.g. the demo reviewer account.

Usage: python scripts/create_user.py --email demo@hyundai-assistant.app --password Demo1234 [--name "Demo"]
"""

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.db import SessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402
from app.schemas import RegisterIn  # noqa: E402
from app.security import hash_password  # noqa: E402


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--email", required=True)
    parser.add_argument("--password", required=True)
    parser.add_argument("--name", default=None)
    args = parser.parse_args()
    data = RegisterIn(email=args.email, password=args.password, full_name=args.name)
    async with SessionLocal() as s:
        user = await s.scalar(select(User).where(User.email == data.email))
        if user:
            user.password_hash = hash_password(data.password)
            if data.full_name:
                user.full_name = data.full_name
            action = "updated"
        else:
            s.add(User(email=data.email, password_hash=hash_password(data.password), full_name=data.full_name))
            action = "created"
        await s.commit()
    await engine.dispose()
    print(f"User {data.email} {action}.")


if __name__ == "__main__":
    asyncio.run(main())
