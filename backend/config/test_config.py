"""
AdEngineAI — Config Tests
===========================
Tests for LLM and Storage config switchers.
All tests run WITHOUT real API keys — they only test the config logic.

Run: pytest tests/test_config.py -v
"""

import os
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# LLM Config Tests
# ---------------------------------------------------------------------------

class TestLLMConfig:

    def test_development_returns_groq(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config, LLMProvider
            cfg = get_llm_config("researcher")
            assert cfg.provider == LLMProvider.GROQ
            assert cfg.api_key == "test-key"

    def test_production_researcher_returns_anthropic(self):
        with patch.dict(os.environ, {"LLM_ENV": "production", "ANTHROPIC_API_KEY": "ant-key", "OPENAI_API_KEY": "oai-key"}):
            from config.llm import get_llm_config, LLMProvider
            cfg = get_llm_config("researcher")
            assert cfg.provider == LLMProvider.ANTHROPIC
            assert "claude" in cfg.model

    def test_production_production_crew_returns_openai(self):
        with patch.dict(os.environ, {"LLM_ENV": "production", "ANTHROPIC_API_KEY": "ant-key", "OPENAI_API_KEY": "oai-key"}):
            from config.llm import get_llm_config, LLMProvider
            cfg = get_llm_config("production")
            assert cfg.provider == LLMProvider.OPENAI
            assert "gpt" in cfg.model

    def test_director_uses_kimi_in_dev(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config
            cfg = get_llm_config("director")
            assert "kimi" in cfg.model

    def test_each_agent_has_different_temperature(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config
            director_cfg = get_llm_config("director")
            researcher_cfg = get_llm_config("researcher")
            # Director needs creativity, researcher needs precision
            assert director_cfg.temperature > researcher_cfg.temperature

    def test_director_has_highest_max_tokens(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config
            director_cfg = get_llm_config("director")
            publisher_cfg = get_llm_config("publisher")
            assert director_cfg.max_tokens > publisher_cfg.max_tokens

    def test_invalid_env_raises_value_error(self):
        with patch.dict(os.environ, {"LLM_ENV": "staging"}):
            from config.llm import get_llm_config
            with pytest.raises(ValueError, match="Invalid LLM_ENV"):
                get_llm_config("researcher")

    def test_missing_groq_key_raises_environment_error(self):
        env = {"LLM_ENV": "development"}
        env.pop("GROQ_API_KEY", None)
        with patch.dict(os.environ, env, clear=True):
            # Need to remove GROQ_API_KEY if it exists
            os.environ.pop("GROQ_API_KEY", None)
            from config.llm import get_llm_config
            with pytest.raises(EnvironmentError, match="GROQ_API_KEY"):
                get_llm_config("researcher")

    def test_missing_anthropic_key_raises_environment_error(self):
        with patch.dict(os.environ, {"LLM_ENV": "production", "OPENAI_API_KEY": "oai"}, clear=False):
            os.environ.pop("ANTHROPIC_API_KEY", None)
            from config.llm import get_llm_config
            with pytest.raises(EnvironmentError, match="ANTHROPIC_API_KEY"):
                get_llm_config("researcher")

    def test_config_is_frozen(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config
            cfg = get_llm_config("researcher")
            with pytest.raises((AttributeError, TypeError)):
                cfg.model = "hacked-model"

    def test_all_agents_have_config(self):
        agents = ["researcher", "director", "production", "qa", "publisher"]
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test-key"}):
            from config.llm import get_llm_config
            for agent in agents:
                cfg = get_llm_config(agent)
                assert cfg.model != ""
                assert cfg.api_key != ""

    def test_get_current_env_returns_correct_value(self):
        with patch.dict(os.environ, {"LLM_ENV": "production"}):
            from config.llm import get_current_env
            assert get_current_env() == "production"

    def test_is_dev_flag(self):
        with patch.dict(os.environ, {"LLM_ENV": "development", "GROQ_API_KEY": "test"}):
            from config.llm import get_llm_config
            cfg = get_llm_config("researcher")
            assert cfg.is_dev() is True
            assert cfg.is_prod() is False

    def test_is_prod_flag(self):
        with patch.dict(os.environ, {"LLM_ENV": "production", "ANTHROPIC_API_KEY": "test", "OPENAI_API_KEY": "test"}):
            from config.llm import get_llm_config
            cfg = get_llm_config("researcher")
            assert cfg.is_prod() is True
            assert cfg.is_dev() is False


# ---------------------------------------------------------------------------
# Storage Config Tests
# ---------------------------------------------------------------------------

class TestStorageConfig:

    def test_development_returns_cloudinary(self):
        with patch.dict(os.environ, {
            "STORAGE_ENV": "development",
            "CLOUDINARY_CLOUD_NAME": "my-cloud",
            "CLOUDINARY_API_KEY": "cld-key",
            "CLOUDINARY_API_SECRET": "cld-secret",
        }):
            from config.storage import get_storage_config, StorageProvider
            cfg = get_storage_config()
            assert cfg.provider == StorageProvider.CLOUDINARY
            assert cfg.cloud_name == "my-cloud"

    def test_production_returns_s3(self):
        with patch.dict(os.environ, {
            "STORAGE_ENV": "production",
            "AWS_ACCESS_KEY_ID": "aws-key",
            "AWS_SECRET_ACCESS_KEY": "aws-secret",
            "AWS_S3_BUCKET": "adengineai-videos",
        }):
            from config.storage import get_storage_config, StorageProvider
            cfg = get_storage_config()
            assert cfg.provider == StorageProvider.S3
            assert cfg.s3_bucket == "adengineai-videos"

    def test_invalid_storage_env_raises(self):
        with patch.dict(os.environ, {"STORAGE_ENV": "azure"}):
            from config.storage import get_storage_config
            with pytest.raises(ValueError, match="Invalid STORAGE_ENV"):
                get_storage_config()

    def test_s3_defaults_to_us_east_1(self):
        with patch.dict(os.environ, {"STORAGE_ENV": "production", "AWS_ACCESS_KEY_ID": "k", "AWS_SECRET_ACCESS_KEY": "s"}):
            os.environ.pop("AWS_REGION", None)
            from config.storage import get_storage_config
            cfg = get_storage_config()
            assert cfg.aws_region == "us-east-1"

    def test_storage_config_is_frozen(self):
        with patch.dict(os.environ, {"STORAGE_ENV": "development", "CLOUDINARY_CLOUD_NAME": "c"}):
            from config.storage import get_storage_config
            cfg = get_storage_config()
            with pytest.raises((AttributeError, TypeError)):
                cfg.cloud_name = "hacked"

    def test_is_dev_flag(self):
        with patch.dict(os.environ, {"STORAGE_ENV": "development"}):
            from config.storage import get_storage_config
            cfg = get_storage_config()
            assert cfg.is_dev() is True
            assert cfg.is_prod() is False

    def test_is_prod_flag(self):
        with patch.dict(os.environ, {"STORAGE_ENV": "production"}):
            from config.storage import get_storage_config
            cfg = get_storage_config()
            assert cfg.is_prod() is True
            assert cfg.is_dev() is False


# ---------------------------------------------------------------------------
# Storage Client URL Tests (no actual uploads)
# ---------------------------------------------------------------------------

class TestStorageClientURLs:

    def test_s3_public_url_without_cloudfront(self):
        from config.storage import StorageConfig, StorageProvider
        from config.storage_client import StorageClient

        cfg = StorageConfig(
            provider=StorageProvider.S3,
            aws_access_key_id="key",
            aws_secret_access_key="secret",
            s3_bucket="my-bucket",
            aws_region="us-east-1",
        )
        # Skip actual S3 init
        client = object.__new__(StorageClient)
        client.cfg = cfg

        url = client.get_public_url("adengineai/user1/campaign1/videos/problem_9x16.mp4")
        assert "my-bucket" in url
        assert "problem_9x16.mp4" in url

    def test_s3_public_url_with_cloudfront(self):
        from config.storage import StorageConfig, StorageProvider
        from config.storage_client import StorageClient

        cfg = StorageConfig(
            provider=StorageProvider.S3,
            s3_bucket="my-bucket",
            cloudfront_url="https://d1234.cloudfront.net",
        )
        client = object.__new__(StorageClient)
        client.cfg = cfg

        url = client.get_public_url("adengineai/user1/campaign1/videos/problem_9x16.mp4")
        assert url.startswith("https://d1234.cloudfront.net")
        assert "problem_9x16.mp4" in url