import networkx as nx

from customs_tier_n.model.entities import (
    Company,
    EvidenceFact,
    RegistryFacts,
    RelationshipEvidence,
    ResolvedCompany,
    Shipment,
)
from customs_tier_n.repository.company_repository import CompanyRepository, normalize_company_name


class GraphRepository:
    def __init__(self) -> None:
        self.graph = nx.MultiDiGraph()

    def add_shipment(
        self,
        shipment: Shipment,
        shipper: ResolvedCompany,
        consignee: ResolvedCompany,
    ) -> None:
        shipment_id = f"shipment:{shipment.bill_of_lading_id.strip()}"
        product_id = f"product:{normalize_company_name(shipment.product_description)}"
        self._add_company(shipper.company)
        self._add_company(consignee.company)
        self.graph.add_node(
            shipment_id,
            node_type="shipment",
            shipment=shipment,
            shipper=shipper,
            consignee=consignee,
        )
        self.graph.add_node(
            product_id,
            node_type="product",
            description=normalize_company_name(shipment.product_description),
        )
        self.graph.add_edge(
            shipper.company.id,
            shipment_id,
            key="shipped",
            edge_type="shipped",
        )
        self.graph.add_edge(
            shipment_id,
            consignee.company.id,
            key="consigned_to",
            edge_type="consigned_to",
        )
        self.graph.add_edge(
            shipment_id,
            product_id,
            key="carries",
            edge_type="carries",
        )

    def add_registry_facts(self, facts: RegistryFacts, companies: CompanyRepository) -> None:
        evidence_by_id = {evidence.id: evidence for evidence in facts.evidences}
        for evidence in facts.evidences:
            self.graph.add_node(
                f"evidence:{evidence.id}",
                node_type="evidence",
                evidence=evidence,
            )

        for group in facts.groups:
            group_id = f"corporate-group:{group.group_id}"
            self.graph.add_node(group_id, node_type="corporate_group", group=group)
            for company_name in group.company_names:
                member = companies.resolve(company_name, None, threshold=1.0)
                self._add_company(member.company)
                claim_id = f"group-membership:{group.group_id}:{member.company.id}"
                self.graph.add_node(
                    claim_id,
                    node_type="group_membership_claim",
                    company_id=member.company.id,
                    group_id=group.group_id,
                )
                self.graph.add_edge(
                    member.company.id,
                    claim_id,
                    key=f"subject_of:{claim_id}",
                    edge_type="subject_of",
                )
                self.graph.add_edge(
                    claim_id,
                    group_id,
                    key=f"member_of:{claim_id}",
                    edge_type="member_of",
                )
                if group.evidence_id in evidence_by_id:
                    self.graph.add_edge(
                        f"evidence:{group.evidence_id}",
                        claim_id,
                        key=f"supports:{claim_id}",
                        edge_type="supports",
                    )

    def same_confirmed_group(self, left_id: str, right_id: str) -> bool:
        return bool(self._confirmed_groups(left_id) & self._confirmed_groups(right_id))

    def inbound_relationships(self, buyer_id: str) -> tuple[RelationshipEvidence, ...]:
        relationships: dict[tuple[str, str], RelationshipEvidence] = {}
        seen_bols: dict[tuple[str, str], set[str]] = {}

        for shipment_id, _, edge_key, edge_data in self.graph.in_edges(
            buyer_id, keys=True, data=True
        ):
            if edge_key != "consigned_to" or edge_data["edge_type"] != "consigned_to":
                continue
            shipment_data = self.graph.nodes[shipment_id]
            if shipment_data.get("node_type") != "shipment":
                continue
            shipment = shipment_data["shipment"]
            buyer = shipment_data["consignee"]

            for supplier_id, _, supplier_edge_key, supplier_edge_data in self.graph.in_edges(
                shipment_id, keys=True, data=True
            ):
                if supplier_edge_key != "shipped" or supplier_edge_data["edge_type"] != "shipped":
                    continue
                supplier = shipment_data["shipper"]
                key = (supplier.company.id, buyer.company.id)
                relationship = relationships.setdefault(
                    key,
                    RelationshipEvidence(supplier=supplier, buyer=buyer),
                )
                relationship.supplier = _best_resolution(relationship.supplier, supplier)
                relationship.buyer = _best_resolution(relationship.buyer, buyer)
                bol_ids = seen_bols.setdefault(key, set())
                if shipment.bill_of_lading_id not in bol_ids:
                    relationship.shipments.append(shipment)
                    bol_ids.add(shipment.bill_of_lading_id)

        return tuple(relationships.values())

    def _confirmed_groups(self, company_id: str) -> set[str]:
        if company_id not in self.graph:
            return set()
        groups: set[str] = set()
        for _, claim_id, _, subject_edge in self.graph.out_edges(company_id, keys=True, data=True):
            if (
                subject_edge.get("edge_type") != "subject_of"
                or self.graph.nodes[claim_id].get("node_type") != "group_membership_claim"
                or not self._has_evidence_support(claim_id)
            ):
                continue
            for _, group_id, _, member_edge in self.graph.out_edges(
                claim_id, keys=True, data=True
            ):
                if (
                    member_edge.get("edge_type") == "member_of"
                    and self.graph.nodes[group_id].get("node_type") == "corporate_group"
                ):
                    groups.add(group_id)
        return groups

    def _has_evidence_support(self, claim_id: str) -> bool:
        return any(
            support_edge.get("edge_type") == "supports"
            and self.graph.nodes[evidence_id].get("node_type") == "evidence"
            and isinstance(self.graph.nodes[evidence_id].get("evidence"), EvidenceFact)
            for evidence_id, _, _, support_edge in self.graph.in_edges(
                claim_id, keys=True, data=True
            )
        )

    def _add_company(self, company: Company) -> None:
        self.graph.add_node(company.id, node_type="company", company=company)


def _best_resolution(current: ResolvedCompany, candidate: ResolvedCompany) -> ResolvedCompany:
    """Keep the strongest endpoint resolution independently of CSV row order."""
    if _resolution_key(candidate) > _resolution_key(current):
        return candidate
    return current


def _resolution_key(resolution: ResolvedCompany) -> tuple[float, int, str]:
    method_rank = {
        "created": 0,
        "fuzzy": 1,
        "alias": 2,
        "exact": 3,
    }[resolution.method.value]
    return resolution.confidence, method_rank, normalize_company_name(resolution.raw_name)
