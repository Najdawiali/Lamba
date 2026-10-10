"""Unit tests for Market profile model columns and schemas."""

import unittest
import uuid
from datetime import datetime, timezone
from pydantic import ValidationError

from app.models.market import Market
from app.schemas.market_profile import (
    MarketProfileUpdate,
    EmployeesUpdate,
    MarketProfileResponse,
)
from app.schemas.merchant_v1 import MarketResponse


class TestMarketProfileModelAndSchemas(unittest.TestCase):
    def test_market_profile_update_valid(self):
        update_data = MarketProfileUpdate(
            name="Super Market",
            name_ar="سوبر ماركت",
            contact_phone="+962791234567",
            contact_email="owner@supermarket.jo",
        )
        self.assertEqual(update_data.name, "Super Market")
        self.assertEqual(update_data.name_ar, "سوبر ماركت")
        self.assertEqual(update_data.contact_phone, "+962791234567")
        self.assertEqual(update_data.contact_email, "owner@supermarket.jo")

    def test_market_profile_update_phone_validation(self):
        # Valid phones
        valid_phones = ["+962 79 123 4567", "0791234567", "00962-79-1234567"]
        for p in valid_phones:
            res = MarketProfileUpdate(contact_phone=p)
            self.assertEqual(res.contact_phone, p)

        # Invalid phones
        invalid_phones = ["123", "abc", "phone123456", "1234567890123456789012345"]
        for p in invalid_phones:
            with self.assertRaises(ValidationError):
                MarketProfileUpdate(contact_phone=p)

    def test_market_profile_update_email_validation(self):
        # Valid emails
        valid_emails = ["test@example.com", "merchant.owner@domain.co.uk"]
        for e in valid_emails:
            res = MarketProfileUpdate(contact_email=e)
            self.assertEqual(res.contact_email, e)

        # Invalid emails
        invalid_emails = ["not-an-email", "test@", "test@domain", "plainaddress"]
        for e in invalid_emails:
            with self.assertRaises(ValidationError):
                MarketProfileUpdate(contact_email=e)

    def test_market_profile_update_empty_strings_rejected(self):
        # Empty name rejected
        with self.assertRaises(ValidationError):
            MarketProfileUpdate(name="   ")

        # Empty phone rejected
        with self.assertRaises(ValidationError):
            MarketProfileUpdate(contact_phone="  ")

    def test_employees_update_validation(self):
        # Valid list
        res = EmployeesUpdate(employees=[" Ahmad ", " Sara ", "Mohammad"])
        self.assertEqual(res.employees, ["Ahmad", "Sara", "Mohammad"])

        # Filter empty strings but preserve valid ones
        res_empty = EmployeesUpdate(employees=["   ", "Ali", "", "  Khaled  "])
        self.assertEqual(res_empty.employees, ["Ali", "Khaled"])

        # At least one employee is mandatory (empty list rejected)
        with self.assertRaises(ValidationError):
            EmployeesUpdate(employees=[])

        # All empty strings rejected
        with self.assertRaises(ValidationError):
            EmployeesUpdate(employees=["", "   "])

        # Exceed max 50 employees
        too_many = [f"Employee {i}" for i in range(51)]
        with self.assertRaises(ValidationError):
            EmployeesUpdate(employees=too_many)

    def test_market_profile_response_structure(self):
        now = datetime.now(timezone.utc)
        resp = MarketProfileResponse(
            name="Downtown Bakery",
            name_ar="مخبز وسط البلد",
            contact_phone="0791234567",
            contact_email="bakery@mail.com",
            employees=["Chef Omar", "Cashier Lana"],
            profile_edited_at=now,
            name_edited_at=now,
            is_name_locked=True,
        )
        self.assertEqual(resp.name, "Downtown Bakery")
        self.assertEqual(resp.employees, ["Chef Omar", "Cashier Lana"])
        self.assertTrue(resp.is_name_locked)
        self.assertEqual(resp.name_edited_at, now)

    def test_market_model_has_columns(self):
        self.assertTrue(hasattr(Market, "profile_edited_at"))
        self.assertTrue(hasattr(Market, "name_edited_at"))
        self.assertTrue(hasattr(Market, "address_edited_at"))
        for column in ("governorate", "area", "street", "landmark"):
            self.assertTrue(hasattr(Market, column), column)
        self.assertFalse(hasattr(Market, "address_ar"))
        self.assertTrue(hasattr(Market, "contact_phone"))
        self.assertTrue(hasattr(Market, "contact_email"))
        self.assertTrue(hasattr(Market, "employees"))

    def test_merchant_market_response_has_new_fields(self):
        m_id = uuid.uuid4()
        u_id = uuid.uuid4()
        now = datetime.now(timezone.utc)
        resp = MarketResponse(
            id=m_id,
            merchant_id=u_id,
            name="My Store",
            name_ar="متجري",
            address="King Abdullah St",
            governorate="amman",
            area="عبدون",
            street="King Abdullah St",
            landmark="مقابل المسجد",
            latitude=31.95,
            longitude=35.91,
            is_currently_open=True,
            is_manual_override=False,
            created_at=now,
            contact_phone="0791112233",
            contact_email="store@lamba.app",
            employees=["Staff A"],
            profile_edited_at=now,
            name_edited_at=now,
            is_name_locked=True,
        )
        self.assertEqual(resp.contact_phone, "0791112233")
        self.assertEqual(resp.contact_email, "store@lamba.app")
        self.assertEqual(resp.employees, ["Staff A"])
        self.assertEqual(resp.name_edited_at, now)
        self.assertTrue(resp.is_name_locked)
        self.assertEqual((resp.governorate, resp.area, resp.street), ("amman", "عبدون", "King Abdullah St"))
        self.assertEqual(resp.landmark, "مقابل المسجد")
