"""Unit tests for Rating API endpoints, testing route functions directly with mocked database sessions."""

import asyncio
import unittest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

# Add backend directory to sys.path to allow imports of app
import sys
import os
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from app.api.customer_v1 import rate_market
from app.models.market import Market
from app.models.user import User
from app.models.rating import Rating
from app.schemas.customer_v1 import RatingCreate, RatingResponse
from fastapi import HTTPException


class TestRatingV1API(unittest.IsolatedAsyncioTestCase):
    
    async def test_rate_market_success(self):
        """Test submitting rating successfully for a valid market and customer."""
        mock_db = AsyncMock()
        market_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        
        # 1. Mock market existence check
        mock_market = Market(id=market_id, name="Olaya Market", address="Olaya Street")
        mock_market_res = MagicMock()
        mock_market_res.scalar_one_or_none.return_value = mock_market
        
        # 2. Mock customer account existence check
        mock_customer = User(id=customer_id, email="customer@mail.com", user_type="customer")
        mock_customer_res = MagicMock()
        mock_customer_res.scalar_one_or_none.return_value = mock_customer
        
        # db.execute returns results sequentially
        mock_db.execute.side_effect = [mock_market_res, mock_customer_res]
        
        # 3. Create schema request payload
        payload = RatingCreate(
            market_id=market_id,
            customer_id=customer_id,
            score=5,
            review="Excellent product fresh inventory!"
        )
        
        # 4. Invoke endpoint
        response = await rate_market(data=payload, db=mock_db)
        
        # 5. Assertions
        self.assertEqual(mock_db.execute.call_count, 2)
        self.assertTrue(mock_db.add.called)
        self.assertTrue(mock_db.flush.called)
        
        # Verify persisted model fields
        persisted_rating = mock_db.add.call_args[0][0]
        self.assertIsInstance(persisted_rating, Rating)
        self.assertEqual(persisted_rating.market_id, market_id)
        self.assertEqual(persisted_rating.customer_id, customer_id)
        self.assertEqual(persisted_rating.score, 5)
        self.assertEqual(persisted_rating.review, "Excellent product fresh inventory!")
        
        # Verify API response matches RatingResponse
        self.assertEqual(response.status, "completed rating")
        self.assertIsInstance(response.stored_at, datetime)

    async def test_rate_market_invalid_score_bounds(self):
        """Test score bounds input validation (must be between 1 and 5)."""
        market_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        
        # Score below bounds
        with self.assertRaises(ValidationError):
            RatingCreate(
                market_id=market_id,
                customer_id=customer_id,
                score=0,  # Below 1
                review="Too low"
            )
            
        # Score above bounds
        with self.assertRaises(ValidationError):
            RatingCreate(
                market_id=market_id,
                customer_id=customer_id,
                score=6,  # Above 5
                review="Too high"
            )

    async def test_rate_market_merchant_account_fails(self):
        """Test that merchant accounts are barred from submitting market ratings."""
        mock_db = AsyncMock()
        market_id = uuid.uuid4()
        merchant_id = uuid.uuid4()
        
        mock_market_res = MagicMock()
        mock_market_res.scalar_one_or_none.return_value = Market(id=market_id)
        
        # Customer exists but has merchant role/type
        mock_merchant = User(id=merchant_id, email="merchant@mail.com", user_type="merchant")
        mock_merchant_res = MagicMock()
        mock_merchant_res.scalar_one_or_none.return_value = mock_merchant
        
        mock_db.execute.side_effect = [mock_market_res, mock_merchant_res]
        
        payload = RatingCreate(
            market_id=market_id,
            customer_id=merchant_id,
            score=4,
            review="Impersonating rating"
        )
        
        with self.assertRaises(HTTPException) as context:
            await rate_market(data=payload, db=mock_db)
            
        self.assertEqual(context.exception.status_code, 400)
        self.assertIn("Only customer accounts", context.exception.detail)

    async def test_rate_market_not_found(self):
        """Test that rating a non-existent market raises a 404 error."""
        mock_db = AsyncMock()
        market_id = uuid.uuid4()
        customer_id = uuid.uuid4()
        
        # Market search returns empty
        mock_market_res = MagicMock()
        mock_market_res.scalar_one_or_none.return_value = None
        mock_db.execute.return_value = mock_market_res
        
        payload = RatingCreate(
            market_id=market_id,
            customer_id=customer_id,
            score=3
        )
        
        with self.assertRaises(HTTPException) as context:
            await rate_market(data=payload, db=mock_db)
            
        self.assertEqual(context.exception.status_code, 404)
        self.assertIn("Shop location not found", context.exception.detail)


if __name__ == "__main__":
    unittest.main()
