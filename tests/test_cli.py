import unittest

from hotseat_core.cli import _config_from_args, _parser


class CliConfigTests(unittest.TestCase):
    def test_serve_provider_and_model_flags_reach_the_config(self):
        args = _parser().parse_args(
            ["--serve", "--provider", "demo", "--model", "demo-model"]
        )
        config = _config_from_args(args)
        self.assertEqual(config.provider, "demo")
        self.assertEqual(config.model, "demo-model")


if __name__ == "__main__":
    unittest.main()
