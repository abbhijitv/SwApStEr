"""Account request contracts reject browser-supplied ownership or state."""
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from backend.models.schemas import Listing, Preferences

Version = Annotated[int, Field(strict=True, ge=0)]


class AccountListing(Listing):
    model_config = ConfigDict(extra='forbid')


class ListingUpdate(AccountListing):
    version: Version


class NegotiationStart(Preferences):
    model_config = ConfigDict(extra='forbid')
    rental_days: int | None = Field(default=None, ge=1, le=90)
    provider: Literal['mock', 'ollama'] = 'mock'
    location: str = Field(default='', min_length=2, max_length=100)

    @model_validator(mode='after')
    def item_location(self):
        if not self.housing and len(self.location.strip()) < 2:
            raise ValueError('A proposed pickup location is required')
        return self


class ExpectedVersion(BaseModel):
    model_config = ConfigDict(extra='forbid')
    version: Version


class HumanDecision(ExpectedVersion):
    decision: Literal['approve', 'reject']
