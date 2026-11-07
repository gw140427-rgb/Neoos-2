import unittest
from pathlib import Path

from neoos_autodev import execute_plan, policy, validate_plan


class NeoOSAutoDevTests(unittest.TestCase):
    def setUp(self):
        self.plan = {
            "version": 1,
            "name": "safe checks",
            "max_runtime_seconds": 30,
            "steps": [
                {"id": "compile", "action": "compile", "retries": 1, "timeout_seconds": 5},
                {"id": "tests", "action": "test", "retries": 0, "timeout_seconds": 5},
            ],
        }

    def test_policy_disallows_arbitrary_shell_and_deploy(self):
        value = policy()
        self.assertFalse(value["arbitrary_shell"])
        self.assertFalse(value["automatic_deploy"])
        self.assertNotIn("deploy", value["allowed_actions"])

    def test_valid_plan_passes(self):
        self.assertEqual(validate_plan(self.plan), [])

    def test_unknown_action_is_rejected(self):
        plan = {**self.plan, "steps": [{"id": "bad", "action": "shell", "command": "rm -rf /"}]}
        self.assertTrue(any("action" in error for error in validate_plan(plan)))

    def test_non_string_action_is_rejected_without_crashing(self):
        plan = {**self.plan, "steps": [{"id": "bad", "action": ["shell"]}]}
        self.assertTrue(any("action" in error for error in validate_plan(plan)))

    def test_duplicate_step_ids_are_rejected(self):
        plan = {**self.plan, "steps": [self.plan["steps"][0], self.plan["steps"][0]]}
        self.assertTrue(any("unique" in error for error in validate_plan(plan)))

    def test_retry_count_is_bounded(self):
        plan = {**self.plan, "steps": [{"id": "compile", "action": "compile", "retries": 4}]}
        self.assertTrue(any("retries" in error for error in validate_plan(plan)))

    def test_execution_requires_explicit_approval(self):
        result = execute_plan(self.plan, Path.cwd(), approved=False)
        self.assertEqual(result["status"], "approval_required")
        self.assertEqual(result["steps"], [])

    def test_failed_step_retries_only_within_plan_limit(self):
        calls = []
        def fake_runner(action, root, timeout):
            calls.append(action)
            return {"returncode": 1, "timed_out": False, "stdout": "", "stderr": "failure"}
        plan = {**self.plan, "steps": [{"id": "compile", "action": "compile", "retries": 2, "timeout_seconds": 5}]}
        result = execute_plan(plan, Path.cwd(), approved=True, runner=fake_runner)
        self.assertEqual(calls, ["compile", "compile", "compile"])
        self.assertEqual(result["steps"][0]["attempts"], 3)
        self.assertEqual(result["status"], "failed")

    def test_successful_steps_run_in_order(self):
        calls = []
        def fake_runner(action, root, timeout):
            calls.append(action)
            return {"returncode": 0, "timed_out": False, "stdout": "ok", "stderr": ""}
        result = execute_plan(self.plan, Path.cwd(), approved=True, runner=fake_runner)
        self.assertEqual(calls, ["compile", "test"])
        self.assertEqual(result["status"], "completed")


if __name__ == "__main__":
    unittest.main()
