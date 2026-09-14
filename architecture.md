# Tier-N Discovery Architecture

This prototype treats customs manifests as evidence of a potential upstream supply relationship. It uses a Python `NetworkX.MultiDiGraph` so multiple shipment records, typed nodes, typed edges, and cycles are preserved.

```mermaid
flowchart LR
    subgraph Sources
        CSV[customs_extract.csv<br/>raw shipment records]
        Registry[corporate_registry_notes.txt<br/>aliases, group facts, exclusions]
    end

    CSV --> Parse[CSV parser<br/>dates, required fields, raw-value retention]
    Parse --> Clean[Normalize and deduplicate<br/>trim, case-fold, whitespace,<br/>BOL duplicate handling]

    Registry --> RegistryModel[Registry model<br/>Company variants, CorporateGroup,<br/>GroupMembershipClaim, Evidence]
    Clean --> Resolve[Entity resolver<br/>exact canonical match → alias match<br/>→ guarded fuzzy match]
    RegistryModel --> Resolve

    Resolve --> GraphIngest
    RegistryModel --> GraphIngest

    subgraph EvidenceGraph[NetworkX MultiDiGraph — heterogeneous evidence graph]
        GraphIngest[Build typed graph]
        Company[Company nodes]
        Shipment[Shipment nodes]
        Product[Product nodes]
        Group[CorporateGroup nodes]
        Claim[GroupMembershipClaim nodes]
        Evidence[Evidence nodes]

        Company -->|SHIPPED| Shipment
        Shipment -->|CONSIGNED_TO| Company
        Shipment -->|CARRIES| Product
        Company -->|SUBJECT_OF| Claim
        Claim -->|MEMBER_OF| Group
        Evidence -->|SUPPORTS| Claim
    end

    GraphIngest --> Traverse[BFS upstream traversal<br/>start: Solstice Materials Co<br/>follow inbound shipments]
    Traverse --> Filter{Candidate filter}

    Filter -->|confirmed intra-group| Parked[Parked evidence<br/>reason: intra_group]
    Filter -->|freight / logistics / packaging| Parked
    Filter -->|cycle found| Cycles[Cycle report]
    Filter -->|material-supplier candidate| Score[Confidence scorer]

    Score --> TierGraph[Projected supply graph<br/>Company ──SUPPLIES──> Company]
    Score --> Candidates[Tier-N candidates JSON<br/>tier, paths, BOL evidence,<br/>score and confidence label]

    TierGraph --> Visual[PyVis interactive HTML<br/>or NetworkX/Matplotlib PNG]
```

## Resolution and filtering rules

1. Normalize manifest names; retain their original spelling on Shipment nodes.
2. Resolve documented aliases before fuzzy matching. `Bergwerk Mining Alias GmbH` resolves to `Solstice Materials Europe GmbH`.
3. Fuzzy resolution is opt-in via `--entity-match-threshold` (default `0.94` normalized Levenshtein similarity), requires a `0.05` margin over the next candidate, and requires country agreement where both countries exist.
4. Do not infer corporate membership from a shared name token: `Solstice Analytics Inc` remains a separate company.
5. Park, rather than delete, confirmed intra-group and pass-through records so every exclusion remains explainable.

## Traversal and confidence

Solstice is Tier 1. For each shipment delivered to a company at Tier *n*, its shipper is a Tier *n + 1* candidate. The traversal records alternate paths and cycles but expands each company only once at its shallowest discovered tier.

```text
edge score = resolution × material relevance × shipment evidence × completeness
path score = product(edge scores) × 0.90^(number of shipment edges - 1)
```

Only High and Medium confidence candidates are buyer-facing by default. Low-confidence candidates, parked records, and cycles remain available for analyst review.
