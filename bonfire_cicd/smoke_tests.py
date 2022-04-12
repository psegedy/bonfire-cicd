import logging
from pathlib import Path
from time import sleep

import attr
from bonfire.utils import FatalError
from invoke import run

from .clients.container import ContainerClient
from .clients.openshift import OpenshiftClient
from .utils import run_mc
from .utils import setup_minio

log = logging.getLogger(__name__)


@attr.s
class SmokeTestRunner:
    oc: OpenshiftClient = attr.ib()
    docker: ContainerClient = attr.ib()
    cji_name: str = attr.ib()
    cji_timeout: str = attr.ib()
    namespace: str = attr.ib()
    job_name: str = attr.ib()
    build_number: str = attr.ib()
    iqe_image_tag: str = attr.ib(default="'")
    iqe_marker: str = attr.ib(default="'")
    iqe_filter: str = attr.ib(default="'")
    iqe_requirements: str = attr.ib(default="'")
    iqe_requirements_priority: str = attr.ib(default="'")
    iqe_test_importance: str = attr.ib(default="'")
    iqe_plugins: str = attr.ib(default="'")
    artifacts_dir: str = attr.ib(default="'")

    def fetch_from_minio(self, pod) -> None:
        # TODO: use python minio
        mc_image = "quay.io/cloudservices/mc"
        minio_access, minio_secret_key, minio_host, minio_port = setup_minio(
            self.oc, self.docker, mc_image, self.namespace
        )
        if not (minio_access or minio_secret_key or minio_port):
            FatalError("Failed to fetch minio connection info when running 'oc' commands")

        container_name = f"mc-{self.job_name}-{self.build_number}"
        bucket_name = f"{pod}-artifacts"
        cmd = f"""
            mkdir -p /artifacts && \
            mc --no-color --quiet alias set minio \
            http://{minio_host}:{minio_port} {minio_access} {minio_secret_key} && \
            mc --no-color --quiet mirror --overwrite minio/{bucket_name} /artifacts/
        """
        # Add retry logic for intermittent minio connection failures
        exception = None
        for _ in range(5):
            try:
                run_mc(self.docker, container_name, mc_image, cmd, self.artifacts_dir)
                break
            except Exception as err:
                exception = err
                log.warn("minio artifact copy failed, retrying in 5sec...")
                sleep(5)
        else:
            raise FatalError(f"minio artifact copy failed - {exception}")

        log.info("copied artifacts from iqe pod: ")
        artifacts_path = Path(self.artifacts_dir)
        for cur_file in artifacts_path.iterdir():
            log.info("%s", cur_file)

    def deploy_iqe_cji(self):
        pod = run(
            f"""
            bonfire deploy-iqe-cji {self.cji_name} \
                --marker '{self.iqe_marker}' \
                --filter '{self.iqe_filter}' \
                --image-tag {self.iqe_image_tag} \
                --requirements '{self.iqe_requirements}' \
                --requirements-priority '{self.iqe_requirements_priority}' \
                --test-importance '{self.iqe_test_importance}' \
                --plugins '{self.iqe_plugins}' \
                --env "clowder_smoke" \
                --cji-name {self.cji_name} \
                --namespace {self.namespace}
            """,
            echo=True,
        ).stdout.strip("\n")

        # Pipe logs to background to keep them rolling in jenkins
        self.oc.logs(pod, "-f", namespace=self.namespace)

        # Wait for the job to Complete or Fail before we try to grab artifacts
        # condition=complete does trigger when the job fails
        self.oc.wait(
            f"cji/{self.cji_name}",
            "--for",
            "condition=JobInvocationComplete",
            timeout=self.cji_timeout,
            namespace=self.namespace,
        )

        log.info("Fetching artifacts from minio...")
        self.fetch_from_minio(pod)
