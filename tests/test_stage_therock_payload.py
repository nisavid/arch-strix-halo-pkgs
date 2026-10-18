import hashlib
import importlib.util
import io
from pathlib import Path
import sys
import tarfile

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
MODULE_PATH = REPO_ROOT / "tools/stage_therock_payload.py"
SPEC = importlib.util.spec_from_file_location("stage_therock_payload", MODULE_PATH)
assert SPEC and SPEC.loader
stage_therock_payload = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = stage_therock_payload
SPEC.loader.exec_module(stage_therock_payload)


def make_tarball(path: Path, files: dict[str, bytes]) -> Path:
    # Like the AMD dist tarball, the archive root is the ROCm prefix itself.
    with tarfile.open(path, "w:gz") as tar:
        for name, data in files.items():
            info = tarfile.TarInfo(f"./{name}")
            info.size = len(data)
            tar.addfile(info, io.BytesIO(data))
    return path


def write_policy(path: Path, tarball: Path, *, pkgver: str = "7.14.1", sha256: str | None = None) -> Path:
    digest = sha256 or hashlib.sha256(tarball.read_bytes()).hexdigest()
    path.write_text(
        "\n".join(
            [
                "[repo]",
                f'pkgver = "{pkgver}"',
                "",
                "[payload]",
                f'url = "{tarball.as_uri()}"',
                f'sha256 = "{digest}"',
                f"size = {tarball.stat().st_size}",
                'gfx_arch = "gfx1151"',
                "",
            ]
        )
    )
    return path


@pytest.fixture
def payload(tmp_path: Path) -> tuple[Path, Path]:
    source = tmp_path / "upstream"
    source.mkdir()
    tarball = make_tarball(
        source / "therock-dist-linux-gfx1151-7.14.1.tar.gz",
        {".info/version": b"7.14.1\n", "lib/librocblas.so.5.5": b"payload\n"},
    )
    return tarball, write_policy(tmp_path / "policy.toml", tarball)


def test_repo_policy_pins_the_therock_7_14_1_payload():
    pin = stage_therock_payload.load_payload_pin(REPO_ROOT / "policies/therock-packages.toml")

    assert pin["url"] == "https://repo.amd.com/rocm/tarball-multi-arch/therock-dist-linux-gfx1151-7.14.1.tar.gz"
    assert pin["sha256"] == "c40e8f2bd6630a7d11557c762b99c6fa8afb04c9bd0e51ed1675ee1ca24afb00"
    assert pin["size"] == 1713467716
    assert pin["pkgver"] == "7.14.1"


def test_stage_fetches_verifies_and_extracts_into_opt_rocm(tmp_path, payload, capsys):
    _tarball, policy = payload
    stage = tmp_path / "stage"

    assert stage_therock_payload.main(["--stage", str(stage), "--policy", str(policy)]) == 0

    assert (stage / "opt/rocm/.info/version").read_text() == "7.14.1\n"
    assert (stage / "opt/rocm/lib/librocblas.so.5.5").read_text() == "payload\n"
    assert not (stage / "opt/rocm.partial").exists()
    cached = tmp_path / "stage.download/therock-dist-linux-gfx1151-7.14.1.tar.gz"
    assert cached.is_file()
    assert "Staged TheRock 7.14.1" in capsys.readouterr().out


def test_stage_root_comes_from_the_environment(tmp_path, payload, monkeypatch):
    _tarball, policy = payload
    stage = tmp_path / "env-stage"
    monkeypatch.setenv(stage_therock_payload.STAGE_ENV_VAR, str(stage))

    assert stage_therock_payload.main(["--policy", str(policy)]) == 0
    assert (stage / "opt/rocm/.info/version").is_file()


def test_stage_root_is_required(payload, monkeypatch, capsys):
    _tarball, policy = payload
    monkeypatch.delenv(stage_therock_payload.STAGE_ENV_VAR, raising=False)

    assert stage_therock_payload.main(["--policy", str(policy)]) == 2
    assert "STAGE_ROOT_MISSING" in capsys.readouterr().err


def test_stage_rejects_a_tarball_that_misses_the_pinned_sha256(tmp_path, payload, capsys):
    tarball, _policy = payload
    policy = write_policy(tmp_path / "bad-policy.toml", tarball, sha256="0" * 64)
    stage = tmp_path / "stage"

    assert stage_therock_payload.main(["--stage", str(stage), "--policy", str(policy)]) == 2
    assert "PAYLOAD_SHA256_MISMATCH" in capsys.readouterr().err
    assert not (stage / "opt/rocm").exists()


def test_stage_refuses_to_replace_an_existing_stage_without_force(tmp_path, payload, capsys):
    _tarball, policy = payload
    stage = tmp_path / "stage"
    (stage / "opt/rocm").mkdir(parents=True)
    (stage / "opt/rocm/stale").write_text("old\n")

    assert stage_therock_payload.main(["--stage", str(stage), "--policy", str(policy)]) == 2
    assert "STAGE_NOT_EMPTY" in capsys.readouterr().err
    assert (stage / "opt/rocm/stale").exists()

    assert stage_therock_payload.main(["--stage", str(stage), "--policy", str(policy), "--force"]) == 0
    assert not (stage / "opt/rocm/stale").exists()
    assert (stage / "opt/rocm/.info/version").is_file()


def test_stage_rejects_a_payload_version_that_differs_from_policy(tmp_path, payload, capsys):
    tarball, _policy = payload
    policy = write_policy(tmp_path / "old-policy.toml", tarball, pkgver="7.13.0")

    assert stage_therock_payload.main(["--stage", str(tmp_path / "stage"), "--policy", str(policy)]) == 2
    assert "PAYLOAD_VERSION_MISMATCH" in capsys.readouterr().err


def test_stage_can_remove_the_downloaded_tarball_but_not_a_supplied_one(tmp_path, payload):
    tarball, policy = payload
    downloads = tmp_path / "dl"

    assert (
        stage_therock_payload.main(
            ["--stage", str(tmp_path / "a"), "--policy", str(policy), "--download-dir", str(downloads), "--remove-tarball"]
        )
        == 0
    )
    assert not (downloads / tarball.name).exists()

    assert (
        stage_therock_payload.main(
            ["--stage", str(tmp_path / "b"), "--policy", str(policy), "--tarball", str(tarball), "--remove-tarball"]
        )
        == 0
    )
    assert tarball.is_file()
    assert (tmp_path / "b/opt/rocm/.info/version").is_file()
