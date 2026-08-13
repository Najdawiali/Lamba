import argparse
import asyncio
import sys
from datetime import datetime, timezone
import math

from sqlalchemy import select, or_, func

from app.database import async_session
from app.models.global_item import GlobalItem
from app.services.embedding import embedding_service
from app.config import settings

async def main():
    # Fix for Windows UTF-8 stdout printing Arabic characters
    if sys.platform == "win32":
        sys.stdout.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(description="Re-embed catalog items in global_items")
    parser.add_argument("--batch-size", type=int, default=32, help="Batch size for embedding (default: 32)")
    parser.add_argument("--force", action="store_true", help="Force re-embed all items regardless of status")
    parser.add_argument("--limit", type=int, default=None, help="Limit number of items to process")
    args = parser.parse_args()

    # Ensure embedding models are loaded if needed
    if hasattr(embedding_service, "load_model"):
        embedding_service.load_model()

    print(f"Starting catalog re-embedding (batch_size={args.batch_size}, force={args.force}, limit={args.limit})")

    async with async_session() as session:
        # Build query
        query = select(GlobalItem)
        
        if not args.force:
            query = query.where(
                or_(
                    GlobalItem.embedding_status != "completed",
                    GlobalItem.embedding_status.is_(None),
                    GlobalItem.text_embedding.is_(None)
                )
            )
        
        # We need total count first (with limit if applicable)
        count_query = select(func.count()).select_from(query.subquery())
        total_items = await session.scalar(count_query)
        
        if args.limit is not None and total_items > args.limit:
            total_items = args.limit
            
        if total_items == 0:
            print("No items need embedding. Exiting.")
            return
            
        print(f"Found {total_items} items to embed.")
        
        if args.limit is not None:
            query = query.limit(args.limit)
            
        result = await session.execute(query)
        items = result.unique().scalars().all()
        
        processed = 0
        total_batches = math.ceil(len(items) / args.batch_size)
        
        for i in range(0, len(items), args.batch_size):
            batch = items[i : i + args.batch_size]
            
            texts = []
            for item in batch:
                name = item.name_ar or item.name or ""
                desc = item.description_ar or item.description or ""
                terms = item.search_terms or ""
                text_bundle = f"{name} | {desc} | {terms}".strip(" |")
                texts.append(text_bundle)
                
            # Embed batch
            try:
                embeddings = await embedding_service.embed_texts_batch(texts, text_type="document")
                
                # Update items
                now = datetime.now(timezone.utc)
                for item, embedding in zip(batch, embeddings):
                    item.text_embedding = embedding
                    item.embedding_model = settings.qwen_embed_model
                    item.embedding_dim = settings.text_embedding_dim
                    item.embedded_at = now
                    item.embedding_status = "completed"
                    
                await session.commit()
                
                processed += len(batch)
                print(f"Processed {processed}/{total_items} items...")
                
            except Exception as e:
                print(f"Error processing batch starting at index {i}: {e}")
                await session.rollback()
                
        print("Re-embedding completed successfully.")

        # Rebuild synonym table from catalog
        try:
            from scripts.build_synonym_table import build_synonym_table
            await build_synonym_table()
        except Exception as e:
            print(f"Synonym table rebuild failed/skipped: {e}")

if __name__ == "__main__":
    asyncio.run(main())
