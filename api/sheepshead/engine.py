import copy
import itertools
import random

from .cards import Card, Rank, Suit, build_deck, card_points, effective_suit, is_trump
from .rules import RuleSet
from .scoring import score_hand, trick_winner
from .state import (
    Action,
    BuryAction,
    CallAction,
    CallUnderAction,
    Event,
    GameState,
    HandState,
    PassAction,
    Phase,
    PickAction,
    PlayAction,
    Seat,
    UnburyAction,
)


class IllegalActionError(ValueError):
    pass


# A rerack is rare — roughly one deal in forty — so the loop effectively never runs twice.
# The cap only exists to keep the function total.
_MAX_DEAL_ATTEMPTS = 100
# Arbitrary co-prime stride, so each redeal is a different shuffle but still reproducible.
_DEAL_ATTEMPT_STRIDE = 7_919


def is_rerack_hand(cards, ruleset: RuleSet) -> bool:
    """Whether this hand forces a redeal: no trump and no ace.

    Such a hand cannot take a trick by any line of play, so the deal is thrown out and everyone
    is dealt again. Only fail aces need testing — the ace of diamonds is trump, so a hand with
    no trump cannot be holding it.
    """
    return not any(
        is_trump(card, ruleset) or card.rank is Rank.ACE for card in cards
    )


def _deal_hand(state: GameState, dealer_seat: int, hand_number: int) -> HandState:
    rules = state.ruleset
    first = (dealer_seat + 1) % rules.num_players
    hands: list[list[Card]] = []
    blind: list[Card] = []

    for attempt in range(_MAX_DEAL_ATTEMPTS):
        deck = build_deck(rules)
        # attempt 0 reproduces the original seed exactly, so deals that never rerack are
        # unchanged by this rule.
        random.Random(
            state.rng_seed + hand_number * 1_000_003 + attempt * _DEAL_ATTEMPT_STRIDE
        ).shuffle(deck)
        hands = [[] for _ in range(rules.num_players)]
        cursor = 0
        for _ in range(rules.cards_per_player):
            for offset in range(rules.num_players):
                hands[(first + offset) % rules.num_players].append(deck[cursor])
                cursor += 1
        blind = deck[cursor : cursor + rules.blind_size]
        if not rules.rerack_enabled:
            break
        if not any(is_rerack_hand(hand, rules) for hand in hands):
            break
    # Falling out of the loop without a clean deal is not reachable in practice; the last
    # attempt stands rather than raising, since a failed deal would strand a live game.

    return HandState(
        hand_number=hand_number,
        dealer_seat=dealer_seat,
        hands=hands,
        blind=blind,
        buried=[],
        phase=Phase.PICKING,
        turn_seat=first,
        passes=[],
        picker_seat=None,
        called_card=None,
        partner_seat=None,
        partner_revealed=False,
        is_leaster=False,
        current_trick=[],
        trick_leader=first,
        taken=[[] for _ in range(rules.num_players)],
        last_trick_winner=None,
    )


def create_game(ruleset: RuleSet, seats: list[Seat], rng_seed: int) -> GameState:
    if len(seats) != ruleset.num_players:
        raise ValueError("Seat count must match the ruleset")
    if [seat.index for seat in seats] != list(range(ruleset.num_players)):
        raise ValueError("Seat indexes must be contiguous")
    placeholder = GameState(ruleset, seats, [0] * ruleset.num_players, None, [], rng_seed)  # type: ignore[arg-type]
    placeholder.hand = _deal_hand(placeholder, dealer_seat=0, hand_number=1)
    return placeholder


_FAIL_SUITS = (Suit.CLUBS, Suit.SPADES, Suit.HEARTS)
# Ace first; a ten only once no ace is callable, a king only once no ten is either.
_CALL_LADDER = (Rank.ACE, Rank.TEN, Rank.KING)


def _led_suit(state: GameState) -> str | None:
    """Effective suit of the open trick, honouring an under that stands in for the called suit."""
    hand = state.hand
    if not hand.current_trick:
        return None
    leader, card = hand.current_trick[0]
    if (
        hand.under_card is not None
        and card == hand.under_card
        and leader == hand.picker_seat
        and hand.called_card is not None
    ):
        return hand.called_card.suit.value
    return effective_suit(card, state.ruleset)


def _other_hands(hand_state: HandState, seat: int) -> list[list[Card]]:
    """Hands other than `seat`'s. Buried cards are in neither, which is what makes a buried
    ace correctly uncallable."""
    return [cards for index, cards in enumerate(hand_state.hands) if index != seat]


def _called_card_candidates(
    picker_hand: list[Card], others: list[list[Card]], ruleset: RuleSet
) -> list[Card]:
    """Partner cards the picker could name, one per suit at most.

    Walks the rank ladder globally rather than per suit: fall through to the next rank only
    when no suit offers a candidate at all, whatever the reason — the picker holding every ace,
    or the missing ones being buried.
    """
    held = set(picker_hand)
    for rank in _CALL_LADDER:
        candidates = [
            Card(suit, rank)
            for suit in _FAIL_SUITS
            if Card(suit, rank) not in held
            and any(Card(suit, rank) in cards for cards in others)
        ]
        if candidates:
            return candidates
    return []


def _ordinary_call_candidates(
    picker_hand: list[Card], others: list[list[Card]], ruleset: RuleSet
) -> list[Card]:
    """Candidates the picker can follow the suit of — the calls that need no under."""
    return [
        candidate
        for candidate in _called_card_candidates(picker_hand, others, ruleset)
        if any(effective_suit(card, ruleset) == candidate.suit.value for card in picker_hand)
    ]


def _bury_actions(state: GameState, seat: int) -> list[Action]:
    """Every combination. Burying is unrestricted; the *call* is what adapts to what is left.

    An earlier version filtered these to forbid burying into an under. That put the restriction
    in the wrong place: the picker is entitled to bury whatever they like, and the consequence
    is simply that they may be left with nothing to call and have to go alone. They can also
    change their mind (`UnburyAction`) until they commit to a call.
    """
    return [
        BuryAction(tuple(cards))
        for cards in itertools.combinations(state.hand.hands[seat], state.ruleset.blind_size)
    ]


def _under_is_legitimate(state: GameState, seat: int) -> bool:
    """Whether this picker genuinely never had a suit to call, rather than burying one away.

    Judged on the **pre-bury** hand — what remains plus what was buried — because that is what
    decides whether the option ever existed. The rule: an under is theirs to take only if they
    hold the ace of every fail suit they hold anything in. Holding a club without the ace of
    clubs means the ace is in somebody else's hand and they could have kept a club to call it.
    """
    before = list(state.hand.hands[seat]) + list(state.hand.buried)
    for suit in _FAIL_SUITS:
        holds_suit = any(effective_suit(card, state.ruleset) == suit.value for card in before)
        if holds_suit and Card(suit, Rank.ACE) not in before:
            return False
    return True


def _call_actions(state: GameState) -> list[Action]:
    """Ordinary calls where the picker can follow the suit; unders only when none can.

    An under is needed exactly when the picker holds no fail card of the suit being called.
    That single condition covers both source cases ("all fail cards are aces" and "no fail at
    all") and shows a called ten never needs one: calling a ten requires holding all three fail
    aces, which guarantees a card in every fail suit.

    Going alone is always available. When nothing is followable the under is offered only if it
    was never avoidable (`_under_is_legitimate`); a picker who buried their callable suit away
    is left with alone as their only option, and may unbury and try again instead.
    """
    hand_state = state.hand
    seat = hand_state.picker_seat
    hand = hand_state.hands[seat]  # type: ignore[index]
    others = _other_hands(hand_state, seat)  # type: ignore[arg-type]

    actions: list[Action] = [CallAction(None)]
    ordinary = _ordinary_call_candidates(hand, others, state.ruleset)
    if ordinary:
        actions.extend(CallAction(card) for card in ordinary)
        return actions
    if _under_is_legitimate(state, seat):  # type: ignore[arg-type]
        for candidate in _called_card_candidates(hand, others, state.ruleset):
            actions.extend(CallUnderAction(candidate, under) for under in hand)
    return actions


def _play_actions(state: GameState, seat: int) -> list[Action]:
    hand_state = state.hand
    cards = list(hand_state.hands[seat])
    led = _led_suit(state)
    if led is not None:
        following = [card for card in cards if effective_suit(card, state.ruleset) == led]
        legal_cards = following or cards
    else:
        legal_cards = cards

    called = hand_state.called_card
    under = hand_state.under_card
    if (
        under is not None
        and called is not None
        and seat == hand_state.picker_seat
        and under in cards
    ):
        # The under stands in for the called suit, so it is the picker's only legal follower
        # when that suit is led — and is otherwise held back, exactly like the last called-suit
        # card in the ordinary case. Never strip it when it is the only card left.
        if led == called.suit.value:
            return [PlayAction(under)]
        remaining = [card for card in legal_cards if card != under]
        if remaining:
            legal_cards = remaining
    elif (
        state.ruleset.partner_method == "called_ace"
        and called is not None
        and seat == hand_state.partner_seat
        and called in cards
    ):
        if led is not None:
            # Uses the resolved led suit, so an under leading also obliges the partner's ace.
            if led == called.suit.value:
                legal_cards = [called]
            elif called in legal_cards and len(legal_cards) > 1:
                legal_cards = [card for card in legal_cards if card != called]
        else:
            # The partner cannot lead another card of the called suit; the ace itself is legal.
            filtered = [
                card
                for card in legal_cards
                if card == called or effective_suit(card, state.ruleset) != called.suit.value
            ]
            if filtered:
                legal_cards = filtered
    elif (
        state.ruleset.partner_method == "called_ace"
        and called is not None
        and seat == hand_state.picker_seat
        and not hand_state.called_suit_led
        and hand_state.current_trick
    ):
        # The picker may fail off the called suit while holding several of them, but must keep
        # the last one back for the trick where that suit is finally led. Leading the called
        # suit themselves is fine — that is the lead, and it sets called_suit_led.
        held = [
            card for card in cards if effective_suit(card, state.ruleset) == called.suit.value
        ]
        if len(held) == 1:
            remaining = [card for card in legal_cards if card != held[0]]
            # Never strip the only playable card; follow-suit obligations still come first.
            if remaining:
                legal_cards = remaining
    return [PlayAction(card) for card in legal_cards]


def legal_actions(state: GameState, seat: int) -> list[Action]:
    hand = state.hand
    if seat < 0 or seat >= state.ruleset.num_players or hand.turn_seat != seat:
        return []
    if hand.phase == Phase.PICKING:
        return [PickAction(), PassAction()]
    if hand.phase == Phase.BURYING:
        if seat != hand.picker_seat:
            return []
        return _bury_actions(state, seat)
    if hand.phase == Phase.CALLING:
        if seat != hand.picker_seat:
            return []
        if state.ruleset.partner_method == "called_ace":
            actions = _call_actions(state)
        else:
            actions = [CallAction(None)]
        # Only a human changes their mind — see UnburyAction.
        if state.seats[seat].is_human:
            actions.append(UnburyAction())
        return actions
    if hand.phase == Phase.PLAYING:
        return _play_actions(state, seat)
    return []


def apply_action(state: GameState, seat: int, action: Action) -> tuple[GameState, list[Event]]:
    legal = legal_actions(state, seat)
    if action not in legal:
        raise IllegalActionError(
            f"{action.type!r} is not legal for seat {seat} during {state.hand.phase.value}"
        )
    next_state = copy.deepcopy(state)
    hand = next_state.hand
    events: list[Event] = []

    if isinstance(action, PickAction):
        hand.picker_seat = seat
        hand.hands[seat].extend(hand.blind)
        hand.blind = []
        hand.phase = Phase.BURYING
        hand.turn_seat = seat
        events.append(Event("picked", seat=seat))
    elif isinstance(action, PassAction):
        hand.passes.append(seat)
        events.append(Event("passed", seat=seat))
        if len(hand.passes) == next_state.ruleset.num_players:
            if not next_state.ruleset.leaster_enabled:
                raise IllegalActionError("All-pass handling is not configured")
            hand.is_leaster = True
            hand.phase = Phase.PLAYING
            hand.trick_leader = (hand.dealer_seat + 1) % next_state.ruleset.num_players
            hand.turn_seat = hand.trick_leader
        else:
            hand.turn_seat = (seat + 1) % next_state.ruleset.num_players
    elif isinstance(action, BuryAction):
        for card in action.cards:
            hand.hands[seat].remove(card)
        hand.buried = list(action.cards)
        hand.phase = Phase.CALLING
        hand.turn_seat = seat
        events.append(Event("buried", seat=seat))
    elif isinstance(action, UnburyAction):
        hand.hands[seat].extend(hand.buried)
        hand.buried = []
        hand.phase = Phase.BURYING
        hand.turn_seat = seat
        events.append(Event("unburied", seat=seat))
    elif isinstance(action, (CallAction, CallUnderAction)):
        hand.called_card = action.card
        if isinstance(action, CallUnderAction):
            hand.under_card = action.under
        if action.card is not None:
            hand.partner_seat = next(
                index
                for index, cards in enumerate(hand.hands)
                if action.card in cards
            )
        hand.phase = Phase.PLAYING
        hand.trick_leader = (hand.dealer_seat + 1) % next_state.ruleset.num_players
        hand.turn_seat = hand.trick_leader
        # The under stays out of the event: it is face down, and events are public.
        events.append(Event("called", seat=seat, card=action.card))
    elif isinstance(action, PlayAction):
        hand.hands[seat].remove(action.card)
        hand.current_trick.append((seat, action.card))
        events.append(Event("card_played", seat=seat, card=action.card))
        if (
            len(hand.current_trick) == 1
            and hand.called_card is not None
            and _led_suit(next_state) == hand.called_card.suit.value
        ):
            # An under leading counts: it stands in for the called suit.
            hand.called_suit_led = True
        if action.card == hand.called_card and seat == hand.partner_seat and not hand.partner_revealed:
            hand.partner_revealed = True
            events.append(Event("partner_revealed", seat=seat))
        if len(hand.current_trick) < next_state.ruleset.num_players:
            hand.turn_seat = (seat + 1) % next_state.ruleset.num_players
        else:
            winner = trick_winner(
                hand.current_trick,
                next_state.ruleset,
                ineligible=hand.under_card,
                led_suit=_led_suit(next_state),
            )
            trick_cards = [card for _, card in hand.current_trick]
            trick_points = sum(card_points(card) for card in trick_cards)
            hand.taken[winner].extend(trick_cards)
            hand.last_trick_winner = winner
            hand.trick_winners.append(winner)
            # Copy before the reset below; this must not alias current_trick.
            hand.completed_tricks.append(list(hand.current_trick))
            hand.current_trick = []
            hand.trick_leader = winner
            hand.turn_seat = winner
            events.append(Event("trick_won", seat=winner, points=trick_points))

            if all(not cards for cards in hand.hands):
                result = score_hand(hand, next_state.ruleset)
                next_state.hand_history.append(result)
                next_state.scores = [
                    score + delta for score, delta in zip(next_state.scores, result.deltas)
                ]
                events.append(Event("hand_scored", result=result))
                next_hand_number = hand.hand_number + 1
                next_dealer = (hand.dealer_seat + 1) % next_state.ruleset.num_players
                next_state.hand = _deal_hand(next_state, next_dealer, next_hand_number)
                events.append(Event("new_hand", hand_number=next_hand_number))

    return next_state, events
