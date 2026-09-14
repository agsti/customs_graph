"""Deterministic JSON and CSV output for discovery results."""

import csv
import json
from dataclasses import asdict
from pathlib import Path

from customs_tier_n.model.entities import (
    Candidate,
    CandidatePath,
    DiscoveryResult,
    RelationshipPathEvidence,
)


class ResultRepository:
    def write(self, result: DiscoveryResult, output_dir: Path) -> tuple[Path, Path, Path, Path]:
        output_dir.mkdir(parents=True, exist_ok=True)
        candidate_path = output_dir / "tier_n_candidates.json"
        candidate_csv_path = output_dir / "tier_n_candidates.csv"
        parked_path = output_dir / "parked_shipments.json"
        cycles_path = output_dir / "cycles.json"
        candidates = sorted(
            result.candidates.values(),
            key=lambda candidate: (
                candidate.tier,
                candidate.company.canonical_name,
                candidate.company.id,
            ),
        )

        self._write_json(
            candidate_path,
            {
                "root_company_id": result.root_company_id,
                "candidates": [
                    self._candidate_dict(candidate) for candidate in candidates
                ],
            },
        )
        self._write_candidate_csv(candidate_csv_path, candidates)
        self._write_json(
            parked_path,
            {
                "parked_shipments": [
                    asdict(shipment)
                    for shipment in sorted(
                        result.parked_shipments,
                        key=lambda shipment: (
                            shipment.bill_of_lading_id,
                            shipment.reason,
                            shipment.supplier_id or "",
                            shipment.buyer_id or "",
                        ),
                    )
                ],
                "data_quality_issues": [
                    asdict(issue)
                    for issue in sorted(
                        result.data_quality_issues,
                        key=lambda issue: (issue.bill_of_lading_id, issue.reason),
                    )
                ],
            },
        )
        self._write_json(
            cycles_path,
            {
                "cycles": [
                    asdict(cycle)
                    for cycle in sorted(
                        result.cycles,
                        key=lambda cycle: (cycle.bill_of_lading_id, cycle.company_ids),
                    )
                ]
            },
        )
        return candidate_path, candidate_csv_path, parked_path, cycles_path

    @staticmethod
    def _write_candidate_csv(path: Path, candidates: list[Candidate]) -> None:
        with path.open("w", newline="", encoding="utf-8") as csv_file:
            writer = csv.DictWriter(csv_file, fieldnames=("company_name", "tier", "confidence"))
            writer.writeheader()
            writer.writerows(
                {
                    "company_name": candidate.company.canonical_name,
                    "tier": candidate.tier,
                    "confidence": candidate.confidence,
                }
                for candidate in candidates
            )

    @staticmethod
    def _candidate_dict(candidate: Candidate) -> dict[str, object]:
        candidate_dict = asdict(candidate)
        candidate_dict["paths"] = [
            ResultRepository._path_dict(path)
            for path in sorted(
                candidate.paths,
                key=lambda path: (
                    path.company_ids,
                    path.score,
                    tuple(sorted(path.bol_ids)),
                    tuple(sorted(path.product_descriptions)),
                    tuple(
                        sorted(
                            ResultRepository._relationship_evidence_key(evidence)
                            for evidence in path.relationship_evidence
                        )
                    ),
                ),
            )
        ]
        return candidate_dict

    @staticmethod
    def _path_dict(path: CandidatePath) -> dict[str, object]:
        path_dict = asdict(path)
        path_dict["bol_ids"] = sorted(path.bol_ids)
        path_dict["product_descriptions"] = sorted(path.product_descriptions)
        path_dict["relationship_evidence"] = [
            ResultRepository._relationship_evidence_dict(evidence)
            for evidence in sorted(
                path.relationship_evidence,
                key=ResultRepository._relationship_evidence_key,
            )
        ]
        return path_dict

    @staticmethod
    def _relationship_evidence_key(
        evidence: RelationshipPathEvidence,
    ) -> tuple[str, str, float, tuple[str, ...], tuple[str, ...]]:
        return (
            evidence.supplier_id,
            evidence.buyer_id,
            evidence.score,
            tuple(sorted(evidence.bol_ids)),
            tuple(sorted(evidence.product_descriptions)),
        )

    @staticmethod
    def _relationship_evidence_dict(evidence: RelationshipPathEvidence) -> dict[str, object]:
        supplier_id, buyer_id, score, bol_ids, product_descriptions = (
            ResultRepository._relationship_evidence_key(evidence)
        )
        return {
            "supplier_id": supplier_id,
            "buyer_id": buyer_id,
            "score": score,
            "bol_ids": list(bol_ids),
            "product_descriptions": list(product_descriptions),
        }

    @staticmethod
    def _write_json(path: Path, contents: dict[str, object]) -> None:
        path.write_text(
            json.dumps(contents, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
            encoding="utf-8",
        )
