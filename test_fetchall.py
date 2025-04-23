from app.db.postgres import PostgresDataSource
import asyncio

async def test_fetch_all():
      ds = PostgresDataSource()
      await ds.connect()
      result = await ds.fetch_all("SELECT chauffeur_id, code_postal, prenom_nom FROM chauffeur limit 2")
      print(result)

if __name__ == "__main__":
      asyncio.run(test_fetch_all())