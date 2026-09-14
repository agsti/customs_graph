import hashlib
import re
import unicodedata

from customs_tier_n.model.entities import Company, RegistryFacts, ResolvedCompany, ResolutionMethod


def normalize_company_name(name: str) -> str:
    """Return a comparable company name without discarding legal suffixes."""
    normalized = unicodedata.normalize("NFKC", name).casefold().strip()
    return " ".join(normalized.split())


def normalized_similarity(left: str, right: str) -> float:
    """Calculate normalized Levenshtein similarity for two company names."""
    maximum_length = max(len(left), len(right))
    if maximum_length == 0:
        return 0.0
    return 1 - _levenshtein_distance(left, right) / maximum_length


def _levenshtein_distance(left: str, right: str) -> int:
    if len(left) < len(right):
        left, right = right, left

    previous = list(range(len(right) + 1))
    for left_index, left_character in enumerate(left, start=1):
        current = [left_index]
        for right_index, right_character in enumerate(right, start=1):
            insertion = current[right_index - 1] + 1
            deletion = previous[right_index] + 1
            substitution = previous[right_index - 1] + (left_character != right_character)
            current.append(min(insertion, deletion, substitution))
        previous = current
    return previous[-1]


class CompanyRepository:
    def __init__(self, registry_facts: RegistryFacts) -> None:
        self._companies: dict[str, Company] = {}
        self._aliases: dict[str, Company] = {}
        self._registry_canonical_names: set[str] = set()
        self._seed_registry_names(registry_facts)

    def resolve(self, name: str, country: str | None, threshold: float) -> ResolvedCompany:
        normalized_name = normalize_company_name(name)
        canonical = self._companies.get(normalized_name)
        if canonical is not None:
            if normalized_name in self._registry_canonical_names:
                return ResolvedCompany(canonical, ResolutionMethod.EXACT, 1.0, name)
            return ResolvedCompany(canonical, ResolutionMethod.CREATED, 0.60, name)

        alias = self._aliases.get(normalized_name)
        if alias is not None:
            return ResolvedCompany(alias, ResolutionMethod.ALIAS, 1.0, name)

        fuzzy_match = self._fuzzy_match(normalized_name, country, threshold)
        if fuzzy_match is not None:
            company, confidence = fuzzy_match
            return ResolvedCompany(company, ResolutionMethod.FUZZY, confidence, name)

        company = Company(
            id=_company_id(name, country),
            canonical_name=name.strip(),
            country=country,
        )
        self._companies[normalized_name] = company
        return ResolvedCompany(company, ResolutionMethod.CREATED, 0.60, name)

    def _seed_registry_names(self, registry_facts: RegistryFacts) -> None:
        aliases_by_canonical = {fact.canonical_name: fact for fact in registry_facts.aliases}
        names = [name for group in registry_facts.groups for name in group.company_names]
        names.extend(registry_facts.unrelated_names)
        names.extend(fact.canonical_name for fact in registry_facts.aliases)

        for name in names:
            alias_fact = aliases_by_canonical.get(name)
            country = alias_fact.canonical_country if alias_fact else None
            normalized_name = normalize_company_name(name)
            self._registry_canonical_names.add(normalized_name)
            if normalized_name not in self._companies:
                variants = (alias_fact.alias,) if alias_fact else ()
                self._companies[normalized_name] = Company(
                    id=_company_id(name, country),
                    canonical_name=name,
                    country=country,
                    name_variants=variants,
                )

        for alias_fact in registry_facts.aliases:
            canonical = self._companies[normalize_company_name(alias_fact.canonical_name)]
            self._aliases[normalize_company_name(alias_fact.alias)] = canonical

    def _fuzzy_match(
        self, normalized_name: str, country: str | None, threshold: float
    ) -> tuple[Company, float] | None:
        candidates = [
            (company, normalized_similarity(normalized_name, normalized_company_name))
            for normalized_company_name, company in self._companies.items()
            if not (country and company.country and country.casefold() != company.country.casefold())
        ]
        candidates.sort(key=lambda candidate: candidate[1], reverse=True)
        if not candidates:
            return None

        best_company, best_score = candidates[0]
        runner_up_score = candidates[1][1] if len(candidates) > 1 else None
        if best_score < threshold:
            return None
        if runner_up_score is not None and best_score - runner_up_score <= 0.05:
            return None
        return best_company, best_score


def _company_id(name: str, country: str | None) -> str:
    normalized_name = normalize_company_name(name)
    slug = re.sub(r"[^a-z0-9]+", "-", normalized_name).strip("-")
    normalized_country = (country or "unknown").casefold()
    identity = f"{normalized_name}\x1f{normalized_country}"
    digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12]
    return f"company:{slug}:{normalized_country}:{digest}"
