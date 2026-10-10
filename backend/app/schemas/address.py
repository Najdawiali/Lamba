"""The structured address of a store as customers receive it."""

from typing import Optional

from pydantic import BaseModel


class AddressParts(BaseModel):
    """
    Next to the one-line `address` text. `governorate` is a key (balqa, amman, ...): the app shows
    its name in the user's language. Everything else is text exactly as the merchant typed it.
    None of the fields is guaranteed; a store from before the structured address has no parts.
    """
    governorate: Optional[str] = None
    area: Optional[str] = None
    street: Optional[str] = None
    landmark: Optional[str] = None
