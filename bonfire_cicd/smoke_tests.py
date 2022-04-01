import base64
import json
import os
import logging
from pathlib import Path

import attr
from invoke import run
from .utils import set_port_forward
# from minio import Minio


from .clients.openshift import OpenshiftClient
from .clients.container import ContainerClient

IQE_MARKER_EXPRESSION = os.getenv("IQE_MARKER_EXPRESSION", "")
IQE_FILTER_EXPRESSION = os.getenv("IQE_FILTER_EXPRESSION", "")
IQE_IMAGE_TAG = os.getenv("IQE_IMAGE_TAG", "")
IQE_REQUIREMENTS = os.getenv("IQE_REQUIREMENTS", "")
IQE_REQUIREMENTS_PRIORITY = os.getenv("IQE_REQUIREMENTS_PRIORITY", "")
IQE_TEST_IMPORTANCE = os.getenv("IQE_TEST_IMPORTANCE", "")

MC_IMAGE = "quay.io/cloudservices/mc:latest"

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
    iqe_image_tag: str = attr.ib(default="")
    iqe_marker: str = attr.ib(default="")
    iqe_filter: str = attr.ib(default="")
    iqe_requirements: str = attr.ib(default="")
    iqe_requirements_priority: str = attr.ib(default="")
    iqe_test_importance: str = attr.ib(default="")

    def setup_minio(self, pod) -> None:
        # Set up port-forward for minio
        svc_port = set_port_forward(self.oc, f"env-{self.namespace}-minio", "9000", self.namespace)
        # Get the secret from the env
        minio_secret = self.oc.get.secret(f"env-{self.namespace}-minio", output="json", _silent=True)
        secret_json = json.loads(minio_secret)
        # Grab the needed creds from the secret
        os.environ["MINIO_ACCESS"] = secret_json["data"]["accessKey"]
        os.environ["MINIO_SECRET_KEY"] = secret_json["data"]["secretKey"]
        os.environ["MINIO_HOST"] = "localhost"
        os.environ["MINIO_PORT"] = svc_port

        container_name = f"mc-{self.job_name}-{self.build_number}"
        bucket_name = f"{pod}-artifacts"
        artifacts_dir = Path("/artifacts")
        artifacts_dir.mkdir(parents=True, exist_ok=True)

        # mc = Minio(
        #     f"http://{minio_host}:{minio_port}",
        #     access_key=access_key,
        #     secret_key=secret_key,
        # )

    def deploy_iqe_cji(self):
        pod = run(
            f"""
            bonfire deploy-iqe-cji {self.cji_name} \
                --marker {self.iqe_marker} \
                --filter {self.iqe_filter} \
                --image-tag {self.iqe_image_tag} \
                --requirements {self.iqe_requirements} \
                --requirements-priority {self.iqe_requirements_priority} \
                --test-importance {self.iqe_test_importance} \
                --env "clowder_smoke" \
                --cji-name {self.cji_name} \
                --namespace {self.namespace}
            """,
            echo=True,
        )

        # Pipe logs to background to keep them rolling in jenkins
        self.oc.logs(pod, "-f", namespace=self.namespace)

        # Wait for the job to Complete or Fail before we try to grab artifacts
        # condition=complete does trigger when the job fails
        self.oc.wait(
            f"cji/{self.cji_name}",
            timeout=self.cji_timeout,
            for_condition="JobInvocationComplete",
            namespace=self.namespace,
        )

        log.info("Fetching artifacts from minio...")
        self.setup_minio(pod)
