"""Playstyles: the same competence, different temperament.

These are **personality, not difficulty** (AI_PLAN.md §2). Every preset plays at the same solid
level and differs in what it *values*, never in how well it executes. There is no ladder, and no
preset is meant to be weaker — a preset that wins materially more than the others is a bug in the
preset, which is what the AI-vs-AI soak exists to catch.

Two invariants constrain the numbers, and both are enforced by tests rather than trusted:

* **Pick bars must sit between the Phase 4 calibration anchors** (six lowest trump ≈ 10.2, three
  high queens ≈ 15.3). Outside that band a style would either pick on six low diamonds or pass on
  three queens, breaking the user's anchors at some seat.
* **`ally_threshold` must sit between the two unknown-team base rates** (0.25 for the picker, 0.667
  for an opponent). Outside it, the role-aware schmear behaviour collapses: below 0.25 the picker
  starts feeding unknown seats, above 0.667 opponents stop helping each other.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class PlayStyle:
    """One personality. Defaults are the balanced baseline the AI was tuned at."""

    name: str = "Balanced"
    description: str = "Plays it straight."

    # --- bidding ---
    # Pick appetite. Lower bars pick more often; both must stay inside the anchor band.
    first_seat_pick_bar: float = 14.5
    last_seat_pick_bar: float = 11.8
    # Alone appetite. Judged on the post-bury hand, which scores far above a pre-blind one.
    alone_bar: float = 27.0
    # Bury style: higher values chase raw buried points, lower ones favour shape and voids.
    bury_point_weight: float = 0.12

    # --- trick play ---
    # Trump aggression: how expensive a card is still worth spending to take a trick.
    cheap_trump_cost: float = 2.0
    # Point risk: how fat a trick must be before a good card is spent on it. Lower is bolder.
    fat_trick_points: int = 10
    # Schmear generosity: the allegiance above which a seat is fed points. Lower gives points
    # away on thinner evidence.
    ally_threshold: float = 0.55


BALANCED = PlayStyle()

CAUTIOUS = PlayStyle(
    name="Cautious",
    description="Picks only on real hands, hoards trump, and gives points away reluctantly.",
    first_seat_pick_bar=15.2,
    last_seat_pick_bar=12.6,
    alone_bar=30.0,
    bury_point_weight=0.10,
    cheap_trump_cost=1.6,
    fat_trick_points=13,
    ally_threshold=0.62,
)

GAMBLER = PlayStyle(
    name="Gambler",
    description="Takes the blind on thin hands, chases going alone, and throws points around.",
    first_seat_pick_bar=13.4,
    last_seat_pick_bar=10.8,
    alone_bar=23.0,
    bury_point_weight=0.15,
    cheap_trump_cost=2.6,
    fat_trick_points=7,
    ally_threshold=0.50,
)

GRINDER = PlayStyle(
    name="Grinder",
    description="Buries every point it can and grinds out safe, unspectacular hands.",
    first_seat_pick_bar=14.6,
    last_seat_pick_bar=11.6,
    alone_bar=28.0,
    bury_point_weight=0.18,
    cheap_trump_cost=1.9,
    fat_trick_points=9,
    ally_threshold=0.58,
)

TACTICIAN = PlayStyle(
    name="Tactician",
    description="Uses trump actively, hunts tricks early, and reads the table.",
    first_seat_pick_bar=14.2,
    last_seat_pick_bar=11.2,
    alone_bar=26.0,
    bury_point_weight=0.11,
    cheap_trump_cost=2.8,
    fat_trick_points=8,
    ally_threshold=0.53,
)

# Registry keys double as the values stored in Seat.ai_strategy and accepted by the create
# endpoint, so they are lowercase and stable. Renaming one orphans existing saved games.
STYLES: dict[str, PlayStyle] = {
    "cautious": CAUTIOUS,
    "gambler": GAMBLER,
    "grinder": GRINDER,
    "tactician": TACTICIAN,
}

PLAYSTYLE_KEYS: tuple[str, ...] = tuple(STYLES)
