"""Compatibility shim."""
from stackr.engine.docker import docker_available, network_exists  # noqa: F401

def run_doctor(config: object) -> bool:
    from stackr.engine.docker import docker_available
    return docker_available()
