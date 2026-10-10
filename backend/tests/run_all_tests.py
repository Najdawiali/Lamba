"""
Eagle Vision — Test Runner
Runs all unit tests. No external API calls required.
"""

import sys
import unittest
import os
import asyncio

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if sys.platform == "win32":
    sys.stdout.reconfigure(encoding="utf-8")

from tests.test_arabic_norm import (
    test_normalize_arabic_tashkeel,
    test_normalize_arabic_tatweel,
    test_normalize_arabic_alef_variants,
    test_normalize_arabic_taa_marbouta_option,
    test_normalize_query_empty,
)
from tests.test_arabizi import (
    test_arabizi_dictionary_lookups,
    test_is_arabizi_word,
)
from tests.test_query_understanding import (
    test_needs_llm_simple_queries,
    test_needs_llm_complex_and_service_queries,
)
from tests.test_llm_adapter import (
    test_clean_llm_response_thinking_tags,
    test_clean_llm_response_markdown_fences,
    test_clean_llm_response_empty,
    test_llm_adapter_generate_qwen_thinking_disabled,
    test_llm_adapter_generate_gemma_offline_model,
)
from tests.test_services_mocked import (
    test_embedding_service_zero_vector_fallback,
    test_embedding_cache_rejects_zero_vectors,
    test_embedding_cache_stores_valid_vectors,
    test_llm_adapter_returns_none_on_missing_key,
    test_llm_adapter_returns_none_on_network_error,
    test_normalize_cache_key_consistency,
)
from tests.test_optimizations import (
    TestHttpPool,
    TestRedisCaching,
    TestQueryExpansionCacheIntegration,
    TestBatchEmbedding,
)
from tests.test_customer_auth import TestCustomerAuth
from tests.test_signin_throttle import TestSigninThrottle
from tests.test_synonym_table import TestSynonymTable
from tests.test_offer_model_and_schemas import TestOfferModelAndSchemas
from tests.test_merchant_offers_api import TestMerchantOffersAPI
from tests.test_market_profile_model_and_schemas import TestMarketProfileModelAndSchemas
from tests.test_merchant_market_profile_api import TestMerchantMarketProfileAPI
from tests.test_password_policy import TestPasswordPolicy
from tests.test_refresh_tokens import TestRefreshTokens, TestAccessTokens
from tests.test_refresh_token_store_pg import TestRefreshTokensPostgres, TestAuthFlowPostgres  # skipped without LAMBA_TEST_DATABASE_URL
from tests.test_attribute_rules import TestSanitizeMerchantAttributes, TestAttributeRuleHelpers, TestPlanAttributeFilters
from tests.test_attribute_filters import TestAttributeFilters, TestSearchUsesTheSharedFilters
from tests.test_build_synonym_table import TestBuildSynonymTable
from tests.test_attributes_version_migration import TestAttributesVersionMigration
from tests.test_attribute_extraction import (
    TestAttributeValidator, TestAttributeJsonParser, TestAttributeExtract, TestAttributePrompt,
)
from tests.test_enrich_attributes import (  # need SQLAlchemy to import the job; skipped without it
    TestEnrichProcess, TestEnrichProbeAndGate, TestEnrichReports, TestEnrichSqlText,
    TestEnrichDatabaseHelpers, TestEnrichRun,
)
from tests.test_enrich_attributes_pg import TestEnrichAttributesSql  # skipped without LAMBA_TEST_DATABASE_URL
from tests.test_query_attributes import TestQueryAttributes
from tests.test_llm_error_reasons import TestErrorReasons
from tests.test_qu_cache import TestQuCache
from tests.test_service_tier import TestServiceTierFields
from tests.test_item_classifier_tier import TestClassifierTier, TestWhoIsInteractive, TestDefaults
from tests.test_query_understanding_service import TestQueryUnderstandingService, TestSettingsDefaults
from tests.test_search_budget import TestUnderstandWithinBudget, TestCounterName, TestAssembleEmbeddings
from tests.test_search_pipeline_structure import TestSearchPipelineStructure
from tests.test_category_match import TestExactNames, TestBoost, TestRealTaxonomy, TestClause, TestSearchUsesIt
from tests.test_compare_search_runs import TestCompare, TestEvalSearchOptions, TestFlushSearchCache


class TestArabicNorm(unittest.TestCase):
    def test_tashkeel(self):
        test_normalize_arabic_tashkeel()

    def test_tatweel(self):
        test_normalize_arabic_tatweel()

    def test_alef_variants(self):
        test_normalize_arabic_alef_variants()

    def test_taa_marbouta(self):
        test_normalize_arabic_taa_marbouta_option()

    def test_empty(self):
        test_normalize_query_empty()


class TestArabizi(unittest.TestCase):
    def test_dictionary_lookups(self):
        test_arabizi_dictionary_lookups()

    def test_is_arabizi_word(self):
        test_is_arabizi_word()


class TestQueryUnderstanding(unittest.TestCase):
    def test_simple_queries(self):
        test_needs_llm_simple_queries()

    def test_complex_and_service_queries(self):
        test_needs_llm_complex_and_service_queries()


class TestLLMAdapter(unittest.TestCase):
    def test_thinking_tags(self):
        test_clean_llm_response_thinking_tags()

    def test_markdown_fences(self):
        test_clean_llm_response_markdown_fences()

    def test_empty(self):
        test_clean_llm_response_empty()

    def test_qwen_thinking_disabled(self):
        asyncio.run(test_llm_adapter_generate_qwen_thinking_disabled())

    def test_gemma_offline_model(self):
        asyncio.run(test_llm_adapter_generate_gemma_offline_model())


class TestServicesMocked(unittest.TestCase):
    def test_zero_vector_fallback(self):
        asyncio.run(test_embedding_service_zero_vector_fallback())

    def test_cache_rejects_zero_vectors(self):
        asyncio.run(test_embedding_cache_rejects_zero_vectors())

    def test_cache_stores_valid_vectors(self):
        asyncio.run(test_embedding_cache_stores_valid_vectors())

    def test_llm_missing_key_returns_none(self):
        asyncio.run(test_llm_adapter_returns_none_on_missing_key())

    def test_llm_network_error_returns_none(self):
        asyncio.run(test_llm_adapter_returns_none_on_network_error())

    def test_cache_key_consistency(self):
        test_normalize_cache_key_consistency()


if __name__ == "__main__":
    unittest.main(verbosity=2)
