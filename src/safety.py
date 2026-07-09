"""Signal transition safety guards.

Enforces the one rule that must never be violated: the set of green lanes may
never change in a single jump. Every change of right-of-way goes
green -> yellow -> all-red -> next green.

State strings follow SUMO conventions: one character per controlled link,
'G'/'g' = green, 'y' = yellow, 'r' = red.
"""

from __future__ import annotations

from dataclasses import dataclass

from src import config

GREEN_CHARS = frozenset("Gg")


def yellow_state_for(state: str) -> str:
    """Return the state with every green link turned yellow (reds unchanged)."""
    return "".join("y" if ch in GREEN_CHARS else ch for ch in state)


def all_red_state(n_links: int) -> str:
    """An all-red state string for a TLS with `n_links` controlled links."""
    return "r" * n_links


def is_safe_switch(old_state: str, new_state: str) -> bool:
    """True if applying `new_state` directly after `old_state` is safe.

    A direct switch is unsafe when any link that was NOT green becomes green
    while some other link is simultaneously dropping green — i.e. right-of-way
    moves in one jump. Staying in the same state, or moving green->yellow,
    yellow->red, red->red is always safe.
    """
    if len(old_state) != len(new_state):
        return False
    gains_green = any(
        n in GREEN_CHARS and o not in GREEN_CHARS
        for o, n in zip(old_state, new_state)
    )
    drops_green = any(
        o in GREEN_CHARS and n not in GREEN_CHARS
        for o, n in zip(old_state, new_state)
    )
    return not (gains_green and drops_green)


@dataclass(frozen=True)
class TransitionStep:
    """One timed step of a signal transition. `duration_sec` is in seconds."""

    state: str
    duration_sec: float


def safe_transition(
    old_state: str,
    new_state: str,
    green_duration_sec: float,
    yellow_sec: float = config.YELLOW_SEC,
    all_red_sec: float = config.ALL_RED_SEC,
) -> list[TransitionStep]:
    """Build the timed step sequence that safely moves a TLS between states.

    Returns [(yellow, YELLOW_SEC), (all-red, ALL_RED_SEC), (new, green_duration_sec)]
    when right-of-way changes, or just [(new, green_duration_sec)] when the
    target equals the current state. Every consecutive pair in the returned
    sequence satisfies `is_safe_switch`.
    """
    if old_state == new_state:
        return [TransitionStep(new_state, green_duration_sec)]
    return [
        TransitionStep(yellow_state_for(old_state), yellow_sec),
        TransitionStep(all_red_state(len(old_state)), all_red_sec),
        TransitionStep(new_state, green_duration_sec),
    ]
