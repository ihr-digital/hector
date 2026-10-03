"""
Link the Books of Rates to commodities and units, and emit the rates (PLAN.md tasks 14 and 17,
decision 2). Local only: writes into build/ like the other Jenks-derived steps.

    .venv/bin/python -m tools.rates.parse_bor            # build/rates/rates.jsonl
    .venv/bin/python -m tools.export.export_hector       # build/site/commodity, ledger
    .venv/bin/python -m tools.units.build_units          # build/site/unit, units ledger, rates_join
    .venv/bin/python -m tools.rates.link_rates           # this: rates into build/site

WHAT IT DOES, per rate row of the 1507, 1545 and 1558 books (1604 waits for decision D6: its
commodities are to return to the LCA glossary first):

1. LINK THE COMMODITY by matching `commodity_text` against every glossary spelling (the
   glossary's forms, normalised), LONGEST MATCH FIRST, anywhere in the text. The parser's own
   head/qualifier split is 15-20% wrong (PLAN.md task 15), so it is not used. A spelling that
   belongs to two concepts is ambiguous and is not used alone.
2. THE QUALIFIER GOES ON THE RATE (3 Oct 2026, replacing decision 2 of 29 Sep). Words left
   over after the matched spelling -- "Saffron of beyownd the se" -> "beyownd the se" -- say
   which kind of the commodity the rate is set on. Every rate sits on its base commodity and
   names its qualifiers in `qualifier`: by the London Customs Accounts qualifier list's modern
   name where the words are one of its spellings (with its AAT concept or Wikidata place), else
   as the book writes them, classified as an attested variant. No spelling is invented: the
   old records' labels were a spelling fold of the leftover words ("saffron (beiound se)").
   Whether a qualified good is a commodity in its own right is for the glossary's curators
   (as with "white cloth"), not a by-product of a price difference. The 686 qualified records
   decision 2 minted are deprecated, each replaced by its base commodity (ledger/qualified.tsv).
3. THE RATE: a Rate node in the record's `taxation`, id <record>#rate-<book>-<direction>-<line>:
   the amount in pence and as written (£ s d), per <quantity> <unit> (the unit through
   build/units/rates_join.tsv and the units ledger), valid from the book's year to the next
   book's, and the source line quoted in `sourceText`.

Rows that cannot be linked -- no spelling found, only an ambiguous one, no unit, no price --
are listed in build/rates/link-report.md, never guessed.
"""
from __future__ import annotations

import argparse
import collections
import csv
import datetime as dt
import json
import re
import sys
import unicodedata
from pathlib import Path

from tools.phonetics.ipa import transcribe as phonetic_key

REPO = Path(__file__).resolve().parents[2]
LCA = REPO.parent / "London_Customs_Accounts"
BUILD = REPO / "build"
W3ID = "https://w3id.org/hector/"
CONTEXT = ["https://linked.art/ns/v1/linked-art.json", "https://w3id.org/hector/context"]
AAT_PREFERRED = {"id": "aat:300404670", "type": "Type", "_label": "preferred terms"}
AAT_BRIEF = {"id": "aat:300418049", "type": "Type", "_label": "brief texts"}
ATTESTED = {"id": "hector:AttestedVariant", "type": "Type", "_label": "attested variant"}
STERLING = {"id": "aat:300411998", "type": "Currency", "_label": "pound sterling (system of money)"}
BOOKS = ["1507", "1545", "1558", "1604"]
LINKED_BOOKS = ("1507", "1545", "1558")        # 1604 after D6
# Words that join a commodity to its qualifier or its measure, and say nothing of either.
FILLER = {"the", "of", "de", "and", "et", "called", "voc", "vocat", "vocatur", "cont", "conteyning",
          "conteynynge", "conteininge", "conteyninge", "containing", "for", "or", "a", "an", "in",
          "with", "wt", "le", "la", "les", "du", "des", "pro", "per", "every", "each",
          # the books' formulae: "that ys to saye", "whether ytt be", "of all sortes"
          "that", "ys", "is", "to", "saye", "say", "whether", "ytt", "it", "be", "all", "sorte",
          "sortes", "sortte", "manare", "maner", "manner", "one", "another", "on", "by", "at",
          "wyth", "videlicet", "viz"}
# Glossary spellings that are ordinary words in the books' English, and so never link on
# their own away from the head: "every" is a spelling of ivory, "made" and "called" of others.
COMMON = FILLER | {"made", "small", "smalle", "great", "grett", "white", "whyte", "black", "blake",
                   "rede", "red", "browne", "new", "old", "fyne", "fine", "course", "coarse"}
# In the MEASURE phrase these spellings belong to the measure, not to the goods: "the C wyte"
# and "the C wyght" are a hundredweight (not white, not the Isle of Wight), "the grett grosse"
# and "the small grosse" are measures, as are the half and the whole piece, "the skynne" and
# "the full". Listed, not inferred: each was read in the rows that carry it (3 Oct 2026).
MEASURE_SENSE = {"wyght", "wyte", "weyte", "wayte", "weyght", "wayght", "small", "smalle", "smale",
                 "grett", "gret", "great", "greate", "hallfe", "halfe", "half", "di", "hole", "whole",
                 "skynne", "skynnes", "full"}
# Rows the matcher links to the wrong concept, read one by one (3 Oct 2026, from the qualifier
# review: the qualifier column made them visible). (book, direction, line) -> the concept, or
# None where the glossary has no concept for these goods yet (they are then reported, not linked).
# With the concept, the words that name the goods in the entry, which are then not a qualifier:
# several are spellings the glossary lacks ("Rose algar", "Bell mettell", "Sackclothe").
# The head-first rule takes a modifier for the goods ("Salt hydes" -> salt, "Bell mettell" ->
# bell); a single word later on can be the material ("Pulleys of yron" -> iron).
LINK_OVERRIDES = {
    ("1507", "none", "10"): ("buckram", "buckroms"),                           # Buckroms in paperes (not pecia)
    ("1545", "inward", "72"): ("balance", "ballandes ballance"),               # Ballandes called ounce ballance (not ounce)
    ("1545", "inward", "601"): ("realgar", "rose algar"),                      # Rose algar = rosalgar (not rose)
    ("1558", "inward", "896"): ("realgar", "rose algar"),
    ("1545", "inward", "610"): ("knife", "knyves"),                            # Rone knyves: Rouen knives (not cheverellus)
    ("1545", "outward", "32"): ("bell metal", "bell mettell"),                 # Bell mettell (not bell)
    ("1558", "outward", "6"): ("bell metal", "bell mettell"),
    ("1558", "inward", "326"): ("carpobalsamum", "cappe balsanum"),            # Cappe balsanum (not cap)
    ("1558", "inward", "368"): ("iron dowbles", "doble yron plates dobles"),   # Doble yron plates vocat' dobles (not iron)
    ("1558", "inward", "578"): ("hoop_2", "hopes"),                            # Hopes for barrelles (not barrel)
    ("1558", "inward", "905"): ("rapier", "rapers"),                           # Rapers ... with velvett sheathes (not velvet)
    ("1558", "inward", "906"): ("rapier", "rapers"),
    ("1558", "inward", "936"): ("hide", "hydes"),                              # Salt hydes (not salt)
    ("1558", "inward", "1044"): ("sack cloth", "sackclothe"),                  # Sackclothe whyte of threde (not thread)
    ("1558", "inward", "1045"): ("sack cloth", "sackclothe"),                  # Sackclothe of sylke (not silk)
    ("1558", "inward", "866"): ("petticoat", "petycotes"),                     # Petycotes knytte of wolle or cotton (not cotton)
    ("1545", "inward", "118"): ("bear", "beres"),                              # Beres quycke: live bears (not beer)
    ("1558", "inward", "878"): ("quicksilver", "quycke sylver"),               # Quycke sylver (not silver)
    ("1558", "inward", "299"): None,                                           # Crippen partlettes of gold or sylver (not silver)
    ("1558", "inward", "324"): None,                                           # Curteyns capparis: caper bark, cortex capparis (not curtain)
    ("1558", "inward", "389"): None,                                           # Dagges with fyer lockes: dags, pistols (not lock)
    ("1558", "inward", "854"): None,                                           # Playne yrones for carpenters: plane irons (not playne)
    ("1558", "inward", "856"): None,                                           # Pulleys of yron (not iron)
    ("1558", "inward", "1110"): None,                                          # Touche boxes covered with velvet (not velvet)
    ("1558", "inward", "1111"): None,                                          # Touche boxes of yron or other mettall guylt (not iron)
    ("1558", "inward", "1112"): None,                                          # Touche boxes of lether (not leather)
    ("1558", "inward", "1120"): None,                                          # Terre Bithina: a medicinal earth (not tar)
    ("1558", "inward", "1123"): None,
}
# Away from the head, a spelling after one of these is not the goods (see link()).
NOT_THE_GOODS = {"of", "with", "wt", "for", "in"}
QUAL_LEDGER_FIELDS = ["slug", "glossary_key", "qualifier", "minted", "status", "replaced_by"]


def norm(s: str) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c)).lower()
    s = s.replace("þ", "th").replace("ð", "th").replace("ſ", "s").replace("æ", "ae")
    s = re.sub(r"[’'`‘ʼ]", "", s)
    s = re.sub(r"[^a-z0-9]+", " ", s)
    return re.sub(r"\s+", " ", s).strip()


def load_tsv(p: Path) -> list[dict]:
    if not p.exists():
        return []
    with p.open(encoding="utf-8", newline="") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def form_index(entries: dict) -> dict[str, set]:
    """normalised spelling -> glossary keys that carry it (keys themselves count as spellings)."""
    idx = collections.defaultdict(set)
    for key, e in entries.items():
        for t in [re.sub(r"_\d+$", "", key)] + [f.get("t") for f in e.get("f", [])]:
            n = norm(t or "")
            if n and len(n) >= 3:
                idx[n].add(key)
    return idx


def link(text: str, idx: dict, max_len: int) -> tuple[str | None, str, str, str]:
    """(glossary key, matched spelling, qualifier, how). The books name the goods FIRST
    ("Canvas called Normandy..."), so, in order: the longest unique spelling at the start;
    then the longest unique phrase (2+ words) anywhere; then a single unique word anywhere
    that is not an ordinary word (COMMON). A spelling shared by several concepts is ambiguous
    and never used. Anywhere-matches linked the wrong word when tried first: "Buckroms in
    paperes, every paper" -> ivory (a spelling of which is "every"), "Corke made in
    barrelles" -> barrel. And away from the head, a spelling straight after "of", "with",
    "for" or "in" names the material, the purpose or the container, not the goods ("Saddels of
    stele" -> steel, "Hornes for lantorns" -> lantern, "Cannes of wode" -> woad): it is never
    linked (3 Oct 2026: 25 of the 28 such links were wrong). After "or" it is an alternative name
    for the goods ("Axes or hatchettes") and still links."""
    toks = norm(text).split()

    def hit(i, n):
        keys = idx.get(" ".join(toks[i:i + n]))
        return next(iter(keys)) if keys and len(keys) == 1 else None

    def result(i, n, how):
        spelling = toks[i:i + n]
        rest = [t for t in toks[:i] + toks[i + n:]
                if t not in FILLER and not t.isdigit() and t not in spelling]
        return hit(i, n), " ".join(spelling), " ".join(rest), how

    for n in range(min(max_len, len(toks)), 0, -1):          # 1. at the head
        if hit(0, n):
            return result(0, n, "head")
    skipped = []                                             # material, purpose, container

    def goods(i, n):
        if hit(i, n) and toks[i - 1] in NOT_THE_GOODS:
            skipped.append(" ".join(toks[i - 1:i + n]))
            return False
        return bool(hit(i, n))

    for n in range(min(max_len, len(toks)), 1, -1):          # 2. a phrase anywhere
        for i in range(1, len(toks) - n + 1):
            if goods(i, n):
                return result(i, n, "phrase")
    for i in range(1, len(toks)):                            # 3. a word anywhere
        if toks[i] not in COMMON and len(toks[i]) >= 4 and goods(i, 1):
            return result(i, 1, "word")
    if skipped:
        return None, "", "", "only a material, purpose or container: " + ", ".join(dict.fromkeys(skipped))
    amb = [t for t in toks if len(idx.get(t, ())) > 1]
    return None, "", "", ("ambiguous: " + ", ".join(amb)) if amb else "no glossary spelling"


def qualifier_store(lca: Path) -> tuple[dict, dict]:
    """LCA's qualifier list (docs/data/qualifiers.json): (normalised spelling -> canonical key,
    for a spelling listed under exactly one canonical; the canonicals)."""
    q = json.loads((lca / "docs/data/qualifiers.json").read_text(encoding="utf-8"))["canonicals"]
    form2c = collections.defaultdict(set)
    for k, v in q.items():
        for f in [k, v.get("label", ""), *v.get("forms", [])]:
            n = norm(f)
            if n:
                form2c[n].add(k)
    return {f: next(iter(c)) for f, c in form2c.items() if len(c) == 1}, q


def unit_words(site: Path) -> set[str]:
    """Every spelling of every unit: a leftover word that names a unit is the measure or the
    package ("the bale", "in barrelles"), not a qualifier."""
    out = set()
    for p in site.glob("unit/**/ontology.json"):
        d = json.loads(p.read_text(encoding="utf-8"))
        for t in [n.get("content", "") for n in d.get("identified_by", [])] + list(d.get("historicalTerm") or []):
            out.update(norm(str(t)).split())
    return out


def words(text: str, toks: list[str]) -> list[str]:
    """The words of `text` as written, one per token of norm(text); the tokens themselves
    where the two cannot be aligned."""
    out = []
    for w in re.findall(r"[^\W_]+", re.sub(r"[’'`‘ʼ]", "", text or "")):
        n = norm(w).split()
        out += [w] if len(n) == 1 else n
    return out if len(out) == len(toks) else toks


def qualifier_node(key: str, c: dict) -> dict:
    node = {"type": "Type", "_label": c.get("label") or key}
    aat = c.get("aat") or {}
    if aat.get("specific"):
        node["equivalent"] = [{"id": f"aat:{aat['specific']}", "type": "Type",
                               "_label": aat.get("label") or str(aat["specific"])}]
    geo = c.get("geo") or {}
    m = re.fullmatch(r"(?:wd:)?(Q[1-9]\d*)", str(geo.get("id", "")))
    if m and geo.get("dataset", "wikidata") == "wikidata":     # CC0 places only, as the exporter
        node["originPlace"] = [{"id": "wd:" + m.group(1), "type": "Place",
                                "_label": geo.get("label") or m.group(1)}]
    return node


def rate_qualifiers(text: str, spelling: str, form2c: dict, canon: dict, units: set) -> list[dict]:
    """The qualifiers in a rate's commodity text: the words left over once the commodity's
    spelling, the joining words (FILLER), numbers and unit words are set aside. The longest run
    of words that is a spelling in LCA's qualifier list becomes that qualifier (modern name);
    the words no spelling covers are kept together, as the book writes them."""
    toks = norm(text).split()
    orig = words(text, toks)
    sp = spelling.split()
    start = next((i for i in range(len(toks) - len(sp) + 1) if sp and toks[i:i + len(sp)] == sp), None)
    head = set(range(start, start + len(sp))) if start is not None else set()
    left = [i for i, t in enumerate(toks)
            if i not in head and t not in FILLER and not t.isdigit() and len(t) > 1
            and t not in sp and t not in units]
    keep, used, found = set(left), set(), []
    for i in left:
        if i in used:
            continue
        for n in range(len(toks) - i, 0, -1):
            span = range(i, i + n)
            if i + n - 1 not in keep or any(j in head or j in used or (j not in keep and toks[j] not in FILLER)
                                                 for j in span):
                continue
            k = form2c.get(" ".join(toks[i:i + n]))
            if k:
                found.append((i, ("c", k)))
                used.update(span)
                break
    rest = [i for i in left if i not in used]
    run = []
    for i in rest + [None]:
        if run and (i is None or any(j in head or j in used or (j not in keep and toks[j] not in FILLER)
                                     for j in range(run[-1] + 1, i))):
            found.append((run[0], ("w", " ".join(orig[run[0]:run[-1] + 1]))))
            run = []
        if i is not None:
            run.append(i)
    out, seen = [], set()
    for _i, (kind, v) in sorted(found):
        if (kind, v) in seen:
            continue
        seen.add((kind, v))
        out.append(qualifier_node(v, canon[v]) if kind == "c"
                   else {"type": "Type", "_label": v, "classified_as": [ATTESTED]})
    return out


def next_year(book: str) -> str:
    i = BOOKS.index(book)
    return BOOKS[i + 1] if i + 1 < len(BOOKS) else book


def _num(v):
    """The per-quantity as a number (the parser gives "100"); 1 when the rate is per one."""
    if v in (None, ""):
        return 1
    f = float(v)
    return int(f) if f.is_integer() else f


def rate_node(rec_uri: str, r: dict, unit_ref: dict, quals: list | None = None) -> dict:
    lsd = (r.get("rate_raw") or "").strip()
    node = {
        "id": f"{rec_uri}#rate-{r['book']}-{r['direction']}-{r['source_line']}",
        "type": "Rate",
        "_label": f"{r['book']}{' ' + r['direction'] if r['direction'] != 'none' else ''}: "
                  f"{r['commodity_raw']} {lsd}",
        "amount": {"type": "MonetaryAmount", "currency": STERLING,
                   "valueInPence": str(r["pence"]), "lsd": lsd.strip("[]")},
        "perQuantity": {"type": "Dimension", "value": _num(r.get("unit_quantity")), "unit": unit_ref},
        "validFrom": r["book"],
        "validThrough": next_year(r["book"]),
        "sourceText": (f"Book of Rates {r['book']}"
                       + (f", {r['direction']}" if r["direction"] != "none" else "")
                       + f", line {r['source_line']} (transcribed by Stuart Jenks): "
                       + f"'{r['commodity_raw']}' {r['rate_raw']}"
                       + (" [the rate is an editorial supply]" if r.get("editorial") else "")),
    }
    if quals:
        node["qualifier"] = quals
    return node


def run(lca: Path = LCA, today: str | None = None) -> dict:
    today = today or dt.date.today().isoformat()
    site = BUILD / "site"
    g = json.loads((lca / "docs/data/glossary_data.json").read_text(encoding="utf-8"))
    entries = g["entries"]
    idx = form_index(entries)
    max_len = max(len(k.split()) for k in idx)
    com = {r["glossary_key"]: r["slug"] for r in load_tsv(BUILD / "ledger/commodities.tsv")
           if r["status"] == "active"}
    units = {r["key"]: r["slug"] for r in load_tsv(BUILD / "ledger/units.tsv") if r["status"] == "active"}
    join = {r["rates_unit"]: r["key"] for r in load_tsv(BUILD / "units/rates_join.tsv")}
    qpath = BUILD / "ledger/qualified.tsv"
    qledger = load_tsv(qpath)

    rows = [json.loads(l) for l in (BUILD / "rates/rates.jsonl").open(encoding="utf-8")]
    form2c, canon = qualifier_store(lca)
    uwords = unit_words(site)
    rep = collections.Counter()
    unlinked = collections.defaultdict(list)
    by_record = collections.defaultdict(list)          # slug -> rate nodes
    as_written = collections.Counter()                 # qualifier words LCA's list does not name
    sample = []
    used_overrides = set()
    for r in rows:
        if r["book"] not in LINKED_BOOKS:
            rep["1604 rows held for D6"] += 1
            continue
        rep["rows considered"] += 1
        if not r.get("pence"):
            unlinked["no price"].append(r); continue
        ukey = join.get(r.get("unit") or "")
        if not ukey or ukey not in units:
            unlinked["no unit"].append(r); continue
        text = r.get("commodity_text") or r.get("commodity_raw") or ""
        key, spelling, qual, why = link(text, idx, max_len)
        ov = (r["book"], r["direction"], str(r["source_line"]))
        if ov in LINK_OVERRIDES:
            used_overrides.add(ov)
            key, spelling = LINK_OVERRIDES[ov] or (None, "")
            why = "override"
            if not key:
                unlinked["no concept for these goods yet (read by hand)"].append(r); continue
        if not key:
            unlinked[why.split(":")[0]].append(r); continue
        rep[f"linked at the {why}"] += 1
        if key not in com:
            unlinked["concept has no HECTOR record"].append(r); continue
        unit_ref = {"id": f"{W3ID}unit/{units[ukey]}", "type": "MeasurementUnit",
                    "_label": re.sub(r"_\d+$", "", re.sub(r"^(bor|hector):", "", ukey))}
        # the parser cuts the measure off the entry, and a qualifier can sit inside it ("the C
        # elles browne"): the measure is read too, but only for qualifiers LCA's list names (it
        # is full of unit spellings no list has, "yarde", "dossyn"), never its measure senses
        # (MEASURE_SENSE), and not the count ("conteynynge five score")
        # another spelling of the goods themselves is not a qualifier ("Iron called Lukes yron")
        own = {t for t in norm(text).split() if key in idx.get(t, ())}
        quals = rate_qualifiers(text, spelling, form2c, canon, uwords | own)
        named = {q["_label"] for q in quals}
        for q in rate_qualifiers(r.get("unit_text") or "", "", form2c, canon, uwords | MEASURE_SENSE):
            if not q.get("classified_as") and q["_label"] not in named:   # named ones only
                quals.append(q)
                named.add(q["_label"])
        for q in quals:
            if q.get("classified_as"):
                as_written[q["_label"].lower()] += 1
                rep["qualifiers as written"] += 1
            else:
                rep["qualifiers named from LCA's list"] += 1
        rep["rates with a qualifier" if quals else "rates without a qualifier"] += 1
        slug = com[key]
        by_record[slug].append(rate_node(f"{W3ID}commodity/{slug}", r, unit_ref, quals))
        if len(sample) < 400:
            sample.append((r["commodity_raw"], key, spelling, "; ".join(q["_label"] for q in quals), why))
    for why, rs in unlinked.items():
        rep[f"not linked: {why}"] += len(rs)
    stale = set(LINK_OVERRIDES) - used_overrides
    if stale:   # a row moved or the books were re-parsed: the override no longer says anything
        raise SystemExit(f"LINK_OVERRIDES matched no rate row: {sorted(stale)}")
    rep["links overridden by hand"] = len(used_overrides)

    # The qualified records decision 2 minted (29 Sep), deprecated 3 Oct: each URI keeps
    # resolving, to a record replaced by its base commodity, which now carries its rates.
    for row in qledger:
        base = com.get(row["glossary_key"])
        base_label = re.sub(r"_\d+$", "", row["glossary_key"])
        if row["status"] == "active":
            row["status"], row["replaced_by"] = "deprecated", base or ""
        doc = {"@context": CONTEXT, "id": f"{W3ID}commodity/{row['slug']}", "type": "Type",
               "_label": f"{base_label} (withdrawn record)",
               "deprecated": True, "modified": "2026-10-03",
               "referred_to_by": [{"type": "LinguisticObject", "classified_as": [AAT_BRIEF],
                                   "content": "Withdrawn 3 Oct 2026. This record stood for the commodity as one "
                                              "Book of Rates entry qualifies it; the rates are now on the commodity "
                                              "itself, each naming its qualifier."}]}
        if row.get("replaced_by"):
            doc["isReplacedBy"] = {"id": f"{W3ID}commodity/{row['replaced_by']}", "type": "Type"}
        p = site / "commodity" / row["slug"] / "ontology.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rep["withdrawn qualified records"] = len(qledger)

    # rates onto the records
    for slug, rates in by_record.items():
        p = site / "commodity" / slug / "ontology.json"
        doc = json.loads(p.read_text(encoding="utf-8"))
        doc["taxation"] = sorted(rates, key=lambda x: x["id"])
        p.write_text(json.dumps(doc, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    rep["records with rates"] = len(by_record)

    qpath.parent.mkdir(parents=True, exist_ok=True)
    with qpath.open("w", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, QUAL_LEDGER_FIELDS, delimiter="\t", lineterminator="\n")
        w.writeheader()
        for r in sorted(qledger, key=lambda r: r["slug"]):
            w.writerow({k: r.get(k, "") for k in QUAL_LEDGER_FIELDS})

    out = BUILD / "rates/link-report.md"
    lines = ["# Books of Rates: linking report", "", f"Built {today} by tools/rates/link_rates.py.", ""]
    lines += [f"- {k}: {v:,}" for k, v in sorted(rep.items())]
    for why, rs in sorted(unlinked.items()):
        lines += ["", f"## Not linked: {why} ({len(rs)})", ""]
        lines += [f"- {r['book']} l.{r['source_line']}: {r['commodity_raw']}" for r in rs[:60]]
    lines += ["", f"## Qualifiers kept as written: not a spelling in LCA's qualifier list ({len(as_written)})", "",
              "Candidates for that list (docs/data/qualifiers.json); with a spelling there, a rate names the "
              "qualifier in its modern form.", ""]
    lines += [f"- {w} ({n})" for w, n in as_written.most_common()]
    lines += ["", "## Sample of links (commodity as written -> concept, spelling, qualifier)", ""]
    lines += [f"- {a} -> **{k}** via '{s}' ({h})" + (f", qualifier '{q}'" if q else "") for a, k, s, q, h in sample[:160]]
    out.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return dict(rep)


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--lca", type=Path, default=LCA)
    a = ap.parse_args(argv)
    print(json.dumps(run(a.lca), indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
