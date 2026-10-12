from collections import Counter

import pytest
from conftest import corpus_files

import fb2kit
from fb2kit.report import Mode

pytestmark = [
    pytest.mark.corpus,
    pytest.mark.skipif(not corpus_files(), reason="FB2KIT_CORPUS is not set: no corpus attached"),
]


def test_corpus_parses_or_is_not_fb2() -> None:
    outcome: Counter[str] = Counter()
    encodings: Counter[str] = Counter()
    strict_errors: Counter[str] = Counter()
    failures: list[str] = []
    for path in corpus_files():
        try:
            book = fb2kit.parse(path, mode=Mode.TOLERANT)
        except fb2kit.Fb2SourceError:
            outcome["bad source"] += 1  # broken or non-FB2 input is an acceptable outcome
            continue
        except Exception as exc:  # any other exception in tolerant mode is a failure
            outcome["error"] += 1
            failures.append(f"{path.name}: {type(exc).__name__}: {exc}")
            continue
        outcome["ok"] += 1
        encodings[book.report.source_encoding] += 1
        try:
            fb2kit.parse(path, mode=Mode.STRICT)
        except fb2kit.Fb2Error as exc:  # strict: summary only, not a failure
            strict_errors[type(exc).__name__] += 1
    print(f"\ntolerant: {dict(outcome)}")
    print(f"encodings: {encodings.most_common()}")
    print(f"strict Fb2Error by type: {strict_errors.most_common()}")
    assert not failures, "\n".join(failures[:20])
