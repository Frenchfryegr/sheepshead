from dataclasses import dataclass, field
from enum import Enum
from typing import TypeAlias

from .cards import Card
from .rules import RuleSet


class Phase(str, Enum):
    PICKING = "picking"
    BURYING = "burying"
    CALLING = "calling"
    PLAYING = "playing"
    HAND_DONE = "hand_done"
    GAME_OVER = "game_over"


@dataclass
class Seat:
    index: int
    name: str
    is_human: bool
    ai_strategy: str | None


@dataclass
class HandResult:
    hand_number: int
    kind: str
    picker_seat: int | None
    partner_seat: int | None
    called_card: Card | None
    deltas: list[int]
    points: list[int]
    buried_points: int
    picker_team_points: int | None
    multiplier: int
    no_schneider: bool
    no_trick: bool
    leaster_winner: int | None = None


@dataclass
class HandState:
    hand_number: int
    dealer_seat: int
    hands: list[list[Card]]
    blind: list[Card]
    buried: list[Card]
    phase: Phase
    turn_seat: int | None
    passes: list[int]
    picker_seat: int | None
    called_card: Card | None
    partner_seat: int | None
    partner_revealed: bool
    is_leaster: bool
    current_trick: list[tuple[int, Card]]
    trick_leader: int
    taken: list[list[Card]]
    last_trick_winner: int | None
    trick_winners: list[int] = field(default_factory=list)
    # Completed tricks in order, each the full (seat, card) sequence as played. Public
    # information — every player watched these fall — and the substrate for AI card counting.
    # apply_action() discards seat attribution from `taken`, so it cannot be recovered later.
    completed_tricks: list[list[tuple[int, Card]]] = field(default_factory=list)
    # The picker's face-down card, when they had to call under. It represents the called suit,
    # can never win a trick, and is seen only by the picker and whoever wins the trick it falls
    # on. The suit it stands for is called_card.suit, so it needs no companion field.
    under_card: Card | None = None
    # Set once any trick is led with the called suit. Until then the picker must hold on to a
    # fail card of that suit so they still have one to play when it finally is led.
    called_suit_led: bool = False


@dataclass
class GameState:
    ruleset: RuleSet
    seats: list[Seat]
    scores: list[int]
    hand: HandState
    hand_history: list[HandResult]
    rng_seed: int


@dataclass(frozen=True)
class PickAction:
    type: str = "pick"


@dataclass(frozen=True)
class PassAction:
    type: str = "pass"


@dataclass(frozen=True)
class BuryAction:
    cards: tuple[Card, ...]
    type: str = "bury"

    def __post_init__(self) -> None:
        object.__setattr__(self, "cards", tuple(sorted(self.cards, key=str)))


@dataclass(frozen=True)
class CallAction:
    card: Card | None
    type: str = "call"


@dataclass(frozen=True)
class UnburyAction:
    """Take the buried cards back and bury again.

    The picker is free to bury anything, but what they are left with decides what they may
    call — so they need a way back until they commit. Offered to human pickers only; an AI has
    no reason to change its mind, and offering it would let the drive loop churn bury/unbury
    against its action cap.
    """

    type: str = "unbury"


@dataclass(frozen=True)
class CallUnderAction:
    """Call a partner card while placing one card face down to stand in for its suit.

    Only legal when no ordinary call exists — i.e. the picker holds no fail card of any
    callable suit. Separate from CallAction so existing call handling stays untouched.
    """

    card: Card
    under: Card
    type: str = "call_under"


@dataclass(frozen=True)
class PlayAction:
    card: Card
    type: str = "play"


Action: TypeAlias = (
    PickAction
    | PassAction
    | BuryAction
    | UnburyAction
    | CallAction
    | CallUnderAction
    | PlayAction
)


@dataclass(frozen=True)
class Event:
    type: str
    seat: int | None = None
    card: Card | None = None
    points: int | None = None
    hand_number: int | None = None
    result: HandResult | None = None
