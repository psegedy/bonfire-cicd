import attr
import requests
from bonfire.utils import FatalError
from docker.errors import APIError as DockerAPIError
from docker.errors import BuildError as DockerBuildError
from podman.errors import APIError as PodmanAPIError
from podman.errors import BuildError as PodmanBuildError

from .clients.container import ContainerClient


@attr.s
class ImageBuilder:
    client: ContainerClient = attr.ib()
    image: str = attr.ib()
    image_tag: str = attr.ib()
    app_root: str = attr.ib()
    quay_api_token: str = attr.ib()
    is_pull_request: bool = attr.ib(default=False)
    dockerfile: str = attr.ib(default="Dockerfile")
    cache_from_latest: bool = attr.ib(default=False)
    quay_expire_time: str = attr.ib(default="3d")

    @property
    def is_quay_image(self) -> bool:
        return self.image.startswith("quay.io")

    def image_present(self) -> bool:
        """Check if image tag already exists in quay."""
        if self.is_quay_image:
            quay_repo = self.image[self.image.find("quay.io/") + len("quay.io/") :]  # noqa
            response = requests.get(
                f"https://quay.io/api/v1/repository/{quay_repo}/tag/{self.image_tag}/images",
                headers={"Authorization": f"Bearer {self.quay_api_token}"},
                allow_redirects=True,
            )
            return bool(response.status_code == 200)
        return False

    def build(self) -> None:
        if self.image_present():
            return
        if self.is_pull_request:
            with open(f"{self.app_root}/{self.dockerfile}", "a") as f:
                f.write(f"LABEL quay.expires-after={self.quay_expire_time}")
        try:
            self.client.build(
                path=self.app_root,
                tag=f"{self.image}:{self.image_tag}",
                dockerfile=self.dockerfile,
                cache_from=self.image if self.cache_from_latest else None,
            )
        except TypeError:
            FatalError("'app_root' is invalid")
        except (PodmanAPIError, DockerAPIError) as err:
            FatalError(f"Podman/Docker server failed: {err}")
        except (PodmanBuildError, DockerBuildError) as err:
            FatalError(f"image build failed: {err}")

    def push(self) -> None:
        if self.image_present():
            return
        try:
            self.client.push(repository=self.image, tag=self.image_tag)
        except (PodmanAPIError, DockerAPIError) as err:
            FatalError(f"Podman/Docker server failed: {err}")
