"""Self-contained PyVis rendering for the company relationship projection."""

from collections import defaultdict
from html import escape
from pathlib import Path

from pyvis.network import Network

from customs_tier_n.model.entities import Candidate, DiscoveryResult, RelationshipPathEvidence


class BrowserGraph:
    _COLORS = {
        "Root": "#d4af37",
        "High": "#2e8b57",
        "Medium": "#e67e22",
        "Low": "#808080",
    }

    def render(self, result: DiscoveryResult, output_path: Path) -> Path:
        output_path.parent.mkdir(parents=True, exist_ok=True)
        network = Network(
            directed=True,
            cdn_resources="in_line",
            height="900px",
            bgcolor="#ffffff",
        )
        network.set_options(
            """
            {
              "layout": {"hierarchical": {"enabled": true, "direction": "RL", "sortMethod": "directed"}},
              "physics": {"enabled": false}
            }
            """
        )

        candidates = result.candidates
        root_name = self._company_name(result.root_company_id, candidates)
        network.add_node(
            result.root_company_id,
            label=root_name,
            title=self._title(root_name, "Root", 1, "N/A", (), ()),
            color=self._COLORS["Root"],
        )
        for candidate in sorted(candidates.values(), key=lambda item: item.company.canonical_name):
            network.add_node(
                candidate.company.id,
                label=candidate.company.canonical_name,
                title=self._title(
                    candidate.company.canonical_name,
                    candidate.label,
                    candidate.tier,
                    candidate.confidence,
                    tuple(
                        product
                        for path in candidate.paths
                        for product in path.product_descriptions
                    ),
                    tuple(bol for path in candidate.paths for bol in path.bol_ids),
                ),
                color=self._COLORS[candidate.label],
            )

        edge_evidence: dict[tuple[str, str], list[RelationshipPathEvidence]] = defaultdict(list)
        for candidate in candidates.values():
            for path in candidate.paths:
                for relationship in self._relationship_evidence(path):
                    edge_evidence[(relationship.supplier_id, relationship.buyer_id)].append(
                        relationship
                    )

        for (supplier_id, buyer_id), relationships in sorted(edge_evidence.items()):
            scores = sorted({relationship.score for relationship in relationships})
            supporting_bols = sorted(
                {bol for relationship in relationships for bol in relationship.bol_ids}
            )
            products = sorted(
                {
                    product
                    for relationship in relationships
                    for product in relationship.product_descriptions
                }
            )
            network.add_edge(
                supplier_id,
                buyer_id,
                arrows="to",
                title=self._edge_title(scores, products, supporting_bols),
            )

        network.write_html(str(output_path), open_browser=False, notebook=False)
        return output_path

    @staticmethod
    def _relationship_evidence(path) -> tuple[RelationshipPathEvidence, ...]:
        if path.relationship_evidence:
            return path.relationship_evidence
        if len(path.company_ids) == 2 and len(path.relationship_scores) == 1:
            return (
                RelationshipPathEvidence(
                    supplier_id=path.company_ids[1],
                    buyer_id=path.company_ids[0],
                    score=path.relationship_scores[0],
                    bol_ids=path.bol_ids,
                    product_descriptions=path.product_descriptions,
                ),
            )
        return ()

    @staticmethod
    def _company_name(company_id: str, candidates: dict[str, Candidate]) -> str:
        candidate = candidates.get(company_id)
        if candidate is not None:
            return candidate.company.canonical_name
        prefix, _, suffix = company_id.partition("company:")
        if not prefix and suffix:
            slug = suffix.rsplit(":", maxsplit=1)[0]
            return " ".join(piece.capitalize() for piece in slug.split("-"))
        return company_id

    @staticmethod
    def _title(
        name: str,
        label: str,
        tier: int,
        score: float | str,
        products: tuple[str, ...],
        bol_ids: tuple[str, ...],
    ) -> str:
        score_value = score if isinstance(score, str) else f"{score:.2f}"
        product_value = ", ".join(sorted(set(products))) if products else "None"
        bol_value = ", ".join(sorted(set(bol_ids))) if bol_ids else "None"
        lines = [
            escape(name),
            f"Score: {score_value}",
            f"Label: {escape(label)}",
            f"Tier: {tier}",
            f"Products: {escape(product_value)}",
            f"BOL IDs: {escape(bol_value)}",
        ]
        return "\n".join(lines)

    @staticmethod
    def _edge_title(scores: list[float], products: list[str], bol_ids: list[str]) -> str:
        return "\n".join(
            (
                f"Relationship score(s): {', '.join(f'{score:.2f}' for score in scores)}",
                f"Products: {escape(', '.join(products))}",
                f"BOL IDs: {escape(', '.join(bol_ids))}",
            )
        )
