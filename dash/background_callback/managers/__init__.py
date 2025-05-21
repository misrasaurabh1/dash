from abc import ABC
import inspect
import hashlib
import pickle
from functools import lru_cache


class BaseBackgroundCallbackManager(ABC):
    UNDEFINED = object()

    # Keep a ref to all the ref to register every callback to every manager.
    managers = []

    # Keep every function for late registering.
    functions = []

    def __init__(self, cache_by):
        # Convert cache_by to list only once if necessary
        if cache_by is not None and not isinstance(cache_by, list):
            cache_by = [cache_by]
        self.cache_by = cache_by

        # Don't lookup each time
        BaseBackgroundCallbackManager.managers.append(self)
        self.func_registry = {}

        # Local ref for hot path
        functions = self.functions
        register = self.register
        for fdetails in functions:
            register(*fdetails)

    def terminate_job(self, job):
        raise NotImplementedError

    def terminate_unhealthy_job(self, job):
        raise NotImplementedError

    def job_running(self, job):
        raise NotImplementedError

    def make_job_fn(self, fn, progress, key=None):
        raise NotImplementedError

    def call_job_fn(self, key, job_fn, args, context):
        raise NotImplementedError

    def get_progress(self, key):
        raise NotImplementedError

    def result_ready(self, key):
        raise NotImplementedError

    def get_result(self, key, job):
        raise NotImplementedError

    def get_updated_props(self, key):
        raise NotImplementedError

    def build_cache_key(self, fn, args, cache_args_to_ignore, triggered):
        # Get the function source (cached)
        fn_source = self._get_fn_source_cached(fn)

        # Normalize cache_args_to_ignore to tuple to avoid repeated isinstance
        if not isinstance(cache_args_to_ignore, (list, tuple)):
            cache_args_to_ignore = (cache_args_to_ignore,)
        else:
            cache_args_to_ignore = tuple(cache_args_to_ignore)
        args_result = args

        if cache_args_to_ignore:
            # Fast-path: don't filter if nothing to ignore
            if isinstance(args, dict):
                ignore_set = set(cache_args_to_ignore)
                args_result = {k: v for k, v in args.items() if k not in ignore_set}
            else:
                ignore_idx = set(cache_args_to_ignore)
                args_result = [arg for i, arg in enumerate(args) if i not in ignore_idx]

        hash_dict = {
            "args": args_result,
            "fn_source": fn_source,
            "triggered": triggered,
        }

        cache_by = self.cache_by
        if cache_by:
            for i, cache_item in enumerate(cache_by):
                # Caching enabled, call cache function only as needed
                hash_dict[f"cache_key_{i}"] = cache_item()

        # Use pickle for deterministic, robust byte serialization (faster than str(dict).encode)
        key_bytes = pickle.dumps(hash_dict, protocol=pickle.HIGHEST_PROTOCOL)
        return hashlib.sha256(key_bytes).hexdigest()

    def register(self, key, fn, progress):
        self.func_registry[key] = self.make_job_fn(fn, progress, key)

    @staticmethod
    def register_func(fn, progress, callback_id):
        key = BaseBackgroundCallbackManager.hash_function(fn, callback_id)
        BaseBackgroundCallbackManager.functions.append(
            (
                key,
                fn,
                progress,
            )
        )

        for manager in BaseBackgroundCallbackManager.managers:
            manager.register(key, fn, progress)

        return key

    @staticmethod
    def _make_progress_key(key):
        return key + "-progress"

    @staticmethod
    def _make_set_props_key(key):
        return f"{key}-set_props"

    @staticmethod
    def hash_function(fn, callback_id=""):
        try:
            fn_source = inspect.getsource(fn)
            fn_str = fn_source
        except OSError:  # pylint: disable=too-broad-exception
            fn_str = getattr(fn, "__name__", "")
        return hashlib.sha256(
            callback_id.encode("utf-8") + fn_str.encode("utf-8")
        ).hexdigest()

    @staticmethod
    @lru_cache(maxsize=128)
    def _get_fn_source_cached(fn):
        return inspect.getsource(fn)
