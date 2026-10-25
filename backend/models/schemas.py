import os
from datetime import datetime
from decimal import Decimal
from typing import Literal, Optional
from pydantic import BaseModel, Field, model_validator, ConfigDict
class Window(BaseModel):
    start: datetime
    end: datetime
    @model_validator(mode='after')
    def valid(self):
        if self.start.tzinfo is None or self.end.tzinfo is None or self.end <= self.start:
            raise ValueError('Use timezone-aware, ordered pickup windows')
        return self
class Listing(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=2000)
    category: str
    course: str
    condition: str = 'Like new'
    price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    minimum: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    type: Literal['Rent', 'Buy'] = 'Rent'
    rental_days: int = Field(default=3, ge=1, le=90)
    windows: list[Window] = Field(min_length=1)
    available_until: datetime
    restrictions: str = Field(default='Return in the same condition.', max_length=1000)
    @model_validator(mode='after')
    def valid(self):
        if self.minimum > self.price: raise ValueError('Minimum exceeds asking price')
        if self.available_until.tzinfo is None: raise ValueError('Availability requires timezone')
        return self
class Preferences(BaseModel):
    listing_id: int
    target: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    maximum: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    rental_days: int = Field(default=3, ge=1, le=90)
    deadline: datetime
    windows: list[Window] = Field(min_length=1)
    location: str = Field(default='Hayden Library', min_length=2, max_length=100)
    provider: Literal['mock', 'ollama'] = Field(default_factory=lambda: os.getenv('AI_PROVIDER','ollama'))
    @model_validator(mode='after')
    def valid(self):
        if self.target > self.maximum: raise ValueError('Target exceeds maximum')
        if self.deadline.tzinfo is None: raise ValueError('Deadline requires timezone')
        return self
class Terms(BaseModel):
    price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    pickup: datetime
    location: str
    rental_days: int
class Action(BaseModel):
    action: Literal['OFFER', 'COUNTER', 'ACCEPT', 'REJECT']
    terms: Optional[Terms] = None

class StudentCreate(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True, extra='forbid')
    display_name: str = Field(min_length=1, max_length=80)
    university: Optional[str] = Field(default=None, max_length=120)
    course_or_major: Optional[str] = Field(default=None, max_length=120)

    @model_validator(mode='after')
    def validate_profile(self):
        for field in ('display_name', 'university', 'course_or_major'):
            value = getattr(self, field)
            if value and any(ord(c) < 32 or ord(c) == 127 for c in value):
                raise ValueError('Profile fields cannot contain control characters')
            if field != 'display_name' and value == '':
                setattr(self, field, None)
        return self
