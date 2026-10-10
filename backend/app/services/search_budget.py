"""
Run query understanding and the first embedding at the same time, and wait for the model only up to a
time budget. Standard library only (asyncio), so the timing behaviour is tested with real asyncio.

Search needs the embedding of the whole query no matter what, so it starts together with the model
call. When the embedding is done, search waits for the model only for what is left of the budget
(counted from the start of both); after that it goes on with the rule-based attributes, so a slow or
saturated model can add at most `budget_seconds` and never more. The model call is NOT cancelled when
it is late: it finishes in the background and fills the query-understanding cache, so the next
identical query gets the full answer at once.

Numbers behind the default budget (24 calls of the production prompt on the server, 2026-10-09):
median 1.77 s, 83% within 2.0 s, 96% within 2.3 s, one outlier at 3.8 s.
"""

from __future__ import annotations

import asyncio
import logging
import time
from dataclasses import dataclass
from typing import Any, Awaitable, Callable, Dict, List, Optional, Sequence, Set

logger = logging.getLogger(__name__)

# Late model calls keep running after the request that started them; hold a reference so they are not
# garbage-collected half way, and drop it when they finish.
_background: Set[asyncio.Future] = set()


@dataclass
class Understood:
    embedding: Any            # the first embedding, or the exception it raised
    intent: Any               # the QueryIntent, or None when the model was late or failed
    outcome: str              # "answered" | "late" | "failed"
    embed_ms: int             # how long the embedding took
    waited_ms: int            # how long search waited for the model after the embedding was done


def _detach(task: asyncio.Future) -> None:
    _background.add(task)

    def finished(done: asyncio.Future) -> None:
        _background.discard(done)
        if not done.cancelled():
            done.exception()  # mark retrieved: a late failure must not warn "exception was never retrieved"

    task.add_done_callback(finished)


async def understand_within_budget(
    embed_coro: Awaitable[Any],
    qu_coro: Awaitable[Any],
    budget_seconds: float,
    *,
    clock: Callable[[], float] = time.monotonic,
) -> Understood:
    start = clock()
    embed_task = asyncio.ensure_future(embed_coro)
    qu_task = asyncio.ensure_future(qu_coro)
    embed_done = start
    try:
        try:
            embedding: Any = await embed_task
        except asyncio.CancelledError:
            raise
        except Exception as exc:  # a failed embedding must not hide the model's answer
            embedding = exc
        embed_done = clock()
        remaining = budget_seconds - (embed_done - start)
        if not qu_task.done() and remaining > 0:
            await asyncio.wait({qu_task}, timeout=remaining)
    except asyncio.CancelledError:  # the request went away: stop both
        embed_task.cancel()
        qu_task.cancel()
        raise

    embed_ms = int((embed_done - start) * 1000)
    waited_ms = int((clock() - embed_done) * 1000)
    if qu_task.done():
        if qu_task.cancelled():
            return Understood(embedding, None, "failed", embed_ms, waited_ms)
        error = qu_task.exception()
        if error is not None:
            logger.warning("[QU BUDGET] query understanding failed: %r", error)
            return Understood(embedding, None, "failed", embed_ms, waited_ms)
        return Understood(embedding, qu_task.result(), "answered", embed_ms, waited_ms)

    _detach(qu_task)
    return Understood(embedding, None, "late", embed_ms, waited_ms)


def counter_name(outcome: str, intent: Any = None) -> str:
    """
    The Redis counter (HGETALL lamba:stats:search:<date>) for one search: "answered" is split by where the
    answer came from, because an instant rules-only fallback (a rejected, failed or unneeded model call) used
    to be counted as answered just like a real model answer:
    budget_answered_model | budget_answered_cache | budget_answered_rules | budget_late | budget_failed
    """
    source = getattr(intent, "source", None)
    if outcome == "answered" and source:
        return f"budget_answered_{source}"
    return f"budget_{outcome}"


async def assemble_embeddings(
    texts: Sequence[str],
    known: Dict[str, Any],
    embed_batch: Callable[[List[str]], Awaitable[Sequence[Any]]],
) -> List[Any]:
    """
    The vector of every text in `texts`, in that order, embedding only the texts not in `known` (one batch
    call). A text without a vector is left out, as before.
    """
    vectors = dict(known)
    missing = [text for text in texts if text not in vectors]
    if missing:
        vectors.update(zip(missing, await embed_batch(missing)))
    return [vectors[text] for text in texts if text in vectors]
