from unittest.mock import patch

from odoo.exceptions import UserError
from odoo.tests import tagged
from odoo.tests.common import TransactionCase

CHAT_PATH = "odoo.addons.altinkaya_llm.models.llm_model.LlmModel._chat"


@tagged("post_install", "-at_install")
class TestTranslationConfig(TransactionCase):
    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        cls.llm_model = cls.env["llm.model"].create(
            {
                "name": "Test Translation Model",
                "code": "test_translation_config",
                "provider_id": cls.env.ref("altinkaya_llm.provider_openrouter").id,
                "model_slug": "test/translation-model",
                "system_prompt": "Use the linked model's translation instructions.",
                "temperature": 0.1,
                "max_tokens": 8192,
            }
        )
        cls.config = cls.env["ai.translation.config"].create(
            {
                "name": "Test Translation Config",
                "llm_model_id": cls.llm_model.id,
                "use_structured_output": True,
            }
        )
        cls.messages = [{"role": "user", "content": "Hello World!"}]
        cls.schema = {
            "type": "object",
            "properties": {"en_GB": {"type": "string"}},
            "required": ["en_GB"],
            "additionalProperties": False,
        }

    def test_call_openrouter_delegates_to_linked_model(self):
        reply = '{"en_GB": "Hello world!"}'
        with patch(CHAT_PATH, autospec=True, return_value=reply) as chat:
            result = self.config._call_openrouter(
                self.messages,
                temperature=0.2,
                max_tokens=512,
                response_schema=self.schema,
            )

        self.assertEqual(result, reply)
        chat.assert_called_once_with(
            self.llm_model,
            self.messages,
            response_schema=self.schema,
            schema_name="translation",
            temperature=0.2,
            max_tokens=512,
        )
        self.assertEqual(chat.call_args.args[0].model_slug, "test/translation-model")

    def test_call_openrouter_requires_linked_model(self):
        self.config.llm_model_id = False
        with patch(CHAT_PATH, autospec=True) as chat:
            with self.assertRaisesRegex(UserError, self.config.name):
                self.config._call_openrouter(self.messages)

        chat.assert_not_called()

    def test_call_openrouter_without_structured_output(self):
        self.config.use_structured_output = False
        with patch(CHAT_PATH, autospec=True, return_value="{}") as chat:
            self.config._call_openrouter(self.messages, response_schema=self.schema)

        chat.assert_called_once_with(
            self.llm_model,
            self.messages,
            response_schema=None,
            schema_name="translation",
            temperature=None,
            max_tokens=None,
        )

    def test_translate_batch_uses_linked_system_prompt(self):
        with patch(
            CHAT_PATH, autospec=True, return_value='{"en_GB": "Hello world!"}'
        ) as chat:
            result = self.config._translate_batch(
                "en_US",
                [
                    {
                        "target_lang": "en_GB",
                        "source_text": "Hello World!",
                        "field_type": "text",
                    }
                ],
            )

        self.assertEqual(result, {"en_GB": "Hello world!"})
        chat.assert_called_once()
        self.assertEqual(
            chat.call_args.args[1][0],
            {"role": "system", "content": self.llm_model.system_prompt},
        )
