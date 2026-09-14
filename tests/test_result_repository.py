import csv
import json

from customs_tier_n.model.entities import (
    Candidate,
    CandidatePath,
    Company,
    CycleRecord,
    DataQualityIssue,
    DiscoveryResult,
    ParkedShipment,
    RelationshipPathEvidence,
)
from customs_tier_n.repository.result_repository import ResultRepository


def test_write_serializes_ranked_candidates_and_explainability_records(tmp_path) -> None:
    root_id = "company:root:us"
    beta = Company(id="company:beta:us", canonical_name="Beta Materials", country="US")
    alpha = Company(id="company:alpha:us", canonical_name="Alpha Minerals", country="AU")
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            beta.id: Candidate(
                company=beta,
                tier=3,
                confidence=0.63,
                label="Medium",
                paths=[
                    CandidatePath(
                        company_ids=(root_id, alpha.id, beta.id),
                        relationship_scores=(0.9, 0.7),
                        bol_ids=("BOL-2", "BOL-1"),
                        product_descriptions=("silica sand", "raw quartz"),
                        score=0.63,
                    )
                ],
            ),
            alpha.id: Candidate(
                company=alpha,
                tier=2,
                confidence=0.9,
                label="High",
                paths=[],
            ),
        },
        parked_shipments=[
            ParkedShipment("PARKED-1", "pass-through relationship", alpha.id, root_id)
        ],
        data_quality_issues=[DataQualityIssue("DUPLICATE-1", "conflicting_duplicate_bol")],
        cycles=[CycleRecord((root_id, alpha.id, root_id), "CYCLE-1")],
    )

    candidate_path, candidate_csv_path, parked_path, cycles_path = ResultRepository().write(
        result, tmp_path
    )

    assert candidate_path.name == "tier_n_candidates.json"
    assert candidate_csv_path.name == "tier_n_candidates.csv"
    assert parked_path.name == "parked_shipments.json"
    assert cycles_path.name == "cycles.json"
    candidates = json.loads(candidate_path.read_text())
    assert candidates["root_company_id"] == root_id
    assert [candidate["company"]["canonical_name"] for candidate in candidates["candidates"]] == [
        "Alpha Minerals",
        "Beta Materials",
    ]
    assert candidates["candidates"][1]["paths"][0]["bol_ids"] == ["BOL-1", "BOL-2"]
    with candidate_csv_path.open(newline="", encoding="utf-8") as csv_file:
        assert list(csv.DictReader(csv_file)) == [
            {"company_name": "Alpha Minerals", "tier": "2", "confidence": "0.9"},
            {"company_name": "Beta Materials", "tier": "3", "confidence": "0.63"},
        ]
    assert json.loads(parked_path.read_text())["data_quality_issues"] == [
        {"bill_of_lading_id": "DUPLICATE-1", "reason": "conflicting_duplicate_bol"}
    ]
    assert json.loads(cycles_path.read_text())["cycles"][0]["bill_of_lading_id"] == "CYCLE-1"


def test_write_breaks_candidate_and_path_ordering_ties_deterministically(tmp_path) -> None:
    root_id = "company:root:us"
    zeta = Company(id="company:zeta:us", canonical_name="Same Name", country="US")
    alpha = Company(id="company:alpha:us", canonical_name="Same Name", country="US")
    zeta_path = CandidatePath(
        company_ids=(root_id, zeta.id),
        relationship_scores=(0.9,),
        bol_ids=("Z-BOL",),
        product_descriptions=("zinc",),
        score=0.9,
    )
    alpha_path = CandidatePath(
        company_ids=(root_id, zeta.id),
        relationship_scores=(0.9,),
        bol_ids=("A-BOL",),
        product_descriptions=("alumina",),
        score=0.9,
    )
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            zeta.id: Candidate(zeta, 2, [zeta_path, alpha_path], 0.9, "High"),
            alpha.id: Candidate(alpha, 2, [], 0.9, "High"),
        },
    )

    candidate_path, _, _, _ = ResultRepository().write(result, tmp_path)

    candidates = json.loads(candidate_path.read_text())["candidates"]
    assert [candidate["company"]["id"] for candidate in candidates] == [alpha.id, zeta.id]
    assert [path["bol_ids"] for path in candidates[1]["paths"]] == [["A-BOL"], ["Z-BOL"]]


def test_write_canonicalizes_relationship_evidence_for_tied_paths(tmp_path) -> None:
    root_id = "company:root:us"
    supplier_a_id = "company:a:us"
    supplier_b_id = "company:b:us"
    supplier = Company(id=supplier_b_id, canonical_name="Supplier B", country="US")
    a_to_root = RelationshipPathEvidence(
        supplier_a_id,
        root_id,
        0.9,
        ("A-ROOT-Z", "A-ROOT-A"),
        ("zinc", "alumina"),
    )
    b_to_a = RelationshipPathEvidence(
        supplier_b_id,
        supplier_a_id,
        0.7,
        ("B-A-Z", "B-A-A"),
        ("raw quartz", "feldspar"),
    )
    path_kwargs = {
        "company_ids": (root_id, supplier_a_id, supplier_b_id),
        "relationship_scores": (0.9, 0.7),
        "bol_ids": ("A-ROOT-A", "A-ROOT-Z", "B-A-A", "B-A-Z"),
        "product_descriptions": ("alumina", "zinc", "feldspar", "raw quartz"),
        "score": 0.63,
    }
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            supplier.id: Candidate(
                supplier,
                3,
                [
                    CandidatePath(**path_kwargs, relationship_evidence=(b_to_a, a_to_root)),
                    CandidatePath(**path_kwargs, relationship_evidence=(a_to_root, b_to_a)),
                ],
                0.63,
                "Medium",
            )
        },
    )

    candidate_path, _, _, _ = ResultRepository().write(result, tmp_path)

    paths = json.loads(candidate_path.read_text())["candidates"][0]["paths"]
    assert paths[0]["relationship_evidence"] == paths[1]["relationship_evidence"]
    assert paths[0]["relationship_evidence"] == [
        {
            "supplier_id": supplier_a_id,
            "buyer_id": root_id,
            "score": 0.9,
            "bol_ids": ["A-ROOT-A", "A-ROOT-Z"],
            "product_descriptions": ["alumina", "zinc"],
        },
        {
            "supplier_id": supplier_b_id,
            "buyer_id": supplier_a_id,
            "score": 0.7,
            "bol_ids": ["B-A-A", "B-A-Z"],
            "product_descriptions": ["feldspar", "raw quartz"],
        },
    ]
