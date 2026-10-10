from pydantic import BaseModel, field_validator
from typing import Optional, List
from datetime import datetime

class MarketProfileUpdate(BaseModel):
    """Update store name and contact info. The name can be changed once (checked in the endpoint).
    The location has its own endpoint: PUT /api/v1/merchant/market/location."""
    name: Optional[str] = None
    name_ar: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None

    @field_validator('name', 'name_ar')
    @classmethod
    def validate_non_empty_string(cls, v):
        if v is not None:
            cleaned = v.strip()
            if not cleaned:
                raise ValueError('Field cannot be empty')
            return cleaned
        return v

    @field_validator('contact_phone')
    @classmethod
    def validate_phone(cls, v):
        if v is not None:
            cleaned = v.strip().replace(' ', '').replace('-', '')
            if not cleaned or not cleaned.replace('+', '').isdigit() or len(cleaned) < 7 or len(cleaned) > 20:
                raise ValueError('Invalid phone number format')
            return v.strip()
        return v

    @field_validator('contact_email')
    @classmethod
    def validate_email(cls, v):
        if v is not None:
            cleaned = v.strip()
            if cleaned:
                if '@' not in cleaned or '.' not in cleaned.split('@')[-1]:
                    raise ValueError('Invalid email format')
                return cleaned
            return None
        return v

class EmployeesUpdate(BaseModel):
    """Replace the entire employees list. At least one employee is required."""
    employees: List[str]

    @field_validator('employees')
    @classmethod
    def validate_employees(cls, v):
        cleaned = [name.strip() for name in v if name.strip()]
        if len(cleaned) < 1:
            raise ValueError('At least one employee is required')
        if len(cleaned) > 50:
            raise ValueError('Maximum 50 employees allowed')
        return cleaned

class MarketProfileResponse(BaseModel):
    name: Optional[str] = None
    name_ar: Optional[str] = None
    contact_phone: Optional[str] = None
    contact_email: Optional[str] = None
    employees: List[str] = []
    profile_edited_at: Optional[datetime] = None
    name_edited_at: Optional[datetime] = None
    is_name_locked: bool = False

    model_config = {"from_attributes": True}
