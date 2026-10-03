"""tools/rates/link_rates.py: how a Book of Rates entry is linked to a glossary concept and
its qualifiers (PLAN.md tasks 14 and 17; qualifiers on the rate, 3 Oct 2026). An invented glossary; nothing Jenks-derived."""
import json

from tools.rates import link_rates as L

ENTRIES = {
    "ivory": {"f": [{"t": "ivory"}, {"t": "every"}]},     # a real glossary spelling of ivory
    "buckram": {"f": [{"t": "buckroms"}, {"t": "buckram"}]},
    "canvas": {"f": [{"t": "canvas"}]},
    "cork": {"f": [{"t": "corke"}]},
    "barrel": {"f": [{"t": "barrelles"}]},
    "pan": {"f": [{"t": "pans"}]},
    "pan_2": {"f": [{"t": "pans"}]},                       # one spelling, two concepts
    "wax": {"f": [{"t": "wax"}]},
    "lantern": {"f": [{"t": "lantorns"}]},
    "hatchet": {"f": [{"t": "hatchettes"}]},
}


def linked(text):
    idx = L.form_index(ENTRIES)
    return L.link(text, idx, max(len(k.split()) for k in idx))


def test_the_goods_at_the_head_win_over_a_word_later_on():
    # anywhere-first linked this to ivory, through "every"
    key, spelling, qual, how = linked("Buckroms in paperes, every paper 1 with another")
    assert (key, how) == ("buckram", "head")
    key, *_ = linked("Corke made in barrelles the laste")
    assert key == "cork"                                   # not the barrel it came in


def test_a_material_or_purpose_away_from_the_head_is_not_the_goods():
    # "Hornes for lantorns": the horns are the goods; lanterns are what they are for
    key, _s, _q, how = linked("Hornes for lantorns the 1000")
    assert key is None and how.startswith("only a material, purpose or container")
    assert linked("Axes or hatchettes the dossen")[0] == "hatchet"     # CONTROL: "or" names the goods
    assert linked("Lantorns of horne")[0] == "lantern"                 # CONTROL: at the head it links


def test_an_ambiguous_spelling_is_never_used():
    key, _s, _q, how = linked("Droppyn pans of yerne")
    assert key is None and how.startswith("ambiguous")


def test_an_ordinary_word_does_not_link_on_its_own():
    idx = L.form_index({"ivory": {"f": [{"t": "every"}]}})
    assert L.link("Thynges every one", idx, 1)[0] is None


def test_the_qualifier_loses_formula_words_and_the_head_again():
    # commodity_text as the parser gives it: the measure ("the bale") is already split off
    key, spelling, qual, _ = linked("Canvas called Vytory canvas that ys to saye")
    assert (key, qual) == ("canvas", "vytory")


QUALS = {"canonicals": {
    "white": {"label": "white", "forms": ["whit", "whyte", "wyte"], "aat": {"specific": "300129784", "label": "white (color)"}},
    "normandy": {"label": "Normandy", "forms": ["normandy"], "geo": {"id": "Q15878", "dataset": "wikidata", "label": "Normandy"}},
    "overseas": {"label": "overseas", "forms": ["ultra mare", "beyownd the se"]},
    "rede": {"label": "red", "forms": ["rede"]},
    "rede_2": {"label": "reed", "forms": ["rede"]},          # one spelling, two qualifiers
}}


def quals(tmp_path, text, spelling, units=()):
    (tmp_path / "docs/data").mkdir(parents=True, exist_ok=True)
    (tmp_path / "docs/data/qualifiers.json").write_text(json.dumps(QUALS), encoding="utf-8")
    form2c, canon = L.qualifier_store(tmp_path)
    return L.rate_qualifiers(text, spelling, form2c, canon, set(units))


def test_a_qualifier_in_lcas_list_is_named_in_its_modern_form(tmp_path):
    q = quals(tmp_path, "Canvas called Normandy whyte", "canvas")
    assert [x["_label"] for x in q] == ["Normandy", "white"]
    assert q[0]["originPlace"][0]["id"] == "wd:Q15878"
    assert q[1]["equivalent"][0]["id"] == "aat:300129784"
    assert not any(x.get("classified_as") for x in q)


def test_a_phrase_with_joining_words_is_one_qualifier(tmp_path):
    q = quals(tmp_path, "Saffron of beyownd the se þe lb", "saffron", units=["lb"])
    assert [x["_label"] for x in q] == ["overseas"]


def test_words_not_in_the_list_are_kept_as_the_book_writes_them(tmp_path):
    # never a spelling fold ("beiound se"): the words, case and all, marked as attested
    q = quals(tmp_path, "Saffron of Beyonde the See", "saffron")
    assert [x["_label"] for x in q] == ["Beyonde the See"]
    assert q[0]["classified_as"][0]["id"] == "hector:AttestedVariant"


def test_unit_words_numbers_and_the_head_are_not_qualifiers(tmp_path):
    q = quals(tmp_path, "Canvas whyte the bale conteyning 100 elles canvas", "canvas", units=["bale", "elles"])
    assert [x["_label"] for x in q] == ["white"]


def test_the_measure_is_read_only_for_named_qualifiers_and_not_its_measure_senses(tmp_path, monkeypatch):
    (tmp_path / "docs/data").mkdir(parents=True)
    (tmp_path / "docs/data/qualifiers.json").write_text(json.dumps(QUALS), encoding="utf-8")
    form2c, canon = L.qualifier_store(tmp_path)
    u = {"elles"}
    measure = lambda t: [q["_label"] for q in L.rate_qualifiers(t, "", form2c, canon, u | L.MEASURE_SENSE)
                         if not q.get("classified_as")]
    assert measure("C elles whyte") == ["white"]                # 1558 l.177: a colour in the measure
    assert measure("the C wyte") == []                          # a hundredweight, not white
    assert [q["_label"] for q in L.rate_qualifiers("the C wyte", "", form2c, canon, u)] == ["white"]   # CONTROL


def test_an_ambiguous_qualifier_spelling_is_kept_as_written(tmp_path):
    q = quals(tmp_path, "Wax rede", "wax")
    assert [x["_label"] for x in q] == ["rede"] and q[0]["classified_as"]
    assert [x["_label"] for x in quals(tmp_path, "Wax whyte", "wax")] == ["white"]   # CONTROL


def test_the_quantity_is_a_number():
    assert L._num("100") == 100 and L._num("2.5") == 2.5 and L._num(None) == 1
