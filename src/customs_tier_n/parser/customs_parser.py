import csv
import math
from datetime import date, datetime
from pathlib import Path

from customs_tier_n.model.entities import DataQualityIssue, Shipment


class InvalidShipmentError(ValueError):
    """Raised when a customs row lacks data required for discovery."""

    def __init__(self, record_id: str, reason: str) -> None:
        self.record_id = record_id
        self.reason = reason
        super().__init__(f"Shipment {record_id}: {reason}")


def parse_customs(path: Path) -> list[Shipment]:
    """Parse every customs row in *path*, preserving source order and duplicates."""
    with path.open(newline="") as customs_file:
        rows = csv.DictReader(customs_file)
        return [_parse_shipment(row, row_number) for row_number, row in enumerate(rows, start=2)]


def parse_customs_with_issues(path: Path) -> tuple[list[Shipment], list[DataQualityIssue]]:
    """Parse valid rows and retain traceable quality issues for malformed rows."""
    shipments: list[Shipment] = []
    issues: list[DataQualityIssue] = []
    with path.open(newline="") as customs_file:
        rows = csv.DictReader(customs_file)
        for row_number, row in enumerate(rows, start=2):
            try:
                shipments.append(_parse_shipment(row, row_number))
            except InvalidShipmentError as error:
                issues.append(DataQualityIssue(error.record_id, error.reason))
    return shipments, issues


def _parse_shipment(row: dict[str, str | None], row_number: int) -> Shipment:
    fields = (
        "bill_of_lading_id",
        "shipment_date",
        "shipper_name",
        "shipper_country",
        "consignee_name",
        "consignee_country",
        "product_description",
        "weight_kg",
        "vessel_name",
    )
    values = {field: (row.get(field) or "").strip() for field in fields}
    bill_of_lading_id = values["bill_of_lading_id"]
    record_id = bill_of_lading_id or f"row:{row_number}"
    _require(values, record_id)

    return Shipment(
        bill_of_lading_id=bill_of_lading_id,
        shipment_date=_parse_date(values["shipment_date"], record_id),
        shipper_name=values["shipper_name"],
        shipper_country=_optional(values["shipper_country"]),
        consignee_name=values["consignee_name"],
        consignee_country=_optional(values["consignee_country"]),
        product_description=values["product_description"],
        weight_kg=_parse_weight(values["weight_kg"], record_id),
        vessel_name=_optional(values["vessel_name"]),
    )


def _require(values: dict[str, str], record_id: str) -> None:
    required_fields = (
        "bill_of_lading_id",
        "shipper_name",
        "consignee_name",
        "shipment_date",
        "product_description",
    )
    missing_fields = [field for field in required_fields if not values[field]]
    if missing_fields:
        raise InvalidShipmentError(record_id, f"missing_required_fields:{','.join(missing_fields)}")


def _parse_date(value: str, bill_of_lading_id: str) -> date:
    for format_string in ("%Y-%m-%d", "%d/%m/%Y"):
        try:
            return datetime.strptime(value, format_string).date()
        except ValueError:
            continue
    raise InvalidShipmentError(bill_of_lading_id, "invalid_shipment_date")


def _optional(value: str) -> str | None:
    return value or None


def _parse_weight(value: str, record_id: str) -> float | None:
    if not value:
        return None
    try:
        weight = float(value)
    except ValueError as error:
        raise InvalidShipmentError(record_id, "invalid_weight") from error
    if not math.isfinite(weight):
        raise InvalidShipmentError(record_id, "invalid_weight")
    return weight
