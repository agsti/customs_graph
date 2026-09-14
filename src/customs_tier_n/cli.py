"""Command-line entry point for Tier-N customs discovery."""

import argparse
from pathlib import Path
from typing import Sequence
import webbrowser

from customs_tier_n.controller.discovery_controller import TierNDiscoveryController
from customs_tier_n.parser.customs_parser import InvalidShipmentError, parse_customs_with_issues
from customs_tier_n.repository.company_repository import CompanyRepository
from customs_tier_n.repository.graph_repository import GraphRepository
from customs_tier_n.repository.registry_repository import StaticRegistryRepository
from customs_tier_n.repository.result_repository import ResultRepository
from customs_tier_n.repository.shipment_repository import ShipmentRepository
from customs_tier_n.visualization.browser_graph import BrowserGraph


def main(argv: Sequence[str] | None = None) -> int:
    parser = _parser()
    try:
        arguments = parser.parse_args(argv)
    except SystemExit as error:
        return int(error.code)

    if not arguments.customs.is_file():
        print(f"error: customs file not found: {arguments.customs}")
        return 2

    try:
        parsed_shipments, parsing_issues = parse_customs_with_issues(arguments.customs)
        shipments = ShipmentRepository(parsed_shipments)
        facts = StaticRegistryRepository().get()
        companies = CompanyRepository(facts)

        resolved_shipments = [
            (
                shipment,
                companies.resolve(
                    shipment.shipper_name,
                    shipment.shipper_country,
                    arguments.entity_match_threshold,
                ),
                companies.resolve(
                    shipment.consignee_name,
                    shipment.consignee_country,
                    arguments.entity_match_threshold,
                ),
            )
            for shipment in shipments.unique_shipments()
        ]

        graph = GraphRepository()
        for shipment, shipper, consignee in resolved_shipments:
            graph.add_shipment(shipment, shipper, consignee)
        graph.add_registry_facts(facts, companies)

        root = companies.resolve(arguments.root, None, arguments.entity_match_threshold)
        result = TierNDiscoveryController(graph, facts.pass_through_terms).discover(root.company.id)
        result.data_quality_issues.extend(parsing_issues)
        result.data_quality_issues.extend(shipments.issues())

        candidate_path, candidate_csv_path, parked_path, cycles_path = ResultRepository().write(
            result, arguments.output_dir
        )
        html_path = BrowserGraph().render(result, arguments.output_dir / "tier_n_graph.html")
    except (InvalidShipmentError, OSError, ValueError) as error:
        print(f"error: {error}")
        return 1

    for path in (candidate_path, candidate_csv_path, parked_path, cycles_path, html_path):
        print(path)

    if arguments.open_browser:
        try:
            opened = webbrowser.open(html_path.resolve().as_uri())
            if not opened:
                print(f"warning: could not open browser; view {html_path}")
        except Exception as error:  # Browser availability must not invalidate discovery output.
            print(f"warning: could not open browser; view {html_path} ({error})")
    return 0


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Discover upstream suppliers from customs manifests.")
    parser.add_argument("--customs", type=Path, default=Path("customs_extract.csv"))
    parser.add_argument("--root", default="Solstice Materials Co")
    parser.add_argument(
        "--entity-match-threshold",
        type=_threshold,
        default=0.94,
        metavar="FLOAT",
    )
    parser.add_argument("--output-dir", type=Path, default=Path("output"))
    parser.add_argument(
        "--open-browser",
        action=argparse.BooleanOptionalAction,
        default=True,
    )
    return parser


def _threshold(value: str) -> float:
    try:
        threshold = float(value)
    except ValueError as error:
        raise argparse.ArgumentTypeError("entity-match-threshold must be a number") from error
    if not 0.0 <= threshold <= 1.0:
        raise argparse.ArgumentTypeError("entity-match-threshold must be between 0.0 and 1.0")
    return threshold
