"""Pilot topic rules: the portable pattern subset, text normalization, matching.

Rules are data (``control_topic_rules``) matched in Spark SQL by the analytics
notebooks, which cannot import this package. This module is the reference
implementation and the test oracle: it defines which patterns are allowed, how
text is normalized before matching, and how several matching rules resolve to one
primary topic, so the SQL can be checked against it on the same fixtures.

Patterns use a deliberately small regex subset that Python ``re`` and Java regex
(Spark ``RLIKE``) read identically.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable, Sequence

TAXONOMY_VERSION = "pilot-topics-v1"
OTHER = "other"
PATTERN_LIMIT = 300
# Matching reads the first N characters of the normalized ``content_text``: the
# title plus the start of the description for YouTube, the start of the post for X.
# On the 73 on-topic training posts 150, 300 and 600 characters and title-only all
# scored within three posts of each other (57 to 62 percent), so 300 is a
# robustness choice, not a tuned one.
MATCH_TEXT_LIMIT = 300
# Non-English posts are flagged, not translated: a post is unsupported when at
# least this many letters are present and more than this share are non-ASCII.
NON_ENGLISH_MIN_LETTERS = 5
NON_ENGLISH_SHARE = 0.3
# Spark has no HTML unescape, so the notebook replaces exactly this table, in this
# order, three passes, to undo single and double escaping. The notebook carries the
# same literal and a test keeps the two equal.
HTML_ENTITIES = (
    ("&#39;", "'"), ("&#x27;", "'"), ("&apos;", "'"), ("&quot;", '"'),
    ("&lt;", "<"), ("&gt;", ">"), ("&nbsp;", " "), ("&amp;", "&"),
)
ENTITY_PASSES = 3

# Literals, alternation, groups, character classes, \b, \s, optional/repeat marks.
# No lookaround, back-references, inline flags, \p{..} classes or {m,n} counts.
_SAFE_PATTERN = re.compile(r"[A-Za-z0-9 _.,:;'\"/&+#@!?*|()\[\]\\^$-]+")
_ALLOWED_ESCAPES = frozenset({"b", "s", "d", ".", "-", "+", "?", "*", "(", ")", "[", "]", "|", "/", "&", "'"})
_ID = re.compile(r"[a-z][a-z0-9_]{0,63}")


class PatternError(ValueError):
    """The pattern is outside the portable subset or does not compile."""


def validate_pattern(pattern: str) -> str:
    """Return the pattern if portable and compilable, else raise ``PatternError``."""
    if not isinstance(pattern, str) or not pattern.strip():
        raise PatternError("pattern is empty")
    if len(pattern) > PATTERN_LIMIT:
        raise PatternError(f"pattern is longer than {PATTERN_LIMIT} characters")
    if not _SAFE_PATTERN.fullmatch(pattern):
        raise PatternError("pattern uses characters outside the portable subset")
    if "(?" in pattern.replace("(?:", ""):
        raise PatternError("lookaround and inline flags are not portable; use (?: ) for plain groups only")
    if "{" in pattern or "}" in pattern:
        raise PatternError("counted repetition {m,n} is not portable")
    index = 0
    while index < len(pattern):
        if pattern[index] == "\\":
            if index + 1 >= len(pattern) or pattern[index + 1] not in _ALLOWED_ESCAPES:
                raise PatternError(f"escape at position {index} is not in the portable subset")
            index += 2
        else:
            index += 1
    if re.search(r"\([^()]*[+*][^()]*\)[+*]", pattern):
        raise PatternError("nested repetition risks catastrophic backtracking")
    try:
        re.compile(pattern)
    except re.error as error:
        raise PatternError(f"pattern does not compile: {error}") from error
    return pattern


@dataclass(frozen=True)
class TopicRule:
    topic_id: str
    rule_id: str
    priority: int
    pattern: str
    enabled: bool = True
    note: str = ""
    # A rule does not fire when this matches, e.g. beginner tutorials and courses
    # for the broad framework rule. Same portable subset as ``pattern``.
    exclude_pattern: str = ""

    def __post_init__(self) -> None:
        if not _ID.fullmatch(self.topic_id) or self.topic_id == OTHER:
            raise ValueError(f"invalid topic_id: {self.topic_id!r}")
        if not _ID.fullmatch(self.rule_id) or not self.rule_id.startswith(self.topic_id):
            raise ValueError(f"rule_id must start with its topic_id: {self.rule_id!r}")
        if not 1 <= self.priority <= 1000:
            raise ValueError("priority must be between 1 and 1000")
        validate_pattern(self.pattern)
        if self.exclude_pattern:
            validate_pattern(self.exclude_pattern)

    def matches(self, normalized_text: str) -> bool:
        # \b is Unicode-aware in Python and in the Databricks runtime's Java regex
        # (checked live: a keyword followed directly by a Japanese or Korean letter
        # has no boundary in Spark). Rules avoid \s and \w, where the two differ.
        if not self.enabled or re.search(self.pattern, normalized_text) is None:
            return False
        return not (self.exclude_pattern and re.search(self.exclude_pattern, normalized_text))


# ASCII whitespace only, the same set as Java's \s.
_WHITESPACE = re.compile(r"[ \t\r\n\f\x0b]+")


def normalize_text(text: str | None) -> str:
    """Undo HTML escaping (also when double-escaped), lowercase, collapse whitespace.

    Landed YouTube titles carry ``&#39;``, ``&amp;`` and sometimes ``&amp;amp;``.
    Only the entities in ``HTML_ENTITIES`` are replaced.
    """
    value = text or ""
    for _ in range(ENTITY_PASSES):
        for entity, char in HTML_ENTITIES:
            value = value.replace(entity, char)
    return _WHITESPACE.sub(" ", value.lower()).strip()


def match_text(content_text: str | None) -> str:
    """The normalized text rules are matched against."""
    return normalize_text(content_text)[:MATCH_TEXT_LIMIT]


def looks_non_english(text: str | None) -> bool:
    """True when the text is mostly non-ASCII letters (non-Latin scripts)."""
    letters = [char for char in (text or "") if char.isalpha()]
    if len(letters) < NON_ENGLISH_MIN_LETTERS:
        return False
    return sum(ord(char) > 127 for char in letters) / len(letters) > NON_ENGLISH_SHARE


def match_rules(text: str | None, rules: Iterable[TopicRule]) -> list[TopicRule]:
    """Every enabled rule that matches, ordered by (priority, rule_id).

    ``text`` is the raw ``content_text``; it is normalized and cut to the match limit.
    """
    normalized = match_text(text)
    return sorted((rule for rule in rules if rule.matches(normalized)), key=lambda rule: (rule.priority, rule.rule_id))


def topics(matched: Sequence[TopicRule]) -> list[str]:
    seen: list[str] = []
    for rule in matched:
        if rule.topic_id not in seen:
            seen.append(rule.topic_id)
    return seen


def primary_topic(text: str | None, rules: Iterable[TopicRule]) -> str:
    """The matched rule with the lowest priority wins; ties break on rule_id."""
    matched = match_rules(text, rules)
    return matched[0].topic_id if matched else OTHER


# Priority is by specificity, not frequency: narrow topics outrank the broad
# ``framework`` rule, which would otherwise swallow most posts.
TAXONOMY_V1_RULES: tuple[TopicRule, ...] = (
    TopicRule("governance_security", "governance_security_terms", 10,
              r"\b(governance|guardrails?|compliance|prompt injection|access control|permissions?|audit(ing|able)?|policy|policies|sandbox(ed|ing)?|security|secure|safe|safety|approv(e|es|ed|al|als)|human[- ]in[- ]the[- ]loop|trust(ed|worthy)?)\b",
              note="controls, risk and trust"),
    TopicRule("evals", "evals_terms", 20,
              r"\b(evals?|evaluat(e|es|ed|ing|ion|ions)|benchmarks?|graders?|grading|llm[- ]as[- ]a[- ]judge)\b",
              note="evaluation and measurement of agents"),
    TopicRule("mcp", "mcp_terms", 30,
              r"\b(mcp|model context protocol)\b",
              note="Model Context Protocol"),
    TopicRule("reliability", "reliability_terms", 40,
              r"\b(reliab(le|ility)|observability|tracing|monitoring|retr(y|ies)|fallbacks?|failures?|checkpoint(s|ing)?|in production|production[- ](ready|grade)|debugging|latency)\b",
              note="running agents in production"),
    TopicRule("build_vs_buy", "build_vs_buy_terms", 50,
              r"\b(build vs\.? buy|buy vs\.? build|build or buy|buy or build|acquires?|acquired|acquisition|series [a-d]|which (agent )?framework|how to choose|choosing (a|an|the|your)|alternatives? to)\b",
              note="choosing between platforms, vendors and frameworks; narrow on purpose, bare 'vs' matches framework comparisons"),
    TopicRule("framework", "framework_terms", 60,
              r"\b(langgraph|crewai|autogen|langchain|llamaindex|pydantic ?ai|agents? sdk|google adk|semantic kernel|agent framework|multi[- ]agent)\b",
              exclude_pattern=r"\b(tutorials?|beginners?|courses?|crash course|from scratch|step by step|for dummies|learn|bootcamp|class)\b",
              note="agent frameworks and SDKs; broadest, so lowest precedence; beginner material is excluded"),
)


def seed_tuples() -> list[tuple]:
    """Rows for ``control_topic_rules`` without the tenant, in column order.

    ``00_initialize_platform.py`` carries the same literal (it cannot import this
    package); a unit test keeps the two identical.
    """
    return [
        (TAXONOMY_VERSION, rule.topic_id, rule.rule_id, rule.priority, rule.pattern,
         rule.exclude_pattern, rule.enabled, rule.note)
        for rule in TAXONOMY_V1_RULES
    ]
