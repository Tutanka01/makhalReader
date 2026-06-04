from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Optional


@dataclass
class SourceIntent:
    query: str
    category: Optional[str] = None
    filters: dict[str, Any] = field(default_factory=dict)


@dataclass
class ResolvedSource:
    name: str
    provider: str
    query_json: dict[str, Any]
    label: str = ""
    provenance_url: str = ""
    category: str = ""


@dataclass
class VerifiedSource:
    verified: bool
    sample_count: int = 0
    message: str = ""


class SourceProvider(ABC):
    provider_id: str = ""

    @abstractmethod
    async def resolve(self, intent: SourceIntent) -> list[ResolvedSource]:
        ...

    @abstractmethod
    async def verify(self, source: ResolvedSource) -> VerifiedSource:
        ...
