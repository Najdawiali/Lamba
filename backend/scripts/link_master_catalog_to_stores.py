import asyncio
import os
import sys

if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
from app.database import async_session
from sqlalchemy import text


async def main():
    print("Linking all master catalog products to demo stores...")
    async with async_session() as session:
        # Check column existence for price on global_items
        cols_res = await session.execute(
            text("SELECT column_name FROM information_schema.columns WHERE table_name='global_items'")
        )
        cols = {r[0] for r in cols_res.fetchall()}
        has_price = "price" in cols

        price_expr = "COALESCE(gi.price, 2.50)" if has_price else "2.50"

        sql = f"""
        INSERT INTO market_items (id, market_id, item_id, price, stock_count, status)
        SELECT gen_random_uuid(), m.id, gi.id, 
               {price_expr}, 
               100, 
               true
        FROM markets m
        CROSS JOIN global_items gi
        WHERE NOT EXISTS (
            SELECT 1 FROM market_items mi 
            WHERE mi.market_id = m.id AND mi.item_id = gi.id
        )
        """
        
        result = await session.execute(text(sql))
        await session.commit()
        print(f"Successfully linked {result.rowcount} market item entries!")

        total_market_items = (await session.execute(text("SELECT count(*) FROM market_items"))).scalar()
        print(f"Total market items now in database: {total_market_items}")


if __name__ == "__main__":
    asyncio.run(main())
