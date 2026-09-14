# Customs Tier-N Candidate Discovery — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Read the customs extract and registry notes, then produce an auditable list of upstream Tier-N material-supplier candidates for `Solstice Materials Co`.

**Architecture:** Model the input as a directed, heterogeneous graph. Shipment records provide the observable `shipper -> consignee` links; corporate registry data resolves aliases and removes confirmed intra-group links. The traversal follows inbound shipments recursively, scores each path, and keeps both accepted candidates and excluded evidence.

**Tech Stack:** Python 3.11; standard-library `csv`, `datetime`, `re`, `unicodedata`, and `collections`; a small pure-Python Levenshtein implementation.

**Spec:** `assignment.md`

## Global Constraints

- Preserve raw shipment records and exclusion reasons for auditability.
- Apply exact and documented-alias resolution before guarded fuzzy matching.
- Never infer corporate-group membership from a shared company-name token.
- Treat freight, logistics, and generic packaging as parked pass-through records.

---

## 1. Graph data model

Use stable IDs internally. Keep raw values from the CSV as shipment evidence, but use canonical company IDs in graph edges.

### Nodes

```python
nodes = [
    {
        "id": "company:solstice-materials-co:us",
        "type": "Company",
        "canonical_name": "Solstice Materials Co",
        "country": "US",
        "name_variants": [],
    },
    {
        "id": "group:solstice-materials",
        "type": "CorporateGroup",
        "name": "Solstice Materials Group",
    },
    {
        "id": "evidence:registry-note-1",
        "type": "Evidence",
        "source": "corporate_registry_notes.txt",
        "statement": "Solstice Materials Europe GmbH and its alias are in the same group as Solstice Materials Co.",
    },
    {
        "id": "claim:solstice-europe-group-membership",
        "type": "GroupMembershipClaim",
        "status": "confirmed",
    },
    {
        "id": "shipment:BOL100007",
        "type": "Shipment",
        "shipment_date": "2026-06-24",
        "raw_product_description": "silica sand",
        "weight_kg": 14531,
    },
    {
        "id": "product:silica-sand",
        "type": "Product",
        "name": "silica sand",
    },
]
```

### Edges

```text
(Company)-[:SHIPPED]->(Shipment)-[:CONSIGNED_TO]->(Company)
(Shipment)-[:CARRIES]->(Product)

(Company)-[:SUBJECT_OF]->(GroupMembershipClaim)
(GroupMembershipClaim)-[:MEMBER_OF]->(CorporateGroup)
(Evidence)-[:SUPPORTS]->(GroupMembershipClaim)
```

`name_variants` stays as a property of the canonical `Company` node. For example, `Bergwerk Mining Alias GmbH` is a variant of `Solstice Materials Europe GmbH`, not a second company node. This keeps entity resolution simple while retaining the raw name on the shipment for auditability.

The graph should distinguish a confirmed relationship from an assumption. `Solstice Analytics Inc` has its own Company node and is linked to no Solstice group; the evidence says it is unrelated. `Solstice Materials Iberia SA` remains unresolved unless a source confirms its group membership.

## 2. Ingestion and normalization

1. Parse the CSV with a real CSV parser, preserving raw fields.
2. Parse ISO dates as `%Y-%m-%d` and slash dates as `%d/%m/%Y`.
3. Trim whitespace, Unicode-normalize, case-fold, and collapse internal whitespace for comparison. Preserve the original spelling for output.
4. Deduplicate exact repeated bills of lading. If the same BOL ID has conflicting content, retain one record, park it as a data-quality issue, and do not silently merge it.
5. Parse the registry notes into Company nodes, aliases, group-membership claims, and Evidence nodes before resolving shipment parties.

### Entity resolution

Resolve a manifest name in this order:

```text
1. Exact normalized canonical-name match.
2. Exact normalized match against a known name variant.
3. Guarded fuzzy match against known canonical names and variants.
4. If unresolved or ambiguous, create an unverified Company node.
```

Expose a `--entity-match-threshold` argument for fuzzy matching, expressed as normalized Levenshtein similarity from `0.00` to `1.00`; default to `0.94`.

```python
def normalized_similarity(left: str, right: str) -> float:
    longest = max(len(left), len(right))
    return 0.0 if longest == 0 else 1 - levenshtein_distance(left, right) / longest
```

Apply fuzzy matching only when the best score is at least the threshold **and** exceeds the second-best score by at least `0.05`. Where both countries are present, require them to match. Otherwise, preserve a separate unverified Company node and add a review flag. This prevents a shared token such as `Solstice` from causing a false merge.

For the supplied data, exact normalization plus the documented alias handles the intended cases; fuzzy matching is a controlled fallback, not the primary resolution method.

## 3. Candidate filtering and graph traversal

The root company is Tier 1. An inbound shipment to a company at Tier *n* makes its shipper a Tier *n + 1* candidate.

```python
queue = [(root_company_id, 1, [root_company_id], 1.0)]
expanded = set()

while queue:
    buyer_id, buyer_tier, path, path_score = queue.pop(0)
    if buyer_id in expanded:
        continue
    expanded.add(buyer_id)

    for shipment in inbound_shipments[buyer_id]:
        supplier_id = shipment.shipper_company_id

        if same_confirmed_group(supplier_id, buyer_id):
            park(shipment, "intra_group")
            continue
        if is_pass_through(shipment.product_description):
            park(shipment, "freight_logistics_or_packaging")
            continue
        if supplier_id in path:
            record_cycle(path + [supplier_id], shipment)
            continue

        relationship_score = score_relationship(
            shipment,
            distinct_bol_count_for_pair(supplier_id, buyer_id),
        )
        hop_penalty = 1.0 if buyer_tier == 1 else 0.90
        candidate = record_candidate(
            supplier_id=supplier_id,
            buyer_id=buyer_id,
            tier=buyer_tier + 1,
            path=path + [supplier_id],
            score=path_score * relationship_score * hop_penalty,
            bill_of_lading_id=shipment.bill_of_lading_id,
        )
        queue.append((supplier_id, buyer_tier + 1,
                      path + [supplier_id], candidate.score))
```

The output is not a tree: retain multiple paths to the same company and report a company at its shallowest discovered tier. Use a visited/expanded set only to prevent repeat expansion and infinite loops; do not discard alternative shipment evidence.

`is_pass_through` should initially use a conservative, explainable vocabulary: `packaging`, `freight`, and `logistics`. It should park—not delete—these rows. “Unrelated” in registry evidence is an entity-resolution fact, not automatically a shipment exclusion: it prevents a group/alias merge, while product and supplier-role rules decide whether the relationship is material-relevant.

## 4. Confidence calculation

Score each accepted `supplier -> buyer` relationship between 0 and 1:

```text
relationship score = 0.30 × entity-resolution certainty
                   + 0.30 × material relevance
                   + 0.25 × repeated-shipment evidence
                   + 0.15 × data completeness
```

Suggested factors:

| Signal | Factor |
|---|---:|
| Exact canonical or documented-alias resolution | 1.00 |
| Guarded fuzzy resolution | its normalized similarity score |
| Unverified company node | 0.60 |
| Named material / chemical input | 1.00 |
| Material relevance unclear | 0.50 |
| Freight, logistics, or packaging | 0.00; park |
| One distinct BOL for the company pair | 0.60 |
| Two distinct BOLs for the company pair | 0.80 |
| Three or more distinct BOLs for the pair | 1.00 |
| Missing shipper, consignee, date, or product | park as invalid |
| Missing country | subtract 0.10 from completeness |
| Missing weight | subtract 0.05 from completeness |

Use `0.60` for a pair with one distinct BOL. The distinct-BOL count excludes CSV duplicates; vessel name has no effect on confidence.

For a path with *h* supply relationships:

```text
path_score = product(relationship_score for every relationship) × 0.90^(h - 1)
```

The final term expresses the product requirement that deeper discoveries are less certain even when each individual shipment appears credible. If more than one path reaches the same company, retain every path but use the strongest path as the displayed company score. Do not combine paths in this prototype because they may represent correlated customs evidence.

```text
company_score = max(path_score for every discovered path)
```

Label scores for display:

```text
High:   score >= 0.75
Medium: 0.45 <= score < 0.75
Low:    score < 0.45
```

Only High and Medium candidates should be buyer-facing by default. Low-confidence candidates remain available for analyst review, alongside the reason for their lower score.

## 5. Deliverables and checks

The prototype should write three auditable outputs:

1. `tier_n_candidates.json` — canonical supplier, shallowest tier, all paths, score/label, material, and BOL evidence.
2. `parked_shipments.json` — excluded rows and explicit reasons, including intra-group and pass-through cases.
3. `cycles.json` — circular paths, if encountered.

Verify the implementation with cases covering: whitespace/case normalization, the Bergwerk alias, the unrelated Solstice Analytics name, duplicate BOLs, both date formats, missing optional fields, logistics/packaging exclusion, a Tier 3+ path, and a detected cycle.
