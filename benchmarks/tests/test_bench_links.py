"""Every relative link in the v1 documents resolves to a file and a heading
(P5.2, §4 item 9): benchmarks/check_links.py, on fixtures and on the repo."""

import check_links


def write(path, text):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_slugs_follow_github():
    assert (
        check_links.slug("## 12. Assumptions — needs review"[3:])
        == "12-assumptions--needs-review"
    )
    assert check_links.slug("Step 11 — Optional: TestPyPI, then PyPI") == (
        "step-11--optional-testpypi-then-pypi"
    )


def test_broken_files_and_headings_are_found(tmp_path, monkeypatch):
    monkeypatch.setattr(check_links, "ROOT", tmp_path)
    write(tmp_path / "docs" / "b.md", "# Title\n\n## A heading\n\n## A heading\n")
    write(
        tmp_path / "a.md",
        "[ok](docs/b.md) [ok](docs/b.md#a-heading) [ok](docs/b.md#a-heading-1) "
        "[dir](docs/) [self](#top) [web](https://example.com/x)\n"
        "[bad file](docs/c.md) [bad heading](docs/b.md#nope)\n\n# Top\n\n"
        "```\n[in code](nowhere.md)\n```\n`[inline](nowhere.md)`\n",
    )
    problems = check_links.broken(tmp_path / "a.md")
    assert problems == [
        "a.md: docs/c.md (no such file)",
        "a.md: docs/b.md#nope (no such heading)",
    ]
    assert check_links.main(["a.md"]) == 1


def test_every_link_in_the_v1_documents_resolves():
    assert check_links.main([]) == 0
