from datetime import date

import pytest

from customs_tier_n.controller.discovery_controller import TierNDiscoveryController
from customs_tier_n.model.entities import (
    Company,
    EvidenceFact,
    GroupFact,
    RegistryFacts,
    ResolvedCompany,
    ResolutionMethod,
    Shipment,
)
from customs_tier_n.repository.company_repository import CompanyRepository
from customs_tier_n.repository.graph_repository import GraphRepository


PASS_THROUGH_TERMS = ("packaging", "freight", "logistics")


def resolved_company(name: str) -> ResolvedCompany:
    return ResolvedCompany(
        company=Company(
            id=f"company:{name.casefold().replace(' ', '-')}:us",
            canonical_name=name,
            country="US",
        ),
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        raw_name=name,
    )


def add_shipment(
    repository: GraphRepository,
    supplier: ResolvedCompany,
    buyer: ResolvedCompany,
    bol_id: str,
    description: str = "silica sand",
) -> None:
    repository.add_shipment(
        Shipment(
            bill_of_lading_id=bol_id,
            shipment_date=date(2026, 1, 1),
            shipper_name=supplier.company.canonical_name,
            shipper_country=supplier.company.country,
            consignee_name=buyer.company.canonical_name,
            consignee_country=buyer.company.country,
            product_description=description,
            weight_kg=500.0,
            vessel_name="MV Atlas",
        ),
        supplier,
        buyer,
    )


def grouped_graph() -> tuple[GraphRepository, ResolvedCompany, ResolvedCompany]:
    facts = RegistryFacts(
        groups=(
            GroupFact(
                group_id="root-group",
                company_names=("Root", "Confirmed Group Member"),
                evidence_id="group-evidence",
            ),
        ),
        evidences=(
            EvidenceFact(
                id="group-evidence",
                source="registry",
                statement="Root and Confirmed Group Member are in one group.",
            ),
        ),
    )
    companies = CompanyRepository(facts)
    registered_root = companies.resolve("Root", "US", threshold=0.94)
    registered_group_member = companies.resolve("Confirmed Group Member", "US", threshold=0.94)
    root = ResolvedCompany(
        company=Company(
            id=registered_root.company.id,
            canonical_name="Root",
            country="US",
        ),
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        raw_name="Root",
    )
    group_member = ResolvedCompany(
        company=Company(
            id=registered_group_member.company.id,
            canonical_name="Confirmed Group Member",
            country="US",
        ),
        method=ResolutionMethod.EXACT,
        confidence=1.0,
        raw_name="Confirmed Group Member",
    )
    repository = GraphRepository()
    repository.add_registry_facts(facts, companies)
    return repository, root, group_member


def test_discovers_tiers_parks_exclusions_and_records_cycle() -> None:
    repository, root, group_member = grouped_graph()
    a = resolved_company("A")
    b = resolved_company("B")
    c = resolved_company("C")
    forwarder = resolved_company("Forwarder")
    add_shipment(repository, a, root, "A-ROOT")
    add_shipment(repository, b, a, "B-A")
    add_shipment(repository, c, b, "C-B")
    add_shipment(repository, a, c, "A-CYCLE")
    add_shipment(repository, group_member, root, "GROUP-ROOT")
    add_shipment(repository, forwarder, root, "FORWARDER-ROOT", "packaging supplies")

    result = TierNDiscoveryController(repository, PASS_THROUGH_TERMS).discover(root.company.id)

    assert result.candidates[a.company.id].tier == 2
    assert result.candidates[b.company.id].tier == 3
    assert result.candidates[c.company.id].tier == 4
    assert group_member.company.id not in result.candidates
    assert forwarder.company.id not in result.candidates
    assert {record.bill_of_lading_id for record in result.parked_shipments} == {
        "GROUP-ROOT",
        "FORWARDER-ROOT",
    }
    assert [(record.company_ids, record.bill_of_lading_id) for record in result.cycles] == [
        ((root.company.id, a.company.id, b.company.id, c.company.id, a.company.id), "A-CYCLE")
    ]

    a_score = 0.90
    b_relationship_score = 0.90
    assert result.candidates[a.company.id].paths[0].score == pytest.approx(a_score)
    assert result.candidates[b.company.id].paths[0].score == pytest.approx(
        a_score * b_relationship_score * 0.90
    )


def test_retains_alternate_paths_and_uses_shallowest_tier_and_strongest_score() -> None:
    repository, root, _ = grouped_graph()
    a = resolved_company("A")
    b = resolved_company("B")
    d = resolved_company("D")
    add_shipment(repository, a, root, "A-ROOT", "unidentified industrial goods")
    add_shipment(repository, b, a, "B-A", "unidentified industrial goods")
    add_shipment(repository, d, root, "D-ROOT")
    add_shipment(repository, b, d, "B-D")

    result = TierNDiscoveryController(repository, PASS_THROUGH_TERMS).discover(root.company.id)

    b_candidate = result.candidates[b.company.id]
    assert b_candidate.tier == 3
    assert len(b_candidate.paths) == 2
    assert sorted(path.score for path in b_candidate.paths) == pytest.approx([0.50625, 0.729])
    assert b_candidate.confidence == pytest.approx(0.729)
    assert b_candidate.label == "Medium"


def test_keeps_mixed_relationship_without_parking_its_pass_through_bol() -> None:
    repository, root, _ = grouped_graph()
    supplier = resolved_company("Mixed Evidence Supplier")
    add_shipment(repository, supplier, root, "PACKAGING-BOL", "packaging supplies")
    add_shipment(repository, supplier, root, "MATERIAL-BOL", "silica sand")

    result = TierNDiscoveryController(repository, PASS_THROUGH_TERMS).discover(root.company.id)

    candidate = result.candidates[supplier.company.id]
    assert candidate.confidence == pytest.approx(0.90)
    assert candidate.paths[0].bol_ids == ("MATERIAL-BOL",)
    assert "PACKAGING-BOL" not in {
        parked_shipment.bill_of_lading_id for parked_shipment in result.parked_shipments
    }


def test_expands_alternate_paths_for_stronger_upstream_confidence_and_cycles() -> None:
    repository, root, _ = grouped_graph()
    a = resolved_company("A")
    b = resolved_company("B")
    c = resolved_company("C")
    d = resolved_company("D")
    add_shipment(repository, a, root, "A-ROOT", "unidentified industrial goods")
    add_shipment(repository, d, root, "D-ROOT")
    add_shipment(repository, b, a, "B-A", "unidentified industrial goods")
    add_shipment(repository, b, d, "B-D")
    add_shipment(repository, c, b, "C-B")
    add_shipment(repository, d, c, "D-C")

    result = TierNDiscoveryController(repository, PASS_THROUGH_TERMS).discover(root.company.id)

    c_candidate = result.candidates[c.company.id]
    assert c_candidate.tier == 4
    assert len(c_candidate.paths) == 2
    assert c_candidate.confidence == pytest.approx(0.59049)
    assert (
        (root.company.id, d.company.id, b.company.id, c.company.id, d.company.id),
        "D-C",
    ) in {(cycle.company_ids, cycle.bill_of_lading_id) for cycle in result.cycles}
