from app.models.hotes import HotesSync
import asyncio

async def main():
    sync = HotesSync()
    result = await sync.sync("1hVtUng_VuP1obHFjMeEJBjngE34FOFkm9J_4bgF7tPk", auto_apply=False)
    print(result)

asyncio.run(main())