from inspect import getmodule
from typing import Any
from typing import Iterable


class InitException(Exception):
    pass


class InitHandlerCycleException(InitException):
    def __init__(self, chain: Iterable[Any]) -> None:
        msg = "Cycle detected in lifecycle init handler chain\n"
        for handler in chain:
            module = getmodule(handler)
            if module:
                module_name = module.__name__
            else:
                module_name = "<unknown>"

            msg += f"  {module_name}.{handler.__qualname__}\n"

        super().__init__(msg)
