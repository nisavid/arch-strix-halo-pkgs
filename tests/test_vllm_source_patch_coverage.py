"""Every vLLM source patch after the local carry is covered by a sentinel.

The vLLM PKGBUILD re-extracts and repatches its source only when a sentinel
string is missing from the tree. A patch that no sentinel covers would be
skipped silently on a reused src/ tree from an older pkgrel, and the built
package would lack it while claiming it.

These tests read the patch list and the sentinels from the policy itself, so
adding a patch to `source_patches` without a `source_patch_sentinels` entry
fails here, in the default suite, and in the renderer.
"""

from __future__ import annotations

import copy
import importlib.util
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parents[1]
TOOLS_DIR = REPO_ROOT / "tools"
if str(TOOLS_DIR) not in sys.path:
    sys.path.insert(0, str(TOOLS_DIR))

MODULE_PATH = TOOLS_DIR / "render_recipe_scaffolds.py"
SPEC = importlib.util.spec_from_file_location("render_recipe_scaffolds", MODULE_PATH)
assert SPEC and SPEC.loader
render_recipe_scaffolds = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = render_recipe_scaffolds
SPEC.loader.exec_module(render_recipe_scaffolds)

import recipe_policy  # noqa: E402


PACKAGE = "python-vllm-rocm-gfx1151"
PKG_DIR = REPO_ROOT / "packages" / PACKAGE
# The template's built-in sentinels cover the first patch, the local carry.
CARRY_SENTINELS = 8


def policy_pkg() -> dict:
    policy = recipe_policy.load_recipe_policy(REPO_ROOT / "policies/recipe-packages.toml")
    return policy["packages"][PACKAGE]


def later_patches() -> list[str]:
    return policy_pkg()["source_patches"][1:]


def text_sentinels() -> list[tuple[str, str, str]]:
    return render_recipe_scaffolds.vllm_source_patch_sentinels(policy_pkg())


def diff_sections(patch: str) -> dict[str, str]:
    """Map each file a patch touches to that file's diff."""
    body = (PKG_DIR / patch).read_text().split("\n---\n", 1)[1]
    sections = {}
    for section in ("\n" + body).split("\ndiff --git a/")[1:]:
        path = section.split(" b/", 1)[0]
        sections[path] = section
    return sections


def lines(section: str, sign: str) -> list[str]:
    return [
        line[1:]
        for line in section.splitlines()
        if line.startswith(sign) and not line.startswith(sign * 3)
    ]


def sentinel_function() -> str:
    text = (PKG_DIR / "PKGBUILD").read_text()
    start = text.index("_source_tree_has_all_source_patches() {")
    return text[start : text.index("\n}\n", start)]


def test_policy_lists_patches_after_the_carry():
    # Without any, the checks below would pass vacuously.
    assert later_patches()
    assert all((PKG_DIR / patch).is_file() for patch in policy_pkg()["source_patches"])


def test_every_patch_after_the_carry_has_a_sentinel_or_an_exemption():
    # vllm_source_patch_sentinels() exits when a patch has neither.
    covered = {name for name, _, _ in text_sentinels()}
    entries = {entry["patch"]: entry for entry in policy_pkg()["source_patch_sentinels"]}

    assert sorted(entries) == sorted(later_patches())
    for patch in later_patches():
        assert patch in covered or "guarded_by" in entries[patch], patch


@pytest.mark.parametrize("index", range(len(later_patches())))
def test_a_patch_without_coverage_is_refused(index, capsys):
    policy = copy.deepcopy(policy_pkg())
    dropped = policy["source_patches"][1:][index]
    policy["source_patch_sentinels"] = [
        entry for entry in policy["source_patch_sentinels"] if entry["patch"] != dropped
    ]

    with pytest.raises(SystemExit) as exc:
        render_recipe_scaffolds.vllm_source_patch_sentinels(policy)

    assert exc.value.code == 2
    assert dropped in capsys.readouterr().err


def test_a_new_patch_without_coverage_is_refused(capsys):
    policy = copy.deepcopy(policy_pkg())
    policy["source_patches"].append("0099-backport-not-yet-covered.patch")

    with pytest.raises(SystemExit) as exc:
        render_recipe_scaffolds.vllm_source_patch_sentinels(policy)

    assert exc.value.code == 2
    err = capsys.readouterr().err
    assert "SOURCE_PATCH_SENTINEL_MISSING" in err
    assert "0099-backport-not-yet-covered.patch" in err


def test_each_sentinel_appears_only_once_its_own_patch_is_applied():
    sentinels = text_sentinels()
    assert sentinels

    for patch, text, path in sentinels:
        sections = diff_sections(patch)
        assert path in sections, f"{patch} does not touch {path}"
        assert any(text in line for line in lines(sections[path], "+")), (patch, text)
        # Not already in the file before the patch, as far as the diff shows.
        assert not any(text in line for line in lines(sections[path], "-")), (patch, text)
        assert not any(text in line for line in lines(sections[path], " ")), (patch, text)
        # No other patch in the series writes the same string anywhere.
        for other in policy_pkg()["source_patches"]:
            if other == patch:
                continue
            for other_path, section in diff_sections(other).items():
                assert not any(text in line for line in lines(section, "+")), (
                    patch,
                    other,
                    other_path,
                )


def test_an_exemption_is_only_for_a_patch_that_adds_no_line():
    exempt = [
        entry for entry in policy_pkg()["source_patch_sentinels"] if "guarded_by" in entry
    ]

    for entry in exempt:
        for path, section in diff_sections(entry["patch"]).items():
            assert lines(section, "+") == [], (entry["patch"], path)
        assert entry["reason"].strip()


def test_the_rendered_pkgbuild_greps_for_every_policy_sentinel():
    function = sentinel_function()
    sentinels = text_sentinels()

    for _, text, path in sentinels:
        assert f"grep -Fq '{text}' {path}" in function
    assert function.count("grep -Fq") == CARRY_SENTINELS + len(sentinels)
