from app.db.postgres import PostgresDataSource
from flask_app.dispatch import solve_dispatch_problem  # Updated import path
import asyncio

async def main():
    ds = PostgresDataSource()  # Initialize with your connection params
    await solve_dispatch_problem(ds, "2024-05-09")

if __name__ == "__main__":
    asyncio.run(main())
