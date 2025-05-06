#!/usr/bin/env python3
import asyncio
from app.db.postgres import PostgresDataSource
from app.core.dispatch_solver_versionAvecVaraibleContrainte import group_courses

async def main():
    ds = PostgresDataSource()
    await group_courses(ds)
    print("Groupage terminé avec succès!")

if __name__ == "__main__":
    asyncio.run(main())
