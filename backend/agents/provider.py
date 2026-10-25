from typing import Protocol
from backend.models.schemas import Action
class Provider(Protocol):
    def decide(self, context: dict) -> Action: ...
