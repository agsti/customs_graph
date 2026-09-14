"""Breadth-first upstream supplier discovery."""

from collections import deque

from customs_tier_n.model.confidence import classify_material, confidence_label, score_relationship
from customs_tier_n.model.entities import (
    Candidate,
    CandidatePath,
    CycleRecord,
    DiscoveryResult,
    ParkedShipment,
    RelationshipPathEvidence,
    RelationshipEvidence,
)
from customs_tier_n.repository.graph_repository import GraphRepository


class TierNDiscoveryController:
    def __init__(self, graph_repository: GraphRepository, pass_through_terms: tuple[str, ...]) -> None:
        self._graph_repository = graph_repository
        self._pass_through_terms = pass_through_terms

    def discover(self, root_company_id: str) -> DiscoveryResult:
        result = DiscoveryResult(root_company_id=root_company_id)
        root_path = CandidatePath((), (), (), (), 1.0)
        queue: deque[tuple[str, int, tuple[str, ...], CandidatePath]] = deque(
            [(root_company_id, 1, (root_company_id,), root_path)]
        )
        queued_paths: set[tuple[str, ...]] = {(root_company_id,)}

        while queue:
            buyer_id, tier, company_path, parent_path = queue.popleft()

            for relationship in self._graph_repository.inbound_relationships(buyer_id):
                if self._graph_repository.same_confirmed_group(
                    relationship.supplier.company.id, relationship.buyer.company.id
                ):
                    self._park_relationship(result, relationship, "intra_group")
                    continue

                eligible_relationship = self._without_pass_through_shipments(result, relationship)
                if eligible_relationship is None:
                    continue

                supplier_id = eligible_relationship.supplier.company.id
                if supplier_id in company_path:
                    result.cycles.append(
                        CycleRecord(
                            company_ids=company_path + (supplier_id,),
                            bill_of_lading_id=eligible_relationship.shipments[0].bill_of_lading_id,
                        )
                    )
                    continue

                breakdown = score_relationship(eligible_relationship, self._pass_through_terms)
                if breakdown is None:
                    continue

                candidate_tier = tier + 1
                relationship_score = breakdown.total
                hop_multiplier = 1.0 if candidate_tier == 2 else 0.90
                candidate_path_score = parent_path.score * relationship_score * hop_multiplier
                candidate_company_path = company_path + (supplier_id,)
                candidate_path = CandidatePath(
                    company_ids=candidate_company_path,
                    relationship_scores=parent_path.relationship_scores + (relationship_score,),
                    bol_ids=parent_path.bol_ids
                    + tuple(shipment.bill_of_lading_id for shipment in eligible_relationship.shipments),
                    product_descriptions=parent_path.product_descriptions
                    + tuple(
                        shipment.product_description for shipment in eligible_relationship.shipments
                    ),
                    score=candidate_path_score,
                    relationship_evidence=parent_path.relationship_evidence
                    + (
                        RelationshipPathEvidence(
                            supplier_id=supplier_id,
                            buyer_id=buyer_id,
                            score=relationship_score,
                            bol_ids=tuple(
                                shipment.bill_of_lading_id
                                for shipment in eligible_relationship.shipments
                            ),
                            product_descriptions=tuple(
                                shipment.product_description
                                for shipment in eligible_relationship.shipments
                            ),
                        ),
                    ),
                )
                self._retain_candidate(result, eligible_relationship, candidate_tier, candidate_path)
                if candidate_company_path not in queued_paths:
                    queued_paths.add(candidate_company_path)
                    queue.append((supplier_id, candidate_tier, candidate_company_path, candidate_path))

        return result

    def _without_pass_through_shipments(
        self, result: DiscoveryResult, relationship: RelationshipEvidence
    ) -> RelationshipEvidence | None:
        eligible_shipments = [
            shipment
            for shipment in relationship.shipments
            if classify_material(shipment.product_description, self._pass_through_terms) is not None
        ]

        if not eligible_shipments:
            self._park_relationship(result, relationship, "freight_logistics_or_packaging")
            return None
        return RelationshipEvidence(
            supplier=relationship.supplier,
            buyer=relationship.buyer,
            shipments=eligible_shipments,
        )

    @staticmethod
    def _park_relationship(
        result: DiscoveryResult, relationship: RelationshipEvidence, reason: str
    ) -> None:
        for shipment in relationship.shipments:
            result.parked_shipments.append(
                ParkedShipment(
                    bill_of_lading_id=shipment.bill_of_lading_id,
                    reason=reason,
                    supplier_id=relationship.supplier.company.id,
                    buyer_id=relationship.buyer.company.id,
                )
            )

    @staticmethod
    def _retain_candidate(
        result: DiscoveryResult,
        relationship: RelationshipEvidence,
        tier: int,
        path: CandidatePath,
    ) -> None:
        company_id = relationship.supplier.company.id
        candidate = result.candidates.get(company_id)
        if candidate is None:
            result.candidates[company_id] = Candidate(
                company=relationship.supplier.company,
                tier=tier,
                paths=[path],
                confidence=path.score,
                label=confidence_label(path.score),
            )
            return

        candidate.paths.append(path)
        candidate.tier = min(candidate.tier, tier)
        if path.score > candidate.confidence:
            candidate.confidence = path.score
            candidate.label = confidence_label(path.score)
