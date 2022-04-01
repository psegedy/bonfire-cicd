from typing import Any
from typing import Dict
from typing import Optional
from typing import Union

import attr
from bonfire.openshift import oc

from .utils import OC_ACTIONS


@attr.s
class OcAction:
    name: str = attr.ib()
    parent: Optional["OcAction"] = attr.ib(default=None)

    def __call__(self, *args: str, **kwargs: Dict[str, Any]) -> Union[str, None]:
        params = []
        sh_kwargs = {}
        for key, val in kwargs.items():
            if key.startswith("_"):
                sh_kwargs[key] = val
                continue
            key = key.replace("_", "-")  # option `sort-by` has to have `sort_by` var
            params.extend([f"--{key}", val])
            # TODO: short options i.e. `-n` instead of `--namespace`
        args = [self.name.replace("_", "-"), *args]  # type: ignore
        if self.parent:
            args = [self.parent.name.replace("_", "-"), *args]  # type: ignore
        return oc(*args, *params, **sh_kwargs)


@attr.s
class OpenshiftClient:
    token: str = attr.ib()
    server: str = attr.ib()
    namespace: Optional[str] = attr.ib(default=None)

    def __attrs_post_init__(self) -> None:
        self.load()
        self.login(token=self.token, server=self.server, _silent=True)
        if self.namespace:
            self.project(self.namespace)

    def load(self) -> None:
        """Load client actions."""
        for action, sub_actions in OC_ACTIONS.items():
            setattr(self, action, OcAction(action))
            for sub_action in sub_actions:
                top = getattr(self, action)
                setattr(top, sub_action, OcAction(sub_action, top))
