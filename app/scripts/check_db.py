import asyncio
from sqlalchemy import text
from app.db.session import engine


async def main() -> None:
    try:
        async with engine.connect() as conn:
            result = await conn.execute(text("SELECT 1"))
            print("Kết nối PostgreSQL OK:", result.scalar() == 1)

            result = await conn.execute(text("SELECT current_database()"))
            print("Database:", result.scalar())

            result = await conn.execute(text("""
                SELECT table_name
                FROM information_schema.tables
                WHERE table_schema = 'public'
                ORDER BY table_name
            """))
            tables = result.scalars().all()
            print("Các bảng hiện có:", tables)

    except Exception as e:
        print("Kết nối PostgreSQL thất bại:", e)

    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())