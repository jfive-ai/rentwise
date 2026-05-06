import asyncio

import pytest

from rentwise.adapters.ratelimit import RateLimitedFetcher


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.sleeps: list[float] = []

    def time(self) -> float:
        return self.now

    async def sleep(self, secs: float) -> None:
        self.sleeps.append(secs)
        self.now += secs


@pytest.mark.asyncio
async def test_first_call_does_not_wait():
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(0, 0))
    async with fetcher:
        pass
    assert clock.sleeps == [pytest.approx(0.0, abs=1e-6)]  # only the (0,0) jitter


@pytest.mark.asyncio
async def test_subsequent_call_waits_min_interval():
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(0, 0))
    async with fetcher:
        pass
    clock.now += 0.3
    async with fetcher:
        pass
    # Expected: 0 jitter + (1.0 - 0.3) wait + 0 jitter
    assert any(abs(s - 0.7) < 1e-6 for s in clock.sleeps)


@pytest.mark.asyncio
async def test_jitter_within_bounds():
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(500, 1500))
    async with fetcher:
        pass
    assert 0.5 <= clock.sleeps[0] <= 1.5


@pytest.mark.asyncio
async def test_no_parallel_for_same_origin():
    """Two concurrent acquires must serialize."""
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(0, 0))
    order: list[str] = []

    async def task(label):
        async with fetcher:
            order.append(label)

    await asyncio.gather(task("a"), task("b"))
    assert order == ["a", "b"] or order == ["b", "a"]
    # The point: no exception, and one had to wait for the other.
    assert len(clock.sleeps) >= 2


@pytest.mark.asyncio
async def test_fetcher_serializes_protected_block():
    """The protected block (entered via async with) must be serialized end-to-end.
    A slow op in flight must block the next operation from even entering the
    rate-limit window — not just from finishing it.

    Regression: the previous acquire()/release-before-body design allowed
    overlapping outbound requests under latency.
    """
    import asyncio

    fetcher = RateLimitedFetcher(rate_per_sec=10.0, jitter_ms=(0, 0))
    sequence: list[str] = []

    async def op(label: str) -> None:
        async with fetcher:
            sequence.append(f"{label}_in")
            await asyncio.sleep(0.05)
            sequence.append(f"{label}_out")

    await asyncio.gather(op("a"), op("b"))

    # Whichever ran first must fully exit before the second enters.
    if sequence[0] == "a_in":
        assert sequence == ["a_in", "a_out", "b_in", "b_out"]
    else:
        assert sequence == ["b_in", "b_out", "a_in", "a_out"]
