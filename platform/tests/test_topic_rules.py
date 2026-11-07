import ast
import unittest
from pathlib import Path

from social_intelligence.topic_rules import (
    ENTITY_PASSES,
    HTML_ENTITIES,
    MATCH_TEXT_LIMIT,
    NON_ENGLISH_MIN_LETTERS,
    NON_ENGLISH_SHARE,
    OTHER,
    TAXONOMY_V1_RULES,
    TAXONOMY_VERSION,
    PatternError,
    TopicRule,
    looks_non_english,
    match_rules,
    match_text,
    normalize_text,
    primary_topic,
    seed_tuples,
    topics,
    validate_pattern,
)

NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "00_initialize_platform.py"
SILVER_NOTEBOOK = Path(__file__).resolve().parents[1] / "notebooks" / "02_build_analytics.py"


def rule(topic_id="evals", suffix="terms", priority=20, pattern=r"\bfoo\b", **kwargs):
    return TopicRule(topic_id, f"{topic_id}_{suffix}", priority, pattern, **kwargs)


class PatternValidatorTests(unittest.TestCase):
    def test_every_seeded_pattern_is_portable(self):
        for item in TAXONOMY_V1_RULES:
            validate_pattern(item.pattern)
            if item.exclude_pattern:
                validate_pattern(item.exclude_pattern)

    def test_rejects_what_python_and_java_would_read_differently(self):
        for bad in (
            r"(?=foo)bar",            # lookahead
            r"(?i)foo",               # inline flag
            r"(?<!x)foo",             # lookbehind
            r"a{2,3}",                # counted repetition
            r"\p{L}+",                # unicode class
            r"(a)\1",                 # back-reference
            r"\w+",                   # \w differs on non-ASCII
            r"(a+)+b",                # catastrophic backtracking
            r"foo(",                  # does not compile
            r"<script>",              # characters outside the subset
            "x" * 301,                # too long
            "   ",                    # empty
        ):
            with self.assertRaises(PatternError, msg=bad):
                validate_pattern(bad)

    def test_accepts_the_portable_subset(self):
        for good in (r"\bmcp\b", r"\b(evals?|benchmarks?)\b", r"llm[- ]as[- ]a[- ]judge", r"(?:a|b)c", r"build vs\.? buy"):
            self.assertEqual(validate_pattern(good), good)


class NormalizationTests(unittest.TestCase):
    def test_unescapes_single_and_double_escaped_html(self):
        self.assertEqual(normalize_text("Don&#39;t  Ship &amp; Pray"), "don't ship & pray")
        self.assertEqual(normalize_text("R&amp;amp;D &amp;quot;agents&amp;quot;"), 'r&d "agents"')

    def test_collapses_whitespace_lowercases_and_tolerates_none(self):
        self.assertEqual(normalize_text("  Agent\n\tEVALS  "), "agent evals")
        self.assertEqual(normalize_text(None), "")


class MatchingTests(unittest.TestCase):
    """Hand-written fixtures; none are copied from the labelled samples."""

    def primary(self, text):
        return primary_topic(text, TAXONOMY_V1_RULES)

    def test_each_topic_has_a_positive_fixture(self):
        cases = {
            "How we evaluate a support agent with LLM-as-a-judge": "evals",
            "Securing agent tool access with approval gates": "governance_security",
            "Writing an MCP server for Postgres": "mcp",
            "Tracing and retries for production agents": "reliability",
            "Should we build or buy an agent platform?": "build_vs_buy",
            "LangGraph nodes and edges explained": "framework",
        }
        for text, expected in cases.items():
            self.assertEqual(self.primary(text), expected, text)

    def test_unmatched_text_is_other_and_beginner_material_is_excluded_from_framework(self):
        self.assertEqual(self.primary("Quarterly planning notes"), OTHER)
        self.assertEqual(self.primary("LangGraph tutorial for beginners"), OTHER)
        self.assertEqual(self.primary("A complete CrewAI course"), OTHER)

    def test_bare_vs_is_not_a_build_vs_buy_signal(self):
        self.assertEqual(self.primary("LangGraph vs CrewAI: state handling"), "framework")

    def test_word_boundaries_stop_matches_inside_other_words(self):
        for text in ("A medieval history of tools", "Dr. McPherson on agents", "Gradient of the loss"):
            self.assertEqual(self.primary(text), OTHER, text)

    def test_html_escaped_titles_match_after_normalization(self):
        self.assertEqual(self.primary("Don&#39;t skip &amp;amp; evals"), "evals")

    def test_specific_topics_outrank_the_broad_framework_rule(self):
        text = "Evaluating LangGraph security guardrails over MCP"
        matched = match_rules(text, TAXONOMY_V1_RULES)
        self.assertEqual(topics(matched), ["governance_security", "evals", "mcp", "framework"])
        self.assertEqual(self.primary(text), "governance_security")

    def test_ties_break_deterministically_on_rule_id(self):
        first = rule("mcp", "b_terms", 30, r"\bfoo\b")
        second = rule("mcp", "a_terms", 30, r"\bfoo\b")
        self.assertEqual([r.rule_id for r in match_rules("foo", [first, second])], ["mcp_a_terms", "mcp_b_terms"])
        self.assertEqual([r.rule_id for r in match_rules("foo", [second, first])], ["mcp_a_terms", "mcp_b_terms"])

    def test_disabled_rules_never_fire(self):
        self.assertEqual(primary_topic("foo", [rule(pattern=r"\bfoo\b", enabled=False)]), OTHER)

    def test_exclude_pattern_blocks_a_match(self):
        blocked = rule(pattern=r"\bfoo\b", exclude_pattern=r"\bbar\b")
        self.assertEqual(primary_topic("foo bar", [blocked]), OTHER)
        self.assertEqual(primary_topic("foo baz", [blocked]), "evals")


class RuleDefinitionTests(unittest.TestCase):
    def test_invalid_rules_are_refused(self):
        with self.assertRaises(ValueError):
            TopicRule("other", "other_terms", 10, r"\bx\b")      # other is the fallback, not a rule
        with self.assertRaises(ValueError):
            TopicRule("evals", "mcp_terms", 10, r"\bx\b")        # rule_id must start with its topic
        with self.assertRaises(ValueError):
            TopicRule("evals", "evals_terms", 0, r"\bx\b")       # priority range
        with self.assertRaises(PatternError):
            TopicRule("evals", "evals_terms", 10, r"(?i)x")

    def test_seed_is_unique_and_ordered_by_specificity(self):
        ids = [r.rule_id for r in TAXONOMY_V1_RULES]
        self.assertEqual(len(ids), len(set(ids)))
        priorities = [r.priority for r in TAXONOMY_V1_RULES]
        self.assertEqual(priorities, sorted(priorities))
        self.assertEqual(len(priorities), len(set(priorities)))
        self.assertEqual(TAXONOMY_V1_RULES[-1].topic_id, "framework")  # broadest topic last


class NotebookParityTests(unittest.TestCase):
    """Static guards: the notebook cannot import the package, and Spark is unavailable."""

    def setUp(self):
        self.source = NOTEBOOK.read_text(encoding="utf-8")

    def test_notebook_seed_equals_the_reference_rules(self):
        tree = ast.parse(self.source)
        seed = next(
            ast.literal_eval(node.value) for node in tree.body
            if isinstance(node, ast.Assign) and any(getattr(t, "id", "") == "TOPIC_RULE_SEED" for t in node.targets)
        )
        self.assertEqual(seed, seed_tuples())
        self.assertTrue(all(row[0] == TAXONOMY_VERSION for row in seed))

    def test_table_is_tenant_scoped_and_merged_on_the_full_key(self):
        start = self.source.index("`control_topic_rules` (")
        ddl = self.source[start: self.source.index(")\n    USING DELTA", start)]
        for column in ("tenant_id STRING NOT NULL", "taxonomy_version STRING NOT NULL", "rule_id STRING NOT NULL",
                       "priority INT NOT NULL", "exclude_pattern STRING NOT NULL", "enabled BOOLEAN NOT NULL"):
            self.assertIn(column, ddl)
        merge = self.source[self.source.index("MERGE INTO {ns}.`control_topic_rules`"):]
        merge = merge[: merge.index('"""')]
        self.assertIn("target.tenant_id = incoming.tenant_id", merge)
        self.assertIn("target.taxonomy_version = incoming.taxonomy_version", merge)
        self.assertIn("target.rule_id = incoming.rule_id", merge)

    def test_removed_rules_are_disabled_only_within_the_seeded_tenant(self):
        merge = self.source[self.source.index("MERGE INTO {ns}.`control_topic_rules`"):]
        merge = merge[: merge.index('"""')]
        clause = merge[merge.index("WHEN NOT MATCHED BY SOURCE"):]
        self.assertIn("target.tenant_id = '{tenant_id}'", clause)
        self.assertIn("enabled = false", clause)
        self.assertNotIn("DELETE", merge.upper())


class MatchTextAndLanguageTests(unittest.TestCase):
    def test_match_text_is_normalized_then_cut_to_the_limit(self):
        self.assertEqual(len(match_text("A" * 1000)), MATCH_TEXT_LIMIT)
        self.assertEqual(match_text("Don&#39;t &amp;amp; STOP"), "don't & stop")
        self.assertEqual(match_text(None), "")

    def test_only_the_listed_entities_are_replaced(self):
        self.assertEqual(normalize_text("a &copy; b"), "a &copy; b")

    def test_description_text_inside_the_limit_can_match(self):
        title_only = primary_topic("Weekly update", TAXONOMY_V1_RULES)
        with_description = primary_topic("Weekly update\nWe cover MCP server design in depth", TAXONOMY_V1_RULES)
        self.assertEqual((title_only, with_description), (OTHER, "mcp"))
        beyond = "Weekly update\n" + "x " * 200 + "mcp"
        self.assertEqual(primary_topic(beyond, TAXONOMY_V1_RULES), OTHER)

    def test_a_letter_of_any_script_next_to_a_keyword_is_not_a_boundary(self):
        # Matches Spark's RLIKE on the Databricks runtime, found by the live parity
        # check: a keyword followed directly by a Japanese letter has no boundary there.
        self.assertEqual(primary_topic("éevals", TAXONOMY_V1_RULES), OTHER)
        self.assertEqual(primary_topic("langgraphに学ぶ", TAXONOMY_V1_RULES), OTHER)
        self.assertEqual(primary_topic("langgraph に学ぶ", TAXONOMY_V1_RULES), "framework")

    def test_non_english_flag(self):
        self.assertTrue(looks_non_english("人工知能エージェントの信頼性について"))
        self.assertTrue(looks_non_english("Агенты ИИ в продакшене"))
        self.assertFalse(looks_non_english("Agent evals in production"))
        self.assertFalse(looks_non_english("Agentes de IA en producción"))   # accented Latin is not flagged
        self.assertFalse(looks_non_english("ok 人"))                          # too few letters
        self.assertFalse(looks_non_english(None))


class SilverMatchingGuardTests(unittest.TestCase):
    """Static guards on the Silver notebook; Spark is unavailable in unit tests."""

    def setUp(self):
        self.source = SILVER_NOTEBOOK.read_text(encoding="utf-8")
        self.block = self.source[self.source.index("# Pilot topic matching."): self.source.index("# GitHub repository rows are adoption signals")]

    def literal(self, name):
        tree = ast.parse(self.source)
        node = next(n for n in tree.body if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == name for t in n.targets))
        return ast.literal_eval(node.value)

    def test_constants_equal_the_reference(self):
        self.assertEqual([tuple(pair) for pair in self.literal("HTML_ENTITIES")], list(HTML_ENTITIES))
        self.assertEqual(self.literal("ENTITY_PASSES"), ENTITY_PASSES)
        self.assertEqual(self.literal("MATCH_TEXT_LIMIT"), MATCH_TEXT_LIMIT)
        self.assertEqual(self.literal("NON_ENGLISH_MIN_LETTERS"), NON_ENGLISH_MIN_LETTERS)
        self.assertEqual(self.literal("NON_ENGLISH_SHARE"), NON_ENGLISH_SHARE)

    def test_every_rule_condition_is_pinned_to_its_tenant_and_the_active_version(self):
        self.assertIn('(F.col("tenant_id") == rule.tenant_id)', self.block)
        self.assertIn('F.col("taxonomy_version") == taxonomy_version', self.block)
        self.assertIn("F.col(\"enabled\")", self.block)
        self.assertIn("rule_tenants", self.block)  # tenants without rules get NULL, not 'other'

    def test_demo_sources_are_excluded_and_posts_are_not_joined_to_rules(self):
        self.assertIn('~F.col("source_id").like("demo-%")', self.block)
        self.assertNotRegex(self.block, r"JOIN\s+\S*control_topic_rules")

    def test_merge_key_and_grain_check(self):
        merge = self.block[self.block.index("MERGE INTO {ns}.`silver_social_posts`"):]
        merge = merge[: merge.index('"""')]
        for predicate in ("target.tenant_id = incoming.tenant_id", "target.platform = incoming.platform", "target.post_id = incoming.post_id"):
            self.assertIn(predicate, merge)
        self.assertNotIn("INSERT", merge.upper())
        self.assertNotIn("DELETE", merge.upper())
        self.assertIn("changed the grain of silver_social_posts", self.block)

    def test_bad_rules_are_skipped_not_fatal_and_empty_arrays_are_safe(self):
        self.assertIn("skipping invalid topic rule", self.block)
        self.assertIn('F.size("pilot_matches") > 0', self.block)

    def test_legacy_topic_and_the_new_columns_are_both_present(self):
        silver = self.source[self.source.index("CREATE OR REPLACE TABLE {ns}.`silver_social_posts`"): self.source.index("# Pilot topic matching.")]
        self.assertIn("END AS topic,", silver)
        for column in ("pilot_topic_primary", "pilot_topic_rule_ids", "pilot_taxonomy_version", "language_unsupported"):
            self.assertIn(f"AS {column}", silver)
        self.assertIn("silver_post_topics", self.block)


if __name__ == "__main__":
    unittest.main()
