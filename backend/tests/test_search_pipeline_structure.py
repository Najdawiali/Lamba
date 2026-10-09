"""
Structure checks for app/api/search_v1.py: query understanding runs in parallel with the first embedding
under a time budget. search_v1 cannot be imported without the whole stack (FastAPI, GeoAlchemy, ...), so the
source is parsed instead; the timing behaviour itself is tested in test_search_budget.py.
"""

import ast
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "app", "api", "search_v1.py")


def load():
    with open(PATH, encoding="utf-8") as f:
        tree = ast.parse(f.read())
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node
    return tree


def find_function(tree, name):
    return next(n for n in ast.walk(tree) if isinstance(n, (ast.AsyncFunctionDef, ast.FunctionDef)) and n.name == name)


def call_name(call):
    func = call.func
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        return func.attr
    return None


def ancestors(node):
    while hasattr(node, "parent"):
        node = node.parent
        yield node


class TestSearchPipelineStructure(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tree = load()
        cls.run_search = find_function(cls.tree, "_run_search")

    def calls(self, scope, name):
        return [n for n in ast.walk(scope) if isinstance(n, ast.Call) and call_name(n) == name]

    def test_every_return_of_run_search_has_four_values(self):
        returns = [n for n in ast.walk(self.run_search) if isinstance(n, ast.Return)]
        # nested functions inside _run_search have their own returns; look at the direct ones only
        own = [r for r in returns if next(a for a in ancestors(r) if isinstance(a, (ast.AsyncFunctionDef, ast.FunctionDef))) is self.run_search]
        self.assertGreaterEqual(len(own), 2)
        for node in own:
            self.assertIsInstance(node.value, ast.Tuple)
            self.assertEqual(len(node.value.elts), 4, ast.unparse(node))

    def test_every_caller_unpacks_four_values(self):
        callers = [
            n for n in ast.walk(self.tree)
            if isinstance(n, ast.Assign) and isinstance(n.value, ast.Await)
            and isinstance(n.value.value, ast.Call) and call_name(n.value.value) == "_run_search"
        ]
        self.assertEqual(len(callers), 2)  # /hybrid and /double-check
        for node in callers:
            self.assertEqual(len(node.targets[0].elts), 4, ast.unparse(node))

    def test_the_model_is_only_called_through_the_budget_helper(self):
        helper_calls = self.calls(self.run_search, "understand_within_budget")
        self.assertEqual(len(helper_calls), 1)
        keywords = {k.arg: k.value for k in helper_calls[0].keywords}
        self.assertEqual(set(keywords), {"embed_coro", "qu_coro", "budget_seconds"})
        # the coroutines are handed over, not awaited here
        self.assertEqual(call_name(keywords["qu_coro"]), "analyze_query_async")
        self.assertEqual(call_name(keywords["embed_coro"]), "encode_text_async")
        self.assertEqual(ast.unparse(keywords["embed_coro"].args[0]), "resolved_query")
        self.assertEqual(ast.unparse(keywords["budget_seconds"]), "settings.query_understanding_budget_seconds")
        awaited = [n for n in ast.walk(self.run_search) if isinstance(n, ast.Await) and isinstance(n.value, ast.Call)]
        self.assertEqual([n for n in awaited if call_name(n.value) == "analyze_query_async"], [])
        self.assertEqual([n for n in awaited if call_name(n.value) == "encode_text_async"], [])

    def test_no_extra_waiting_for_the_model(self):
        self.assertEqual(self.calls(self.run_search, "wait_for"), [])

    def test_a_late_model_means_rules_only_attributes(self):
        source = ast.unparse(self.run_search)
        self.assertIn("rules_only_intent(resolved_query)", source)
        self.assertIn("parallel.intent or", source)

    def test_only_the_missing_texts_are_embedded(self):
        helper = self.calls(self.run_search, "assemble_embeddings")
        self.assertEqual(len(helper), 1)
        self.assertEqual(ast.unparse(helper[0].args[0]), "texts")
        self.assertIn("embed_texts_batch", ast.unparse(helper[0].args[2]))
        self.assertEqual(self.calls(self.run_search, "embed_texts_batch").__len__(), 1)  # only inside the helper's callback

    def test_a_response_built_while_the_model_was_late_is_not_cached(self):
        hybrid = find_function(self.tree, "hybrid_search")
        writes = self.calls(hybrid, "cache_search")
        self.assertEqual(len(writes), 2)
        for write in writes:
            guards = [a for a in ancestors(write) if isinstance(a, ast.If) and ast.unparse(a.test) == "not qu_late"]
            self.assertEqual(len(guards), 1, ast.unparse(write)[:60])

    def test_outcomes_against_the_budget_are_counted(self):
        self.assertEqual(len(self.calls(self.run_search, "_count_budget_outcome")), 1)
        helper = find_function(self.tree, "_count_budget_outcome")
        self.assertIn("budget_", ast.unparse(helper))
        self.assertIn('group="search"', ast.unparse(helper).replace("'", '"'))


if __name__ == "__main__":
    unittest.main(verbosity=2)
