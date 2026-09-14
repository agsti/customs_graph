# Customs Tier-N Candidate Discovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a Python application that reads the supplied customs extract, applies embedded registry facts, discovers upstream Tier-N supplier candidates, writes auditable JSON results, and opens an interactive graph in the browser.

**Architecture:** Use a standard source layout under `src/customs_tier_n/`. Parsers create domain objects, repositories resolve companies and own the NetworkX graph, the controller filters and traverses it, and the visualization layer renders a company projection with PyVis.

**Tech Stack:** uv; Python 3.12+; NetworkX 3.6; PyVis 0.3; pytest 8; Python standard library.

**Spec:** `assignment.md` and `architecture.md`

## Global Constraints

- Keep application code under `src/customs_tier_n/`.
- Split code into `model`, `parser`, `repository`, `controller`, and `visualization` packages.
- Apply exact and documented-alias resolution before guarded fuzzy matching.
- Default `--entity-match-threshold` to `0.94`, require a `0.05` winning margin, and require matching countries when both are known.
- Never infer corporate-group membership from a shared name token.
- Park invalid, intra-group, freight, logistics, and generic-packaging records with explicit reasons.
- Preserve every distinct BOL as evidence and ignore exact CSV duplicates.
- Include all accepted tiers in the analyst graph; distinguish Low confidence visually.
- Generate a self-contained `output/tier_n_graph.html` and open it by default.
- Keep NetworkX and PyVis out of the model and parser layers.
- The workspace currently has no Git metadata; do not initialize Git as part of this implementation.

---

## Behavioral contract

Use a heterogeneous `networkx.MultiDiGraph` containing Company, Shipment, Product, CorporateGroup, GroupMembershipClaim, and Evidence nodes. The visible graph is a projection containing Company nodes and aggregated `SUPPLIES` edges, with BOLs and product descriptions in hover text.

Resolve names in this order: normalized canonical name, documented alias, guarded normalized-Levenshtein match, then a new unverified Company. Keep the raw shipper and consignee strings on Shipment objects for auditability.

Calculate relationship confidence as:

```text
0.30 × entity resolution
+ 0.30 × material relevance
+ 0.25 × repeated-shipment evidence
+ 0.15 × data completeness
```

Calculate a candidate path as `product(relationship scores) × 0.90^(relationship count - 1)`. Retain alternate paths, display the strongest path score, and report the shallowest discovered tier.

---

## File structure

```text
pyproject.toml
uv.lock
src/customs_tier_n/
├── __init__.py
├── __main__.py
├── cli.py
├── model/
│   ├── __init__.py
│   ├── entities.py
│   └── confidence.py
├── parser/
│   ├── __init__.py
│   └── customs_parser.py
├── repository/
│   ├── __init__.py
│   ├── company_repository.py
│   ├── registry_repository.py
│   ├── shipment_repository.py
│   ├── graph_repository.py
│   └── result_repository.py
├── controller/
│   ├── __init__.py
│   └── discovery_controller.py
└── visualization/
    ├── __init__.py
    └── browser_graph.py
tests/
├── test_model.py
├── test_customs_parser.py
├── test_company_repository.py
├── test_registry_repository.py
├── test_shipment_repository.py
├── test_graph_repository.py
├── test_confidence.py
├── test_discovery_controller.py
├── test_result_repository.py
├── test_browser_graph.py
└── test_cli.py
```

---

### Task 1: Create the uv project and domain model

**Files:**

- Create: `pyproject.toml`
- Create: `src/customs_tier_n/__init__.py`
- Create: `src/customs_tier_n/__main__.py`
- Create: `src/customs_tier_n/model/__init__.py`
- Create: `src/customs_tier_n/model/entities.py`
- Test: `tests/test_model.py`

**Interfaces:**

- Consumes: no application interfaces.
- Produces: all dataclasses and enums used by later layers.

- [ ] **Step 1: Add project metadata**

Create `pyproject.toml`:

```toml
[project]
name = "customs-tier-n"
version = "0.1.0"
description = "Tier-N supplier discovery from customs manifests"
requires-python = ">=3.12"
dependencies = [
  "networkx>=3.6,<4",
  "pyvis>=0.3.2,<0.4",
]

[project.scripts]
tier-n-discovery = "customs_tier_n.cli:main"

[dependency-groups]
dev = ["pytest>=8,<9"]

[build-system]
requires = ["hatchling"]
build-backend = "hatchling.build"

[tool.hatch.build.targets.wheel]
packages = ["src/customs_tier_n"]

[tool.pytest.ini_options]
testpaths = ["tests"]
```

- [ ] **Step 2: Sync dependencies**

Run: `uv sync --dev`

Expected: `uv.lock` is created and NetworkX, PyVis, and pytest install.

- [ ] **Step 3: Write the first model test**

```python
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
```

- [ ] **Step 4: Verify the test fails**

Run: `uv run pytest tests/test_model.py -v`

Expected: FAIL because `customs_tier_n.model.entities` does not exist.

- [ ] **Step 5: Implement domain types**

Use frozen, slotted dataclasses for source facts and mutable dataclasses for accumulated results. Define:

```text
ResolutionMethod: exact, alias, fuzzy, created
Company: id, canonical_name, country, name_variants
Shipment: bill_of_lading_id, shipment_date, shipper_name, shipper_country,
          consignee_name, consignee_country, product_description, weight_kg,
          vessel_name
AliasFact: canonical_name, canonical_country, alias, evidence_id
GroupFact: group_id, company_names, evidence_id
EvidenceFact: id, source, statement
RegistryFacts: aliases, groups, evidences, unrelated_names, pass_through_terms
ResolvedCompany: company, method, confidence, raw_name
RelationshipEvidence: supplier, buyer, shipments
ConfidenceBreakdown: entity_resolution, material_relevance,
                     repeated_shipments, data_completeness, total
CandidatePath: company_ids, relationship_scores, bol_ids,
               product_descriptions, score
Candidate: company, tier, paths, confidence, label
ParkedShipment: bill_of_lading_id, reason, supplier_id, buyer_id
DataQualityIssue: bill_of_lading_id, reason
CycleRecord: company_ids, bill_of_lading_id
DiscoveryResult: root_company_id, candidates, parked_shipments,
                 data_quality_issues, cycles
```

Use `date` for shipment dates, `float | None` for weight, `tuple` for immutable collections, and `list` or `dict` only for accumulated result collections. Make `DiscoveryResult.candidates` a `dict[str, Candidate]` keyed by company ID.

Make `src/customs_tier_n/__main__.py` call `customs_tier_n.cli.main()`.

- [ ] **Step 6: Verify the model**

Run: `uv run pytest tests/test_model.py -v`

Expected: PASS.

---

### Task 2: Parse the customs source

**Files:**

- Create: `src/customs_tier_n/parser/__init__.py`
- Create: `src/customs_tier_n/parser/customs_parser.py`
- Test: `tests/test_customs_parser.py`

**Interfaces:**

- Consumes: a customs CSV path and model dataclasses.
- Produces: `parse_customs(path: Path) -> list[Shipment]`.

- [ ] **Step 1: Write customs parser tests**

Use a temporary CSV containing an ISO date and a `DD/MM/YYYY` date. Assert trimmed names and nullable optional values:

```python
records = parse_customs(csv_path)

assert records[0].shipment_date == date(2026, 6, 24)
assert records[1].shipment_date == date(2026, 6, 13)
assert records[1].consignee_name == "Boreal Resins Inc"
assert records[1].consignee_country is None
assert records[1].weight_kg is None
assert records[1].vessel_name is None
```

Add parameterized cases proving that missing shipper, consignee, date, or product raises `InvalidShipmentError` containing the BOL ID.

- [ ] **Step 2: Verify customs tests fail**

Run: `uv run pytest tests/test_customs_parser.py -v`

Expected: FAIL because the customs parser does not exist.

- [ ] **Step 3: Implement the customs parser**

Use `csv.DictReader`. Strip all strings but retain their casing. Parse dates by trying `%Y-%m-%d` and `%d/%m/%Y`. Convert blank country, weight, and vessel fields to `None`. Return every parsed row, including duplicates; deduplication belongs to the repository layer.

- [ ] **Step 4: Verify the customs parser**

Run: `uv run pytest tests/test_customs_parser.py -v`

Expected: PASS.

---

### Task 3: Normalize names and deduplicate shipments

**Files:**

- Create: `src/customs_tier_n/repository/__init__.py`
- Create: `src/customs_tier_n/repository/company_repository.py`
- Create: `src/customs_tier_n/repository/registry_repository.py`
- Create: `src/customs_tier_n/repository/shipment_repository.py`
- Test: `tests/test_company_repository.py`
- Test: `tests/test_registry_repository.py`
- Test: `tests/test_shipment_repository.py`

**Interfaces:**

- Consumes: `RegistryFacts` and parsed `Shipment` objects.
- Produces: `StaticRegistryRepository.get() -> RegistryFacts`, `normalize_company_name(name: str) -> str`, `normalized_similarity(left, right) -> float`, `CompanyRepository.resolve(name, country, threshold) -> ResolvedCompany`, `ShipmentRepository.unique_shipments() -> tuple[Shipment, ...]`, and `ShipmentRepository.issues() -> tuple[DataQualityIssue, ...]`.

- [ ] **Step 1: Write the static registry test**

```python
facts = StaticRegistryRepository().get()

assert facts.aliases[0].canonical_name == "Solstice Materials Europe GmbH"
assert facts.aliases[0].alias == "Bergwerk Mining Alias GmbH"
assert "Solstice Materials Co" in facts.groups[0].company_names
assert facts.evidences[0].source == "corporate_registry_notes.txt"
assert "Solstice Analytics Inc" in facts.unrelated_names
assert facts.pass_through_terms == ("packaging", "freight", "logistics")
```

- [ ] **Step 2: Verify the static registry test fails**

Run: `uv run pytest tests/test_registry_repository.py -v`

Expected: FAIL because `StaticRegistryRepository` does not exist.

- [ ] **Step 3: Implement the static registry repository**

Return immutable `RegistryFacts` containing the alias, confirmed Solstice group membership, unrelated Solstice Analytics fact, pass-through terms, and short `EvidenceFact` statements extracted from `corporate_registry_notes.txt`. The application must not read or parse that text file at runtime.

- [ ] **Step 4: Verify the static registry repository**

Run: `uv run pytest tests/test_registry_repository.py -v`

Expected: PASS.

- [ ] **Step 5: Write company repository tests**

```python
assert normalize_company_name("  AURORA   PIGMENTS LTD ") == "aurora pigments ltd"
assert normalized_similarity("aurora pigments ltd", "aurora pigment ltd") > 0.94

alias = companies.resolve("Bergwerk Mining Alias GmbH", "DE", threshold=0.94)
assert alias.company.canonical_name == "Solstice Materials Europe GmbH"
assert alias.method is ResolutionMethod.ALIAS
assert alias.confidence == 1.0

analytics = companies.resolve("Solstice Analytics Inc", "US", threshold=0.94)
assert analytics.company.id != solstice.company.id
```

Add tests rejecting fuzzy matches below the threshold, within `0.05` of the runner-up, or conflicting with a known country.

- [ ] **Step 6: Verify company tests fail**

Run: `uv run pytest tests/test_company_repository.py -v`

Expected: FAIL because the repository does not exist.

- [ ] **Step 7: Implement company resolution**

Normalize with Unicode NFKC, `casefold()`, trimming, and collapsed internal whitespace. Do not remove legal suffixes. Implement Levenshtein distance with a two-row dynamic-programming matrix and normalize it as:

```text
1 - distance / max(length(left), length(right))
```

Return `0.0` if both values are empty. Resolve in this order: canonical exact, alias exact, unique guarded fuzzy match, new unverified Company. Seed all registry names before customs resolution. Generate deterministic IDs from normalized canonical name and country.

- [ ] **Step 8: Verify company resolution**

Run: `uv run pytest tests/test_company_repository.py -v`

Expected: PASS.

- [ ] **Step 9: Write shipment repository tests**

Given two identical `BOL100021` rows, assert one unique shipment and no issue. Given conflicting content under the same BOL, retain the first row and assert:

```python
assert repository.issues() == (
    DataQualityIssue(
        bill_of_lading_id="BOL100021",
        reason="conflicting_duplicate_bol",
    ),
)
```

- [ ] **Step 10: Verify shipment repository tests fail**

Run: `uv run pytest tests/test_shipment_repository.py -v`

Expected: FAIL because `ShipmentRepository` does not exist.

- [ ] **Step 11: Implement shipment deduplication**

Index by stripped BOL ID. Ignore exact dataclass duplicates. For a conflicting duplicate, retain the first record and append one `DataQualityIssue`; do not create graph nodes from the conflicting row.

- [ ] **Step 12: Verify repositories**

Run: `uv run pytest tests/test_registry_repository.py tests/test_company_repository.py tests/test_shipment_repository.py -v`

Expected: PASS.

---

### Task 4: Build the heterogeneous NetworkX repository

**Files:**

- Create: `src/customs_tier_n/repository/graph_repository.py`
- Test: `tests/test_graph_repository.py`

**Interfaces:**

- Consumes: canonical companies, resolved parties, shipments, and registry facts.
- Produces: `GraphRepository.graph: nx.MultiDiGraph`, `add_registry_facts(facts, companies)`, `add_shipment(shipment, shipper, consignee)`, `same_confirmed_group(left_id, right_id) -> bool`, and `inbound_relationships(buyer_id) -> tuple[RelationshipEvidence, ...]`.

- [ ] **Step 1: Write shipment graph tests**

Add `Terra Silica Partners -> BOL100007 -> Solstice Materials Co` and assert:

```python
assert graph.nodes[terra_id]["node_type"] == "company"
assert graph.nodes["shipment:BOL100007"]["node_type"] == "shipment"
assert graph.has_edge(terra_id, "shipment:BOL100007", key="shipped")
assert graph.has_edge(
    "shipment:BOL100007",
    solstice_id,
    key="consigned_to",
)
```

Assert that the Shipment has a `carries` edge to a normalized Product node.

- [ ] **Step 2: Write registry graph and inbound-query tests**

Assert registry ingestion creates CorporateGroup, GroupMembershipClaim, and Evidence nodes with `subject_of`, `member_of`, and `supports` edges. Then assert:

```python
assert repository.same_confirmed_group(solstice_id, europe_id) is True
assert repository.same_confirmed_group(solstice_id, analytics_id) is False

relationships = repository.inbound_relationships(solstice_id)
assert relationships[0].supplier.company.id == terra_id
assert relationships[0].shipments[0].bill_of_lading_id == "BOL100007"
```

- [ ] **Step 3: Verify graph tests fail**

Run: `uv run pytest tests/test_graph_repository.py -v`

Expected: FAIL because `GraphRepository` does not exist.

- [ ] **Step 4: Implement the graph repository**

Store `node_type` on every node and `edge_type` on every edge. Use BOL IDs for Shipment node IDs and normalized descriptions for Product node IDs. Use stable edge keys `shipped`, `consigned_to`, and `carries`; claim/evidence edge keys include their claim ID. Resolve every customs party first, then add registry facts so group-member names without a country can bind to the unique canonical Company already observed in the manifests.

`inbound_relationships` must walk from a buyer Company to predecessor Shipment nodes, then to predecessor supplier Companies, and aggregate distinct shipments by canonical `(supplier_id, buyer_id)`.

- [ ] **Step 5: Verify the graph repository**

Run: `uv run pytest tests/test_graph_repository.py -v`

Expected: PASS.

---

### Task 5: Implement confidence and Tier-N traversal

**Files:**

- Create: `src/customs_tier_n/model/confidence.py`
- Create: `src/customs_tier_n/controller/__init__.py`
- Create: `src/customs_tier_n/controller/discovery_controller.py`
- Test: `tests/test_confidence.py`
- Test: `tests/test_discovery_controller.py`

**Interfaces:**

- Consumes: `GraphRepository`, `RelationshipEvidence`, pass-through terms, and a root company ID.
- Produces: `classify_material(description, pass_through_terms) -> float | None`, `score_relationship(evidence, pass_through_terms) -> ConfidenceBreakdown | None`, `confidence_label(score) -> str`, and `TierNDiscoveryController.discover(root_company_id) -> DiscoveryResult`.

- [ ] **Step 1: Write confidence tests**

```python
breakdown = score_relationship(
    exact_material_relationship_with_two_bols,
    pass_through_terms=("packaging", "freight", "logistics"),
)

assert breakdown is not None
assert breakdown.entity_resolution == 1.0
assert breakdown.material_relevance == 1.0
assert breakdown.repeated_shipments == 0.8
assert breakdown.data_completeness == 1.0
assert breakdown.total == pytest.approx(0.95)
```

Also assert: packaging returns `None`; an unclear product scores `0.50`; one, two, and three BOLs score `0.60`, `0.80`, and `1.00`; missing country subtracts `0.10`; missing weight subtracts `0.05`; missing vessel has no effect.

- [ ] **Step 2: Verify confidence tests fail**

Run: `uv run pytest tests/test_confidence.py -v`

Expected: FAIL because `score_relationship` does not exist.

- [ ] **Step 3: Implement pure confidence functions**

Keep this module free of NetworkX and PyVis. Match material stems for alumina, titanium, pigment, silica, quartz, borate, resin, bisphenol, phenol, benzene, feedstock, ore, flocculant, acrylamide, monomer, reagent, cobalt, and chemical. Return `None` for pass-through terms, `1.00` for a material match, and `0.50` otherwise.

For entity resolution use the lower of supplier and buyer resolution confidence. Average material relevance and data completeness across eligible shipments. Calculate the weighted total exactly as specified; round only for display.

- [ ] **Step 4: Verify confidence**

Run: `uv run pytest tests/test_confidence.py -v`

Expected: PASS.

- [ ] **Step 5: Write traversal tests**

Construct this synthetic graph:

```text
Root <- A <- B <- C
       ^         |
       +---------+
Root <- confirmed group member
Root <- packaging forwarder
```

Assert A, B, and C are Tier 2, 3, and 4; group member and forwarder are parked; the back-edge records a cycle; and:

```python
assert result.candidates[a_id].paths[0].score == pytest.approx(a_score)
assert result.candidates[b_id].paths[0].score == pytest.approx(
    a_score * b_relationship_score * 0.90
)
```

Add an alternate route to B. Assert both paths remain, while B uses its shallowest tier and strongest path score.

- [ ] **Step 6: Verify traversal tests fail**

Run: `uv run pytest tests/test_discovery_controller.py -v`

Expected: FAIL because `TierNDiscoveryController` does not exist.

- [ ] **Step 7: Implement breadth-first discovery**

Use `collections.deque` entries `(buyer_id, tier, company_path, path_score)`. For each inbound relationship:

1. Park it if supplier and buyer have confirmed membership in the same group.
2. Remove pass-through shipments; park the relationship if none remain.
3. Record a cycle and stop that branch if the supplier is already in `company_path`.
4. Score the remaining evidence.
5. Multiply by the parent path score and use a hop multiplier of `1.0` for Tier 2 or `0.90` thereafter.
6. Retain all paths, minimum tier, and maximum path confidence.
7. Expand each Company once at its shallowest tier; stop when the queue is empty.

- [ ] **Step 8: Verify traversal**

Run: `uv run pytest tests/test_confidence.py tests/test_discovery_controller.py -v`

Expected: PASS.

---

### Task 6: Write results, render the browser graph, and expose the CLI

**Files:**

- Create: `src/customs_tier_n/repository/result_repository.py`
- Create: `src/customs_tier_n/visualization/__init__.py`
- Create: `src/customs_tier_n/visualization/browser_graph.py`
- Create: `src/customs_tier_n/cli.py`
- Test: `tests/test_result_repository.py`
- Test: `tests/test_browser_graph.py`
- Test: `tests/test_cli.py`

**Interfaces:**

- Consumes: `DiscoveryResult`, customs path, threshold, output directory, and browser flag.
- Produces: `ResultRepository.write(result, output_dir) -> tuple[Path, Path, Path]`, `BrowserGraph.render(result, output_path) -> Path`, and `main(argv: Sequence[str] | None = None) -> int`.

- [ ] **Step 1: Write result-repository tests**

```python
candidate_path, parked_path, cycles_path = repository.write(result, tmp_path)

assert candidate_path.name == "tier_n_candidates.json"
assert parked_path.name == "parked_shipments.json"
assert cycles_path.name == "cycles.json"
assert json.loads(candidate_path.read_text())["root_company_id"] == root_id
```

- [ ] **Step 2: Verify result-repository tests fail**

Run: `uv run pytest tests/test_result_repository.py -v`

Expected: FAIL because `ResultRepository` does not exist.

- [ ] **Step 3: Implement deterministic JSON**

Create the output directory. Serialize dataclasses to JSON-safe dictionaries, sort candidates by `(tier, canonical_name)`, sort BOL IDs, and use UTF-8 with two-space indentation. Include data-quality issues in `parked_shipments.json` under a separate `data_quality_issues` key.

- [ ] **Step 4: Write browser rendering tests**

Render Root plus High, Medium, and Low candidates. Assert `tier_n_graph.html` exists and contains every company name, `vis-network`, all three labels, and the supporting BOL IDs.

- [ ] **Step 5: Verify browser rendering tests fail**

Run: `uv run pytest tests/test_browser_graph.py -v`

Expected: FAIL because `BrowserGraph` does not exist.

- [ ] **Step 6: Implement PyVis rendering**

Build a Company-only projection with one directed `supplier -> buyer` edge per relationship. Put score, label, tier, products, and BOL IDs in hover text. Style Root gold, High green, Medium orange, and Low gray. Use `Network(directed=True, cdn_resources="in_line", height="900px", bgcolor="#ffffff")`, a right-to-left hierarchical layout, and `write_html(open_browser=False, notebook=False)`.

- [ ] **Step 7: Write CLI tests**

Call `main` with the supplied customs file, `tmp_path`, threshold `0.94`, and `--no-open-browser`. Assert exit code `0` and:

```text
tier_n_candidates.json
parked_shipments.json
cycles.json
tier_n_graph.html
```

In a second test, patch `webbrowser.open`, omit `--no-open-browser`, and assert one call with the HTML file URI.

- [ ] **Step 8: Verify CLI tests fail**

Run: `uv run pytest tests/test_cli.py -v`

Expected: FAIL because `customs_tier_n.cli` does not exist.

- [ ] **Step 9: Implement CLI orchestration**

Define:

```text
--customs PATH                  default customs_extract.csv
--root NAME                     default Solstice Materials Co
--entity-match-threshold FLOAT  default 0.94, range 0.0–1.0
--output-dir PATH               default output
--open-browser / --no-open-browser
```

Default browser opening to true with `argparse.BooleanOptionalAction`. Parse the customs source, load `StaticRegistryRepository`, populate repositories, build the graph, run discovery, write JSON, render HTML, print all four paths, and call `webbrowser.open(html_path.resolve().as_uri())`. Invalid inputs return non-zero with a concise message. Browser-open failure does not fail discovery; print the HTML path.

- [ ] **Step 10: Verify outputs and CLI**

Run: `uv run pytest tests/test_result_repository.py tests/test_browser_graph.py tests/test_cli.py -v`

Expected: PASS.

---

### Task 7: Verify the supplied dataset end to end

**Files:**

- Modify: `architecture.md`
- Modify: `tests/test_cli.py`

**Interfaces:**

- Consumes: complete application plus `customs_extract.csv` and embedded registry facts.
- Produces: verified JSON and browser artifacts under `output/`.

- [ ] **Step 1: Add real-data assertions**

Index candidate JSON records by `canonical_name`, then assert:

```python
assert candidates["Terra Silica Partners"]["tier"] == 2
assert candidates["Quartz Extraction Co"]["tier"] == 3
assert candidates["Acrylamide Monomer Pty"]["tier"] == 5
assert "Bergwerk Mining Alias GmbH" not in candidates
assert "Solstice Materials Europe GmbH" not in candidates
assert any(item["reason"] == "intra_group" for item in parked)
assert any(
    item["reason"] == "freight_logistics_or_packaging"
    for item in parked
)
```

- [ ] **Step 2: Run all tests**

Run: `uv run pytest -v`

Expected: all tests PASS.

- [ ] **Step 3: Run the application**

```bash
uv run tier-n-discovery \
  --customs customs_extract.csv \
  --root "Solstice Materials Co" \
  --entity-match-threshold 0.94 \
  --output-dir output
```

Expected: the default browser opens `output/tier_n_graph.html`, and the terminal prints that path plus the three JSON paths.

- [ ] **Step 4: Inspect the visible result**

Confirm the graph starts at Solstice, follows directed upstream relationships through Tier 5, colors nodes by confidence, shows scores/products/BOLs on hover, includes Low candidates for analyst inspection, and omits parked links. Confirm `cycles.json` remains valid when no cycle exists in the supplied extract.

- [ ] **Step 5: Align architecture documentation**

Keep the two Mermaid diagrams at overview level. Add the exact run command and four output filenames to `architecture.md`; change component names only if the final implementation differs from the approved architecture.
