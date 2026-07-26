"""A short soak inside the normal test run.

`simulate.run()` asserts the engine's invariants on every action — legality is never empty,
deltas sum to zero, points sum to 120, full state round-trips, and every `Knowledge` derivation
matches the true hidden state. Running a small sample here means an ordinary `uv run pytest`
exercises all of that; the long 3000-hand run stays a separate command for real confidence.

Plain unittest so both `pytest` and `python -m unittest` can run it.
"""

import unittest

from .simulate import run

# Enough hands to reach the all-pass leaster path several times over while staying quick.
# The run is deterministic, so this either always passes or always fails — if leasters ever
# come back zero, raise the count rather than weakening the assertion.
SAMPLE_HANDS = 300


class SimulationSoakTests(unittest.TestCase):
    def test_short_soak_holds_every_invariant(self) -> None:
        summary = run(SAMPLE_HANDS)
        self.assertEqual(SAMPLE_HANDS, summary["hands"])
        self.assertGreater(summary["actions"], SAMPLE_HANDS)
        self.assertGreater(summary["leasters"], 0, "all-pass leaster path went unexercised")


if __name__ == "__main__":
    unittest.main()
