from dataclasses import asdict, dataclass, fields


@dataclass(frozen=True)
class RuleSet:
    num_players: int = 5
    cards_per_player: int = 6
    blind_size: int = 2
    partner_method: str = "called_ace"
    leaster_enabled: bool = True
    leaster_blind: str = "last_trick"
    # Redeal when any player is dealt no trump and no ace — a hand that cannot take a trick.
    # Off only for tests that need to observe the raw deal.
    rerack_enabled: bool = True

    def __post_init__(self) -> None:
        if self.num_players * self.cards_per_player + self.blind_size != 32:
            raise ValueError("RuleSet deal geometry must consume the 32-card deck")
        if self.partner_method not in {"called_ace", "jack_of_diamonds", "none"}:
            raise ValueError("Unsupported partner method")

    def to_dict(self) -> dict:
        return asdict(self)

    @classmethod
    def from_dict(cls, value: dict) -> "RuleSet":
        # Games persisted before a field was removed still carry it. Drop unknown keys rather
        # than raising — `no_callable_ace_fallback` was retired when unders were implemented,
        # and every stored online game predating that has it.
        known = {field.name for field in fields(cls)}
        return cls(**{key: item for key, item in value.items() if key in known})


RULESET_PRESETS: dict[str, RuleSet] = {
    "five_handed_called_ace": RuleSet(),
}
