"""
Helpers for importing REAL repo modules whose third-party dependencies are not installed on a dev machine
(httpx, pydantic-settings, ...): stand-ins are put into sys.modules for the length of a `with` block, the
repo modules are imported fresh against them, and everything is put back afterwards.

    with stubbed({"httpx": make_httpx(), "app.config": make_config(deepinfra_api_key="k")},
                 fresh=("app.services.http_pool", "app.services.llm")):
        from app.services import llm
        ...

Not a test file: the runner ignores it.
"""

import contextlib
import sys
import types

_MISSING = object()


@contextlib.contextmanager
def stubbed(stubs: dict, fresh: tuple = ()):
    """Install `stubs` (name -> module) and forget cached copies of the `fresh` repo modules, then restore."""
    names = list(stubs) + [n for n in fresh if n not in stubs]
    saved = {name: sys.modules.get(name, _MISSING) for name in names}
    try:
        for name in fresh:
            sys.modules.pop(name, None)
        sys.modules.update(stubs)
        yield
    finally:
        for name in names:
            before = saved[name]
            if before is _MISSING:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = before
            parent_name, _, child = name.rpartition(".")
            parent = sys.modules.get(parent_name)
            if parent is not None and child:  # keep `from package import module` consistent too
                if before is _MISSING:
                    parent.__dict__.pop(child, None)
                else:
                    setattr(parent, child, before)


def make_module(name: str, **attributes) -> types.ModuleType:
    module = types.ModuleType(name)
    for key, value in attributes.items():
        setattr(module, key, value)
    return module


def make_httpx() -> types.ModuleType:
    """The parts of httpx that llm.py and http_pool.py touch."""

    class HTTPError(Exception):
        pass

    class TimeoutException(HTTPError):
        pass

    class ReadTimeout(TimeoutException):
        pass

    class HTTPStatusError(HTTPError):
        def __init__(self, message="", response=None):
            super().__init__(message)
            self.response = response

    class AsyncClient:
        is_closed = False

        def __init__(self, *args, **kwargs):
            pass

    return make_module(
        "httpx",
        HTTPError=HTTPError, TimeoutException=TimeoutException, ReadTimeout=ReadTimeout,
        HTTPStatusError=HTTPStatusError, AsyncClient=AsyncClient,
        Timeout=lambda *a, **k: None, Limits=lambda *a, **k: None,
    )


def make_config(**settings) -> types.ModuleType:
    """A stand-in for app.config with a `settings` object holding the given values."""
    defaults = dict(
        deepinfra_api_base="https://api.example.test/v1",
        deepinfra_api_key="test-key",
        query_llm_model="Qwen/Qwen3.6-35B-A3B",
        query_llm_fallback_model="google/gemma-4-26B-A4B-it",
    )
    defaults.update(settings)
    return make_module("app.config", settings=types.SimpleNamespace(**defaults))
