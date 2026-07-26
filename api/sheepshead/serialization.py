from dataclasses import asdict

from .cards import Card, card_points, sort_key
from .engine import legal_actions
from .rules import RuleSet
from .state import (
    Action,
    BuryAction,
    CallAction,
    CallUnderAction,
    Event,
    GameState,
    HandResult,
    HandState,
    PassAction,
    PickAction,
    PlayAction,
    Seat,
    UnburyAction,
)


def card_to_json(card: Card | None) -> str | None:
    return str(card) if card is not None else None


def action_to_dict(action: Action) -> dict:
    if isinstance(action, (PickAction, PassAction, UnburyAction)):
        return {"type": action.type}
    if isinstance(action, BuryAction):
        return {"type": action.type, "cards": [str(card) for card in action.cards]}
    if isinstance(action, CallUnderAction):
        return {"type": action.type, "card": str(action.card), "under": str(action.under)}
    if isinstance(action, CallAction):
        return {"type": action.type, "card": card_to_json(action.card)}
    if isinstance(action, PlayAction):
        return {"type": action.type, "card": str(action.card)}
    raise TypeError("Unknown action")


def action_from_dict(value: dict) -> Action:
    kind = value.get("type")
    try:
        if kind == "pick":
            return PickAction()
        if kind == "pass":
            return PassAction()
        if kind == "unbury":
            return UnburyAction()
        if kind == "bury":
            cards = value.get("cards")
            if not isinstance(cards, list):
                raise ValueError("Bury action requires a cards list")
            return BuryAction(tuple(Card.parse(card) for card in cards))
        if kind == "call":
            card = value.get("card")
            return CallAction(Card.parse(card) if card is not None else None)
        if kind == "call_under":
            return CallUnderAction(Card.parse(value["card"]), Card.parse(value["under"]))
        if kind == "play":
            return PlayAction(Card.parse(value["card"]))
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError(f"Invalid {kind or 'unknown'} action: {exc}") from exc
    raise ValueError(f"Unknown action type: {kind!r}")


def result_to_dict(result: HandResult) -> dict:
    data = asdict(result)
    data["called_card"] = card_to_json(result.called_card)
    return data


def event_to_dict(event: Event) -> dict:
    data: dict = {"type": event.type}
    if event.seat is not None:
        data["seat"] = event.seat
    if event.card is not None:
        data["card"] = str(event.card)
    if event.points is not None:
        data["points"] = event.points
    if event.hand_number is not None:
        data["hand_number"] = event.hand_number
    if event.result is not None:
        data["result"] = result_to_dict(event.result)
    return data


def full_state_to_dict(state: GameState) -> dict:
    hand = state.hand
    return {
        "ruleset": state.ruleset.to_dict(),
        "seats": [asdict(seat) for seat in state.seats],
        "scores": state.scores,
        "hand": {
            "hand_number": hand.hand_number,
            "dealer_seat": hand.dealer_seat,
            "hands": [[str(card) for card in cards] for cards in hand.hands],
            "blind": [str(card) for card in hand.blind],
            "buried": [str(card) for card in hand.buried],
            "phase": hand.phase.value,
            "turn_seat": hand.turn_seat,
            "passes": hand.passes,
            "picker_seat": hand.picker_seat,
            "called_card": card_to_json(hand.called_card),
            "partner_seat": hand.partner_seat,
            "partner_revealed": hand.partner_revealed,
            "is_leaster": hand.is_leaster,
            "current_trick": [[seat, str(card)] for seat, card in hand.current_trick],
            "trick_leader": hand.trick_leader,
            "taken": [[str(card) for card in cards] for cards in hand.taken],
            "last_trick_winner": hand.last_trick_winner,
            "trick_winners": hand.trick_winners,
            "called_suit_led": hand.called_suit_led,
            "completed_tricks": [
                [[seat, str(card)] for seat, card in trick] for trick in hand.completed_tricks
            ],
            "under_card": card_to_json(hand.under_card),
        },
        "hand_history": [result_to_dict(result) for result in state.hand_history],
        "rng_seed": state.rng_seed,
    }


def _result_from_dict(value: dict) -> HandResult:
    return HandResult(
        **{
            **value,
            "called_card": Card.parse(value["called_card"]) if value.get("called_card") else None,
        }
    )


def full_state_from_dict(value: dict) -> GameState:
    from .state import Phase

    hand = value["hand"]
    return GameState(
        ruleset=RuleSet.from_dict(value["ruleset"]),
        seats=[Seat(**seat) for seat in value["seats"]],
        scores=list(value["scores"]),
        hand=HandState(
            hand_number=hand["hand_number"],
            dealer_seat=hand["dealer_seat"],
            hands=[[Card.parse(card) for card in cards] for cards in hand["hands"]],
            blind=[Card.parse(card) for card in hand["blind"]],
            buried=[Card.parse(card) for card in hand["buried"]],
            phase=Phase(hand["phase"]),
            turn_seat=hand["turn_seat"],
            passes=list(hand["passes"]),
            picker_seat=hand["picker_seat"],
            called_card=Card.parse(hand["called_card"]) if hand.get("called_card") else None,
            partner_seat=hand["partner_seat"],
            partner_revealed=hand["partner_revealed"],
            is_leaster=hand["is_leaster"],
            current_trick=[(seat, Card.parse(card)) for seat, card in hand["current_trick"]],
            trick_leader=hand["trick_leader"],
            taken=[[Card.parse(card) for card in cards] for cards in hand["taken"]],
            last_trick_winner=hand["last_trick_winner"],
            trick_winners=list(hand.get("trick_winners", [])),
            # Snapshots written before this flag existed fall back to partner_revealed: the ace
            # can only have been played on a lead of its own suit.
            called_suit_led=bool(hand.get("called_suit_led", hand.get("partner_revealed", False))),
            # Snapshots written before this field existed decode to []. An AI resuming such a
            # hand plays the rest of it without history; the next hand is whole. Seat attribution
            # cannot be reconstructed from `taken`, so there is nothing better to do here.
            completed_tricks=[
                [(seat, Card.parse(card)) for seat, card in trick]
                for trick in hand.get("completed_tricks", [])
            ],
            under_card=Card.parse(hand["under_card"]) if hand.get("under_card") else None,
        ),
        hand_history=[_result_from_dict(result) for result in value["hand_history"]],
        rng_seed=value["rng_seed"],
    )


def _may_see_under(hand: HandState, seat: int) -> bool:
    """The picker always; otherwise only whoever won the trick the under fell on.

    While the under sits in the open trick nobody has won it yet, so only the picker sees it.
    """
    if hand.under_card is None:
        return False
    if seat == hand.picker_seat:
        return True
    for index, trick in enumerate(hand.completed_tricks):
        if any(card == hand.under_card for _, card in trick):
            return index < len(hand.trick_winners) and hand.trick_winners[index] == seat
    return False


def _play_json(hand: HandState, trick_seat: int, card: Card, may_see_under: bool) -> dict:
    """One play, with the under masked for seats not entitled to its identity.

    `under: true` is public either way — everyone at the table watches a card go down face
    first — and it is what lets a viewer exclude the card from trick-winner logic and from
    void inference without knowing what it is.
    """
    is_under = (
        hand.under_card is not None
        and card == hand.under_card
        and trick_seat == hand.picker_seat
    )
    if not is_under:
        return {"seat": trick_seat, "card": str(card)}
    return {
        "seat": trick_seat,
        "card": str(card) if may_see_under else None,
        "under": True,
    }


def _event_json(hand: HandState, event: Event, may_see_under: bool) -> dict:
    """Events are per-seat too: a card_played event would otherwise announce the under.

    seat_view embeds the events from the actions just applied, so masking only the trick
    entries is not enough — the event carries the same card.
    """
    data = event_to_dict(event)
    if (
        event.type == "card_played"
        and hand.under_card is not None
        and not may_see_under
        and event.seat == hand.picker_seat
        and event.card == hand.under_card
    ):
        data["card"] = None
        data["under"] = True
    return data


def seat_view(
    state: GameState,
    seat: int,
    *,
    version: int | None = None,
    events: list[Event] | None = None,
) -> dict:
    hand = state.hand
    own_hand = sorted(hand.hands[seat], key=lambda card: sort_key(card, state.ruleset), reverse=True)
    may_see_under = _may_see_under(hand, seat)
    public_seats = []
    for player_seat in state.seats:
        public_seats.append(
            {
                "index": player_seat.index,
                "name": player_seat.name,
                "is_human": player_seat.is_human,
                # The AI's playstyle key. Public by design — the player is meant to see who
                # they are up against and adapt. None for the human seat.
                "ai_strategy": player_seat.ai_strategy,
                "card_count": len(hand.hands[player_seat.index]),
                "trick_count": len(hand.taken[player_seat.index]) // state.ruleset.num_players,
                # Public: tricks are taken face up. The blind is folded into a leaster winner's
                # total inside score_hand() only, so this cannot leak it mid-hand.
                "taken_points": sum(
                    card_points(card) for card in hand.taken[player_seat.index]
                ),
            }
        )
    view = {
        "ruleset": state.ruleset.to_dict(),
        "seat": seat,
        "seats": public_seats,
        "scores": state.scores,
        "hand_number": hand.hand_number,
        "dealer_seat": hand.dealer_seat,
        "hand": [str(card) for card in own_hand],
        "phase": hand.phase.value,
        "turn_seat": hand.turn_seat,
        "passes": hand.passes,
        "picker_seat": hand.picker_seat,
        "called_card": card_to_json(hand.called_card),
        # The picker's own bury is theirs to remember — they chose it. It stays hidden from
        # every other seat, and those points are already banked for the picker's team.
        "buried": [str(card) for card in hand.buried] if seat == hand.picker_seat else [],
        "partner_revealed": hand.partner_revealed,
        "partner_seat": hand.partner_seat if hand.partner_revealed else None,
        "is_leaster": hand.is_leaster,
        # The picker's own under, before and after it is played. Nobody else gets this field.
        "under_card": card_to_json(hand.under_card) if seat == hand.picker_seat else None,
        # ...but the *fact* of an under is public: everyone watched the card go down. Whether it
        # has since been played is derivable from the `under` flag on the trick entries.
        "under_declared": hand.under_card is not None,
        "current_trick": [
            _play_json(hand, trick_seat, card, may_see_under)
            for trick_seat, card in hand.current_trick
        ],
        "completed_tricks": [
            {
                "winner": hand.trick_winners[index],
                "plays": [
                    _play_json(hand, trick_seat, card, may_see_under)
                    for trick_seat, card in trick
                ],
            }
            for index, trick in enumerate(hand.completed_tricks)
        ],
        "legal_actions": [action_to_dict(action) for action in legal_actions(state, seat)],
        "hand_history": [result_to_dict(result) for result in state.hand_history],
        "events": [_event_json(hand, event, may_see_under) for event in (events or [])],
    }
    if version is not None:
        view["version"] = version
    return view
