"""Checks on the rules text.

Not spell-checking prose for its own sake: these pin the things that go
stale when the game changes underneath the text. The rulebook describes
what this app enforces, so if the app stops enforcing positional superko
or stops using area scoring, the text is then wrong and a reader is
actively misled.
"""

import re

from gogame import rulebook
from gogame.rules import Rules


def _all_text() -> str:
    """Titles included: a heading is text the reader sees, so a topic
    covered by a section called "Handicap" is covered."""
    return "\n".join(
        "\n".join((section.title,) + section.paragraphs)
        for section in rulebook.SECTIONS
    ).lower()


def test_every_section_has_a_title_and_a_body():
    assert rulebook.SECTIONS
    for section in rulebook.SECTIONS:
        assert section.title.strip()
        assert section.paragraphs
        for paragraph in section.paragraphs:
            assert paragraph.strip()


def test_section_titles_are_unique():
    titles = [section.title for section in rulebook.SECTIONS]
    assert len(titles) == len(set(titles))


def test_title_of_matches_the_section():
    assert rulebook.title_of(0) == rulebook.SECTIONS[0].title


def test_paragraphs_are_prose_not_source_formatting():
    """Caught a real one: an em dash split across a line continuation came
    out as a literal "--" on screen."""
    for section in rulebook.SECTIONS:
        for paragraph in section.paragraphs:
            assert "--" not in paragraph, (section.title, paragraph)
            assert "  " not in paragraph, (section.title, paragraph)
            assert paragraph == paragraph.strip()


def test_covers_the_rules_a_beginner_has_to_be_told():
    text = _all_text()
    for topic in ("liberti", "captur", "ko", "komi", "pass", "handicap", "dead"):
        assert topic in text, topic


def test_describes_the_repetition_rule_this_app_actually_enforces():
    """GameState keeps every previous position's hash, not just the last,
    which is positional superko rather than simple ko."""
    assert "superko" in _all_text()


def test_describes_area_scoring_rather_than_territory():
    """rules.GameState.score() calls Board.area_score()."""
    text = _all_text()
    assert "area scoring" in text
    assert "territory scoring" not in text


def test_quotes_the_default_komi_the_app_actually_uses():
    komi = Rules().komi
    assert re.search(rf"\b{re.escape(f'{komi:g}')}\b", _all_text())


def test_handicap_range_matches_the_new_game_screen():
    assert "2 to 9" in "\n".join(
        p for s in rulebook.SECTIONS for p in s.paragraphs
    )
