import logging
from typing import Any
from typing import Dict
from typing import Iterator
from typing import Optional
from typing import Tuple
from typing import Union

import attr
from docker import DockerClient
from docker.errors import BuildError as DockerBuildError
from docker.models.images import Image as DockerImage
from invoke import run
from podman import PodmanClient
from podman.domain.images import Image as PodmanImage
from podman.errors import BuildError as PodmanBuildError

log = logging.getLogger(__name__)


@attr.s
class ContainerClient:
    def __attrs_post_init__(self) -> None:
        self.client = PodmanClient() if self.podman_available() else DockerClient()

    @staticmethod
    def podman_available() -> bool:
        return bool(run("which podman"))

    def login(
        self,
        username: str,
        password: str,
        registry: str,
        **kwargs,
    ) -> Dict[str, Any]:
        return self.client.login(username=username, password=password, registry=registry, **kwargs)

    def build(
        self, path: str, tag: str, dockerfile: str, **kwargs
    ) -> Tuple[Union[PodmanImage, DockerImage], Iterator[bytes]]:
        if kwargs.get("cache_from"):
            log.info("Attempting to build image using cache")
            self.client.images.pull(kwargs["cache_from"])
            try:
                return self.client.images.build(
                    path=path,
                    tag=tag,
                    dockerfile=dockerfile,
                    cache_from=[kwargs["cache_from"]],
                )
            except (PodmanBuildError, DockerBuildError):
                log.info("Build from cache failed, attempting build without cache")
                pass
        return self.client.images.build(
            path=path,
            tag=tag,
            dockerfile=dockerfile,
        )

    def push(
        self, repository: str, tag: Optional[str] = None, **kwargs
    ) -> Union[str, Iterator[Union[str, Dict[str, Any]]]]:
        return self.client.images.push(repository=repository, tag=tag, **kwargs)
