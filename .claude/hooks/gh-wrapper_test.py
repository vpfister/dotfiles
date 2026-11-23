import os
from pathlib import Path
import subprocess
import tempfile
import unittest

WRAPPER = Path.home() / ".local/bin/gh"
APPROVED = Path.home() / ".local/bin/gh-approved"


class GhWrapperTest(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.dir = Path(temp.name)
        fake = self.dir / "bin/gh"
        fake.parent.mkdir()
        fake.write_text("#!/bin/sh\necho REAL \"$@\"\n")
        fake.chmod(0o755)

    def run_gh(self, *args, exe=WRAPPER, agent="claude"):
        env = {"PATH": "{}:{}:/usr/bin:/bin".format(WRAPPER.parent, self.dir / "bin"), "HOME": str(Path.home())}
        if agent == "claude":
            env["CLAUDECODE"] = "1"
        elif agent == "codex":
            env["CODEX_THREAD_ID"] = "t"
        return subprocess.run([str(exe), *args], env=env, cwd=self.dir, capture_output=True, text=True)

    def assertPasses(self, result):
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertTrue(result.stdout.startswith("REAL"))

    def assertBlocked(self, result):
        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("REAL", result.stdout)

    def test_routine_commands_pass(self):
        for args in [
            ["pr", "create", "--title", "Today's freeze", "--body-file", "x.md"],
            ["pr", "view", "123"],
            ["api", "-X", "POST", "repos/o/r/pulls/1/comments/2/replies", "-f", "body=merge after CI"],
            ["api", "graphql", "-f", "query=mutation { resolveReviewThread(input: {threadId: \"x\"}) { clientMutationId } }"],
        ]:
            with self.subTest(args=args):
                self.assertPasses(self.run_gh(*args))

    def test_merges_are_blocked_in_agents(self):
        (self.dir / "q.graphql").write_text("mutation { enablePullRequestAutoMerge(input: {}) { clientMutationId } }")
        for args in [
            ["pr", "merge", "123", "--squash"],
            ["stack", "merge"],
            ["api", "-X", "PUT", "repos/o/r/pulls/1/merge"],
            ["api", "graphql", "-f", "query=mutation { mergePullRequest(input: {}) { clientMutationId } }"],
            ["api", "graphql", "-F", "query=@q.graphql"],
            ["api", "graphql", "--input", "-"],
        ]:
            for agent in ["claude", "codex"]:
                with self.subTest(args=args, agent=agent):
                    self.assertBlocked(self.run_gh(*args, agent=agent))

    def test_humans_are_not_blocked(self):
        self.assertPasses(self.run_gh("pr", "merge", "123", agent=None))

    def test_approved_merge_passes_for_claude_only(self):
        self.assertPasses(self.run_gh("pr", "merge", "123", exe=APPROVED))
        self.assertBlocked(self.run_gh("pr", "merge", "123", exe=APPROVED, agent="codex"))


if __name__ == "__main__":
    unittest.main()
