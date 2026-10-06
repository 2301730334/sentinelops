"""Sanity checks for the container runtime configuration (docker/)."""
import logging.config
import os
import runpy

import pytest

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
GUNICORN_CONF = os.path.join(ROOT, "docker", "gunicorn.conf.py")


def load_conf(monkeypatch, **env):
    for key, value in env.items():
        monkeypatch.setenv(key, value)
    return runpy.run_path(GUNICORN_CONF)


def test_gunicorn_defaults(monkeypatch):
    for key in ("PORT", "GUNICORN_WORKERS", "GUNICORN_THREADS"):
        monkeypatch.delenv(key, raising=False)
    conf = load_conf(monkeypatch)
    assert conf["bind"] == "0.0.0.0:8000"
    assert conf["workers"] == 1 and conf["threads"] == 4
    assert conf["worker_class"] == "gthread"
    assert conf["worker_tmp_dir"] == "/dev/shm"
    assert conf["control_socket_disable"] is True
    assert conf["accesslog"] is None


def test_gunicorn_env_overrides(monkeypatch):
    conf = load_conf(monkeypatch, PORT="9000", GUNICORN_WORKERS="2", GUNICORN_THREADS="8")
    assert conf["bind"] == "0.0.0.0:9000"
    assert (conf["workers"], conf["threads"]) == (2, 8)


def test_gunicorn_logconfig_is_valid_json_logging(monkeypatch, capsys):
    conf = load_conf(monkeypatch)
    logging.config.dictConfig(conf["logconfig_dict"])
    logging.getLogger("gunicorn.error").info("hello")
    assert '"logger": "gunicorn.error"' in capsys.readouterr().out


@pytest.mark.parametrize("path", ["docker/entrypoint.sh", "Dockerfile"])
def test_container_files_use_lf_line_endings(path):
    with open(os.path.join(ROOT, path), "rb") as fh:
        assert b"\r\n" not in fh.read()


def test_dockerfile_runs_as_non_root():
    with open(os.path.join(ROOT, "Dockerfile")) as fh:
        content = fh.read()
    assert "USER 10001:10001" in content
    assert "HEALTHCHECK" in content
