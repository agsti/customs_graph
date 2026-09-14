"""Pure relationship-confidence calculations for supplier discovery."""

from customs_tier_n.model.entities import ConfidenceBreakdown, RelationshipEvidence, Shipment


MATERIAL_STEMS = (
    "alumina",
    "titanium",
    "pigment",
    "silica",
    "quartz",
    "borate",
    "resin",
    "bisphenol",
    "phenol",
    "benzene",
    "feedstock",
    "ore",
    "flocculant",
    "acrylamide",
    "monomer",
    "reagent",
    "cobalt",
    "chemical",
)


def classify_material(description: str, pass_through_terms: tuple[str, ...]) -> float | None:
    """Classify a shipment description without depending on graph infrastructure."""
    normalized_description = description.casefold()
    if any(term.casefold() in normalized_description for term in pass_through_terms):
        return None
    if any(stem in normalized_description for stem in MATERIAL_STEMS):
        return 1.0
    return 0.5


def score_relationship(
    evidence: RelationshipEvidence, pass_through_terms: tuple[str, ...]
) -> ConfidenceBreakdown | None:
    """Score the eligible shipment evidence between one supplier and buyer."""
    eligible = [
        (shipment, classification)
        for shipment in evidence.shipments
        if (classification := classify_material(shipment.product_description, pass_through_terms))
        is not None
    ]
    if not eligible:
        return None

    shipments = [shipment for shipment, _ in eligible]
    material_relevance = sum(classification for _, classification in eligible) / len(eligible)
    repeated_shipments = _repeated_shipments_score(shipments)
    data_completeness = sum(_data_completeness(shipment) for shipment in shipments) / len(
        shipments
    )
    entity_resolution = min(evidence.supplier.confidence, evidence.buyer.confidence)

    return ConfidenceBreakdown(
        entity_resolution=entity_resolution,
        material_relevance=material_relevance,
        repeated_shipments=repeated_shipments,
        data_completeness=data_completeness,
        total=(
            0.30 * entity_resolution
            + 0.30 * material_relevance
            + 0.25 * repeated_shipments
            + 0.15 * data_completeness
        ),
    )


def confidence_label(score: float) -> str:
    if score >= 0.75:
        return "High"
    if score >= 0.45:
        return "Medium"
    return "Low"


def _repeated_shipments_score(shipments: list[Shipment]) -> float:
    distinct_bols = len({shipment.bill_of_lading_id for shipment in shipments})
    if distinct_bols >= 3:
        return 1.0
    if distinct_bols == 2:
        return 0.8
    return 0.6


def _data_completeness(shipment: Shipment) -> float:
    score = 1.0
    if shipment.shipper_country is None or shipment.consignee_country is None:
        score -= 0.1
    if shipment.weight_kg is None:
        score -= 0.05
    return score
