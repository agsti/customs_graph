from datetime import date

import pytest

from customs_tier_n.model.confidence import (
    classify_material,
    confidence_label,
    score_relationship,
)
from customs_tier_n.model.entities import (
    Company,
    RelationshipEvidence,
    ResolvedCompany,
    ResolutionMethod,
    Shipment,
)


PASS_THROUGH_TERMS = ("packaging", "freight", "logistics")


def resolved_company(name: str, confidence: float = 1.0) -> ResolvedCompany:
    return ResolvedCompany(
        company=Company(id=f"company:{name.lower()}", canonical_name=name, country="US"),
        method=ResolutionMethod.EXACT,
        confidence=confidence,
        raw_name=name,
    )


def shipment(
    bol_id: str,
    description: str = "Titanium dioxide pigment",
    *,
    shipper_country: str | None = "US",
    consignee_country: str | None = "DE",
    weight_kg: float | None = 1200.0,
    vessel_name: str | None = "MV Atlas",
) -> Shipment:
    return Shipment(
        bill_of_lading_id=bol_id,
        shipment_date=date(2026, 1, 1),
        shipper_name="Supplier",
        shipper_country=shipper_country,
        consignee_name="Buyer",
        consignee_country=consignee_country,
        product_description=description,
        weight_kg=weight_kg,
        vessel_name=vessel_name,
    )


def relationship(*shipments: Shipment) -> RelationshipEvidence:
    return RelationshipEvidence(
        supplier=resolved_company("Supplier"),
        buyer=resolved_company("Buyer"),
        shipments=list(shipments),
    )


def test_scores_exact_material_relationship_with_two_bols() -> None:
    breakdown = score_relationship(
        relationship(shipment("BOL-1"), shipment("BOL-2")),
        pass_through_terms=PASS_THROUGH_TERMS,
    )

    assert breakdown is not None
    assert breakdown.entity_resolution == 1.0
    assert breakdown.material_relevance == 1.0
    assert breakdown.repeated_shipments == 0.8
    assert breakdown.data_completeness == 1.0
    assert breakdown.total == pytest.approx(0.95)


def test_classify_material_excludes_pass_through_terms() -> None:
    assert classify_material("industrial packaging supplies", PASS_THROUGH_TERMS) is None


def test_classify_material_scores_unclear_product_at_half_relevance() -> None:
    assert classify_material("unidentified industrial goods", PASS_THROUGH_TERMS) == 0.5


@pytest.mark.parametrize(
    ("bol_count", "expected_score"),
    ((1, 0.60), (2, 0.80), (3, 1.00)),
)
def test_scores_repeated_shipments_by_distinct_bol_count(
    bol_count: int, expected_score: float
) -> None:
    evidence = relationship(*(shipment(f"BOL-{number}") for number in range(bol_count)))

    breakdown = score_relationship(evidence, pass_through_terms=PASS_THROUGH_TERMS)

    assert breakdown is not None
    assert breakdown.repeated_shipments == expected_score


def test_missing_country_reduces_data_completeness_by_ten_points() -> None:
    breakdown = score_relationship(
        relationship(shipment("BOL-1", shipper_country=None)),
        pass_through_terms=PASS_THROUGH_TERMS,
    )

    assert breakdown is not None
    assert breakdown.data_completeness == pytest.approx(0.90)


def test_missing_weight_reduces_data_completeness_by_five_points() -> None:
    breakdown = score_relationship(
        relationship(shipment("BOL-1", weight_kg=None)),
        pass_through_terms=PASS_THROUGH_TERMS,
    )

    assert breakdown is not None
    assert breakdown.data_completeness == pytest.approx(0.95)


def test_missing_vessel_does_not_reduce_data_completeness() -> None:
    breakdown = score_relationship(
        relationship(shipment("BOL-1", vessel_name=None)),
        pass_through_terms=PASS_THROUGH_TERMS,
    )

    assert breakdown is not None
    assert breakdown.data_completeness == 1.0


def test_returns_none_when_every_shipment_is_pass_through() -> None:
    breakdown = score_relationship(
        relationship(shipment("BOL-1", "Freight forwarding service")),
        pass_through_terms=PASS_THROUGH_TERMS,
    )

    assert breakdown is None


def test_entity_resolution_uses_the_lower_endpoint_confidence() -> None:
    evidence = relationship(shipment("BOL-1"))
    evidence.supplier = resolved_company("Supplier", confidence=0.75)
    evidence.buyer = resolved_company("Buyer", confidence=0.90)

    breakdown = score_relationship(evidence, pass_through_terms=PASS_THROUGH_TERMS)

    assert breakdown is not None
    assert breakdown.entity_resolution == 0.75


def test_weights_each_confidence_component_as_specified() -> None:
    evidence = relationship(
        shipment("BOL-1", "unidentified industrial goods", shipper_country=None)
    )
    evidence.supplier = resolved_company("Supplier", confidence=0.8)

    breakdown = score_relationship(evidence, pass_through_terms=PASS_THROUGH_TERMS)

    assert breakdown is not None
    assert breakdown.total == pytest.approx(0.675)


@pytest.mark.parametrize(
    ("score", "expected_label"),
    ((0.75, "High"), (0.45, "Medium"), (0.44, "Low")),
)
def test_confidence_label_uses_high_medium_low_thresholds(
    score: float, expected_label: str
) -> None:
    assert confidence_label(score) == expected_label
