from .arxiv import ArxivProvider
from .base import ResolvedSource, SourceIntent, SourceProvider, VerifiedSource
from .crossref import CrossrefProvider
from .dblp import DblpProvider
from .doaj import DoajProvider
from .generic_rss import GenericRSSProvider
from .hal import HalProvider
from .openalex import OpenAlexProvider
from .openreview import OpenReviewProvider

PROVIDER_REGISTRY: dict[str, type[SourceProvider]] = {
    "openalex": OpenAlexProvider,
    "crossref": CrossrefProvider,
    "arxiv": ArxivProvider,
    "doaj": DoajProvider,
    "hal": HalProvider,
    "dblp": DblpProvider,
    "openreview": OpenReviewProvider,
    "rss": GenericRSSProvider,
}

__all__ = [
    "SourceProvider",
    "ResolvedSource",
    "VerifiedSource",
    "SourceIntent",
    "OpenAlexProvider",
    "CrossrefProvider",
    "ArxivProvider",
    "DoajProvider",
    "HalProvider",
    "DblpProvider",
    "OpenReviewProvider",
    "GenericRSSProvider",
    "PROVIDER_REGISTRY",
]
