import logging
from typing import Any
from typing import Dict
from typing import Iterator
from typing import List
from typing import Optional
from typing import Tuple
from typing import Union

import attr
from docker import DockerClient
from docker.errors import BuildError as DockerBuildError
from docker.models.images import Image as DockerImage
from docker.utils import parse_repository_tag
from invoke import run
from invoke.exceptions import UnexpectedExit
from podman import PodmanClient
from podman.domain.images import Image as PodmanImage
from podman.errors import BuildError as PodmanBuildError

log = logging.getLogger(__name__)


@attr.s
class ContainerClient:
    base_url: Optional[str] = attr.ib(default=None)
    auth: dict = attr.ib(init=False, default=attr.Factory(dict))

    def __attrs_post_init__(self) -> None:
        if self.podman_available():
            if self.base_url:
                self.client = PodmanClient(base_url=self.base_url)
            else:
                # Podman client can't handle base_url=None
                self.client = PodmanClient()
        else:
            self.client = DockerClient(base_url=self.base_url)

    @classmethod
    def from_env(cls):
        cls.client = PodmanClient.from_env() if cls.podman_available() else DockerClient.from_env()

    @staticmethod
    def podman_available() -> bool:
        try:
            return bool(run("which podman"))
        except UnexpectedExit:
            return False

    def _podman_auth(self, repository) -> Optional[dict]:
        """Workaround for missing PodmanClient.login."""
        if isinstance(self.client, PodmanClient):
            for registry in self.auth:
                if registry in repository:
                    return self.auth[registry]
        return None

    def _podman_pull_from_dockerfile(self, path, dockerfile):
        if isinstance(self.client, PodmanClient):
            dockerfile_path = f"{path}/{dockerfile}"
            images = []
            with open(dockerfile_path, "r") as f:
                lines = f.readlines()
                for line in lines:
                    if line.lower().startswith("from"):
                        images.append(line.split()[1])
            for image in images:
                repository, tag = parse_repository_tag(image)
                auth_config = self._podman_auth(repository)
                self.pull(repository, tag, auth_config=auth_config)

    def login(
        self,
        username: str,
        password: str,
        registry: str,
        **kwargs,
    ) -> Dict[str, Any]:
        if isinstance(self.client, PodmanClient):
            # `login` method is not implemented in podman-py
            # create auth dict which will be used for pull/push
            self.auth.update({registry: {"username": username, "password": password}})
            return self.auth
        return self.client.login(username=username, password=password, registry=registry, **kwargs)

    def pull(
        self, repository: str, tag: Optional[str] = None, all_tags: bool = False, **kwargs
    ) -> Union[Union[PodmanImage, DockerImage], List[Union[PodmanImage, DockerImage]]]:
        auth_config = kwargs.get("auth_config") or self._podman_auth(repository)
        if auth_config:
            return self.client.images.pull(
                repository, tag, all_tags, auth_config=auth_config, **kwargs
            )
        # podman client can't handle auth_config=None in kwargs
        return self.client.images.pull(repository, tag, all_tags, **kwargs)

    def build(
        self, path: str, tag: str, dockerfile: str, **kwargs
    ) -> Tuple[Union[PodmanImage, DockerImage], Iterator[bytes]]:
        self._podman_pull_from_dockerfile(path, dockerfile)
        if kwargs.get("cache_from"):
            log.info("Attempting to build image using cache")
            repository, __ = parse_repository_tag(tag)
            auth_config = kwargs.get("auth_config") or self._podman_auth(repository)
            self.pull(repository=repository, auth_config=auth_config, cache_from=True)
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
        auth_config = kwargs.get("auth_config") or self._podman_auth(repository)
        if auth_config:
            return self.client.images.push(
                repository=repository, tag=tag, auth_config=auth_config, **kwargs
            )
        # podman client can't handle auth_config=None in kwargs
        return self.client.images.push(repository=repository, tag=tag, **kwargs)
