from datetime import date

import pytest

from customs_tier_n.parser.customs_parser import InvalidShipmentError, parse_customs


CSV_HEADER = (
    "bill_of_lading_id,shipment_date,shipper_name,shipper_country,"
    "consignee_name,consignee_country,product_description,weight_kg,vessel_name\n"
)


def write_csv(tmp_path, rows: list[str]):
    csv_path = tmp_path / "customs.csv"
    csv_path.write_text(CSV_HEADER + "\n".join(rows) + "\n")
    return csv_path


def test_parse_customs_normalizes_dates_optional_values_and_keeps_duplicates(tmp_path) -> None:
    csv_path = write_csv(
        tmp_path,
        [
            "BOL-001,2026-06-24,  Atlas Minerals Ltd  ,AU,Solstice Materials Co,US,Silica Sand,14531,MV Aurora",
            "BOL-002,13/06/2026,Northshore Chemicals,CA,  Boreal Resins Inc  ,,Epoxy Resin,,",
            "BOL-001,2026-06-24,  Atlas Minerals Ltd  ,AU,Solstice Materials Co,US,Silica Sand,14531,MV Aurora",
        ],
    )

    records = parse_customs(csv_path)

    assert len(records) == 3
    assert records[0].shipment_date == date(2026, 6, 24)
    assert records[0].shipper_name == "Atlas Minerals Ltd"
    assert records[1].shipment_date == date(2026, 6, 13)
    assert records[1].consignee_name == "Boreal Resins Inc"
    assert records[1].consignee_country is None
    assert records[1].weight_kg is None
    assert records[1].vessel_name is None
    assert records[2].bill_of_lading_id == "BOL-001"


@pytest.mark.parametrize("field", ["shipper_name", "consignee_name", "shipment_date", "product_description"])
def test_parse_customs_rejects_rows_missing_required_fields(tmp_path, field: str) -> None:
    values = {
        "bill_of_lading_id": "BOL-INVALID",
        "shipment_date": "2026-06-24",
        "shipper_name": "Atlas Minerals Ltd",
        "shipper_country": "AU",
        "consignee_name": "Solstice Materials Co",
        "consignee_country": "US",
        "product_description": "Silica Sand",
        "weight_kg": "14531",
        "vessel_name": "MV Aurora",
    }
    values[field] = ""
    csv_path = write_csv(tmp_path, [",".join(values.values())])

    with pytest.raises(InvalidShipmentError, match="BOL-INVALID"):
        parse_customs(csv_path)


def test_parse_customs_rejects_omitted_required_header(tmp_path) -> None:
    csv_path = tmp_path / "customs.csv"
    csv_path.write_text(
        "bill_of_lading_id,shipment_date,shipper_name,shipper_country,"
        "consignee_name,consignee_country,weight_kg,vessel_name\n"
        "BOL-MISSING-HEADER,2026-06-24,Atlas Minerals Ltd,AU,Solstice Materials Co,US,14531,MV Aurora\n"
    )

    with pytest.raises(InvalidShipmentError, match="BOL-MISSING-HEADER"):
        parse_customs(csv_path)


def test_parse_customs_rejects_malformed_date(tmp_path) -> None:
    csv_path = write_csv(
        tmp_path,
        [
            "BOL-MALFORMED-DATE,2026/06/24,Atlas Minerals Ltd,AU,"
            "Solstice Materials Co,US,Silica Sand,14531,MV Aurora"
        ],
    )

    with pytest.raises(InvalidShipmentError, match="BOL-MALFORMED-DATE"):
        parse_customs(csv_path)
