import json
import os
import time
from pathlib import Path

import pytest
from conftest import case, corpus_files

pytest.importorskip("lxml")
from oracle import check_book, summarize

FIXTURES = sorted(Path(__file__).parent.joinpath("fixtures").glob("*.fb2"))
# these fail to parse by design (unsafe input) or are not valid XML for the oracle
_SKIP = {"entity-bomb.fb2", "xxe-doctype.fb2", "utf16-doctype.fb2", "regression-nul-in-prolog.fb2"}


@pytest.mark.parametrize("path", [p for p in FIXTURES if p.name not in _SKIP], ids=lambda p: p.name)
def test_oracle_on_fixtures(path: Path) -> None:
    r = check_book(path)
    assert r["ratio"] == 1.0, r["diffs"]
    assert all(a == b for a, b in r["counts"].values()), r["counts"]
    assert not r["meta"], r["meta"]
    assert r["links"]["n_missing_in_model"] == 0
    assert r["chunks"]["share"] == 1.0, r["chunks"]
    assert r["rough"]["missing"] == r["rough"]["extra"] == r["rough"]["pipes"] == 0, r["rough"]
    assert r["rough"]["order"], r["rough"]


@pytest.mark.corpus
@pytest.mark.skipif(not corpus_files(), reason="FB2KIT_CORPUS is not set: no corpus attached")
def test_oracle_on_corpus() -> None:
    import fb2kit

    results, errors = [], []
    for path in corpus_files():
        t0 = time.monotonic()
        try:
            results.append(check_book(path))
        except fb2kit.Fb2SourceError:
            continue
        except Exception as exc:
            errors.append(f"{path.name}: {type(exc).__name__}: {exc}")
        if time.monotonic() - t0 > 10:
            print(f"slow: {path.name} {time.monotonic() - t0:.0f}s")
    summary = summarize(results, errors)
    print("\n" + json.dumps(summary, ensure_ascii=False, indent=1))
    if out := os.environ.get("FB2KIT_ORACLE_OUT"):
        Path(out).write_text(
            json.dumps({"summary": summary, "books": results}, ensure_ascii=False), "utf-8"
        )
    assert not errors, "\n".join(errors[:20])


def test_oracle_explains_invalid_nesting(tmp_path: Path) -> None:
    ns = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0" xmlns:l="http://www.w3.org/1999/xlink"'
    body = (
        '<section><title><p>t</p><subtitle>s</subtitle><image l:href="#i"/></title>'
        "<epigraph><emphasis><p>a</p><p>b</p></emphasis><section><p>c</p></section></epigraph>"
        '<table><tr><td>x</td><image l:href="#i"/></tr></table><tr><td>y</td><td>z</td></tr></section>'
    )
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?><FictionBook {ns}><description><title-info>'
        "<genre>g</genre><author><first-name>a</first-name></author><book-title>t</book-title>"
        f"<lang>ru</lang></title-info></description><body>{body}</body>"
        '<binary id="i" content-type="image/png">AAAA</binary></FictionBook>'
    )
    path = tmp_path / "b.fb2"
    path.write_text(xml, "utf-8")
    r = check_book(path)
    assert r["ratio"] == 1.0, r["diffs"]
    assert all(a == b for a, b in r["counts"].values()), r["counts"]
    assert r["chunks"]["share"] == 1.0, r["chunks"]


def test_rough_check_sees_stray_text_duplicates_and_tails(tmp_path: Path) -> None:
    ns = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
    body = case("export", "stray_text_in_containers_is_kept")["body"] + (
        "<section><table><tr><td>a|b</td><td>c</td></tr></table></section>"
    )
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?><FictionBook {ns}><description><title-info>'
        "<genre>g</genre><author><first-name>a</first-name></author><book-title>t</book-title>"
        f"<lang>ru</lang></title-info></description><body>{body}</body></FictionBook>"
    )
    path = tmp_path / "b.fb2"
    path.write_text(xml, "utf-8")
    r = check_book(path)
    assert (r["rough"]["missing"], r["rough"]["extra"], r["rough"]["order"]) == (0, 0, True)


def test_rough_check_detects_loss_and_duplicates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    import oracle

    from fb2kit.export import TextBlock, iter_blocks

    ns = 'xmlns="http://www.gribuser.ru/xml/fictionbook/2.0"'
    xml = (
        f'<?xml version="1.0" encoding="utf-8"?><FictionBook {ns}><description><title-info>'
        "<genre>g</genre><author><first-name>a</first-name></author><book-title>t</book-title>"
        "<lang>ru</lang></title-info></description><body><section><p>abc</p><p>def</p></section></body>"
        "</FictionBook>"
    )
    path = tmp_path / "b.fb2"
    path.write_text(xml, "utf-8")

    def broken(book: object) -> list[TextBlock]:
        blocks = list(iter_blocks(book))  # type: ignore[arg-type]
        return [blocks[1], blocks[1], TextBlock("ab", "paragraph")]

    monkeypatch.setattr(oracle, "iter_blocks", broken)
    r = check_book(path)["rough"]
    assert r["order"] is False
    assert r["missing"] > 0 and r["extra"] > 0 and r["first_diff"]
