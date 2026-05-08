from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter


@dataclass
class UsageLedger:
    prompt_tokens_estimated: int = 0
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    cached_input_tokens: int = 0

    def as_dict(self) -> dict:
        return asdict(self)


class Timer:
    def __init__(self) -> None:
        self.start = perf_counter()

    def elapsed_ms(self) -> int:
        return round((perf_counter() - self.start) * 1000)


def usage_from_openai(response: object, prompt_estimate: int) -> UsageLedger:
    usage = getattr(response, "usage", None)
    if usage is None:
        return UsageLedger(prompt_tokens_estimated=prompt_estimate)
    input_tokens = int(getattr(usage, "input_tokens", 0) or 0)
    output_tokens = int(getattr(usage, "output_tokens", 0) or 0)
    total_tokens = int(getattr(usage, "total_tokens", 0) or input_tokens + output_tokens)
    cached_input_tokens = 0
    input_details = getattr(usage, "input_tokens_details", None)
    if input_details is not None:
        cached_input_tokens = int(getattr(input_details, "cached_tokens", 0) or 0)
    return UsageLedger(
        prompt_tokens_estimated=prompt_estimate,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        total_tokens=total_tokens,
        cached_input_tokens=cached_input_tokens,
    )
