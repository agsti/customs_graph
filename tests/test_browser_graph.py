import json
import re

from customs_tier_n.model.entities import (
    Candidate,
    CandidatePath,
    Company,
    DiscoveryResult,
    RelationshipPathEvidence,
)
from customs_tier_n.visualization.browser_graph import BrowserGraph


def test_render_writes_self_contained_company_graph_with_candidate_evidence(tmp_path) -> None:
    root_id = "company:root:us"
    high = Company("company:high:us", "High Supplier", "US")
    medium = Company("company:medium:us", "Medium Supplier", "US")
    low = Company("company:low:us", "Low Supplier", "US")
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            high.id: Candidate(
                high,
                2,
                [
                    CandidatePath(
                        (root_id, high.id),
                        (0.9,),
                        ("HIGH-BOL",),
                        ("silica sand",),
                        0.9,
                        (
                            RelationshipPathEvidence(
                                high.id, root_id, 0.9, ("HIGH-BOL",), ("silica sand",)
                            ),
                        ),
                    )
                ],
                0.9,
                "High",
            ),
            medium.id: Candidate(
                medium,
                3,
                [
                    CandidatePath(
                        (root_id, high.id, medium.id),
                        (0.9, 0.7),
                        ("HIGH-BOL", "MEDIUM-BOL"),
                        ("silica sand", "raw quartz"),
                        0.63,
                        (
                            RelationshipPathEvidence(
                                high.id, root_id, 0.9, ("HIGH-BOL",), ("silica sand",)
                            ),
                            RelationshipPathEvidence(
                                medium.id, high.id, 0.7, ("MEDIUM-BOL",), ("raw quartz",)
                            ),
                        ),
                    )
                ],
                0.63,
                "Medium",
            ),
            low.id: Candidate(
                low,
                4,
                [
                    CandidatePath(
                        (root_id, high.id, medium.id, low.id),
                        (0.9, 0.7, 0.4),
                        ("HIGH-BOL", "MEDIUM-BOL", "LOW-BOL"),
                        ("silica sand", "raw quartz", "ore"),
                        0.2,
                        (
                            RelationshipPathEvidence(
                                high.id, root_id, 0.9, ("HIGH-BOL",), ("silica sand",)
                            ),
                            RelationshipPathEvidence(
                                medium.id, high.id, 0.7, ("MEDIUM-BOL",), ("raw quartz",)
                            ),
                            RelationshipPathEvidence(
                                low.id, medium.id, 0.4, ("LOW-BOL",), ("ore",)
                            ),
                        ),
                    )
                ],
                0.2,
                "Low",
            ),
        },
    )

    output_path = BrowserGraph().render(result, tmp_path / "tier_n_graph.html")

    html = output_path.read_text(encoding="utf-8")
    assert output_path.name == "tier_n_graph.html"
    assert "vis-network" in html
    assert all(name in html for name in ("Root", "High Supplier", "Medium Supplier", "Low Supplier"))
    assert all(label in html for label in ("High", "Medium", "Low"))
    assert all(bol_id in html for bol_id in ("HIGH-BOL", "MEDIUM-BOL", "LOW-BOL"))
    node_title = next(node["title"] for node in _dataset(html, "nodes") if node["id"] == high.id)
    edge_title = next(edge["title"] for edge in _dataset(html, "edges") if edge["from"] == high.id)
    assert "\n" in node_title
    assert "\n" in edge_title
    assert "<br" not in node_title
    assert "<br" not in edge_title


def test_render_keeps_multi_hop_edge_evidence_scoped_to_its_relationship(tmp_path) -> None:
    root_id = "company:root:us"
    supplier_a = Company("company:a:us", "Supplier A", "US")
    supplier_b = Company("company:b:us", "Supplier B", "US")
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            supplier_a.id: Candidate(
                supplier_a,
                2,
                [
                    CandidatePath(
                        (root_id, supplier_a.id),
                        (0.9,),
                        ("A-ROOT-BOL",),
                        ("silica sand",),
                        0.9,
                        (
                            RelationshipPathEvidence(
                                supplier_a.id,
                                root_id,
                                0.9,
                                ("A-ROOT-BOL",),
                                ("silica sand",),
                            ),
                        ),
                    )
                ],
                0.9,
                "High",
            ),
            supplier_b.id: Candidate(
                supplier_b,
                3,
                [
                    CandidatePath(
                        (root_id, supplier_a.id, supplier_b.id),
                        (0.9, 0.7),
                        ("A-ROOT-BOL", "B-A-BOL"),
                        ("silica sand", "raw quartz"),
                        0.63,
                        (
                            RelationshipPathEvidence(
                                supplier_a.id,
                                root_id,
                                0.9,
                                ("A-ROOT-BOL",),
                                ("silica sand",),
                            ),
                            RelationshipPathEvidence(
                                supplier_b.id,
                                supplier_a.id,
                                0.7,
                                ("B-A-BOL",),
                                ("raw quartz",),
                            ),
                        ),
                    )
                ],
                0.63,
                "Medium",
            )
        },
    )

    html = BrowserGraph().render(result, tmp_path / "tier_n_graph.html").read_text(encoding="utf-8")
    edges = _dataset(html, "edges")
    root_edge = next(
        edge
        for edge in edges
        if edge["from"] == supplier_a.id and edge["to"] == root_id
    )
    root_node = next(node for node in _dataset(html, "nodes") if node["id"] == root_id)

    assert "A-ROOT-BOL" in root_edge["title"]
    assert "silica sand" in root_edge["title"]
    assert "B-A-BOL" not in root_edge["title"]
    assert "raw quartz" not in root_edge["title"]
    assert all(value in root_node["title"] for value in ("Score: N/A", "Label: Root", "Tier: 1", "Products: None", "BOL IDs: None"))


def test_render_adds_each_linking_fact_to_the_selectable_edge(tmp_path) -> None:
    root_id = "company:root:us"
    supplier = Company("company:supplier:us", "Supplier", "US")
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            supplier.id: Candidate(
                supplier,
                2,
                [
                    CandidatePath(
                        (root_id, supplier.id),
                        (0.8,),
                        ("BOL-ONE",),
                        ("silica sand",),
                        0.8,
                        (
                            RelationshipPathEvidence(
                                supplier.id,
                                root_id,
                                0.8,
                                ("BOL-ONE",),
                                ("silica sand",),
                            ),
                        ),
                    ),
                    CandidatePath(
                        (root_id, supplier.id),
                        (0.6,),
                        ("BOL-TWO",),
                        ("quartz powder",),
                        0.6,
                        (
                            RelationshipPathEvidence(
                                supplier.id,
                                root_id,
                                0.6,
                                ("BOL-TWO",),
                                ("quartz powder",),
                            ),
                        ),
                    ),
                ],
                0.8,
                "High",
            )
        },
    )

    html = BrowserGraph().render(result, tmp_path / "tier_n_graph.html").read_text(encoding="utf-8")
    edge = next(edge for edge in _dataset(html, "edges") if edge["from"] == supplier.id)

    assert edge["facts"] == [
        {"score": 0.6, "bol_ids": ["BOL-TWO"], "product_descriptions": ["quartz powder"]},
        {"score": 0.8, "bol_ids": ["BOL-ONE"], "product_descriptions": ["silica sand"]},
    ]
    assert 'network.on("selectNode"' in html
    assert "if (network.getSelectedNodes().length) return;" in html
    assert all(header in html for header in ("<table>", "<th>Supplier</th>", "<th>BOL IDs</th>"))


def test_render_keeps_facts_for_every_incoming_relationship(tmp_path) -> None:
    root_id = "company:root:us"
    supplier_a = Company("company:a:us", "Supplier A", "US")
    supplier_b = Company("company:b:us", "Supplier B", "US")
    result = DiscoveryResult(
        root_company_id=root_id,
        candidates={
            supplier_a.id: Candidate(
                supplier_a,
                2,
                [
                    CandidatePath(
                        (root_id, supplier_a.id),
                        (0.8,),
                        ("A-BOL",),
                        ("silica sand",),
                        0.8,
                        (
                            RelationshipPathEvidence(
                                supplier_a.id, root_id, 0.8, ("A-BOL",), ("silica sand",)
                            ),
                        ),
                    )
                ],
                0.8,
                "High",
            ),
            supplier_b.id: Candidate(
                supplier_b,
                2,
                [
                    CandidatePath(
                        (root_id, supplier_b.id),
                        (0.6,),
                        ("B-BOL",),
                        ("quartz powder",),
                        0.6,
                        (
                            RelationshipPathEvidence(
                                supplier_b.id, root_id, 0.6, ("B-BOL",), ("quartz powder",)
                            ),
                        ),
                    )
                ],
                0.6,
                "Medium",
            ),
        },
    )

    html = BrowserGraph().render(result, tmp_path / "tier_n_graph.html").read_text(encoding="utf-8")
    incoming_edges = [edge for edge in _dataset(html, "edges") if edge["to"] == root_id]

    assert [(edge["from"], edge["facts"]) for edge in incoming_edges] == [
        (supplier_a.id, [{"score": 0.8, "bol_ids": ["A-BOL"], "product_descriptions": ["silica sand"]}]),
        (supplier_b.id, [{"score": 0.6, "bol_ids": ["B-BOL"], "product_descriptions": ["quartz powder"]}]),
    ]


def _dataset(html: str, name: str) -> list[dict[str, object]]:
    match = re.search(rf"{name} = new vis.DataSet\((\[.*?\])\);", html, re.DOTALL)
    assert match is not None
    return json.loads(match.group(1))
