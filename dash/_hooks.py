import typing as _t

from importlib import metadata as _importlib_metadata

import typing_extensions as _tx
import flask as _f

from .exceptions import HookError
from .resources import ResourceType
from ._callback import ClientsideFuncType

if _t.TYPE_CHECKING:
    from .dash import Dash
    from .development.base_component import Component

    ComponentType = _t.TypeVar("ComponentType", bound=Component)
    LayoutType = _t.Union[ComponentType, _t.List[ComponentType]]
else:
    LayoutType = None
    ComponentType = None
    Dash = None


HookDataType = _tx.TypeVar("HookDataType")


# pylint: disable=too-few-public-methods
class _Hook(_tx.Generic[HookDataType]):
    def __init__(self, func, priority=0, final=False, data: HookDataType = None):
        self.func = func
        self.final = final
        self.data = data
        self.priority = priority

    def __call__(self, *args, **kwargs):
        return self.func(*args, **kwargs)


class _Hooks:
    def __init__(self) -> None:
        # Use lists in ns directly without copying on get
        self._ns = {
            "setup": [],
            "layout": [],
            "routes": [],
            "error": [],
            "callback": [],
            "index": [],
            "custom_data": [],
        }
        self._js_dist = []
        self._css_dist = []
        self._clientside_callbacks: _t.List[
            _t.Tuple[ClientsideFuncType, _t.Any, _t.Any]
        ] = []

        self._finals = {}

    def add_hook(
        self,
        hook: str,
        func: _t.Callable,
        priority: _t.Optional[int] = None,
        final: bool = False,
        data: _t.Optional[HookDataType] = None,
    ):
        if final:
            if hook in self._finals:
                raise HookError("Final hook already present")
            self._finals[hook] = _Hook(func, final, data=data)
            return

        # Always get the actual list (never default).
        try:
            hks = self._ns[hook]
        except KeyError:
            hks = []
            self._ns[hook] = hks

        if priority is None:
            if hks:
                # Priority: 1 smaller than current minimum in hks
                min_priority = hks[
                    -1
                ].priority  # last element: lowest, list is sorted desc
                p = min_priority - 1
            else:
                p = 0
        else:
            p = priority

        # Keep hks sorted in descending priority during insert using bisect
        new_hook = _Hook(func, priority=p, data=data)
        # _Hook instances are sorted by priority descending,
        # so we insert at proper position (use a wrapper of bisect, since descending):
        left, right = 0, len(hks)
        while left < right:
            mid = (left + right) // 2
            if hks[mid].priority > p:
                left = mid + 1
            else:
                right = mid
        hks.insert(left, new_hook)

    def get_hooks(self, hook: str) -> _t.List[_Hook]:
        final = self._finals.get(hook, None)
        if final:
            final = [final]
        else:
            final = []
        return self._ns.get(hook, []) + final

    def layout(self, priority: _t.Optional[int] = None, final: bool = False):
        """
        Run a function when serving the layout, the return value
        will be used as the layout.
        """

        def _wrap(func: _t.Callable[[LayoutType], LayoutType]):
            self.add_hook("layout", func, priority=priority, final=final)
            return func

        return _wrap

    def setup(self, priority: _t.Optional[int] = None, final: bool = False):
        """
        Can be used to get a reference to the app after it is instantiated.
        """

        def _setup(func: _t.Callable[[Dash], None]):
            self.add_hook("setup", func, priority=priority, final=final)
            return func

        return _setup

    def route(
        self,
        name: _t.Optional[str] = None,
        methods: _t.Sequence[str] = ("GET",),
        priority: _t.Optional[int] = None,
        final: bool = False,
    ):
        """
        Add a route to the Dash server.
        """

        def wrap(func: _t.Callable[[], _f.Response]):
            _name = name or func.__name__
            self.add_hook(
                "routes",
                func,
                priority=priority,
                final=final,
                data=dict(name=_name, methods=methods),
            )
            return func

        return wrap

    def error(self, priority: _t.Optional[int] = None, final: bool = False):
        """Automatically add an error handler to the dash app."""

        def _error(func: _t.Callable[[Exception], _t.Any]):
            self.add_hook("error", func, priority=priority, final=final)
            return func

        return _error

    def callback(
        self, *args, priority: _t.Optional[int] = None, final: bool = False, **kwargs
    ):
        """
        Add a callback to all the apps with the hook installed.
        """

        def wrap(func):
            self.add_hook(
                "callback",
                func,
                priority=priority,
                final=final,
                data=(list(args), dict(kwargs)),
            )
            return func

        return wrap

    def clientside_callback(
        self, clientside_function: ClientsideFuncType, *args, **kwargs
    ):
        """
        Add a callback to all the apps with the hook installed.
        """
        self._clientside_callbacks.append((clientside_function, args, kwargs))

    def script(self, distribution: _t.List[ResourceType]):
        """Add js scripts to the page."""
        self._js_dist.extend(distribution)

    def stylesheet(self, distribution: _t.List[ResourceType]):
        """Add stylesheets to the page."""
        self._css_dist.extend(distribution)

    def index(self, priority: _t.Optional[int] = None, final=False):
        """Modify the index of the apps."""

        def wrap(func):
            self.add_hook(
                "index",
                func,
                priority=priority,
                final=final,
            )
            return func

        return wrap

    def custom_data(
        self, namespace: str, priority: _t.Optional[int] = None, final=False
    ):
        """
        Add data to the callback_context.custom_data property under the namespace.

        The hook function takes the current context_value and before the ctx is set
        and has access to the flask request context.
        """

        def wrap(func: _t.Callable[[_t.Dict], _t.Any]):
            self.add_hook(
                "custom_data",
                func,
                priority=priority,
                final=final,
                data={"namespace": namespace},
            )
            return func

        return wrap


hooks = _Hooks()


class HooksManager:
    # Flag to only run `register_setuptools` once
    _registered = False
    hooks = hooks

    # pylint: disable=too-few-public-methods
    class HookErrorHandler:
        def __init__(self, original):
            self.original = original

        def __call__(self, err: Exception):
            result = None
            if self.original:
                result = self.original(err)
            hook_result = None
            for hook in HooksManager.get_hooks("error"):
                hook_result = hook(err)
            return result or hook_result

    @classmethod
    def get_hooks(cls, hook: str):
        return cls.hooks.get_hooks(hook)

    @classmethod
    def register_setuptools(cls):
        if cls._registered:
            # Only have to register once.
            return

        for dist in _importlib_metadata.distributions():
            for entry in dist.entry_points:
                # Look for setup.py entry points named `dash_hooks`
                if entry.group != "dash_hooks":
                    continue
                entry.load()
