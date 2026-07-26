"""The heuristic AI: bidding, trick play, and leasters.

Everything here selects from the `legal` list it is handed, never from actions it constructs
itself, so an illegal intent cannot escape into `apply_action`.

Constants are the tuning surface, and the ones a playstyle varies live on `PlayStyle` in
`ai_style.py` — the module-level names below are the balanced baseline everything was calibrated
against. The pick bars are boxed in by the Phase 4 calibration anchors: six low trump must fall
below every seat's bar and three high queens above it, which leaves only a narrow band to work
in. Adjust them from the soak's reported leaster rate, not by feel.
"""

import random

from .ai_evaluate import (
    FAIL_SUITS,
    TRUMP_WEIGHTS,
    HandShape,
    callable_suits,
    leaster_strength,
    offensive_strength,
    shape,
)
from .ai_knowledge import Knowledge, read_view
from .ai_style import BALANCED, PlayStyle
from .cards import Card, Rank, card_points, fail_power, is_trump, trump_power
from .rules import RuleSet
from .scoring import trick_winner
from .state import (
    Action,
    BuryAction,
    CallAction,
    CallUnderAction,
    PassAction,
    PickAction,
    PlayAction,
)

# --- picking -----------------------------------------------------------------------------

# The bar falls linearly from the first seat to the last. Both must sit strictly between the
# anchors (six lowest trump ~10.2, three high queens ~15.3) so the former never picks and the
# latter always does.
# The baseline values now live on PlayStyle (see ai_style.py); these names are kept because the
# balanced style is what every constant here was calibrated against, and because the anchor
# tests read them.
FIRST_SEAT_PICK_BAR = BALANCED.first_seat_pick_bar
# Measured at 10.6: the last seat picked 80% of the time and only 3.8% of hands reached a
# leaster, against a 10-15% target. The last seat is by far the strongest lever on that rate.
LAST_SEAT_PICK_BAR = BALANCED.last_seat_pick_bar

# The last seat's alternative is a leaster, not someone else's problem. A hand that would play
# the leaster badly lowers its own bar — but at 1.6 this was compounding an already low bar.
POOR_LEASTER_STRENGTH = 0.0
POOR_LEASTER_RELIEF = 1.2

# Going alone pays (num_players - 1) x instead of 2 x, but faces four opponents unaided.
# Measured at 22.0: 32% of picked hands went alone, which is not "monsters only" — post-bury
# hands score far higher than pre-blind ones, since two cards are added and the worst two go.
ALONE_BAR = BALANCED.alone_bar

# --- burying -----------------------------------------------------------------------------

# Buried points are banked for the picker's team, immune to being lost in a trick. 11 points is
# worth a bit over one strength unit.
#
# This is also what makes a *forced* trump bury spend the right trump (user's rule): when a hand
# is all trump, or has one fail card worth protecting, the two that go should be the point
# carriers. Burying A-diamond over 9-diamond costs 0.6 of trump quality and banks 11 points, so
# the points win — no separate rule needed, but see the tests that pin it down.
BURY_POINT_WEIGHT = BALANCED.bury_point_weight

# --- call preference ---------------------------------------------------------------------

# Holding exactly one fail card of the called suit is ideal: it can be led at a chosen moment
# and leaves the picker nearly void. Three is awkward and hard to reach the partner through.
CALL_LENGTH_VALUE = {1: 2.4, 2: 1.0, 3: 0.2}
CALL_LONG_SUIT_VALUE = 0.0
# The retention rule forces the picker to keep a called-suit card until the suit is led. Being
# forced to hold on to an ace or ten is a liability, not an asset.
CALL_HIGH_KEEPER_PENALTY = 1.2
# No ordinary call means going under. Playable, but the face-down card is a wasted trick.
UNDER_CALL_VALUE = -1.4

# --- trick play --------------------------------------------------------------------------

# Before the called ace appears, `is_teammate` returns None. The base rates are not symmetric:
# from an opponent's seat, 2 of the 3 other non-pickers are fellow opponents; from the picker's
# seat, only 1 of the 4 unknowns is the partner. Guessing with the real arithmetic beats one
# blanket rule, and costs nothing.
#
# NOTE: reading the partner from behaviour (who schmeared to whom, who ducked when they could
# have won) is deliberately not implemented — see AI_IMPLEMENTATION.md §7.2. These base rates
# are the placeholder for it. When that lands, it replaces these two constants with a posterior.
PICKER_UNKNOWN_ALLY = 0.25
OPPONENT_UNKNOWN_ALLY = 2.0 / 3.0
# Allegiance above which a seat is treated as an ally worth giving points to.
ALLY_THRESHOLD = BALANCED.ally_threshold

# A trick worth spending a good card to take.
FAT_TRICK_POINTS = BALANCED.fat_trick_points
# Trump this cheap is worth spending to take any trick with points in it.
CHEAP_TRUMP_COST = BALANCED.cheap_trump_cost
# Fail cards, cheapest first, indexed by fail_power (7, 8, 9, K, T, A).
FAIL_COST = (0.2, 0.3, 0.4, 0.7, 1.3, 1.6)

# Point lines that change the payout. The picker's team needs 61; the opponents need 60. A
# losing team held under 31 pays double, and a winning team reaching 91 collects double.
PICKER_TARGET = 61
OPPONENT_TARGET = 60
SCHNEIDER_LINE = 31
NO_SCHNEIDER_LINE = 91

# --- leaster play ------------------------------------------------------------------------

# Inverted objective: take the fewest points, but take at least one trick or you cannot win.
# A trick this cheap is worth taking to qualify.
LEASTER_CHEAP_TRICK = 4
# ...and the budget loosens as the chances to qualify run out.
LEASTER_URGENCY_PER_TRICK = 6.0
# The blind's points land on whoever takes the last trick. It averages 7-8, so price the last
# trick as if it already held about this much more than it shows.
LEASTER_BLIND_WEIGHT = 10
# With this many tricks left and still no trick taken, stop waiting and secure one.
LEASTER_SECURE_AT = 2


def pick_threshold(
    position: int,
    num_players: int,
    *,
    first: float = FIRST_SEAT_PICK_BAR,
    last: float = LAST_SEAT_PICK_BAR,
) -> float:
    """Interpolate the bar from the first seat to the last. Two knobs, any seat count."""
    if num_players <= 1:
        return last
    span = min(max(position, 0), num_players - 1) / (num_players - 1)
    return first + (last - first) * span


def _suit_call_value(hand: HandShape, suit: str) -> float:
    held = hand.fail_by_suit[suit]
    if not held:
        return 0.0
    value = CALL_LENGTH_VALUE.get(len(held), CALL_LONG_SUIT_VALUE)
    if held[-1].rank in {Rank.ACE, Rank.TEN}:
        # The lowest card is what gets kept back, so a high one is dead weight.
        value -= CALL_HIGH_KEEPER_PENALTY
    return value


def call_quality(cards, ruleset: RuleSet) -> float:
    """How good the best available ordinary call would be for this hand."""
    suits = callable_suits(cards, ruleset)
    if not suits:
        return UNDER_CALL_VALUE
    hand = shape(cards, ruleset)
    return max(_suit_call_value(hand, suit) for suit in suits)


def bury_score(remaining, buried, ruleset: RuleSet, style: PlayStyle = BALANCED) -> float:
    """Value of a bury, judged jointly with the call it leaves available."""
    return (
        offensive_strength(remaining, ruleset)
        + style.bury_point_weight * sum(card_points(card) for card in buried)
        + call_quality(remaining, ruleset)
    )


def card_cost(card: Card, ruleset: RuleSet) -> float:
    """What spending this card costs the hand. Trump is priced on the same curve as evaluation."""
    if is_trump(card, ruleset):
        return TRUMP_WEIGHTS[trump_power(card, ruleset)]
    return FAIL_COST[fail_power(card)]


def allegiance(knowledge: Knowledge, seat: int | None) -> float:
    """1.0 certain ally, 0.0 certain opponent, base rate in between when unknown."""
    if seat is None:
        return 0.0
    known = knowledge.is_teammate(seat)
    if known is not None:
        return 1.0 if known else 0.0
    return (
        PICKER_UNKNOWN_ALLY
        if knowledge.seat == knowledge.picker_seat
        else OPPONENT_UNKNOWN_ALLY
    )


def beats(candidate: Card, winning: Card, led_suit: str, ruleset: RuleSet) -> bool:
    """Whether `candidate` would take the trick from `winning`.

    Delegates to the engine's own ordering rather than restating it, so the AI can never
    disagree with the rules about which card is higher.
    """
    return trick_winner(
        [(0, winning), (1, candidate)], ruleset, led_suit=led_suit
    ) == 1


def _permitted_buries(buries: list[BuryAction]) -> list[BuryAction]:
    """Narrow the burials by rank before any scoring runs. A queen is never buried.

    An absolute rule from the user, not a weight to be outvoted by a strong enough score: bury
    no queen or jack; a jack only when nothing else can go; a queen never, under any
    circumstances.

    Expressed as a *minimisation* rather than tiers, because "avoid queens" and "avoid jacks"
    are not one threshold each. A hand of four queens, three jacks and one low club can only
    bury one non-jack card, and must then spend exactly one jack — not two.

    Always satisfiable for queens: the deck holds four of each, so an eight-card hand made only
    of queens and jacks holds every one, leaving two jacks free. The queen count therefore
    minimises to zero for any reachable hand.
    """

    def counts(action: BuryAction) -> tuple[int, int]:
        queens = sum(card.rank is Rank.QUEEN for card in action.cards)
        jacks = sum(card.rank is Rank.JACK for card in action.cards)
        return queens, jacks

    fewest = min(counts(action) for action in buries)
    return [action for action in buries if counts(action) == fewest]


class HeuristicStrategy:
    """Plays a full hand. `style` shifts what it values, never how well it executes."""

    def __init__(self, style: PlayStyle = BALANCED) -> None:
        self.style = style

    def choose(self, view: dict, legal: list[Action], rng: random.Random) -> Action:
        if not legal:
            raise ValueError("AI was asked to choose with no legal actions")
        ruleset = RuleSet.from_dict(view["ruleset"])
        hand = [Card.parse(card) for card in view["hand"]]
        phase = view["phase"]

        if phase == "picking":
            chosen = self._pick(view, hand, ruleset, legal)
        elif phase == "burying":
            chosen = self._bury(hand, ruleset, legal)
        elif phase == "calling":
            chosen = self._call(hand, ruleset, legal)
        elif phase == "playing":
            chosen = self._play(read_view(view), legal)
        else:
            chosen = None
        return self._ensure_legal(chosen, legal, rng)

    @staticmethod
    def _ensure_legal(chosen, legal: list[Action], rng: random.Random) -> Action:
        """apply_action raises on an intent outside legal_actions, so never let one through."""
        if chosen is not None and chosen in legal:
            return chosen
        return rng.choice(legal)

    def _pick(self, view: dict, hand, ruleset: RuleSet, legal: list[Action]) -> Action | None:
        position = len(view.get("passes", []))
        threshold = pick_threshold(
            position,
            ruleset.num_players,
            first=self.style.first_seat_pick_bar,
            last=self.style.last_seat_pick_bar,
        )

        # Passing from the last seat starts a leaster rather than passing the problem on, so a
        # hand that would play the leaster badly should be readier to pick.
        is_last = position >= ruleset.num_players - 1
        if is_last and ruleset.leaster_enabled:
            if leaster_strength(hand, ruleset) < POOR_LEASTER_STRENGTH:
                threshold -= POOR_LEASTER_RELIEF

        wants_pick = offensive_strength(hand, ruleset) >= threshold
        wanted = PickAction() if wants_pick else PassAction()
        return wanted if wanted in legal else None

    def _bury(self, hand, ruleset: RuleSet, legal: list[Action]) -> Action | None:
        buries = [action for action in legal if isinstance(action, BuryAction)]
        if not buries:
            return None
        held = list(hand)

        def score(action: BuryAction) -> float:
            discarded = list(action.cards)
            remaining = [card for card in held if card not in discarded]
            return bury_score(remaining, discarded, ruleset, self.style)

        return max(_permitted_buries(buries), key=score)

    # --- trick play ----------------------------------------------------------------------

    def _play(self, knowledge: Knowledge, legal: list[Action]) -> Action | None:
        plays = [action for action in legal if isinstance(action, PlayAction)]
        if not plays:
            return None
        if len(plays) == 1:
            return plays[0]
        if knowledge.is_leaster:
            return self._play_leaster(knowledge, plays)
        if knowledge.led_suit is None:
            return self._lead(knowledge, plays)
        return self._follow(knowledge, plays)

    # --- leaster play --------------------------------------------------------------------

    def _play_leaster(self, knowledge: Knowledge, plays: list[PlayAction]) -> PlayAction:
        """Take the fewest points — but take one trick, or you cannot win at all.

        Three inversions from normal play, and the third is easy to miss:

        1. Giving points away is *good*, so a discard is the fattest card, not the leanest.
        2. There are no teams, so nobody is ever schmeared to.
        3. **A high card is a liability, not an asset.** When a card has to be spent, spend the
           most dangerous one — `-card_cost` rather than `card_cost` as the tiebreak. Keeping a
           queen back only means winning a trick later that you did not want.
        """
        ruleset = knowledge.ruleset
        tricks_left = len(knowledge.hand)
        eligible = knowledge.trick_counts[knowledge.seat] > 0

        if knowledge.led_suit is None:
            return self._lead_leaster(knowledge, plays, tricks_left, eligible)

        winning = knowledge.trick_winning_card
        winners = [
            play
            for play in plays
            if winning is not None
            and beats(play.card, winning, knowledge.led_suit, ruleset)
        ]
        losers = [play for play in plays if play not in winners]

        if not eligible and winners:
            affordable = [
                play
                for play in winners
                if self._leaster_pot(knowledge, play, tricks_left)
                <= self._leaster_budget(knowledge, tricks_left)
            ]
            if affordable:
                # Cheapest in points, then spend the *most* dangerous card — see below.
                return min(
                    affordable,
                    key=lambda play: (
                        self._leaster_pot(knowledge, play, tricks_left),
                        -card_cost(play.card, ruleset),
                    ),
                )

        if losers:
            # Not winning this one, so the points land on somebody else — which is exactly
            # where they should go. Dump the fattest card that stays under the winner.
            return max(
                losers,
                key=lambda play: (card_points(play.card), card_cost(play.card, ruleset)),
            )

        # Every legal card takes the trick, so the only question is what it costs.
        return min(
            plays,
            key=lambda play: (card_points(play.card), -card_cost(play.card, ruleset)),
        )

    def _leaster_pot(
        self, knowledge: Knowledge, play: PlayAction, tricks_left: int
    ) -> float:
        """Points this trick would cost to take, pricing in the blind on the last one."""
        pot = knowledge.trick_points + card_points(play.card)
        if tricks_left == 1:
            pot += LEASTER_BLIND_WEIGHT
        return pot

    def _leaster_budget(self, knowledge: Knowledge, tricks_left: int) -> float:
        """How expensive a qualifying trick this seat can still afford to take."""
        if tricks_left <= 1:
            # Last chance. Being ineligible loses outright, so any price beats not qualifying.
            return 120.0
        spent = knowledge.ruleset.cards_per_player - tricks_left
        return LEASTER_CHEAP_TRICK + LEASTER_URGENCY_PER_TRICK * spent

    def _lead_leaster(
        self,
        knowledge: Knowledge,
        plays: list[PlayAction],
        tricks_left: int,
        eligible: bool,
    ) -> PlayAction:
        ruleset = knowledge.ruleset
        if not eligible and tricks_left <= LEASTER_SECURE_AT:
            # Out of time: lead the strongest card to force a trick through. Everyone will
            # throw their points at it, which is the price of not being eligible at all.
            return max(plays, key=lambda play: card_cost(play.card, ruleset))
        # Otherwise lead something that will not win and is not worth points.
        return min(
            plays,
            key=lambda play: (card_points(play.card), card_cost(play.card, ruleset)),
        )

    def _on_picker_team(self, knowledge: Knowledge) -> bool:
        picker = knowledge.picker_seat
        # Never None in practice: the picker knows itself, the partner holds the ace, and an
        # opponent knows the picker is hostile. Default to False if it somehow is.
        return bool(picker is not None and knowledge.is_teammate(picker))

    def _team_points(self, knowledge: Knowledge) -> float:
        """Expected points taken by my side, weighting unknown seats by their base rate."""
        total = sum(
            allegiance(knowledge, seat) * points
            for seat, points in enumerate(knowledge.taken_points)
        )
        # Buried points are banked for the picker's team, and only the picker can see them.
        if knowledge.buried and self._on_picker_team(knowledge):
            total += sum(card_points(card) for card in knowledge.buried)
        return total

    def _urgency(self, knowledge: Knowledge) -> float:
        """How badly this side needs points, from 0 (comfortable) to 1 (desperate).

        Drives both schneider directions: a side that has already won still pushes for 91, and
        one that has clearly lost still fights to 31 to halve what it pays.
        """
        mine = self._team_points(knowledge)
        target = PICKER_TARGET if self._on_picker_team(knowledge) else OPPONENT_TARGET
        if mine >= target:
            # Won. The remaining prize is the schneider double at 91.
            return 0.35 if mine < NO_SCHNEIDER_LINE else 0.0
        seen = sum(knowledge.taken_points)
        live = max(0, 120 - seen - sum(card_points(card) for card in knowledge.buried))
        if mine + live < target:
            # Cannot win any more. Everything now rides on clearing 31 to avoid paying double.
            return 1.0 if mine < SCHNEIDER_LINE else 0.2
        shortfall = (target - mine) / max(target, 1)
        return min(1.0, 0.4 + 0.6 * shortfall)

    def _seats_after(self, knowledge: Knowledge) -> list[int]:
        return [
            (knowledge.seat + offset) % knowledge.num_players
            for offset in range(1, knowledge.plays_remaining_in_trick + 1)
        ]

    def _trick_is_safe(self, knowledge: Knowledge) -> bool:
        """Whether an opponent still to play could take this trick off the current winner."""
        winning = knowledge.trick_winning_card
        if winning is None or knowledge.led_suit is None:
            return False
        # Work out what beats the current winner once, rather than per seat.
        threats = [
            card
            for card in knowledge.unseen
            if beats(card, winning, knowledge.led_suit, knowledge.ruleset)
        ]
        for seat in self._seats_after(knowledge):
            if allegiance(knowledge, seat) >= self.style.ally_threshold:
                continue  # A likely ally taking it keeps the points on this side anyway.
            if any(knowledge.could_hold(seat, card) for card in threats):
                return False
        return True

    def _follow(self, knowledge: Knowledge, plays: list[PlayAction]) -> PlayAction:
        ruleset = knowledge.ruleset
        led = knowledge.led_suit
        winning = knowledge.trick_winning_card
        friendly = (
            allegiance(knowledge, knowledge.trick_winning_seat) >= self.style.ally_threshold
        )

        winners = [
            play
            for play in plays
            if winning is not None and beats(play.card, winning, led, ruleset)
        ]
        losers = [play for play in plays if play not in winners]

        # Schmear: an ally is taking it and nobody dangerous can take it back, so pay them the
        # fattest card that will not overtake them. Getting this sign wrong is the single most
        # visible way an AI looks foolish, which is why it is decided first.
        if friendly and self._trick_is_safe(knowledge):
            if losers:
                return max(
                    losers,
                    key=lambda play: (card_points(play.card), -card_cost(play.card, ruleset)),
                )
            # Every legal card would overtake our own ally. Take it as cheaply as possible —
            # the points stay on this side either way, so do not also spend a good card.
            return min(plays, key=lambda play: card_cost(play.card, ruleset))

        if winners:
            cheapest = min(winners, key=lambda play: card_cost(play.card, ruleset))
            if self._worth_taking(knowledge, cheapest):
                return cheapest

        # Not taking it: shed the least useful card, and no points to the other side.
        pool = losers or plays
        return min(pool, key=lambda play: (card_points(play.card), card_cost(play.card, ruleset)))

    def _committed_points(self, knowledge: Knowledge) -> int:
        """Points certain to land in this trick that have not been played yet.

        Exactly one card is ever forced: when the called suit is led, `legal_actions` compels the
        partner to produce the called card. Its points are as good as in the pot already, which
        is the difference between reading a called-suit trick as worth 3 and as worth 14 — and
        the reason an opponent holding one queen would duck a trick it should take.

        Only opponents get this. On the picker's side the called card is already coming to them,
        so counting it would only buy over-trumping their own partner's ace.
        """
        called = knowledge.called_card
        if called is None or knowledge.is_leaster:
            return 0
        if knowledge.partner_revealed:
            return 0  # already on the table, so trick_points has it
        if knowledge.led_suit != called.suit.value:
            return 0
        if self._on_picker_team(knowledge):
            return 0
        return card_points(called)

    def _worth_taking(self, knowledge: Knowledge, play: PlayAction) -> bool:
        cost = card_cost(play.card, knowledge.ruleset)
        pot = knowledge.trick_points + card_points(play.card) + self._committed_points(knowledge)
        if knowledge.plays_remaining_in_trick == 0:
            # Last to play, so taking it is certain: any points at all beat a cheap card.
            return pot > 0 or cost <= self.style.cheap_trump_cost
        if pot >= self.style.fat_trick_points:
            return True
        # Otherwise only spend something cheap, and lean in when the side needs points.
        return cost <= self.style.cheap_trump_cost * (0.6 + self._urgency(knowledge))

    def _lead(self, knowledge: Knowledge, plays: list[PlayAction]) -> PlayAction:
        ruleset = knowledge.ruleset
        called = knowledge.called_card
        trump = [play for play in plays if is_trump(play.card, ruleset)]
        fail = [play for play in plays if not is_trump(play.card, ruleset)]

        if self._on_picker_team(knowledge):
            # Pull trump while holding the good ones: it strips the opposition's ability to
            # trump in later, and protects the partner's ace.
            if trump and knowledge.seat == knowledge.picker_seat:
                strongest = max(trump, key=lambda play: card_cost(play.card, ruleset))
                if card_cost(strongest.card, ruleset) >= self.style.cheap_trump_cost:
                    return strongest
        elif called is not None and not knowledge.partner_revealed:
            # Opponent, partner still hidden: lead the called suit to force the ace out and
            # identify them (user's rule). Cheapest card of that suit — the ace will beat it
            # whatever we spend.
            in_suit = [
                play
                for play in fail
                if play.card.suit.value == called.suit.value
            ]
            if in_suit:
                return min(in_suit, key=lambda play: card_cost(play.card, ruleset))

        # Otherwise lead a fail card, cheapest first, keeping points and trump back.
        pool = fail or plays
        return min(pool, key=lambda play: (card_points(play.card), card_cost(play.card, ruleset)))

    def _call(self, hand, ruleset: RuleSet, legal: list[Action]) -> Action | None:
        alone = next(
            (
                action
                for action in legal
                if isinstance(action, CallAction) and action.card is None
            ),
            None,
        )
        if alone is not None and offensive_strength(hand, ruleset) >= self.style.alone_bar:
            return alone

        current = shape(hand, ruleset)
        ordinary = [
            action
            for action in legal
            if isinstance(action, CallAction) and action.card is not None
        ]
        if ordinary:
            return max(ordinary, key=lambda action: _suit_call_value(current, action.card.suit.value))

        unders = [action for action in legal if isinstance(action, CallUnderAction)]
        if unders:
            # The under is a wasted card, so spend the least useful one: whichever leaves the
            # strongest hand behind. Reuses the main evaluation rather than a rival heuristic.
            def remaining_strength(action: CallUnderAction) -> float:
                return offensive_strength(
                    [card for card in hand if card != action.under], ruleset
                )

            return max(unders, key=remaining_strength)
        return alone


# Suits are iterated in a fixed order everywhere so choices stay reproducible for a given seed.
assert FAIL_SUITS == ("C", "S", "H")
