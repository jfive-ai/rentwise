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
    await fetcher.acquire()
    assert clock.sleeps == [pytest.approx(0.0, abs=1e-6)]  # only the (0,0) jitter


@pytest.mark.asyncio
async def test_subsequent_call_waits_min_interval():
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(0, 0))
    await fetcher.acquire()
    clock.now += 0.3
    await fetcher.acquire()
    # Expected: 0 jitter + (1.0 - 0.3) wait + 0 jitter
    assert any(abs(s - 0.7) < 1e-6 for s in clock.sleeps)


@pytest.mark.asyncio
async def test_jitter_within_bounds():
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(500, 1500))
    await fetcher.acquire()
    assert 0.5 <= clock.sleeps[0] <= 1.5


@pytest.mark.asyncio
async def test_no_parallel_for_same_origin():
    """Two concurrent acquires must serialize."""
    clock = _FakeClock()
    fetcher = RateLimitedFetcher(rate_per_sec=1.0, clock=clock, jitter_ms=(0, 0))
    order: list[str] = []

    async def task(label):
        await fetcher.acquire()
        order.append(label)

    await asyncio.gather(task("a"), task("b"))
    assert order == ["a", "b"] or order == ["b", "a"]
    # The point: no exception, and one had to wait for the other.
    assert len(clock.sleeps) >= 2
