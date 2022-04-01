import base64
import json
import logging
import os

import attr
from bonfire.bonfire import FatalError
from invoke import run

from .clients.openshift import OpenshiftClient
from .utils import convert_arg
from .utils import set_port_forward
from .utils import teardown

logger = logging.getLogger(__name__)


@attr.s
class EphemeralDeployerBase:
    oc: OpenshiftClient = attr.ib()
    job_name: str = attr.ib()
    build_number: str = attr.ib()
    app_name: str = attr.ib()
    component_name: str = attr.ib()
    template_ref: str = attr.ib()
    image: str = attr.ib()
    image_tag: str = attr.ib()
    ref_env: str = attr.ib("insights-production")
    db_deployment_name: str = attr.ib(default=f"{component_name}-db")
    deploy_timeout: str = attr.ib(default="600")
    namespace: str = attr.ib(default="")
    components: str = attr.ib(
        default="",
        converter=lambda x: convert_arg("--component", x),  # type: ignore
    )
    components_resources: str = attr.ib(
        default="",
        converter=lambda x: convert_arg("--no-remove-resources", x),  # type: ignore
    )
    extra_deploy_args: str = attr.ib(default="")

    def _reserve_namespace(self):
        if not self.namespace:
            self.namespace = run("bonfire namespace reserve", echo=True).stdout.rstrip("\n")

    def _pre_deploy(self):
        raise NotImplementedError

    def _post_deploy(self):
        raise NotImplementedError

    def _deploy(self):
        raise NotImplementedError

    def deploy(self):
        self._pre_deploy()
        try:
            self._deploy()
        except Exception as err:
            if self.namespace:
                teardown(self.oc, self.namespace)
            raise err
        self._post_deploy()


@attr.s
class EphemeralDeployer(EphemeralDeployerBase):
    def _pre_deploy(self):
        os.environ["BONFIRE_NS_REQUESTER"] = f"{self.job_name}-{self.build_number}"
        self._reserve_namespace()
        os.environ["SMOKE_NAMESPACE"] = self.namespace

    def _post_deploy(self):
        pass

    def _deploy(self):
        run(
            f"""
            bonfire deploy {self.app_name} \
                --source=appsre \
                --ref-env {self.ref_env} \
                --set-template-ref {self.template_ref} \
                --set-image-tag {self.image}={self.image_tag} \
                --namespace {self.namespace} \
                --timeout {self.deploy_timeout} \
                {self.components} \
                {self.components_resources} \
                {self.extra_deploy_args}
            """,
            echo=True,
        )


@attr.s
class EphemeralDeployerDB(EphemeralDeployerBase):
    def _pre_deploy(self):
        os.environ["BONFIRE_NS_REQUESTER"] = f"{self.job_name}-{self.build_number}-db"
        self._reserve_namespace()
        os.environ["DB_NAMESPACE"] = self.namespace
        # self.db_deployment_name = os.getenv("DB_DEPLOYMENT_NAME", f"{self.component_name}-db")

    def _deploy(self):
        run(
            f"""
            bonfire process {self.app_name} \
                --source=appsre \
                --ref-env {self.ref_env} \
                --set-template-ref {self.template_ref} \
                --set-image-tag {self.image}={self.image_tag} \
                --namespace {self.namespace} \
                --no-get-dependencies \
                {self.components} \
                {self.components_resources} | oc apply -f - -n {self.namespace}
            """,
            echo=True,
        )
        run(f"bonfire namespace wait-on-resources {self.namespace} --db-only", echo=True)

    def _post_deploy(self):
        # Set up port-forward for DB
        local_db_port = set_port_forward(self.oc, self.db_deployment_name, "5432", self.namespace)

        # Store database access info to env vars
        secret = self.oc.get.secret(self.component_name, output="json", namespace=self.namespace)
        secret_json = json.loads(secret.stdout)
        decoded = base64.b64decode(secret_json["data"]["cdappconfig.json"])
        db_creds = json.loads(decoded).get("database", {})
        db_name = db_creds.get("name")
        if not db_name:
            teardown(self.oc, self.namespace)
            raise FatalError(
                "DATABASE_NAME is null, error with ephemeral env / clowder config, exiting"
            )
        os.environ["DATABASE_NAME"] = db_name
        os.environ["DATABASE_ADMIN_USERNAME"] = db_creds.get("adminUsername")
        os.environ["DATABASE_ADMIN_PASSWORD"] = db_creds.get("adminPassword")
        os.environ["DATABASE_USER"] = db_creds.get("username")
        os.environ["DATABASE_PASSWORD"] = db_creds.get("password")
        os.environ["DATABASE_HOST"] = "localhost"
        os.environ["DATABASE_PORT"] = local_db_port

        logger.info("DB_DEPLOYMENT_NAME: %s", self.db_deployment_name)
        logger.info("DATABASE_NAME: %s", db_name)
