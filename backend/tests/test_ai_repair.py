"""Regression coverage for provider formatting and bounded diagnosis correction."""
import json
import unittest
from unittest.mock import patch

from app.ai.analyzer import analyze_investigation, validate_completion
from app.ai.prompt_builder import build_prompt
from test_ai import settings, evidence, diagnosis


class RepairTests(unittest.TestCase):
    def test_malformed_answer_corrected_once(self):
        with patch('app.ai.analyzer.get_settings', return_value=settings()), patch(
                'app.ai.analyzer.LLMClient.complete', side_effect=['{"root_cause": "incomplete"}', json.dumps(diagnosis())]) as provider:
            result = analyze_investigation(evidence())
        self.assertEqual(result['status'], 'success')
        self.assertEqual(provider.call_count, 2)
        repair = provider.call_args.args[0][-1]['content']
        self.assertIn('missing', repair)
        self.assertIn('kubectl_commands', repair)

    def test_invalid_reference_remains_rejected_after_two_attempts(self):
        answer = diagnosis()
        answer['evidence_references'] = ['/evidence/logs/entries/0/text']
        with patch('app.ai.analyzer.get_settings', return_value=settings()), patch(
                'app.ai.analyzer.LLMClient.complete', return_value=json.dumps(answer)) as provider:
            result = analyze_investigation(evidence())
        self.assertEqual(provider.call_count, 2)
        self.assertEqual(result['status'], 'error')
        self.assertIn('evidence validation', result['validation_detail'])

    def test_schema_details_do_not_echo_values_or_unknown_field_names(self):
        answer = diagnosis()
        answer['confidence'] = 'private-password'
        answer['private-secret-field'] = 'secret-value'
        with self.assertRaises(ValueError) as caught:
            validate_completion(json.dumps(answer), evidence()['investigation'], 'success')
        detail = str(caught.exception)
        for secret in ('private-password', 'private-secret-field', 'secret-value'):
            self.assertNotIn(secret, detail)
        self.assertIn('confidence', detail)

    def test_fenced_json_is_accepted_but_surrounding_prose_is_not(self):
        content = json.dumps(diagnosis())
        parsed = validate_completion('```json\n' + content + '\n```', evidence()['investigation'], 'success')
        self.assertEqual(parsed.confidence, 92)
        with self.assertRaises(ValueError):
            validate_completion('Here is my answer: ' + content, evidence()['investigation'], 'success')

    def test_actual_healthy_evidence_allows_empty_commands(self):
        payload = evidence()
        payload['investigation']['pods'] = {'ok': True, 'healthy': True, 'total': 9, 'problematic_pods': []}
        payload['investigation']['logs'] = {'ok': True, 'entries': []}
        answer = diagnosis()
        answer.update(root_cause='No failure demonstrated', kubectl_commands=[],
                      evidence_references=['/pods/healthy'], missing_evidence=['DNS not tested'])
        with patch('app.ai.analyzer.get_settings', return_value=settings()), patch(
                'app.ai.analyzer.LLMClient.complete', return_value=json.dumps(answer)) as provider:
            result = analyze_investigation(payload)
        self.assertEqual(result['status'], 'success')
        self.assertEqual(result['diagnosis']['kubectl_commands'], [])
        self.assertEqual(provider.call_count, 1)
        messages, _ = build_prompt(payload)
        example = json.loads(messages[1]['content'])['format_example_only_do_not_copy_conclusions']
        self.assertEqual(example['evidence_references'], ['/pods/healthy'])
