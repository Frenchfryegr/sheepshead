"""Public facts derivable from one seat's view of a hand.

Pure and exact: everything here is either copied from the view or proven from cards that have
already fallen. Nothing in this module evaluates, guesses, or decides — hand strength is
`ai_evaluate`, policy is the strategy. See `AI_IMPLEMENTATION.md` §3.6 for the scope line.

Rebuilt from scratch on every AI turn. Strategies are constructed fresh per action
(`_drive_online_ai` in `api/main.py`), so no knowledge can be carried between turns; this is the
substitute for memory, and it is cheap enough to not care.
"""

from dataclasses import dataclass

from .cards import Card, build_deck, card_points, effective_suit
from .rules import RuleSet
from .scoring import trick_winner

# Phases in which the picker's team is finally determined. Between `pick` and the call, a picker
# exists but nobody — including the picker — knows who is on which side.
_TEAMS_SETTLED = {"playing", "hand_done", "game_over"}


@dataclass(frozen=True)
class Knowledge:
    """One seat's complete, honest picture of a hand in progress."""

    # --- copied from the view ---
    ruleset: RuleSet
    seat: int
    phase: str
    hand: tuple[Card, ...]
    num_players: int
    is_leaster: bool
    picker_seat: int | None
    called_card: Card | None
    partner_seat: int | None
    partner_revealed: bool
    buried: tuple[Card, ...]
    card_counts: tuple[int, ...]
    taken_points: tuple[int, ...]
    # Tricks taken per seat. In a leaster this is eligibility: a seat on zero cannot win.
    trick_counts: tuple[int, ...]

    # --- derived ---
    played: frozenset[Card]
    unseen: frozenset[Card]
    voids: tuple[frozenset[str], ...]
    led_suit: str | None
    trick_points: int
    trick_winning_seat: int | None
    # The card currently taking the trick. Needed to decide whether a candidate play beats it;
    # None whenever trick_winning_seat is.
    trick_winning_card: Card | None
    plays_remaining_in_trick: int

    def is_teammate(self, other: int) -> bool | None:
        """True, False, or None when genuinely unknown. Never guesses.

        `None` must be treated as uncertainty by callers, not coerced to False — before the
        called ace appears, only the seat holding it knows the teams (see §3.2/§3.5).
        """
        if other == self.seat:
            return True
        if self.is_leaster:
            return False  # No teams at all; everyone plays for themselves.
        if self.picker_seat is None:
            return None  # Still bidding.
        if self.phase not in _TEAMS_SETTLED:
            return None  # Picked, but not yet called.
        if self.called_card is None:
            # Playing alone. Public the moment it happens, so it resolves for every seat.
            return (other == self.picker_seat) == (self.seat == self.picker_seat)
        if self.partner_revealed and self.partner_seat is not None:
            team = {self.picker_seat, self.partner_seat}
            return (other in team) == (self.seat in team)
        if self.called_card in self.hand:
            return other == self.picker_seat  # I hold the ace, so I am the partner.
        if self.seat == self.picker_seat:
            return None  # Any other seat could hold my called ace.
        if other == self.picker_seat:
            return False
        return None  # A fellow opponent, or the partner — no way to tell yet.

    def could_hold(self, seat: int, card: Card) -> bool:
        """Whether `seat` can still hold `card`. A hard constraint, not a likelihood."""
        if seat == self.seat:
            return card in self.hand
        if card not in self.unseen:
            return False
        if self.card_counts[seat] == 0:
            return False
        return effective_suit(card, self.ruleset) not in self.voids[seat]

    def is_void(self, seat: int, suit: str) -> bool:
        return suit in self.voids[seat]


@dataclass(frozen=True)
class _Play:
    seat: int
    card: Card | None  # None when a face-down under this seat may not see
    under: bool


def _plays(entries: list[dict]) -> list[_Play]:
    return [
        _Play(
            seat=int(entry["seat"]),
            card=Card.parse(entry["card"]) if entry.get("card") else None,
            under=bool(entry.get("under")),
        )
        for entry in entries
    ]


def _trick_led_suit(trick: list[_Play], ruleset: RuleSet, called: Card | None) -> str | None:
    if not trick:
        return None
    lead = trick[0]
    # An under stands in for the called suit, whatever it actually is.
    if lead.under:
        return called.suit.value if called is not None else None
    return effective_suit(lead.card, ruleset) if lead.card is not None else None


def _infer_voids(
    tricks: list[list[_Play]],
    ruleset: RuleSet,
    num_players: int,
    called: Card | None,
    picker_seat: int | None,
    under_outstanding: bool,
) -> tuple[frozenset[str], ...]:
    """A seat that could follow, must. Failing to follow is proof of a void, not a hint.

    With one exception, and it is a real one rather than a caution: a picker holding an unplayed
    under is exempt from follow-suit for that one card, so they can legally discard on a club
    lead while still holding a club. Nobody watching knows which suit the face-down card is, so
    no void can be *proven* for that seat until it has been played. Knowledge claims to be exact,
    so it says nothing rather than something that might be false.

    The exemption is dropped as soon as the under falls. Voids missed during the window are not
    recovered afterwards — that would mean re-reading earlier tricks against a card most seats
    still cannot see, for very little.
    """
    voids: list[set[str]] = [set() for _ in range(num_players)]
    for trick in tricks:
        led = _trick_led_suit(trick, ruleset, called)
        if led is None:
            continue
        # The leader chose the suit, so they prove nothing about it; only followers do.
        for play in trick[1:]:
            # An under proves nothing either way: it counts as following the called suit, and
            # when discarded elsewhere its real suit is not public.
            if play.under or play.card is None:
                continue
            if under_outstanding and play.seat == picker_seat:
                continue
            if effective_suit(play.card, ruleset) != led:
                voids[play.seat].add(led)
        if any(play.under for play in trick):
            under_outstanding = False
    return tuple(frozenset(suits) for suits in voids)


def read_view(view: dict) -> Knowledge:
    """Derive everything publicly knowable from a redacted seat view."""
    ruleset = RuleSet.from_dict(view["ruleset"])
    num_players = ruleset.num_players
    seat = int(view["seat"])

    hand = tuple(Card.parse(card) for card in view["hand"])
    buried = tuple(Card.parse(card) for card in view.get("buried", []))
    called_card = Card.parse(view["called_card"]) if view.get("called_card") else None

    completed = [_plays(trick["plays"]) for trick in view.get("completed_tricks", [])]
    current = _plays(view.get("current_trick", []))

    # A masked under is deliberately absent from `played`: this seat has not seen it, so it
    # stays in `unseen` alongside the bury — dead but unidentified, exactly like a human's view.
    played = frozenset(
        play.card
        for trick in completed + [current]
        for play in trick
        if play.card is not None
    )
    # The open trick is evidence too — a seat that just failed to follow is void right now.
    voids = _infer_voids(
        completed + [current],
        ruleset,
        num_players,
        called_card,
        view.get("picker_seat"),
        bool(view.get("under_declared")),
    )

    # For anyone but the picker this still contains the two dead bury/blind cards, which is
    # exactly a human's information state. Do not try to correct for it.
    unseen = frozenset(build_deck(ruleset)) - played - frozenset(hand) - frozenset(buried)

    # The under can never win, so it is excluded from the contenders whether or not this seat
    # can see it. Which play is the under is public even when its identity is not.
    contenders = [
        (play.seat, play.card) for play in current if play.card is not None and not play.under
    ]
    led_suit = _trick_led_suit(current, ruleset, called_card)

    seats = sorted(view["seats"], key=lambda entry: entry["index"])

    return Knowledge(
        ruleset=ruleset,
        seat=seat,
        phase=view["phase"],
        hand=hand,
        num_players=num_players,
        is_leaster=bool(view["is_leaster"]),
        picker_seat=view.get("picker_seat"),
        called_card=called_card,
        partner_seat=view.get("partner_seat"),
        partner_revealed=bool(view["partner_revealed"]),
        buried=buried,
        card_counts=tuple(int(entry["card_count"]) for entry in seats),
        taken_points=tuple(int(entry["taken_points"] or 0) for entry in seats),
        trick_counts=tuple(int(entry["trick_count"]) for entry in seats),
        played=played,
        unseen=unseen,
        voids=voids,
        led_suit=led_suit,
        # Only counts cards this seat can see; a masked under's points are unknown to it.
        trick_points=sum(card_points(play.card) for play in current if play.card is not None),
        # None when no trick is open, or when only the picker's face-down under has fallen.
        trick_winning_seat=(
            trick_winner(contenders, ruleset, led_suit=led_suit) if contenders else None
        ),
        trick_winning_card=(
            dict(contenders)[trick_winner(contenders, ruleset, led_suit=led_suit)]
            if contenders
            else None
        ),
        # How many seats play after this one, assuming this seat is on turn and about to
        # play. Only meaningful on your own turn — a view built for a seat that has already
        # played this trick will read one too low.
        plays_remaining_in_trick=max(0, num_players - len(current) - 1),
    )
