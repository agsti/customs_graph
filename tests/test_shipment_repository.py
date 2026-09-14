from datetime import date

from customs_tier_n.model.entities import DataQualityIssue, Shipment
from customs_tier_n.repository.shipment_repository import ShipmentRepository


def shipment(*, product_description: str = "titanium ore concentrate") -> Shipment:
    return Shipment(
        bill_of_lading_id="BOL100021",
        shipment_date=date(2026, 4, 30),
        shipper_name="Rutile Mineral Exports Pty",
        shipper_country="AU",
        consignee_name="Aurora Pigments Ltd",
        consignee_country="US",
        product_description=product_description,
        weight_kg=43160,
        vessel_name="MV Southern Cross",
    )


def test_unique_shipments_ignores_exact_duplicate_bol_rows() -> None:
    record = shipment()
    repository = ShipmentRepository((record, record))

    assert repository.unique_shipments() == (record,)
    assert repository.issues() == ()


def test_unique_shipments_retains_first_conflicting_duplicate_and_reports_issue() -> None:
    first = shipment()
    repository = ShipmentRepository((first, shipment(product_description="rutile concentrate")))

    assert repository.unique_shipments() == (first,)
    assert repository.issues() == (
        DataQualityIssue(
            bill_of_lading_id="BOL100021",
            reason="conflicting_duplicate_bol",
        ),
    )
