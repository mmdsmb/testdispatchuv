from app.db.postgres import PostgresDataSource
import asyncio

async def test_fetch_one():
      ds = PostgresDataSource()
      await ds.connect()
      result = await ds.fetch_one("SELECT 1")
      print(result)

if __name__ == "__main__":
      asyncio.run(test_fetch_one())