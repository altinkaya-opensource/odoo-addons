-- Neutralize API keys for demo/test environments.
-- WARNING: Run only on non-production databases.
UPDATE ai_translation_config
SET openrouter_api_key = 'dummy'
WHERE openrouter_api_key IS NOT NULL
  AND openrouter_api_key != 'dummy';
