from customs_tier_n.model.entities import GroupFact, RegistryFacts, ResolutionMethod
from customs_tier_n.repository.company_repository import (
    CompanyRepository,
    normalize_company_name,
    normalized_similarity,
)
from customs_tier_n.repository.registry_repository import StaticRegistryRepository


def test_normalization_preserves_legal_suffixes_and_similarity_handles_typo() -> None:
    assert normalize_company_name("  AURORA   PIGMENTS LTD ") == "aurora pigments ltd"
    assert normalized_similarity("aurora pigments ltd", "aurora pigment ltd") > 0.94


def test_resolve_uses_documented_alias_before_fuzzy_matching() -> None:
    companies = CompanyRepository(StaticRegistryRepository().get())

    alias = companies.resolve("Bergwerk Mining Alias GmbH", "DE", threshold=0.94)

    assert alias.company.canonical_name == "Solstice Materials Europe GmbH"
    assert alias.method is ResolutionMethod.ALIAS
    assert alias.confidence == 1.0


def test_resolve_keeps_unrelated_registry_name_separate_from_solstice_group() -> None:
    companies = CompanyRepository(StaticRegistryRepository().get())

    analytics = companies.resolve("Solstice Analytics Inc", "US", threshold=0.94)
    solstice = companies.resolve("Solstice Materials Co", "US", threshold=0.94)

    assert analytics.company.id != solstice.company.id


def test_resolve_creates_unverified_company_when_fuzzy_score_is_below_threshold() -> None:
    companies = CompanyRepository(StaticRegistryRepository().get())

    resolved = companies.resolve("Solstice Mineral Co", "US", threshold=0.94)

    assert resolved.method is ResolutionMethod.CREATED
    assert resolved.company.canonical_name == "Solstice Mineral Co"


def test_created_companies_with_colliding_slugs_keep_distinct_ids() -> None:
    companies = CompanyRepository(RegistryFacts())

    punctuated = companies.resolve("Acme+Minerals", "US", threshold=1.0)
    spaced = companies.resolve("Acme Minerals", "US", threshold=1.0)

    assert punctuated.company.id != spaced.company.id
    assert punctuated.company.canonical_name == "Acme+Minerals"
    assert spaced.company.canonical_name == "Acme Minerals"


def test_created_company_uses_documented_unresolved_confidence_baseline() -> None:
    companies = CompanyRepository(RegistryFacts())

    resolved = companies.resolve("Unregistered Minerals Ltd", "US", threshold=1.0)

    assert resolved.method is ResolutionMethod.CREATED
    assert resolved.confidence == 0.60


def test_resolve_rejects_fuzzy_match_within_margin_of_runner_up() -> None:
    companies = CompanyRepository(
        RegistryFacts(
            groups=(
                GroupFact(
                    group_id="aurora",
                    company_names=("Aurora Pigment Ltd", "Aurora Pigmented Ltd"),
                    evidence_id="test",
                ),
            ),
        )
    )

    resolved = companies.resolve("Aurora Pigments Ltd", "US", threshold=0.94)

    assert resolved.method is ResolutionMethod.CREATED


def test_resolve_rejects_fuzzy_match_when_known_countries_conflict() -> None:
    companies = CompanyRepository(StaticRegistryRepository().get())

    resolved = companies.resolve("Solstice Materials Europe GmbX", "US", threshold=0.94)

    assert resolved.method is ResolutionMethod.CREATED
