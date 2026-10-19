"""Load the generic Ops logger; no application-owned logging configuration."""
from functools import lru_cache
import importlib.util
from pathlib import Path


_LOGGING_MODULE = Path("/run/ops/shared-logging/python/ops_logging.py")


@lru_cache(maxsize=1)
def ops_logger():
    spec = importlib.util.spec_from_file_location("planora_ops_logging", _LOGGING_MODULE)
    if spec is None or spec.loader is None:
        raise RuntimeError("Ops logging is unavailable.")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module.create_logger()
