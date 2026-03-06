"""Unit tests for html_diff module."""

import pytest

from html_diff import wrap_text_to_lines, compute_diff_counts, generate_diff_html


# ---------------------------------------------------------------------------
# wrap_text_to_lines
# ---------------------------------------------------------------------------

class TestWrapTextToLines:
    def test_short_text_unchanged(self):
        text = "hello world"
        assert wrap_text_to_lines(text, width=100) == ["hello world"]

    def test_wraps_long_line(self):
        words = ["word"] * 30  # "word word word ..." = 149 chars
        text = " ".join(words)
        lines = wrap_text_to_lines(text, width=50)
        assert all(len(line) <= 50 for line in lines)
        # Reassembled text should equal original
        assert " ".join(lines) == text

    def test_preserves_blank_lines(self):
        text = "paragraph one\n\nparagraph two"
        lines = wrap_text_to_lines(text, width=100)
        assert lines == ["paragraph one", "", "paragraph two"]

    def test_preserves_multiple_paragraphs(self):
        text = "a\nb\nc"
        assert wrap_text_to_lines(text, width=100) == ["a", "b", "c"]

    def test_empty_string(self):
        assert wrap_text_to_lines("", width=100) == [""]

    def test_no_break_on_hyphens(self):
        text = "state-of-the-art technology is well-known"
        lines = wrap_text_to_lines(text, width=25)
        # Should not break in the middle of hyphenated words
        rejoined = " ".join(lines)
        assert "state-of-the-art" in rejoined

    def test_custom_width(self):
        text = "The quick brown fox jumps over the lazy dog"
        lines = wrap_text_to_lines(text, width=20)
        assert all(len(line) <= 20 for line in lines)
        assert len(lines) > 1


# ---------------------------------------------------------------------------
# compute_diff_counts
# ---------------------------------------------------------------------------

class TestComputeDiffCounts:
    def test_identical(self):
        lines = ["a", "b", "c"]
        assert compute_diff_counts(lines, lines) == (0, 0, 0)

    def test_pure_insertion(self):
        a = ["a", "b"]
        b = ["a", "b", "c", "d"]
        ins, dels, rep = compute_diff_counts(a, b)
        assert ins == 2
        assert dels == 0
        assert rep == 0

    def test_pure_deletion(self):
        a = ["a", "b", "c"]
        b = ["a"]
        ins, dels, rep = compute_diff_counts(a, b)
        assert ins == 0
        assert dels == 2
        assert rep == 0

    def test_replacement(self):
        a = ["a", "b", "c"]
        b = ["a", "x", "c"]
        ins, dels, rep = compute_diff_counts(a, b)
        assert rep >= 1
        assert ins == 0
        assert dels == 0


# ---------------------------------------------------------------------------
# generate_diff_html
# ---------------------------------------------------------------------------

class TestGenerateDiffHtml:
    def test_no_differences_message(self):
        html = generate_diff_html(
            "case_test", "http://a", "http://b",
            "#a", "#b", "same text", "same text", 1.0,
        )
        assert "No differences found" in html
        assert "case_test" in html

    def test_differences_produce_table(self):
        html = generate_diff_html(
            "case_diff", "http://a", "http://b",
            "#a", "#b", "hello world", "hello earth", 0.8,
        )
        assert "<table" in html
        assert "diff_chg" in html or "diff_sub" in html or "diff_add" in html

    def test_toolbar_present(self):
        html = generate_diff_html(
            "c1", "a", "b", "#a", "#b", "x", "y", 0.5,
        )
        assert "Similarity" in html
        assert "Insertions" in html
        assert "Deletions" in html
        assert "Replacements" in html
        assert 'id="next"' in html
        assert 'id="prev"' in html
        assert 'id="togUnchanged"' in html
