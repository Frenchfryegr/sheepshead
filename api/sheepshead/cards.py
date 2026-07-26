from dataclasses import dataclass
from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .rules import RuleSet


class Suit(str, Enum):
    CLUBS = "C"
    SPADES = "S"
    HEARTS = "H"
    DIAMONDS = "D"


class Rank(str, Enum):
    SEVEN = "7"
    EIGHT = "8"
    NINE = "9"
    KING = "K"
    TEN = "T"
    ACE = "A"
    JACK = "J"
    QUEEN = "Q"


@dataclass(frozen=True)
class Card:
    suit: Suit
    rank: Rank

    def __str__(self) -> str:
        return f"{self.rank.value}{self.suit.value}"

    @classmethod
    def parse(cls, value: str) -> "Card":
        if not isinstance(value, str) or len(value) != 2:
            raise ValueError(f"Invalid card: {value!r}")
        return cls(Suit(value[1]), Rank(value[0]))


CARD_POINTS = {
    Rank.ACE: 11,
    Rank.TEN: 10,
    Rank.KING: 4,
    Rank.QUEEN: 3,
    Rank.JACK: 2,
}

_FAIL_ORDER = [Rank.SEVEN, Rank.EIGHT, Rank.NINE, Rank.KING, Rank.TEN, Rank.ACE]
_TRUMP_LOW_TO_HIGH = [
    Card(Suit.DIAMONDS, Rank.SEVEN),
    Card(Suit.DIAMONDS, Rank.EIGHT),
    Card(Suit.DIAMONDS, Rank.NINE),
    Card(Suit.DIAMONDS, Rank.KING),
    Card(Suit.DIAMONDS, Rank.TEN),
    Card(Suit.DIAMONDS, Rank.ACE),
    Card(Suit.DIAMONDS, Rank.JACK),
    Card(Suit.HEARTS, Rank.JACK),
    Card(Suit.SPADES, Rank.JACK),
    Card(Suit.CLUBS, Rank.JACK),
    Card(Suit.DIAMONDS, Rank.QUEEN),
    Card(Suit.HEARTS, Rank.QUEEN),
    Card(Suit.SPADES, Rank.QUEEN),
    Card(Suit.CLUBS, Rank.QUEEN),
]


def card_points(card: Card) -> int:
    return CARD_POINTS.get(card.rank, 0)


def is_trump(card: Card, ruleset: "RuleSet") -> bool:
    del ruleset
    return card.rank in {Rank.QUEEN, Rank.JACK} or card.suit == Suit.DIAMONDS


def trump_power(card: Card, ruleset: "RuleSet") -> int:
    if not is_trump(card, ruleset):
        raise ValueError(f"{card} is not trump")
    return _TRUMP_LOW_TO_HIGH.index(card)


def fail_power(card: Card) -> int:
    if card.rank in {Rank.JACK, Rank.QUEEN}:
        raise ValueError(f"{card} is not a fail card")
    return _FAIL_ORDER.index(card.rank)


def effective_suit(card: Card, ruleset: "RuleSet") -> str:
    return "TRUMP" if is_trump(card, ruleset) else card.suit.value


def build_deck(ruleset: "RuleSet") -> list[Card]:
    del ruleset
    return [Card(suit, rank) for suit in Suit for rank in Rank]


def sort_key(card: Card, ruleset: "RuleSet") -> tuple[int, int, str]:
    if is_trump(card, ruleset):
        return (1, trump_power(card, ruleset), str(card))
    suit_order = {Suit.CLUBS: 0, Suit.SPADES: 1, Suit.HEARTS: 2, Suit.DIAMONDS: 3}
    return (0, suit_order[card.suit] * 10 + fail_power(card), str(card))


_SANITY_DECK = build_deck(None)  # type: ignore[arg-type]
assert len(_SANITY_DECK) == 32
assert sum(card_points(card) for card in _SANITY_DECK) == 120
