import json
from pathlib import Path
from unittest.mock import patch

from customs_tier_n.cli import main


CUSTOMS_PATH = Path(__file__).parents[1] / "customs_extract.csv"


def test_main_writes_all_outputs_without_opening_a_browser(tmp_path) -> None:
    exit_code = main(
        [
            "--customs",
            str(CUSTOMS_PATH),
            "--output-dir",
            str(tmp_path),
            "--entity-match-threshold",
            "0.94",
            "--no-open-browser",
        ]
    )

    assert exit_code == 0
    assert {path.name for path in tmp_path.iterdir()} == {
        "tier_n_candidates.json",
        "tier_n_candidates.csv",
        "parked_shipments.json",
        "cycles.json",
        "tier_n_graph.html",
    }


def test_main_opens_the_rendered_html_by_default(tmp_path) -> None:
    with patch("customs_tier_n.cli.webbrowser.open") as open_browser:
        exit_code = main(["--customs", str(CUSTOMS_PATH), "--output-dir", str(tmp_path)])

    assert exit_code == 0
    open_browser.assert_called_once_with((tmp_path / "tier_n_graph.html").resolve().as_uri())


def test_main_discovers_known_tiers_and_parks_excluded_real_data(tmp_path) -> None:
    exit_code = main(
        [
            "--customs",
            str(CUSTOMS_PATH),
            "--root",
            "Solstice Materials Co",
            "--entity-match-threshold",
            "0.94",
            "--output-dir",
            str(tmp_path),
            "--no-open-browser",
        ]
    )

    assert exit_code == 0
    candidates = {
        item["company"]["canonical_name"]: item
        for item in json.loads((tmp_path / "tier_n_candidates.json").read_text())["candidates"]
    }
    parked = json.loads((tmp_path / "parked_shipments.json").read_text())["parked_shipments"]

    assert candidates["Terra Silica Partners"]["tier"] == 2
    assert candidates["Quartz Extraction Co"]["tier"] == 3
    assert candidates["Acrylamide Monomer Pty"]["tier"] == 5
    assert "Bergwerk Mining Alias GmbH" not in candidates
    assert "Solstice Materials Europe GmbH" not in candidates
    assert any(item["reason"] == "intra_group" for item in parked)
    assert any(item["reason"] == "freight_logistics_or_packaging" for item in parked)


def test_main_records_malformed_rows_and_still_writes_valid_discovery_artifacts(tmp_path) -> None:
    customs_path = tmp_path / "mixed.csv"
    customs_path.write_text(
        "bill_of_lading_id,shipment_date,shipper_name,shipper_country,"
        "consignee_name,consignee_country,product_description,weight_kg,vessel_name\n"
        "BOL-VALID,2026-01-01,Valid Supplier,US,Root,US,silica sand,100,MV Atlas\n"
        "BOL-BAD-DATE,2026/01/01,Bad Date Supplier,US,Root,US,silica sand,100,MV Atlas\n"
        ",2026-01-01,No Bol Supplier,US,Root,US,silica sand,100,MV Atlas\n"
    )

    exit_code = main(
        [
            "--customs",
            str(customs_path),
            "--root",
            "Root",
            "--output-dir",
            str(tmp_path / "output"),
            "--no-open-browser",
        ]
    )

    output_dir = tmp_path / "output"
    assert exit_code == 0
    candidates = json.loads((output_dir / "tier_n_candidates.json").read_text())["candidates"]
    issues = json.loads((output_dir / "parked_shipments.json").read_text())["data_quality_issues"]
    assert {candidate["company"]["canonical_name"] for candidate in candidates} == {
        "Valid Supplier"
    }
    assert {(issue["bill_of_lading_id"], issue["reason"]) for issue in issues} == {
        ("BOL-BAD-DATE", "invalid_shipment_date"),
        ("row:4", "missing_required_fields:bill_of_lading_id"),
    }


def test_main_keeps_unregistered_supplier_confidence_independent_of_csv_row_order(tmp_path) -> None:
    header = (
        "bill_of_lading_id,shipment_date,shipper_name,shipper_country,"
        "consignee_name,consignee_country,product_description,weight_kg,vessel_name\n"
    )
    solstice_row = (
        "BOL-SOLSTICE,2026-01-01,Supplier,US,Solstice Materials Co,US,"
        "silica sand,100,MV Atlas\n"
    )
    analytics_row = (
        "BOL-ANALYTICS,2026-01-02,Supplier,US,Solstice Analytics Inc,US,"
        "silica sand,100,MV Atlas\n"
    )

    def supplier_confidence(name: str, rows: tuple[str, str]) -> float:
        customs_path = tmp_path / f"{name}.csv"
        output_dir = tmp_path / name
        customs_path.write_text(header + "".join(rows))
        assert main(
            [
                "--customs",
                str(customs_path),
                "--output-dir",
                str(output_dir),
                "--no-open-browser",
            ]
        ) == 0
        candidates = json.loads((output_dir / "tier_n_candidates.json").read_text())["candidates"]
        return next(
            candidate["confidence"]
            for candidate in candidates
            if candidate["company"]["canonical_name"] == "Supplier"
        )

    assert supplier_confidence("solstice-first", (solstice_row, analytics_row)) == 0.78
    assert supplier_confidence("analytics-first", (analytics_row, solstice_row)) == 0.78
