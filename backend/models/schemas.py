import os
from datetime import datetime, date
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
class HousingDetails(BaseModel):
    listing_type: Literal['Apartment sublease', 'Private room sublease', 'Room rental']
    neighborhood: str = Field(min_length=2, max_length=120)
    lease_start: date
    lease_end: date
    furnished: bool
    utilities_included: bool
    bedrooms: int = Field(ge=1, le=12)
    bathrooms: float = Field(gt=0, le=12)
    roommate_info: str = Field(default='', max_length=1000)
    @model_validator(mode='after')
    def valid(self):
        if self.lease_end <= self.lease_start: raise ValueError('Lease end must follow lease start')
        return self
class HousingPreferences(BaseModel):
    desired_move_in: date
    desired_move_out: date
    preferred_location: str = Field(default='', max_length=120)
    furnished: Optional[bool] = None
    utilities_included: Optional[bool] = None
    move_in_flex_days: int = Field(default=0, ge=0, le=14)
    requirements: str = Field(default='', max_length=1000)
    @model_validator(mode='after')
    def valid(self):
        if self.desired_move_out <= self.desired_move_in: raise ValueError('Move-out must follow move-in')
        return self
class Listing(BaseModel):
    title: str = Field(min_length=3, max_length=120)
    description: str = Field(min_length=5, max_length=2000)
    category: str
    course: str = ''
    condition: str = 'Like new'
    price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    minimum: Decimal = Field(ge=0, max_digits=8, decimal_places=2)
    type: Literal['Rent', 'Buy'] = 'Rent'
    rental_days: int = Field(default=3, ge=1, le=90)
    windows: list[Window] = Field(default_factory=list)
    available_until: Optional[datetime] = None
    housing: Optional[HousingDetails] = None
    restrictions: str = Field(default='Return in the same condition.', max_length=1000)
    @model_validator(mode='after')
    def valid(self):
        if self.minimum > self.price: raise ValueError('Minimum exceeds asking price')
        if self.category == 'Housing & Subleases':
            if not self.housing or self.type != 'Rent': raise ValueError('Housing requires rental details')
        elif self.housing or not self.windows or not self.available_until or self.available_until.tzinfo is None:
            raise ValueError('Items require pickup windows and timezone-aware availability')
        return self
class Preferences(BaseModel):
    listing_id: int
    target: Optional[Decimal] = Field(default=None, gt=0, max_digits=8, decimal_places=2)
    maximum: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    rental_days: int = Field(default=3, ge=1, le=90)
    deadline: Optional[datetime] = None
    housing: Optional[HousingPreferences] = None
    windows: list[Window] = Field(default_factory=list)
    location: str = Field(default='Hayden Library', min_length=2, max_length=100)
    provider: Literal['mock', 'ollama'] = Field(default_factory=lambda: os.getenv('AI_PROVIDER','ollama'))
    @model_validator(mode='after')
    def valid(self):
        if self.housing and self.target is None: self.target = (self.maximum * Decimal('0.9')).quantize(Decimal('0.01'))
        if self.target is None: raise ValueError('Item target is required')
        if self.target > self.maximum: raise ValueError('Target exceeds maximum')
        if not self.housing and (not self.windows or not self.deadline or self.deadline.tzinfo is None): raise ValueError('Items require pickup windows and a timezone-aware deadline')
        return self
class Terms(BaseModel):
    price: Decimal = Field(gt=0, max_digits=8, decimal_places=2)
    pickup: Optional[datetime] = None
    location: str
    rental_days: Optional[int] = None
    transaction: Literal['item', 'housing', 'purchase'] = 'item'
    lease_start: Optional[date] = None
    lease_end: Optional[date] = None
    @model_validator(mode='after')
    def valid(self):
        if self.transaction == 'housing':
            if not self.lease_start or not self.lease_end or self.lease_end <= self.lease_start or self.pickup is not None or self.rental_days is not None:
                raise ValueError('Housing requires ordered lease dates without item pickup terms')
        elif self.transaction == 'purchase':
            if self.pickup is None or self.rental_days is not None or self.lease_start or self.lease_end:
                raise ValueError('Purchases require pickup without rental duration or lease dates')
        elif self.pickup is None or self.rental_days is None or self.lease_start or self.lease_end:
            raise ValueError('Item terms require pickup and duration')
        return self
class Action(BaseModel):
    message: Optional[str] = Field(default=None, max_length=400)
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
