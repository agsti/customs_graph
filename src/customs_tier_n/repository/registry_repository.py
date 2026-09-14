from customs_tier_n.model.entities import AliasFact, EvidenceFact, GroupFact, RegistryFacts


class StaticRegistryRepository:
    """Embedded registry facts curated from the companion reference."""

    def get(self) -> RegistryFacts:
        return RegistryFacts(
            aliases=(
                AliasFact(
                    canonical_name="Solstice Materials Europe GmbH",
                    canonical_country="DE",
                    alias="Bergwerk Mining Alias GmbH",
                    evidence_id="registry-1",
                ),
            ),
            groups=(
                GroupFact(
                    group_id="solstice-materials-group",
                    company_names=(
                        "Solstice Materials Europe GmbH",
                        "Solstice Materials Co",
                    ),
                    evidence_id="registry-1",
                ),
            ),
            evidences=(
                EvidenceFact(
                    id="registry-1",
                    source="corporate_registry_notes.txt",
                    statement=(
                        "Solstice Materials Europe GmbH also trades as Bergwerk Mining Alias GmbH "
                        "and is in the same corporate group as Solstice Materials Co."
                    ),
                ),
                EvidenceFact(
                    id="registry-2",
                    source="corporate_registry_notes.txt",
                    statement=(
                        "Solstice Analytics Inc has no group or ownership relationship to "
                        "Solstice Materials Co."
                    ),
                ),
                EvidenceFact(
                    id="registry-3",
                    source="corporate_registry_notes.txt",
                    statement=(
                        "Packaging, freight, and logistics shipments are usually pass-through services."
                    ),
                ),
            ),
            unrelated_names=("Solstice Analytics Inc",),
            pass_through_terms=("packaging", "freight", "logistics"),
        )
