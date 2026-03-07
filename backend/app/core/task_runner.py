import logging
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)

# Shared background executor for lightweight async-offload in sync routers.
_executor = ThreadPoolExecutor(max_workers=4, thread_name_prefix="bg-task")


def submit_background(task_name: str, fn, *args, **kwargs):
    def _wrapped():
        try:
            logger.info("[BG] Start task=%s", task_name)
            return fn(*args, **kwargs)
        except Exception as e:
            logger.error("[BG] Task failed: %s (%s)", task_name, e)

    return _executor.submit(_wrapped)
