from customs_tier_n.repository.registry_repository import StaticRegistryRepository


def test_static_registry_embeds_the_corporate_registry_facts() -> None:
    facts = StaticRegistryRepository().get()

    assert facts.aliases[0].canonical_name == "Solstice Materials Europe GmbH"
    assert facts.aliases[0].alias == "Bergwerk Mining Alias GmbH"
    assert "Solstice Materials Co" in facts.groups[0].company_names
    assert facts.evidences[0].source == "corporate_registry_notes.txt"
    assert "Solstice Analytics Inc" in facts.unrelated_names
    assert facts.pass_through_terms == ("packaging", "freight", "logistics")
