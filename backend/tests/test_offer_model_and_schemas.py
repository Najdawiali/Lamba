"""Unit tests for Offer model and schemas."""

import unittest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from app.models.offer import Offer
from app.models.market import Market
from app.models.market_item import MarketItem
from app.schemas.offer import OfferCreate, OfferUpdate, OfferResponse, VALID_OFFER_TYPES


class TestOfferModelAndSchemas(unittest.TestCase):
    def test_offer_create_valid_types(self):
        item_id = uuid.uuid4()

        # percentage
        p = OfferCreate(market_item_id=item_id, offer_type="percentage", config={"percent": 25.0})
        self.assertEqual(p.offer_type, "percentage")
        self.assertEqual(p.config["percent"], 25.0)

        # fixed_amount
        fa = OfferCreate(market_item_id=item_id, offer_type="fixed_amount", config={"amount": 10})
        self.assertEqual(fa.offer_type, "fixed_amount")
        self.assertEqual(fa.config["amount"], 10)

        # buy_x_get_y
        bogo = OfferCreate(market_item_id=item_id, offer_type="buy_x_get_y", config={"buy": 2, "get": 1})
        self.assertEqual(bogo.offer_type, "buy_x_get_y")
        self.assertEqual(bogo.config["buy"], 2)
        self.assertEqual(bogo.config["get"], 1)

        # quantity_price
        qp = OfferCreate(market_item_id=item_id, offer_type="quantity_price", config={"quantity": 3, "price": 12.5})
        self.assertEqual(qp.offer_type, "quantity_price")
        self.assertEqual(qp.config["quantity"], 3)
        self.assertEqual(qp.config["price"], 12.5)

    def test_offer_create_invalid_type(self):
        item_id = uuid.uuid4()
        with self.assertRaises(ValidationError) as ctx:
            OfferCreate(market_item_id=item_id, offer_type="invalid_type", config={"percent": 20})
        self.assertIn("offer_type must be one of", str(ctx.exception))

    def test_offer_create_invalid_configs(self):
        item_id = uuid.uuid4()

        # percentage invalid percent
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="percentage", config={"percent": 0})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="percentage", config={"percent": 105})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="percentage", config={})

        # fixed_amount invalid amount
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="fixed_amount", config={"amount": 0})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="fixed_amount", config={"amount": -5})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="fixed_amount", config={})

        # buy_x_get_y invalid buy/get
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="buy_x_get_y", config={"buy": 0, "get": 1})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="buy_x_get_y", config={"buy": 1, "get": 0})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="buy_x_get_y", config={"buy": 1})

        # quantity_price invalid quantity/price
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="quantity_price", config={"quantity": 1, "price": 10})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="quantity_price", config={"quantity": 2, "price": 0})
        with self.assertRaises(ValidationError):
            OfferCreate(market_item_id=item_id, offer_type="quantity_price", config={})

    def test_offer_response_and_update_schemas(self):
        offer_id = uuid.uuid4()
        market_id = uuid.uuid4()
        market_item_id = uuid.uuid4()
        now = datetime.now(timezone.utc)

        update = OfferUpdate(is_active=False, description="Updated desc")
        self.assertFalse(update.is_active)
        self.assertEqual(update.description, "Updated desc")

        resp = OfferResponse(
            id=offer_id,
            market_id=market_id,
            market_item_id=market_item_id,
            offer_type="percentage",
            config={"percent": 15},
            description="Test offer",
            is_active=True,
            starts_at=now,
            expires_at=None,
            created_at=now,
            item_name="Item",
            item_name_ar="عنصر",
            item_price=20.0,
            item_image_url="http://example.com/img.png",
        )
        self.assertEqual(resp.id, offer_id)
        self.assertEqual(resp.item_name_ar, "عنصر")

    def test_offer_model_structure(self):
        self.assertEqual(Offer.__tablename__, "offers")
        offer_id = uuid.uuid4()
        offer = Offer(
            id=offer_id,
            market_id=uuid.uuid4(),
            market_item_id=uuid.uuid4(),
            offer_type="percentage",
            config={"percent": 50},
            description="Half price",
            is_active=True,
        )
        self.assertEqual(offer.id, offer_id)
        self.assertEqual(offer.offer_type, "percentage")
        self.assertEqual(Offer.id.property.columns[0].type.as_uuid, True)
