from customs_tier_n.model.entities import Company


def test_company_keeps_canonical_name_and_variants() -> None:
    company = Company(
        id="company:solstice-materials-europe:de",
        canonical_name="Solstice Materials Europe GmbH",
        country="DE",
        name_variants=("Bergwerk Mining Alias GmbH",),
    )

    assert company.canonical_name == "Solstice Materials Europe GmbH"
    assert company.name_variants == ("Bergwerk Mining Alias GmbH",)
