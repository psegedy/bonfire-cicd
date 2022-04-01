import json
import logging
import os
import shutil
import socket
from pathlib import Path
from typing import Dict
from typing import List
from typing import Optional

from distutils.util import strtobool
from invoke import run

from .clients.openshift import OpenshiftClient

logger = logging.getLogger(__name__)

RELEASE_NAMESPACE = strtobool(os.getenv("RELEASE_NAMESPACE", "true"))
K8S_ARTIFACTS_DIR = os.getenv("K8S_ARTIFACTS_DIR")


def _get_pod_logs(oc: OpenshiftClient, ns: str) -> None:
    logs_dir = Path(f"{K8S_ARTIFACTS_DIR}/{ns}/logs")
    logs_dir.mkdir(parents=True, exist_ok=True)
    logger.info("Collecting container logs...")
    pods_json = json.loads(oc.get.pods(namespace=ns, output="json", _silent=True).stdout)
    pods_containers: Dict[str, List[str]] = {}
    for item in pods_json["items"]:
        pod_name = item["metadata"]["name"]
        pods_containers[pod_name] = []
        for container in item["spec"].get("containers", []):
            pods_containers[pod_name].append(container["name"])
        for init_container in item["spec"].get("initContainers", []):
            pods_containers[pod_name].append(init_container["name"])

    for pod, containers in pods_containers.items():
        for container in containers:
            current = oc.logs(
                pod, container=container, namespace=ns, _ignore_errors=True, _silent=True
            )
            previous = oc.logs(
                pod, container=container, namespace=ns, _ignore_errors=True, _silent=True
            )
            if current:
                with open(logs_dir / f"{pod}_{container}.log", "wb") as f:
                    f.write(current.stdout)
            if previous:
                with open(logs_dir / f"{pod}_{container}-previous.log", "wb") as f:
                    f.write(previous.stdout)


def _collect_k8s_artifacts(oc: OpenshiftClient, ns: str) -> None:
    ns_artifacts_dir = Path(f"{K8S_ARTIFACTS_DIR}/{ns}")
    ns_artifacts_dir.mkdir(parents=True, exist_ok=True)
    _get_pod_logs(oc, ns)
    logger.info("Collecting events and k8s configs...")

    events = oc.get.events(namespace=ns, sort_by=".lastTimestamp", _silent=True)
    all = oc.get.all(namespace=ns, output="yaml", _silent=True)
    clowdapp = oc.get.clowdapp(namespace=ns, output="yaml", _silent=True)
    clowdenv = oc.get.clowdenvironment(f"env-{ns}", output="yaml", _silent=True)
    cji = oc.get.clowdjobinvocation(namespace=ns, output="yaml", _silent=True)

    logs = (
        (ns_artifacts_dir / "oc_get_events.txt", events),
        (ns_artifacts_dir / "oc_get_all.yaml", all),
        (ns_artifacts_dir / "oc_get_clowdapp.yaml", clowdapp),
        (ns_artifacts_dir / "oc_get_clowdenvironment.yaml", clowdenv),
        (ns_artifacts_dir / "oc_get_clowdjobinvocation.yaml", cji),
    )
    for log in logs:
        with open(log[0], "wb") as f:
            f.write(log[1].stdout)


def teardown(oc: OpenshiftClient, namespace: Optional[str] = None) -> None:
    logger.info("------------------------")
    logger.info("----- TEARING DOWN -----")
    logger.info("------------------------")
    if K8S_ARTIFACTS_DIR:
        shutil.rmtree(K8S_ARTIFACTS_DIR, ignore_errors=True)
    namespace_env = os.getenv("NAMESPACE")
    db_namespace_env = os.getenv("DB_NAMESPACE")
    smoke_namespace_env = os.getenv("SMOKE_NAMESPACE")
    namespaces = {
        ns for ns in (namespace, namespace_env, db_namespace_env, smoke_namespace_env) if ns
    }

    for ns in namespaces:
        try:
            logger.info("Running teardown for ns: %s", ns)
            _collect_k8s_artifacts(oc, ns)
        finally:
            if RELEASE_NAMESPACE:
                logger.info("Releasing namespace reservation")
                run(f"bonfire namespace release {ns} -f")


def convert_arg(option_name: str, values: Optional[str] = None) -> str:
    if not values:
        return ""
    return " ".join([f"{option_name}={x}" for x in values.split(",")])


def set_port_forward(oc: OpenshiftClient, svc_name: str, port: str, ns: str) -> str:
    s = socket.socket()
    s.bind(("", 0))
    local_port = s.getsockname()[1]
    s.close()
    port_forward_pid = oc(
        "port-forward",
        f"svc/{svc_name}",
        f"{local_port}:{port}",
        namespace={ns},
    ).pid
    os.environ["PORT_FORWARD_PID"] = port_forward_pid
    return str(local_port)
