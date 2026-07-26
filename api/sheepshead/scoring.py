from .cards import card_points
from .rules import RuleSet
from .state import HandResult, HandState


# Reaching 30 *is* schneider — the team is safe there and the stake stays at 1x. Only a team
# held to 29 or fewer pays double. Mirrored on the winning side: 91 is the least that holds the
# opposition under 30 (120 - 91 = 29), so the no-schneider line needs no separate constant.
SCHNEIDER_LINE = 30


def trick_winner(
    trick: list[tuple[int, object]],
    ruleset: RuleSet,
    *,
    ineligible: "object | None" = None,
    led_suit: str | None = None,
) -> int:
    """Seat that takes this trick.

    `ineligible` is the picker's under card, which can never win regardless of its rank — the
    only exception to the ordering. `led_suit` overrides the suit the trick was led in, which
    the caller supplies when the under itself led: it stands in for the called suit.
    """
    from .cards import Card, effective_suit, fail_power, is_trump, trump_power

    if not trick:
        raise ValueError("Cannot score an empty trick")
    typed_trick = [(seat, card) for seat, card in trick if isinstance(card, Card)]
    if led_suit is None:
        led_suit = effective_suit(typed_trick[0][1], ruleset)
    # Fall back to the full trick if the under is somehow the only card, so this stays total.
    contenders = [item for item in typed_trick if item[1] != ineligible] or typed_trick

    def power(item: tuple[int, Card]) -> tuple[int, int]:
        card = item[1]
        if is_trump(card, ruleset):
            return (2, trump_power(card, ruleset))
        if effective_suit(card, ruleset) == led_suit:
            return (1, fail_power(card))
        return (0, fail_power(card))

    return max(contenders, key=power)[0]


def score_hand(hand: HandState, ruleset: RuleSet) -> HandResult:
    points = [sum(card_points(card) for card in cards) for cards in hand.taken]

    if hand.is_leaster:
        if hand.last_trick_winner is None:
            raise ValueError("Leaster ended without a last trick winner")
        if ruleset.leaster_blind == "last_trick":
            points[hand.last_trick_winner] += sum(card_points(card) for card in hand.blind)
        # Only players who took a trick are eligible; "take nothing" must not win a leaster.
        # Six tricks are always dealt, so trick_winners is non-empty in any real hand.
        eligible = set(hand.trick_winners) or set(range(ruleset.num_players))
        minimum = min(points[seat] for seat in eligible)
        tied = {seat for seat in eligible if points[seat] == minimum}
        if len(tied) > 1:
            # A tied leaster is a wash: nobody scores at all. There is deliberately no
            # tie-break — an earlier version awarded it to whoever won a trick latest, which
            # both invented a winner and rewarded taking the last trick, the one carrying the
            # blind.
            winner = None
            deltas = [0] * ruleset.num_players
        else:
            winner = next(iter(tied))
            deltas = [-1] * ruleset.num_players
            deltas[winner] = ruleset.num_players - 1
        assert sum(points) == 120
        assert sum(deltas) == 0
        return HandResult(
            hand_number=hand.hand_number,
            kind="leaster",
            picker_seat=None,
            partner_seat=None,
            called_card=None,
            deltas=deltas,
            points=points,
            buried_points=0,
            picker_team_points=None,
            multiplier=1,
            no_schneider=False,
            no_trick=False,
            leaster_winner=winner,
        )

    if hand.picker_seat is None:
        raise ValueError("Picker hand ended without a picker")

    picker_team = {hand.picker_seat}
    if hand.partner_seat is not None:
        picker_team.add(hand.partner_seat)
    buried_points = sum(card_points(card) for card in hand.buried)
    picker_points = sum(points[seat] for seat in picker_team) + buried_points
    opponent_points = 120 - picker_points
    picker_won = picker_points >= 61
    losing_points = opponent_points if picker_won else picker_points
    winning_team = picker_team if picker_won else set(range(ruleset.num_players)) - picker_team
    winners_took_every_trick = bool(hand.trick_winners) and all(
        winner in winning_team for winner in hand.trick_winners
    )
    if winners_took_every_trick:
        multiplier = 3
    elif losing_points < SCHNEIDER_LINE:
        multiplier = 2
    else:
        multiplier = 1

    sign = 1 if picker_won else -1
    deltas = [-sign * multiplier] * ruleset.num_players
    if hand.partner_seat is None:
        deltas[hand.picker_seat] = sign * (ruleset.num_players - 1) * multiplier
    else:
        deltas[hand.picker_seat] = sign * 2 * multiplier
        deltas[hand.partner_seat] = sign * multiplier

    assert sum(points) + buried_points == 120
    assert sum(deltas) == 0
    return HandResult(
        hand_number=hand.hand_number,
        kind="picker_win" if picker_won else "picker_loss",
        picker_seat=hand.picker_seat,
        partner_seat=hand.partner_seat,
        called_card=hand.called_card,
        deltas=deltas,
        points=points,
        buried_points=buried_points,
        picker_team_points=picker_points,
        multiplier=multiplier,
        no_schneider=multiplier >= 2,
        no_trick=multiplier == 3,
    )
