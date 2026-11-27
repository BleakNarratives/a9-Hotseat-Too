import unittest

from hotseat_core.personas import MODES, cast_roster, get_persona_set, list_modes


class PersonaTests(unittest.TestCase):
    def test_known_cast_keys(self):
        self.assertEqual(
            [p.key for p in get_persona_set("classic").personas],
            ["audrey", "claib", "vertical"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v2").personas],
            ["skeptic1", "skeptic2", "skeptic3", "volunteer"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v3").personas],
            ["marlowe", "priya", "zero"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("v3", "tribunal").personas],
            ["adversary", "reason", "whistleblower", "evangelist", "fixer"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("bmad").personas],
            ["analyst", "pm", "architect", "builder", "qa"],
        )
        self.assertEqual(
            [p.key for p in get_persona_set("arena").personas],
            ["producer", "critic", "foreman", "architect", "coroner"],
        )

    def test_default_variant_and_closer(self):
        panel = get_persona_set("v3")
        self.assertEqual(panel.variant, "panel")
        self.assertIsNone(panel.closer)
        tribunal = get_persona_set("v3", "tribunal")
        self.assertEqual(tribunal.closer, "fixer")

    def test_overrides_change_fields(self):
        persona_set = get_persona_set(
            "classic", overrides={"zero": {"model": "ignored"}, "audrey": {"model": "custom", "temperature": 0.1}}
        )
        audrey = persona_set.by_key("audrey")
        self.assertEqual(audrey.model, "custom")
        self.assertEqual(audrey.temperature, 0.1)
        # Overrides for a persona outside the set are simply unused.
        with self.assertRaises(KeyError):
            persona_set.by_key("zero")

    def test_invalid_override_rejected(self):
        with self.assertRaises(ValueError):
            get_persona_set("classic", overrides={"audrey": {"max_tokens": "lots"}})
        with self.assertRaises(ValueError):
            get_persona_set("classic", overrides={"audrey": {"max_tokens": 0}})

    def test_unknown_mode_and_variant(self):
        with self.assertRaises(ValueError):
            get_persona_set("v9")
        with self.assertRaises(ValueError):
            get_persona_set("v3", "nope")

    def test_modes_are_listed_with_variants(self):
        modes = {entry["mode"]: entry for entry in list_modes()}
        self.assertEqual(set(modes), set(MODES) - {"custom"})
        self.assertEqual(modes["v3"]["variants"], ["panel", "tribunal"])
        self.assertEqual(modes["bmad"]["variants"], ["brief"])
        self.assertEqual(modes["arena"]["variants"], ["season"])

    def test_custom_cast_resolves_mode_prefixed_keys(self):
        roster = cast_roster()
        self.assertEqual(len(roster), 29)
        self.assertEqual(len({member["id"] for member in roster}), 29)
        cast = get_persona_set(
            "custom",
            cast=["arena:producer", "bmad:architect", "arena:architect"],
        )
        self.assertEqual(
            [p.key for p in cast.personas],
            ["arena_producer", "bmad_architect", "arena_architect"],
        )
        self.assertEqual(cast.closer, "arena_architect")
        self.assertEqual(cast.label, "Custom cast — 3 called")

    def test_custom_cast_rejects_empty_unknown_and_overflow(self):
        with self.assertRaises(ValueError):
            get_persona_set("custom", cast=[])
        with self.assertRaises(ValueError):
            get_persona_set("custom", cast=["nope:nobody"])
        nine = [
            "arena:producer",
            "arena:critic",
            "arena:foreman",
            "arena:architect",
            "arena:coroner",
            "classic:audrey",
            "classic:claib",
            "classic:vertical",
            "v2:skeptic1",
        ]
        with self.assertRaises(ValueError):
            get_persona_set("custom", cast=nine)

    def test_public_payload_hides_system_by_default(self):
        public = get_persona_set("classic").by_key("audrey").public()
        self.assertNotIn("system", public)
        self.assertIn("system", get_persona_set("classic").by_key("audrey").public(include_system=True))


if __name__ == "__main__":
    unittest.main()
