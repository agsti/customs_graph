from customs_tier_n.model.entities import DataQualityIssue, Shipment


class ShipmentRepository:
    def __init__(self, shipments: tuple[Shipment, ...] | list[Shipment]) -> None:
        self._shipments = tuple(shipments)
        self._unique_shipments: tuple[Shipment, ...] | None = None
        self._issues: tuple[DataQualityIssue, ...] | None = None

    def unique_shipments(self) -> tuple[Shipment, ...]:
        self._deduplicate()
        assert self._unique_shipments is not None
        return self._unique_shipments

    def issues(self) -> tuple[DataQualityIssue, ...]:
        self._deduplicate()
        assert self._issues is not None
        return self._issues

    def _deduplicate(self) -> None:
        if self._unique_shipments is not None:
            return

        by_bill_of_lading: dict[str, Shipment] = {}
        issues: list[DataQualityIssue] = []
        conflicting_bols: set[str] = set()
        for shipment in self._shipments:
            bill_of_lading_id = shipment.bill_of_lading_id.strip()
            first = by_bill_of_lading.get(bill_of_lading_id)
            if first is None:
                by_bill_of_lading[bill_of_lading_id] = shipment
            elif shipment != first and bill_of_lading_id not in conflicting_bols:
                conflicting_bols.add(bill_of_lading_id)
                issues.append(
                    DataQualityIssue(
                        bill_of_lading_id=bill_of_lading_id,
                        reason="conflicting_duplicate_bol",
                    )
                )

        self._unique_shipments = tuple(by_bill_of_lading.values())
        self._issues = tuple(issues)
