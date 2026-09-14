Product Engineer Case Study: Tier N Discovery from Customs Trade Data
Context
At EcoVadis we track confirmed Tier 1 relationships between a buyer and its direct suppliers. Buyers keep asking what their Tier 1 supplier's own suppliers look like, meaning Tier 2, Tier 3 and beyond (we call this Tier N). We don't have that today because deeper tiers are never self reported on the platform.
One signal we've been testing is the customs bill of lading data. A lot of countries, the US included, publish import manifests that name both the shipper (who sent the goods) and the consignee (who received them) for every ocean shipment. If a Tier 1 supplier shows up as the consignee on a shipment, the shipper on that shipment is a candidate supplier to them, a Tier 2 candidate. Do that again from each Tier 2 company and you start walking down the chain: Tier 3, Tier 4, and so on.
This case study is not about building a production system. It's about how you reason through an imperfect data source, turn that reasoning into an architecture, and prove the core idea with code that actually runs.
The scenario
Solstice Materials Co is a fictional Tier 1 supplier (aluminum inputs). All company names in this exercise are made up so do not expect finding public insights about them.
Attached, you will find a 12 month extract of US customs records, customs_extract.csv, plus a short companion file, corporate_registry_notes.txt, with a couple of facts you'll need to cross reference.
Your challenge : starting from Solstice Materials Co, walk the chain as far down as the data lets you and produce a Tier N candidate list. You can go as many hops as needed (and potentially identify circular references too).
What to expect in this data
Some of this is visible if you look closely, some of it is structural to this kind of source:
Intra group noise. A chunk of the shipments are the same corporate group shipping to its own regional entities.
Name variants and outright renames. The same real company can show up under different strings, including a rename that happened mid year (see the companion notes).
Shared names that mean nothing. Two unrelated companies can happen to share part of a name. Don't assume a name match means a group relationship, check.
Pass through entities. Some consignees or shippers are just customs brokers or freight forwarders moving goods on someone else's behalf, not actual material suppliers.
The data itself is dirty, as it always is! Duplicate rows, missing fields, inconsistent casing, inconsistent date formats, stray whitespace. Ordinary data engineering mess, handle it however you'd handle it in real life.
What we want from you
Budget about an hour to an hour plus total. We care more about how you think than about hitting the clock exactly.
Part 1: Trade off memo (about 10 minutes, written, one pager max)
In plain language, what does this source tell you that EcoVadis's own confirmed relationship data can't, and what does it cost you (noise, coverage, confidence)? If you had to choose between this free but noisy customs feed and a paid, cleaner trade data API for a real product feature, what would you weigh?
Part 2: Architecture sketch (about 15 minutes, module/class+sequence diagrams)
Sketch how a pipeline would take this raw extract and turn it into a Tier N signal that's safe to show a buyer. At minimum cover:
Where entity resolution and intra group filtering happens.
Where a confidence score (propose a meta one) gets attached, and how it should behave as you go deeper. Should a Tier 5 guess carry the same weight as a Tier 2 one?
How this would merge with EcoVadis's existing confirmed Tier 1 relationships.
A component list with sequencedata flow is enough. I do not need infra diagram.
Part 3: Working prototype (about 35 to 40 minutes, code)
Write a script, any language, that reads customs_extract.csv and the companion notes (plain text but would be coming from data sources in the real world), and recursively walks the chain from Solstice Materials Co as far as the data supports. Filter out intra-group noise (and park it), renamed entities, coincidental name matches, and pass through entities, and attach a confidence label to whatever survives.
You don't need to fully resolve every branch by hand. Showing that your approach generalizes and applying it correctly through at least Tier 3 is enough, going deeper is a bonus, not a requirement.
Part 4: Wrap up (about 5 to 10 minutes, two or three bullets)
What would you instrument or test before this ship?
What would you explicitly punt to version 2.
What we're evaluating
Do you reason about trade offs (breadth versus noise versus cost) instead of treating the source as ground truth.
Is the architecture coherent, does it show you understand where uncertainty enters and compounds as you go deeper.
Does the prototype actually run and produce something defensible?
Can you say clearly what's out of scope instead of trying to solve everything!
What we are not expecting
Full entity resolution or NLP matching.
Multi country support.
Production grade error handling.
A UI. Console output, CSV, or JSON is fine.

