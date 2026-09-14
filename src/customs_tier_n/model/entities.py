from dataclasses import dataclass, field
from datetime import date
from enum import Enum


class ResolutionMethod(str, Enum):
    EXACT = "exact"
    ALIAS = "alias"
    FUZZY = "fuzzy"
    CREATED = "created"


@dataclass(frozen=True, slots=True)
class Company:
    id: str
    canonical_name: str
    country: str | None
    name_variants: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class Shipment:
    bill_of_lading_id: str
    shipment_date: date
    shipper_name: str
    shipper_country: str | None
    consignee_name: str
    consignee_country: str | None
    product_description: str
    weight_kg: float | None
    vessel_name: str | None


@dataclass(frozen=True, slots=True)
class AliasFact:
    canonical_name: str
    canonical_country: str | None
    alias: str
    evidence_id: str


@dataclass(frozen=True, slots=True)
class GroupFact:
    group_id: str
    company_names: tuple[str, ...]
    evidence_id: str


@dataclass(frozen=True, slots=True)
class EvidenceFact:
    id: str
    source: str
    statement: str


@dataclass(frozen=True, slots=True)
class RegistryFacts:
    aliases: tuple[AliasFact, ...] = ()
    groups: tuple[GroupFact, ...] = ()
    evidences: tuple[EvidenceFact, ...] = ()
    unrelated_names: tuple[str, ...] = ()
    pass_through_terms: tuple[str, ...] = ()


@dataclass(slots=True)
class ResolvedCompany:
    company: Company
    method: ResolutionMethod
    confidence: float
    raw_name: str


@dataclass(slots=True)
class RelationshipEvidence:
    supplier: ResolvedCompany
    buyer: ResolvedCompany
    shipments: list[Shipment] = field(default_factory=list)


@dataclass(slots=True)
class ConfidenceBreakdown:
    entity_resolution: float
    material_relevance: float
    repeated_shipments: float
    data_completeness: float
    total: float


@dataclass(slots=True)
class RelationshipPathEvidence:
    supplier_id: str
    buyer_id: str
    score: float
    bol_ids: tuple[str, ...]
    product_descriptions: tuple[str, ...]


@dataclass(slots=True)
class CandidatePath:
    company_ids: tuple[str, ...]
    relationship_scores: tuple[float, ...]
    bol_ids: tuple[str, ...]
    product_descriptions: tuple[str, ...]
    score: float
    relationship_evidence: tuple[RelationshipPathEvidence, ...] = ()


@dataclass(slots=True)
class Candidate:
    company: Company
    tier: int
    paths: list[CandidatePath] = field(default_factory=list)
    confidence: float = 0.0
    label: str = "Low"


@dataclass(slots=True)
class ParkedShipment:
    bill_of_lading_id: str
    reason: str
    supplier_id: str | None = None
    buyer_id: str | None = None


@dataclass(slots=True)
class DataQualityIssue:
    bill_of_lading_id: str
    reason: str


@dataclass(slots=True)
class CycleRecord:
    company_ids: tuple[str, ...]
    bill_of_lading_id: str


@dataclass(slots=True)
class DiscoveryResult:
    root_company_id: str
    candidates: dict[str, Candidate] = field(default_factory=dict)
    parked_shipments: list[ParkedShipment] = field(default_factory=list)
    data_quality_issues: list[DataQualityIssue] = field(default_factory=list)
    cycles: list[CycleRecord] = field(default_factory=list)
