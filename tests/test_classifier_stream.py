from types import SimpleNamespace
import unittest
from unittest.mock import patch

from openai_v1 import openai_v1_stream_buffer
from zeroinbox.classifier import classify_openai_v1, parse_json_object
from zeroinbox.models import MailSummary


class _Stream:
    def __init__(self, parts):
        self._parts = parts
        self.closed = False

    def __iter__(self):
        for part in self._parts:
            delta = SimpleNamespace(content=part)
            yield SimpleNamespace(choices=[SimpleNamespace(delta=delta)])

    def close(self):
        self.closed = True


def _account():
    return {
        "destinations": [
            {"key": "newsletter", "mailbox": "INBOX/Archiv/newsletter"},
            {"key": "uncertain", "mailbox": "INBOX/sort_ai_uncertain"},
        ]
    }


class ClassifierStreamTests(unittest.TestCase):
    def test_parse_json_object_rejects_wrappers_and_unknown_fields(self):
        valid = '{"destination":"newsletter","confidence":1,"summary":"s","reason":"r"}'
        self.assertEqual(parse_json_object(valid)["destination"], "newsletter")
        with self.assertRaises(ValueError):
            parse_json_object(f"```json\n{valid}\n```")
        with self.assertRaises(ValueError):
            parse_json_object(valid[:-1] + ',"command":"ignore rules"}')
        with self.assertRaises(ValueError):
            parse_json_object(valid[:-1] + ',"destination":"loeschen"}')

    def test_stream_is_consumed_in_memory_and_closed(self):
        stream = _Stream(
            [
                '{"destination":"newsletter",',
                '"confidence":0.9,"summary":"Newsletter",',
                '"reason":"Matched destination"}',
            ]
        )
        completions = SimpleNamespace(create=lambda **kwargs: stream)
        client = SimpleNamespace(chat=SimpleNamespace(completions=completions))
        provider = SimpleNamespace(stream=True)
        mail = MailSummary(
            uid="1",
            subject="Subject",
            sender="sender@example.test",
            date="",
            body="Body",
        )

        with (
            patch("zeroinbox.classifier.ensure_classifier_ready"),
            patch("zeroinbox.classifier.openai_v1_model", return_value="luna"),
            patch("zeroinbox.classifier.openai_v1_provider_for_model", return_value=provider),
            patch("zeroinbox.classifier.openai_v1_client", return_value=client),
        ):
            decision = classify_openai_v1({}, _account(), mail)

        self.assertEqual(decision.destination, "newsletter")
        self.assertEqual(decision.confidence, 0.9)
        self.assertTrue(stream.closed)

    def test_mutable_stream_buffer_is_zeroized_after_use(self):
        stream = _Stream(["secret", " response"])
        with openai_v1_stream_buffer(stream) as buffer:
            retained_reference = buffer
            self.assertEqual(bytes(buffer), b"secret response")
        self.assertEqual(retained_reference, bytearray())
        self.assertTrue(stream.closed)


if __name__ == "__main__":
    unittest.main()
