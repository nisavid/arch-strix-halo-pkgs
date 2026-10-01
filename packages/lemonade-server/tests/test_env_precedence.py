"""Behavior of the packaged lemond.service EnvironmentFile= order under systemd.

The PKGBUILD's 30-env-files.conf drop-in replaces upstream's single
EnvironmentFile=-/etc/default/lemond with the full list. These tests replay
upstream's line, the drop-in's lines, and the blackhole Environment= line in a
transient user unit, against temporary files that stand in for the real
paths, and read the resulting environment back with /usr/bin/env.
"""

from pathlib import Path
import re
import shutil
import subprocess

import pytest


PKGBUILD = Path(__file__).resolve().parents[1] / "PKGBUILD"
ENV_FILES_DROPIN = "/usr/lib/systemd/system/lemond.service.d/30-env-files.conf"
LLAMACPP_ENV = "/usr/lib/lemonade/llamacpp-gfx1151.env"
UPSTREAM_ENV_FILE_LINE = "EnvironmentFile=-/etc/default/lemond"
BLACKHOLE = "http://127.0.0.1:9"
SYSTEMD_RUN = ["systemd-run", "--user", "--wait", "--pipe", "--collect", "--quiet"]


def _heredoc(target):
    match = re.search(
        rf'"\$pkgdir{re.escape(target)}" <<\'EOF\'\n(.*?)\nEOF\n',
        PKGBUILD.read_text(),
        re.DOTALL,
    )
    assert match, f"no heredoc install for {target}"
    return match.group(1)


def _systemd_user_available():
    if shutil.which("systemd-run") is None:
        return False
    try:
        probe = subprocess.run(
            [*SYSTEMD_RUN, "/usr/bin/true"], capture_output=True, timeout=30
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    return probe.returncode == 0


pytestmark = pytest.mark.skipif(
    not _systemd_user_available(), reason="systemd --user is unavailable"
)


def _service_env(tmp_path, *, conf_d, default, extra=()):
    """Run /usr/bin/env under the packaged EnvironmentFile= order; return its env."""
    (tmp_path / "conf.d").mkdir()
    for name, text in conf_d.items():
        (tmp_path / "conf.d" / name).write_text(text)
    (tmp_path / "default-lemond").write_text(default)
    (tmp_path / "llamacpp.env").write_text(_heredoc(LLAMACPP_ENV) + "\n")
    stand_ins = {
        "/etc/lemonade/conf.d/": f"{tmp_path}/conf.d/",
        "/etc/default/lemond": f"{tmp_path}/default-lemond",
        LLAMACPP_ENV: f"{tmp_path}/llamacpp.env",
    }

    def stand_in(line):
        for real, temp in stand_ins.items():
            line = line.replace(real, temp)
        return line

    dropin = [
        line
        for line in _heredoc(ENV_FILES_DROPIN).splitlines()
        if line.startswith("EnvironmentFile=")
    ]
    properties = [f"Environment=HF_ENDPOINT={BLACKHOLE}", UPSTREAM_ENV_FILE_LINE, *dropin]
    argv = [*SYSTEMD_RUN]
    for prop in properties:
        argv += ["-p", stand_in(prop)]
    for prop in extra:
        argv += ["-p", prop]
    result = subprocess.run(
        [*argv, "/usr/bin/env"], capture_output=True, text=True, timeout=60, check=True
    )
    return dict(
        line.split("=", 1) for line in result.stdout.splitlines() if "=" in line
    )


@pytest.fixture
def service_env(tmp_path):
    return _service_env(
        tmp_path,
        conf_d={
            "10-bind.conf": (
                "SHARED_KEY=conf.d\n"
                "CONF_D_ONLY_KEY=conf.d\n"
                "LEMONADE_LLAMACPP_ROCM_BIN=/stale/conf.d/llama-server\n"
            ),
        },
        default=(
            "SHARED_KEY=default\n"
            "LEMONADE_LLAMACPP_ROCM_BIN=/stale/default/llama-server\n"
            "HF_ENDPOINT=http://owner.invalid\n"
        ),
    )


def test_etc_default_lemond_overrides_conf_d(service_env):
    assert service_env["SHARED_KEY"] == "default"


def test_a_conf_d_only_key_applies(service_env):
    assert service_env["CONF_D_ONLY_KEY"] == "conf.d"


def test_the_package_env_file_overrides_a_stale_llamacpp_key(service_env):
    package = dict(
        line.split("=", 1)
        for line in _heredoc(LLAMACPP_ENV).splitlines()
        if line and not line.startswith("#")
    )
    assert service_env["LEMONADE_LLAMACPP_ROCM_BIN"] == package["LEMONADE_LLAMACPP_ROCM_BIN"]
    for key, value in package.items():
        assert service_env[key] == value


def test_an_owner_env_file_overrides_the_blackhole_environment(service_env):
    # Overriding a blackhole takes an explicit owner edit; nothing is silent.
    assert service_env["HF_ENDPOINT"] == "http://owner.invalid"


def test_only_an_owner_env_file_overrides_the_package_env_file(tmp_path):
    # The documented override: a later drop-in such as
    # 40-llamacpp-override.conf with its own EnvironmentFile=. An Environment=
    # line there loses, because every env file overrides Environment=.
    override = tmp_path / "override.env"
    override.write_text("LEMONADE_LLAMACPP_ROCM_BIN=/owner/file/llama-server\n")
    env = _service_env(
        tmp_path,
        conf_d={},
        default="",
        extra=[
            f"EnvironmentFile={override}",
            "Environment=LEMONADE_LLAMACPP_VULKAN_BIN=/owner/env/llama-server",
        ],
    )
    assert env["LEMONADE_LLAMACPP_ROCM_BIN"] == "/owner/file/llama-server"
    assert env["LEMONADE_LLAMACPP_VULKAN_BIN"] != "/owner/env/llama-server"
