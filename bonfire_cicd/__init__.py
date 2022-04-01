import os

import click
from distutils.util import strtobool

from .build import ImageBuilder
from .clients.openshift import OpenshiftClient
from .deploy import EphemeralDeployer
from .deploy import EphemeralDeployerDB
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


@click.group("cicd")
def main():
    pass


@main.command()
def build():
    ib = ImageBuilder(
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


@main.group()
@click.pass_context
def deploy(ctx):
    oc = OpenshiftClient(token=OC_LOGIN_TOKEN, server=OC_LOGIN_SERVER)
    ctx.obj = oc


@deploy.command()
@click.pass_obj
def ephemeral(oc):
    deployer = EphemeralDeployer(
        oc=oc,
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
def ephemeral_db(oc):
    deployer = EphemeralDeployerDB(
        oc=oc,
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

