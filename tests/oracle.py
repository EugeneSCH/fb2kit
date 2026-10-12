"""Oracle: independent extraction from raw XML (lxml, no model) compared with the fb2kit model."""

from __future__ import annotations

import re
from collections import Counter
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from lxml import etree

import fb2kit
from fb2kit.export import _raw_text, iter_blocks
from fb2kit.model import (
    Cell,
    Link,
    Paragraph,
    Raw,
    Style,
    Subtitle,
    Table,
    Text,
    TextAuthor,
    Verse,
    iter_nodes,
)
from fb2kit.report import Mode
from fb2kit.source import decode_source, open_container

_WS = re.compile(r"\s+")
BLOCKS = ("p", "v", "subtitle", "text-author", "td", "th")
_TEXT_HOLDERS = frozenset(BLOCKS)
_TEXT_NODES = (Paragraph, Verse, Subtitle, TextAuthor, Cell)
_CONTAINERS = frozenset(
    {"section", "title", "epigraph", "annotation", "poem", "stanza", "cite", "table", "tr"}
)
COUNTED = ("section", "p", "poem", "stanza", "v", "table", "image", "epigraph")
_BARE_AMP = re.compile(r"&(?!(?:amp|lt|gt|quot|apos|#\d+|#x[0-9a-fA-F]+);)")
_BAD_CHARS = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f]")
_HREF = "{http://www.w3.org/1999/xlink}href"


def norm(s: str | None) -> str:
    return _WS.sub(" ", s or "").strip()


def _name(el: Any) -> str:
    return str(el.tag).rpartition("}")[2] if isinstance(el.tag, str) else ""


def _oracle_root(path: Path) -> Any:
    raw = open_container(path).raw
    text = decode_source(raw, mode=Mode.TOLERANT).text
    text = _BAD_CHARS.sub(
        "", _BARE_AMP.sub("&amp;", text)
    )  # own minimal repair, lxml would drop "&"
    parser = etree.XMLParser(recover=True, resolve_entities=False, huge_tree=True, encoding="utf-8")
    return etree.fromstring(text.encode("utf-8"), parser)


_STRAY_HOLDERS = frozenset({"body", "section", "title", "epigraph", "annotation", "cite"})
_SEPARATED = _CONTAINERS | _TEXT_HOLDERS | {"empty-line"}


def _sep_text(e: Any) -> str:
    """itertext with a space around block elements, as the export separates them."""
    parts: list[str] = [e.text or ""]
    for c in e:
        if isinstance(c.tag, str):
            sep = " " if _name(c) in _SEPARATED else ""
            parts += [sep, _sep_text(c), sep]
        parts.append(c.tail or "")
    return "".join(parts)


def _walk(root: Any) -> list[Any]:
    return [e for e in root.iter() if isinstance(e.tag, str)]


def _bodies(root: Any) -> list[Any]:
    return [c for c in root if isinstance(c.tag, str) and _name(c) == "body"]


def _model_inline_text(children: tuple[Any, ...]) -> str:
    out: list[str] = []
    for c in children:
        if isinstance(c, Text):
            out.append(c.value)
        elif isinstance(c, Style | Link):
            out.append(_model_inline_text(c.children))
        elif isinstance(c, Raw):
            out.append(_raw_text(c))
    return "".join(out)


def _opt(s: str | None) -> str | None:
    return norm(s) or None


def _int(s: str | None) -> int | None:
    try:
        return int(norm(s))
    except ValueError:
        return None


def _oracle_meta(root: Any) -> dict[str, Any]:
    ti = next(
        (e for d in root if _name(d) == "description" for e in d if _name(e) == "title-info"), None
    )
    if ti is None:
        return {}

    def kids(name: str) -> list[Any]:
        return [e for e in ti if _name(e) == name]

    def person(a: Any) -> tuple[str | None, ...]:
        f = {_name(x): norm("".join(x.itertext())) or None for x in a}
        return (f.get("first-name"), f.get("middle-name"), f.get("last-name"), f.get("nickname"))

    first = lambda name: next(iter(kids(name)), None)  # noqa: E731
    title, lang = first("book-title"), first("lang")
    return {
        "book-title": _opt("".join(title.itertext())) if title is not None else None,
        "lang": _opt("".join(lang.itertext())) if lang is not None else None,
        "genre": [norm("".join(g.itertext())) for g in kids("genre")],
        "authors": [person(a) for a in kids("author")],
        "sequences": [(_opt(s.get("name")), _int(s.get("number"))) for s in kids("sequence")],
    }


def _model_meta(book: fb2kit.FictionBook) -> dict[str, Any]:
    ti = book.description.title_info
    return {
        "book-title": _opt(ti.title),
        "lang": _opt(ti.lang),
        "genre": [norm(g) for g in ti.genres],
        "authors": [
            (_opt(a.first_name), _opt(a.middle_name), _opt(a.last_name), _opt(a.nickname))
            for a in ti.authors
        ],
        "sequences": [(_opt(s.name), s.number) for s in ti.sequences],
    }


def _compare(a: list[str], b: list[str]) -> tuple[float, list[dict[str, str]]]:
    """Ratio and first differences; equal head and tail are trimmed so the matcher stays cheap."""
    if a == b:
        return 1.0, []
    head = 0
    while head < min(len(a), len(b)) and a[head] == b[head]:
        head += 1
    tail = 0
    while tail < min(len(a), len(b)) - head and a[-1 - tail] == b[-1 - tail]:
        tail += 1
    ma, mb = a[head : len(a) - tail], b[head : len(b) - tail]
    sm = SequenceMatcher(None, ma, mb, autojunk=False)
    matched = head + tail + sum(m.size for m in sm.get_matching_blocks())
    ratio = 2.0 * matched / (len(a) + len(b)) if a or b else 1.0
    diffs = [
        {
            "op": op,
            "xml": " | ".join(ma[i1:i2][:2])[:160],
            "model": " | ".join(mb[j1:j2][:2])[:160],
        }
        for op, i1, i2, j1, j2 in sm.get_opcodes()
        if op != "equal"
    ][:5]
    return ratio, diffs


def _in_place(name: str, parent: str) -> bool:
    """A container is structural only under its grammatical parent; elsewhere the model keeps Raw."""
    if name == "section":
        return parent in ("body", "section")
    return name != "tr" or parent == "table"


def _xml_structure(bodies: list[Any]) -> tuple[list[str], Counter[str]]:
    """Walk like the model: holders are one text entry, an unexpected element is one Raw entry.

    A block inside a holder (p in p, p in td) is flattened; an element outside the FB2 grammar
    (emphasis wrapping p in epigraph, section in epigraph) stays Raw and is not descended into.
    """
    texts: list[str] = []
    counts: Counter[str] = Counter()

    def loose(text: str | None, holder: str) -> None:
        if holder in _STRAY_HOLDERS and norm(text):  # the model keeps it as a paragraph
            texts.append(norm(text))
            counts["p"] += 1

    def visit(e: Any, parent: str) -> None:
        n = _name(e)
        stray = (parent == "title" and n not in ("p", "subtitle", "empty-line")) or (
            parent == "tr" and n not in ("td", "th", "empty-line")
        )  # the model keeps these as Raw / a one-element Cell
        if stray:
            texts.append(norm(_sep_text(e)))
            counts["image"] += n == "image" and parent == "tr"
        elif n in _TEXT_HOLDERS:
            texts.append(norm(_sep_text(e)))
            counts["p" if parent == "title" and n == "subtitle" else n] += 1
            counts["image"] += sum(_name(x) == "image" for x in e.iter())
        elif n == "empty-line":
            return
        elif n == "image":
            counts[n] += 1
        elif n in _CONTAINERS and _in_place(n, parent):
            counts[n] += 1
            loose(e.text, n)
            for c in e:
                if isinstance(c.tag, str):
                    visit(c, n)
                loose(c.tail, n)
        else:
            texts.append(norm(_sep_text(e)))

    for b in bodies:
        loose(b.text, "body")
        for c in b:
            if isinstance(c.tag, str):
                visit(c, "body")
            loose(c.tail, "body")
    return texts, counts


def _squash(s: str) -> str:
    return _WS.sub("", s)


def _table_separators(body: Any) -> int:
    """Cell separators the export adds: non-empty cells minus one, per table row."""
    return sum(
        max(sum(bool(norm(_model_inline_text(c.children))) for c in r.cells) - 1, 0)
        for t in iter_nodes(body)
        if isinstance(t, Table)
        for r in t.rows
    )


def rough_check(bodies: list[Any], book: fb2kit.FictionBook) -> dict[str, Any]:
    """Coarse text check per body: all raw-XML characters vs all exported block characters.

    Whitespace is ignored. ``|`` (the table cell separator) is dropped from both sides; ``pipes``
    is the surplus of real ``|`` in the export over the source after subtracting the separators.
    Missing/extra are character counts (multiset), ``order`` tells whether the sequences are equal.
    """
    by_body: dict[int, list[str]] = {}
    for b in iter_blocks(book):
        by_body.setdefault(b.body_idx, []).append(b.text)
    missing: Counter[str] = Counter()
    extra: Counter[str] = Counter()
    order = True
    first = ""
    seps = pipes = 0
    for i, body in enumerate(bodies):
        raw_xml = _squash("".join(body.itertext(tag=etree.Element)))
        raw_model = _squash("".join(by_body.get(i, [])))
        if i < len(book.bodies):
            seps += _table_separators(book.bodies[i])
        pipes += raw_model.count("|") - raw_xml.count("|")
        xml, model = raw_xml.replace("|", ""), raw_model.replace("|", "")
        cx, cm = Counter(xml), Counter(model)
        missing.update(cx - cm)
        extra.update(cm - cx)
        if xml != model and order:
            order = False
            k = next(
                (j for j, (p, q) in enumerate(zip(xml, model, strict=False)) if p != q),
                min(len(xml), len(model)),
            )
            first = f"body {i} at {k}: xml {xml[max(k - 20, 0) : k + 30]!r} | model {model[max(k - 20, 0) : k + 30]!r}"
    return {
        "missing": sum(missing.values()),
        "extra": sum(extra.values()),
        "order": order,
        "pipes": pipes - seps,
        "missing_chars": dict(missing.most_common(8)),
        "extra_chars": dict(extra.most_common(8)),
        "first_diff": first,
    }


def chunk_coverage(xml_text: list[str], book: fb2kit.FictionBook) -> dict[str, Any]:
    """Share of oracle block characters found, in order, in the joined chunk texts."""
    blob = " ".join(norm(c.text) for c in iter_blocks(book))
    pos = covered = total = 0
    missing: list[str] = []
    for t in xml_text:
        total += len(t)
        i = blob.find(t, pos)
        if i < 0:
            missing.append(t[:160])
            continue
        covered += len(t)
        pos = i + len(t)
    return {
        "share": covered / total if total else 1.0,
        "missing": missing[:5],
        "n_missing": len(missing),
    }


def check_book(path: Path) -> dict[str, Any]:
    """Compare one book with its raw XML; never judges, only measures."""
    root = _oracle_root(path)
    book = fb2kit.parse(path, mode=Mode.TOLERANT)
    bodies = _bodies(root)
    xml_text, xml_counts = _xml_structure(bodies)
    xml_ids = {e.get("id") for e in _walk(root) if e.get("id")}

    nodes = list(iter_nodes(book.bodies))
    inline_raw = {
        id(r)
        for n in nodes
        if isinstance(n, _TEXT_NODES)
        for r in iter_nodes(n.children)
        if isinstance(r, Raw)
    }
    model_text = [
        norm(_raw_text(n)) if isinstance(n, Raw) else norm(_model_inline_text(n.children))
        for n in nodes
        if isinstance(n, _TEXT_NODES) or (isinstance(n, Raw) and id(n) not in inline_raw)
    ]
    ratio, diffs = _compare(xml_text, model_text)

    model_counts: Counter[str] = Counter(
        dict.fromkeys(COUNTED, 0)
    )  # model class name -> xml tag name
    tag = {
        "Section": "section", "Paragraph": "p", "Poem": "poem", "Stanza": "stanza",
        "Verse": "v", "Table": "table", "Image": "image", "Epigraph": "epigraph",
    }  # fmt: skip
    for n in nodes:
        if type(n).__name__ in tag:
            model_counts[tag[type(n).__name__]] += 1
    counts = {k: [xml_counts[k], model_counts[k]] for k in COUNTED}

    xm, mm = _oracle_meta(root), _model_meta(book)
    meta = {k: [xm.get(k), mm[k]] for k in mm if xm.get(k) != mm[k]}

    hrefs = [
        e.get(_HREF, e.get("href", ""))
        for e in (x for b in bodies for x in _walk(b))
        if _name(e) == "a"
    ]
    targets = [h[1:] for h in hrefs if h.startswith("#")]
    missing = [t for t in targets if t not in book.index]
    links = {
        "total": len(targets),
        "missing_in_model": [t for t in missing if t in xml_ids][:5],
        "n_missing_in_model": sum(t in xml_ids for t in missing),
        "n_broken_in_source": sum(t not in xml_ids for t in missing),
    }

    body_chars = sum(len(norm("".join(b.itertext()))) for b in bodies)
    raws = [n for n in nodes if isinstance(n, Raw)]
    raw_chars = sum(len(norm("".join(r.element.itertext()))) for r in raws if r.element is not None)
    raw = {
        "share": raw_chars / body_chars if body_chars else 0.0,
        "tags": dict(Counter(r.tag for r in raws)),
    }
    return {
        "file": path.name,
        "n_blocks": [len(xml_text), len(model_text)],
        "ratio": ratio,
        "diffs": diffs,
        "counts": counts,
        "meta": meta,
        "links": links,
        "raw": raw,
        "chunks": chunk_coverage(xml_text, book),
        "rough": rough_check(bodies, book),
    }


def summarize(results: list[dict[str, Any]], errors: list[str]) -> dict[str, Any]:
    ratios = sorted(r["ratio"] for r in results)
    mismatch: Counter[str] = Counter()
    raw_tags: Counter[str] = Counter()
    for r in results:
        mismatch.update(k for k, (a, b) in r["counts"].items() if a != b)
        mismatch.update(f"meta:{k}" for k in r["meta"])
        if r["links"]["n_missing_in_model"]:
            mismatch["links"] += 1
        raw_tags.update(r["raw"]["tags"])
    cov = sorted(
        (r for r in results if r["chunks"]["share"] < 1), key=lambda r: r["chunks"]["share"]
    )
    worst = sorted((r for r in results if r["ratio"] < 1), key=lambda r: r["ratio"])[:10]
    rough = [
        r for r in results if r["rough"]["missing"] or r["rough"]["extra"] or r["rough"]["pipes"]
    ]
    return {
        "books": len(results),
        "rough_missing": sum(r["rough"]["missing"] for r in results),
        "rough_extra": sum(r["rough"]["extra"] for r in results),
        "rough_pipes": sum(abs(r["rough"]["pipes"]) for r in results),
        "rough_order_broken": sum(not r["rough"]["order"] for r in results),
        "rough_bad_books": [{"file": r["file"], **r["rough"]} for r in rough[:10]],
        "rough_order_samples": [
            {"file": r["file"], "diff": r["rough"]["first_diff"]}
            for r in results
            if not r["rough"]["order"]
        ][:10],
        "errors": errors,
        "text_equal": sum(r["ratio"] == 1.0 for r in results),
        "ratio_median": ratios[len(ratios) // 2] if ratios else None,
        "ratio_min": ratios[0] if ratios else None,
        "mismatch_books_by_type": dict(mismatch),
        "mismatch_sums": {
            k: sum(abs(r["counts"][k][0] - r["counts"][k][1]) for r in results) for k in COUNTED
        },
        "raw_tags": dict(raw_tags.most_common()),
        "raw_share_mean": sum(r["raw"]["share"] for r in results) / len(results) if results else 0,
        "chunks_full": sum(r["chunks"]["share"] == 1.0 for r in results),
        "chunks_share_min": min((r["chunks"]["share"] for r in results), default=None),
        "chunks_worst": [{"file": r["file"], **r["chunks"]} for r in cov[:10]],
        "worst": [{"file": r["file"], "ratio": r["ratio"], "diffs": r["diffs"][:2]} for r in worst],
    }
