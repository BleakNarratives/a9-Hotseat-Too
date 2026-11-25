import io
import json
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path

from hotseat_core.cli import main
from hotseat_core.config import load_config
from hotseat_core.runtime import HotseatRuntime
from hotseat_core.storage import SessionStore


class EngineTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def runtime(self) -> HotseatRuntime:
        config = load_config(root=self.root, env={"HOTSEAT_DATA_DIR": str(self.root), "HOTSEAT_PROVIDER": "demo"})
        store = SessionStore(config.db_path, config.session_log)
        return HotseatRuntime(config, store=store)

    def test_classic_emits_three_turns_and_saves(self):
        events = []
        result = self.runtime().run_session("classic", "ship the small version", emit=events.append)
        self.assertEqual(len(result.turns), 3)
        self.assertEqual([t.persona for t in result.turns], ["audrey", "claib", "vertical"])
        self.assertIsNotNone(result.memory_id)
        types = [event["type"] for event in events]
        self.assertEqual(types[0], "session_start")
        self.assertIn("persona_turn", types)
        self.assertIn("memory_saved", types)
        self.assertEqual(types[-1], "session_end")
        self.assertIn("demo output", result.transcript)

    def test_demo_reply_is_built_from_the_case_and_the_wire(self):
        from hotseat_core.providers import demo_response

        system = "You are the Coroner. Write the autopsy of the seed idea."
        evidence = (
            "MARKET ANCHORS (structured pricing):\n"
            "- acme.test | paid | monthly | $29/mo | Acme Quotes | 2026-11-20"
        )
        reply = demo_response(
            system,
            [
                {
                    "role": "user",
                    "content": "Seed idea: 'a quote tool for roofers'. Constraints: none.\n\n" + evidence,
                }
            ],
        )
        self.assertIn("a quote tool for roofers", reply)
        self.assertIn("$29/mo", reply)
        self.assertIn("demo output", reply)

    def test_v2_and_v3_variants(self):
        runtime = self.runtime()
        debate = runtime.run_session("v2", "an idea", save=False)
        self.assertEqual(len(debate.turns), 4)
        panel = runtime.run_session("v3", "a situation", save=False)
        self.assertEqual([t.persona for t in panel.turns], ["marlowe", "priya", "zero"])
        tribunal = runtime.run_session("v3", "a decision", variant="tribunal", save=False)
        self.assertEqual(len(tribunal.turns), 5)
        self.assertEqual(tribunal.turns[-1].persona, "fixer")

    def test_bmad_brief_is_a_single_five_turn_pass(self):
        runtime = self.runtime()
        result = runtime.run_session(
            "bmad", "a CLI that turns a voice memo into tasks", save=False
        )
        self.assertEqual(
            [t.persona for t in result.turns],
            ["analyst", "pm", "architect", "builder", "qa"],
        )
        self.assertEqual(result.variant, "brief")
        self.assertIn("bmad:brief", result.transcript)
        self.assertEqual(len(result.turns), 5)

    def test_arena_runs_four_contenders_to_a_brief_and_autopsy(self):
        runtime = self.runtime()
        result = runtime.run_session(
            "arena", "a CLI that turns a voice memo into tasks", save=False
        )
        self.assertEqual(
            [t.persona for t in result.turns],
            ["producer", "critic", "foreman", "architect", "coroner"],
        )
        self.assertEqual(result.variant, "season")
        self.assertIn("arena:season", result.transcript)

    def test_arena_constraints_reach_the_producer(self):
        seen = []

        class Recorder:
            provider = "recorder"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                seen.append(messages[-1]["content"])
                if on_chunk:
                    on_chunk("ok")
                return "ok"

        config = load_config(root=self.root, env={"HOTSEAT_DATA_DIR": str(self.root)})
        runtime = HotseatRuntime(
            config,
            store=SessionStore(config.db_path, config.session_log),
            client_factory=lambda provider, model: Recorder(),
        )
        runtime.run_session(
            "arena", "seed", save=False, options={"constraints": "budget $0, one weekend"}
        )
        self.assertIn("budget $0, one weekend", seen[0])

    def test_stop_event_ends_after_current_turn(self):
        runtime = self.runtime()
        stop = threading.Event()
        events = []

        def emit(event):
            events.append(event)
            if event["type"] == "persona_turn":
                stop.set()

        result = runtime.run_session("v3", "stop early", save=False, emit=emit, stop_event=stop)
        self.assertEqual(len(result.turns), 1)

    def test_injection_reaches_a_later_prompt(self):
        seen = []

        class Recorder:
            provider = "recorder"

            def complete(self, *, messages, model=None, system=None, sampling=None, on_chunk=None):
                seen.append(messages[-1]["content"])
                if on_chunk:
                    on_chunk("ok")
                return "ok"

        config = load_config(root=self.root, env={"HOTSEAT_DATA_DIR": str(self.root)})
        runtime = HotseatRuntime(
            config,
            store=SessionStore(config.db_path, config.session_log),
            client_factory=lambda provider, model: Recorder(),
        )
        notes = iter([None, "focus on pricing"])
        runtime.run_session(
            "classic",
            "inject me",
            save=False,
            injection=lambda: next(notes, None),
            emit=lambda event: None,
        )
        self.assertNotIn("focus on pricing", seen[0])
        self.assertTrue(any("focus on pricing" in prompt for prompt in seen[1:]))

    def test_cli_json_stream_is_parseable_ndjson(self):
        out, err = io.StringIO(), io.StringIO()
        code = None
        with redirect_stdout(out), redirect_stderr(err):
            code = main(
                [
                    "--provider",
                    "demo",
                    "--mode",
                    "v3",
                    "--json-stream",
                    "--no-save",
                    "--data-dir",
                    str(self.root),
                    "test the contract",
                ]
            )
        self.assertEqual(code, 0)
        events = [json.loads(line) for line in out.getvalue().splitlines() if line.strip()]
        self.assertEqual(events[0]["type"], "session_start")
        self.assertEqual(events[-1]["type"], "session_end")
        self.assertEqual(len(events[-1]["turns"]), 3)

    def test_cli_reports_usage_errors(self):
        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            code = main(["--mode", "nope", "--no-save", "--provider", "demo", "x"])
        self.assertEqual(code, 2)
        self.assertIn("Unknown mode", err.getvalue())


if __name__ == "__main__":
    unittest.main()
