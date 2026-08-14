import asyncio
from sqlalchemy import text
from app.database import async_session

async def update_custom():
    async with async_session() as session:
        await session.execute(text("""
            UPDATE markets 
            SET name_ar = 'سوبرماركت القدس', 
                name_en = 'Quds Supermarket', 
                address_ar = 'السلط، شارع اليرموك، بالقرب من وسط المدينة' 
            WHERE name ILIKE '%quds%';
        """))
        await session.execute(text("""
            UPDATE markets 
            SET name_ar = 'سوق مدينة السلط', 
                name_en = 'Salt City Market', 
                address_ar = 'الشارع الرئيسي، السلط، البلقاء، الأردن' 
            WHERE name ILIKE '%Salt City Market%';
        """))
        await session.commit()
        print("Updated custom markets.")

if __name__ == "__main__":
    asyncio.run(update_custom())
