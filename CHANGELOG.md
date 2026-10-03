# Changelog

Releases are tagged `vYYYY.MM` and deposited on Zenodo (docs/uri-policy.md §4). Alpha
pre-releases (`vYYYY.MM-alpha.N`) are snapshots for discussion with no DOI and no promise of
persistence; until the first full release HECTOR is an **alpha** and records and URIs may change.

## Unreleased (alpha)

- **Qualifiers are on the rates, not separate commodities.** A Book of Rates entry such as
  "Saffron of beyownd the se" is now a rate on *saffron* that names its qualifier, rather than a
  record of its own. Each qualifier has its modern name (with its AAT concept or Wikidata place)
  where it is a spelling in the London Customs Accounts qualifier list, and otherwise is given in
  the book's words. The 686 qualified-commodity records of v2026.10-alpha.1 are withdrawn: each
  URI still resolves, to a deprecated record replaced by its base commodity. Their labels were
  spelling-folded ("saffron (beiound se)"), and about a fifth were minted because a price differed
  between books rather than between qualifiers.
- New vocabulary term `hector:qualifier`.

## v2026.10-alpha.1 (3 October 2026): alpha pre-release

A snapshot for discussion. **It promises nothing persistent**: no DOI, and records, URIs and
ledgers may still change or be withdrawn before the first full release.

First publication. Stuart Jenks granted CC BY 4.0 on his transcriptions and all data derived
from them.

- 2,452 commodities from the London Customs Accounts glossary, with their attested spellings
  (dated where the source allows), late Middle English phonetic keys, descriptions, groups,
  AAT and Wikidata identifiers, and counts of occurrence in the London customs accounts.
- 688 commodities as the Books of Rates price them, each linked to its commodity, carrying
  1,834 customs rates from the books of 1507, 1545 and 1558, with the source line quoted.
- 248 units of measure, with their sourced definitions and conversions; five kinds of
  quantity; no links to vocabularies of modern units, by design.
- JSON-LD aligned with Linked Art, Turtle, RDF/XML, and a Turtle dump of every record.
- Slug ledgers recording how every URI was minted and what replaced it.
- A site at https://w3id.org/hector/: search by any attested spelling or a near miss, and a
  readable view of every record.
- A validator that dereferences every external identifier, with tests proving each check can
  fail; CI on every push.

Deferred to later versions: the 1604 Book of Rates; harmonisation with the Sound Toll
Registers.
