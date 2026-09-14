from datetime import date

import pytest

from customs_tier_n.model.confidence import score_relationship
from customs_tier_n.model.entities import (
    Company,
    GroupFact,
    RegistryFacts,
    ResolvedCompany,
    ResolutionMethod,
    Shipment,
)
from customs_tier_n.repository.company_repository import CompanyRepository, normalize_company_name
from customs_tier_n.repository.graph_repository import GraphRepository
from customs_tier_n.repository.registry_repository import StaticRegistryRepository


def shipment() -> Shipment:
    return Shipment(
        bill_of_lading_id="BOL100007",
        shipment_date=date(2026, 6, 24),
        shipper_name="Terra Silica Partners",
        shipper_country="US",
        consignee_name="Solstice Materials Co",
        consignee_country="US",
        product_description="  Silica   Sand ",
        weight_kg=14531,
        vessel_name=None,
    )


def test_add_shipment_creates_typed_evidence_nodes_and_edges() -> None:
    facts = StaticRegistryRepository().get()
    companies = CompanyRepository(facts)
    terra = companies.resolve("Terra Silica Partners", "US", threshold=0.94)
    solstice = companies.resolve("Solstice Materials Co", "US", threshold=0.94)
    repository = GraphRepository()

    repository.add_shipment(shipment(), terra, solstice)

    product_id = f"product:{normalize_company_name('Silica Sand')}"
    assert repository.graph.nodes[terra.company.id]["node_type"] == "company"
    assert repository.graph.nodes["shipment:BOL100007"]["node_type"] == "shipment"
    assert repository.graph.nodes[product_id]["node_type"] == "product"
    assert repository.graph.has_edge(terra.company.id, "shipment:BOL100007", key="shipped")
    assert repository.graph.has_edge("shipment:BOL100007", solstice.company.id, key="consigned_to")
    assert repository.graph.has_edge("shipment:BOL100007", product_id, key="carries")
    assert repository.graph.edges[terra.company.id, "shipment:BOL100007", "shipped"]["edge_type"] == "shipped"


def test_registry_claims_confirm_groups_and_inbound_query_aggregates_shipments() -> None:
    facts = StaticRegistryRepository().get()
    companies = CompanyRepository(facts)
    terra = companies.resolve("Terra Silica Partners", "US", threshold=0.94)
    solstice = companies.resolve("Solstice Materials Co", "US", threshold=0.94)
    europe = companies.resolve("Solstice Materials Europe GmbH", "DE", threshold=0.94)
    analytics = companies.resolve("Solstice Analytics Inc", "US", threshold=0.94)
    repository = GraphRepository()

    repository.add_shipment(shipment(), terra, solstice)
    repository.add_registry_facts(facts, companies)

    claim_id = f"group-membership:{facts.groups[0].group_id}:{solstice.company.id}"
    group_id = f"corporate-group:{facts.groups[0].group_id}"
    evidence_id = f"evidence:{facts.groups[0].evidence_id}"
    assert repository.graph.nodes[group_id]["node_type"] == "corporate_group"
    assert repository.graph.nodes[claim_id]["node_type"] == "group_membership_claim"
    assert repository.graph.nodes[evidence_id]["node_type"] == "evidence"
    assert repository.graph.has_edge(
        solstice.company.id, claim_id, key=f"subject_of:{claim_id}"
    )
    assert repository.graph.has_edge(claim_id, group_id, key=f"member_of:{claim_id}")
    assert repository.graph.has_edge(evidence_id, claim_id, key=f"supports:{claim_id}")
    assert repository.same_confirmed_group(solstice.company.id, europe.company.id) is True
    assert repository.same_confirmed_group(solstice.company.id, analytics.company.id) is False

    relationships = repository.inbound_relationships(solstice.company.id)

    assert relationships[0].supplier.company.id == terra.company.id
    assert relationships[0].buyer.company.id == solstice.company.id
    assert relationships[0].shipments[0].bill_of_lading_id == "BOL100007"


def test_same_confirmed_group_rejects_unsupported_membership_claim() -> None:
    facts = StaticRegistryRepository().get()
    companies = CompanyRepository(facts)
    solstice = companies.resolve("Solstice Materials Co", "US", threshold=0.94)
    analytics = companies.resolve("Solstice Analytics Inc", "US", threshold=0.94)
    repository = GraphRepository()
    repository.add_registry_facts(facts, companies)
    group_id = f"corporate-group:{facts.groups[0].group_id}"
    unsupported_claim_id = f"group-membership:inferred:{analytics.company.id}"
    repository.graph.add_node(
        unsupported_claim_id,
        node_type="group_membership_claim",
    )
    repository.graph.add_edge(
        analytics.company.id,
        unsupported_claim_id,
        key=f"subject_of:{unsupported_claim_id}",
        edge_type="subject_of",
    )
    repository.graph.add_edge(
        unsupported_claim_id,
        group_id,
        key=f"member_of:{unsupported_claim_id}",
        edge_type="member_of",
    )

    assert repository.same_confirmed_group(solstice.company.id, analytics.company.id) is False


def test_same_confirmed_group_rejects_group_with_missing_evidence_fact() -> None:
    facts = RegistryFacts(
        groups=(
            GroupFact(
                group_id="unverified-group",
                company_names=("Alpha Minerals Ltd", "Beta Materials Ltd"),
                evidence_id="missing-evidence",
            ),
        ),
    )
    companies = CompanyRepository(facts)
    alpha = companies.resolve("Alpha Minerals Ltd", "US", threshold=0.94)
    beta = companies.resolve("Beta Materials Ltd", "US", threshold=0.94)
    repository = GraphRepository()

    repository.add_registry_facts(facts, companies)

    assert repository.same_confirmed_group(alpha.company.id, beta.company.id) is False


def test_inbound_relationships_groups_distinct_bols_by_canonical_endpoints() -> None:
    facts = StaticRegistryRepository().get()
    companies = CompanyRepository(facts)
    terra = companies.resolve("Terra Silica Partners", "US", threshold=0.94)
    solstice = companies.resolve("Solstice Materials Co", "US", threshold=0.94)
    later_shipment = Shipment(
        bill_of_lading_id="BOL100006",
        shipment_date=date(2026, 1, 7),
        shipper_name="Terra Silica Partners",
        shipper_country="US",
        consignee_name="Solstice Materials Co",
        consignee_country="US",
        product_description="silica sand",
        weight_kg=34618,
        vessel_name="MV Nordwind",
    )
    repository = GraphRepository()

    repository.add_shipment(shipment(), terra, solstice)
    repository.add_shipment(later_shipment, terra, solstice)

    relationships = repository.inbound_relationships(solstice.company.id)

    assert len(relationships) == 1
    assert [record.bill_of_lading_id for record in relationships[0].shipments] == [
        "BOL100007",
        "BOL100006",
    ]


def test_inbound_relationship_resolution_uses_best_endpoint_evidence_regardless_of_row_order() -> None:
    supplier = Company("company:supplier:us", "Supplier", "US")
    buyer = Company("company:buyer:us", "Buyer", "US")

    def relationship_score_for(confidences: tuple[float, float]) -> float:
        repository = GraphRepository()
        for number, confidence in enumerate(confidences, start=1):
            repository.add_shipment(
                Shipment(
                    bill_of_lading_id=f"BOL-{number}",
                    shipment_date=date(2026, 1, number),
                    shipper_name="Supplier",
                    shipper_country="US",
                    consignee_name="Buyer",
                    consignee_country="US",
                    product_description="silica sand",
                    weight_kg=100.0,
                    vessel_name=None,
                ),
                ResolvedCompany(
                    supplier,
                    ResolutionMethod.CREATED if confidence < 1 else ResolutionMethod.EXACT,
                    confidence,
                    "Supplier",
                ),
                ResolvedCompany(buyer, ResolutionMethod.EXACT, 1.0, "Buyer"),
            )
        relationship = repository.inbound_relationships(buyer.id)[0]
        breakdown = score_relationship(relationship, pass_through_terms=())
        assert breakdown is not None
        return breakdown.total

    assert relationship_score_for((0.60, 1.0)) == pytest.approx(0.95)
    assert relationship_score_for((1.0, 0.60)) == pytest.approx(0.95)
