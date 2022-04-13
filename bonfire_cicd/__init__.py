import os

import click
from distutils.util import strtobool

from .build import ImageBuilder
from .deploy import EphemeralDeployer
from .deploy import EphemeralDeployerDB
from .smoke_tests import SmokeTestRunner
from .utils import Clients
from .utils import teardown

IMAGE = os.getenv("IMAGE", "")
IMAGE_TAG = os.getenv("IMAGE_TAG", "")
APP_ROOT = os.getenv("APP_ROOT", "")

QUAY_USER = os.getenv("QUAY_USER", "")
QUAY_TOKEN = os.getenv("QUAY_TOKEN", "")
QUAY_API_TOKEN = os.getenv("QUAY_API_TOKEN", "")
RH_REGISTRY_USER = os.getenv("RH_REGISTRY_USER", "")
RH_REGISTRY_TOKEN = os.getenv("RH_REGISTRY_TOKEN", "")
PR_ID = os.getenv("ghprbPullId") or os.getenv("gitlabMergeRequestIid")

DOCKERFILE = os.getenv("DOCKERFILE", "Dockerfile")
CACHE_FROM_LATEST_IMAGE = os.getenv("CACHE_FROM_LATEST_IMAGE", "false")

OC_LOGIN_TOKEN = os.getenv("OC_LOGIN_TOKEN", "")
OC_LOGIN_SERVER = os.getenv("OC_LOGIN_SERVER", "")

JOB_NAME = os.getenv("JOB_NAME", "")
BUILD_NUMBER = os.getenv("BUILD_NUMBER", "")

APP_NAME = os.getenv("APP_NAME", "")
COMPONENT_NAME = os.getenv("COMPONENT_NAME", "")
IMAGE = os.getenv("IMAGE", "")
COMPONENTS = os.getenv("COMPONENTS", "")
COMPONENTS_W_RESOURCES = os.getenv("COMPONENTS_W_RESOURCES", "")
DEPLOY_TIMEOUT = os.getenv("DEPLOY_TIMEOUT", "")
RELEASE_NAMESPACE = os.getenv("RELEASE_NAMESPACE", "")
IMAGE_TAG = os.getenv("IMAGE_TAG", "")
ARTIFACTS_DIR = os.getenv("ARTIFACTS_DIR", "")
GIT_COMMIT = os.getenv("GIT_COMMIT", "")
REF_ENV = os.getenv("REF_ENV", "insights-production")
EXTRA_DEPLOY_ARGS = os.getenv("EXTRA_DEPLOY_ARGS", "")

IQE_MARKER_EXPRESSION = os.getenv("IQE_MARKER_EXPRESSION", "")
IQE_FILTER_EXPRESSION = os.getenv("IQE_FILTER_EXPRESSION", "")
IQE_IMAGE_TAG = os.getenv("IQE_IMAGE_TAG", "")
IQE_REQUIREMENTS = os.getenv("IQE_REQUIREMENTS", "")
IQE_REQUIREMENTS_PRIORITY = os.getenv("IQE_REQUIREMENTS_PRIORITY", "")
IQE_TEST_IMPORTANCE = os.getenv("IQE_TEST_IMPORTANCE", "")
IQE_PLUGINS = os.getenv("IQE_PLUGINS", "")
IQE_CJI_TIMEOUT = os.getenv("IQE_CJI_TIMEOUT", "30m")


@click.group("cicd")
@click.pass_context
def main(ctx):
    clients = Clients(OC_LOGIN_TOKEN, OC_LOGIN_SERVER)
    clients.docker.login(username=QUAY_USER, password=QUAY_TOKEN, registry="quay.io")
    clients.docker.login(
        username=RH_REGISTRY_USER, password=RH_REGISTRY_TOKEN, registry="registry.redhat.io"
    )
    ctx.obj = clients


@main.command()
@click.pass_obj
def build(clients):
    ib = ImageBuilder(
        client=clients.docker,
        image=IMAGE,
        image_tag=IMAGE_TAG,
        app_root=APP_ROOT,
        quay_user=QUAY_USER,
        quay_token=QUAY_TOKEN,
        quay_api_token=QUAY_API_TOKEN,
        rh_registry_user=RH_REGISTRY_USER,
        rh_registry_token=RH_REGISTRY_TOKEN,
        is_pull_request=strtobool(PR_ID),
        dockerfile=DOCKERFILE,
        cache_from_latest=strtobool(CACHE_FROM_LATEST_IMAGE),
    )
    ib.build()
    ib.push()


@main.command()
@click.pass_obj
def smoke_tests(clients):
    ns = os.getenv("NAMESPACE", "")
    try:
        runner = SmokeTestRunner(
            oc=clients.oc,
            docker=clients.docker,
            cji_name=COMPONENT_NAME,
            cji_timeout=IQE_CJI_TIMEOUT,
            namespace=ns,
            job_name=JOB_NAME,
            build_number=BUILD_NUMBER,
            iqe_image_tag=IQE_IMAGE_TAG,
            iqe_marker=IQE_MARKER_EXPRESSION,
            iqe_filter=IQE_FILTER_EXPRESSION,
            iqe_requirements=IQE_REQUIREMENTS,
            iqe_requirements_priority=IQE_REQUIREMENTS_PRIORITY,
            iqe_test_importance=IQE_TEST_IMPORTANCE,
            iqe_plugins=IQE_PLUGINS,
            artifacts_dir=ARTIFACTS_DIR,
        )
        runner.deploy_iqe_cji()
    finally:
        teardown(clients.oc, runner.namespace)


@main.group()
def deploy():
    pass


@deploy.command()
@click.pass_obj
def ephemeral(clients):
    deployer = EphemeralDeployer(
        oc=clients.oc,
        job_name=JOB_NAME,
        build_number=BUILD_NUMBER,
        app_name=APP_NAME,
        component_name=COMPONENT_NAME,
        template_ref=f"{COMPONENT_NAME}={GIT_COMMIT}",
        image=IMAGE,
        image_tag=IMAGE_TAG,
        ref_env=REF_ENV,
        deploy_timeout=DEPLOY_TIMEOUT,
        components=COMPONENTS,
        components_resources=COMPONENTS_W_RESOURCES,
        extra_deploy_args=EXTRA_DEPLOY_ARGS,
    )
    deployer.deploy()


@deploy.command()
@click.pass_obj
def ephemeral_db(clients):
    deployer = EphemeralDeployerDB(
        oc=clients.oc,
        job_name=JOB_NAME,
        build_number=BUILD_NUMBER,
        app_name=APP_NAME,
        component_name=COMPONENT_NAME,
        template_ref=f"{COMPONENT_NAME}={GIT_COMMIT}",
        image=IMAGE,
        image_tag=IMAGE_TAG,
        ref_env=REF_ENV,
        deploy_timeout=DEPLOY_TIMEOUT,
        components=COMPONENTS,
        components_resources=COMPONENTS_W_RESOURCES,
        extra_deploy_args=EXTRA_DEPLOY_ARGS,
    )
    deployer.deploy()
