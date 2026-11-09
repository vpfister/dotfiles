import json
from pathlib import Path
import shlex
import subprocess
import sys
import tempfile
import unittest


HOOK = Path(__file__).with_name("gh-api-write-guard.py")
REVIEWS = "repos/mistralai/mistral/pulls/123/reviews"


class ReviewPermissionsTest(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.cwd = Path(self.temp.name)
        self.payload = self.cwd / "review.json"
        self.write_review("COMMENT")

    def write_review(self, event):
        self.payload.write_text(json.dumps({"event": event, "body": "A finding", "comments": []}))

    def decision(self, command):
        result = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"cwd": str(self.cwd), "tool_input": {"command": command}}),
            capture_output=True,
            text=True,
            check=True,
        )
        if not result.stdout:
            return "pass"
        return json.loads(result.stdout)["hookSpecificOutput"]["permissionDecision"]

    def test_prepared_comment_review(self):
        commands = [
            f"gh api -X POST {REVIEWS} --input review.json",
            f"gh api {REVIEWS} --input={self.payload}",
            f"gh api --method=POST {REVIEWS} --input review.json",
            f"gh api -XPOST {REVIEWS} --input review.json",
            f"cd {self.cwd}; gh api -X POST {REVIEWS} --input review.json -q .html_url",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "pass")

    def test_relative_input_after_cd(self):
        directory = self.cwd / "review files"
        directory.mkdir()
        (directory / "body.json").write_text(self.payload.read_text())
        self.assertEqual(
            self.decision(f"cd 'review files' && gh api {REVIEWS} --input body.json"), "pass"
        )

    def test_inline_comment_review(self):
        for flag in ["-f event=COMMENT", "--raw-field=event=COMMENT", "-fevent=COMMENT"]:
            with self.subTest(flag=flag):
                self.assertEqual(self.decision(f"gh api {REVIEWS} {flag} -f body=Finding"), "pass")

    def test_review_approvals_and_other_events_prompt(self):
        for event in ["APPROVE", "REQUEST_CHANGES", None]:
            self.write_review(event)
            with self.subTest(event=event):
                self.assertEqual(self.decision(f"gh api {REVIEWS} --input review.json"), "ask")
        self.assertEqual(self.decision(f"gh api {REVIEWS} -f event=APPROVE"), "ask")

    def test_uninspectable_payloads_do_not_pass(self):
        for contents in ["not JSON", "[]", "{}"]:
            self.payload.write_text(contents)
            with self.subTest(contents=contents):
                self.assertEqual(self.decision(f"gh api {REVIEWS} --input review.json"), "ask")
        for filename in ["missing.json", "-", "$BODY"]:
            with self.subTest(filename=filename):
                self.assertEqual(self.decision(f"gh api {REVIEWS} --input {filename}"), "deny")

    def test_same_command_cannot_replace_checked_payload(self):
        replacement = shlex.quote(json.dumps({"event": "APPROVE"}))
        command = f"printf %s {replacement} > review.json; gh api {REVIEWS} --input review.json"
        self.assertEqual(self.decision(command), "deny")
        self.assertEqual(self.decision(f"gh api {REVIEWS} --input review.json"), "pass")

    def test_conflicting_event_field_prompts(self):
        self.assertEqual(
            self.decision(f"gh api {REVIEWS} --input review.json -f event=APPROVE"), "ask"
        )

    def test_shell_expansion_requires_preparation(self):
        commands = [
            f'gh api {REVIEWS} --input review.json -q "$(touch review.json)"',
            f"gh api {REVIEWS} --input review.json $ARGS",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "deny")

    def test_other_writes_still_prompt(self):
        commands = [
            "gh api -X DELETE repos/mistralai/mistral",
            "gh api -X POST repos/mistralai/mistral/actions/workflows/1/dispatches -f ref=main",
            "gh api -X PATCH repos/mistralai/mistral --input review.json",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "ask")

    def test_merges_still_prompt(self):
        commands = [
            "gh api -X PUT repos/mistralai/mistral/pulls/123/merge",
            "gh api graphql -f 'query=mutation{mergePullRequest(input:{pullRequestId:\"x\"}){clientMutationId}}'",
            "gh api graphql -f 'query=mutation{enablePullRequestAutoMerge(input:{pullRequestId:\"x\"}){clientMutationId}}'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "ask")

    def test_existing_reads_and_thread_operations_pass(self):
        commands = [
            f"gh api {REVIEWS}",
            "gh api repos/mistralai/mistral/pulls/123/comments --paginate",
            "gh api -X POST repos/mistralai/mistral/pulls/123/comments/456/replies -f body=Fixed",
            "gh api graphql -f 'query=mutation{resolveReviewThread(input:{threadId:\"x\"}){thread{isResolved}}}'",
        ]
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.decision(command), "pass")


if __name__ == "__main__":
    unittest.main()
