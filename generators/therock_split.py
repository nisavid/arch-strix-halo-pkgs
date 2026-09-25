#!/usr/bin/env python3

from __future__ import annotations

import argparse
import fnmatch
import json
import os
import posixpath
import re
import struct
import sys
import textwrap
import tomllib
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path
from string import Template


STRUCTURED_FAILURES = {
    "unmapped": "UNMAPPED_COMPONENT",
    "ambiguous": "AMBIGUOUS_OWNERSHIP",
    "new_class": "NEW_THEROCK_PACKAGE_CLASS",
    "missing_pkg_meta": "MISSING_PACKAGE_METADATA",
    "kpack_ref_unowned": "KPACK_REF_UNOWNED",
    "soname_depend": "SONAME_DEPEND_UNRESOLVED",
}

IGNORED = "__ignored__"
KPACK_REF_SECTION = ".rocm_kpack_ref"
GFXARCH_TOKEN = "@GFXARCH@"


@dataclass
class Failure:
    kind: str
    subject: str
    detail: str
    hint: str

    def render(self) -> str:
        return f"{STRUCTURED_FAILURES[self.kind]}: {self.subject}\nDETAIL: {self.detail}\nHINT: {self.hint}"


def load_policy(path: Path) -> dict:
    with path.open("rb") as fh:
        data = tomllib.load(fh)
    return data


def read_template(path: Path) -> str:
    return path.read_text()


def pkgfunc_name(pkgname: str) -> str:
    return pkgname


def derive_pkg_conflicts(name: str, meta: dict, bundle_conflict: str) -> list[str]:
    conflicts = set(meta.get("conflicts", []))
    skipped = set(meta.get("skip_conflicts_for_provides", []))
    provides = {provide for provide in meta.get("provides", []) if provide not in skipped}
    conflicts.update(provides)
    conflicts.add(bundle_conflict)
    if name.endswith("-gfx1151"):
        conflicts.add(name.removesuffix("-gfx1151"))
    return sorted(conflicts)


def render_array(values: list[str]) -> str:
    return " ".join(f"'{v}'" for v in values)


class Classifier:
    def __init__(self, policy: dict) -> None:
        self.policy = policy
        self.repo = policy["repo"]
        self.packages = policy["packages"]
        self.component_dirs = policy.get("aliases", {}).get("component_dirs", {})
        self.binary_prefixes = policy.get("aliases", {}).get("binary_prefixes", {})
        self.library_prefixes = policy.get("aliases", {}).get("library_prefixes", {})
        self.path_owners = policy.get("overrides", {}).get("path_owners", {})
        self.synthetic_files = policy.get("synthetic_files", {})
        self.ignore_globs = policy.get("filters", {}).get("ignore_globs", [])
        self.failures: list[Failure] = []
        self.package_files: dict[str, list[str]] = defaultdict(list)
        self.package_dirs: dict[str, set[str]] = defaultdict(set)
        self._new_class_seen: set[str] = set()

    def classify(self, relpath: str) -> str | None:
        if self.is_ignored(relpath):
            return IGNORED
        if relpath in self.path_owners:
            return self.path_owners[relpath]

        # Path prefix overrides for directories represented in the overrides map.
        for prefix, owner in self.path_owners.items():
            normalized = prefix.rstrip("/") + "/"
            if relpath.startswith(normalized):
                return owner

        candidates = set()
        path = Path(relpath)
        parts = path.parts
        if len(parts) < 2:
            return None

        # opt/rocm/... layout
        inner = parts[2:] if parts[:2] == ("opt", "rocm") else parts
        if not inner:
            return None

        top = inner[0]

        if top == "amdgcn":
            candidates.add("rocm-device-libs-gfx1151")
        elif top == "bin" and len(inner) > 1:
            name = inner[1]
            if self._is_bin_noise(inner):
                return IGNORED
            candidates.update(self._match_prefix(name, self.binary_prefixes))
        elif top == "lib" and len(inner) > 1:
            if inner[1] == "cmake" and len(inner) > 2:
                candidates.update(self._lookup_component(inner[2], relpath))
            elif inner[1] == "pkgconfig" and len(inner) > 2:
                candidates.update(self._classify_pkgconfig(inner[2]))
            elif inner[1] == "llvm":
                candidates.add("rocm-llvm-gfx1151")
            elif inner[1].startswith("python"):
                basename = path.name
                if "amd_smi" in relpath or "amdsmi" in basename:
                    candidates.add("amdsmi-gfx1151")
                elif basename.startswith("migraphx"):
                    candidates.add("migraphx-gfx1151")
                else:
                    self._record_new_class(
                        relpath,
                        "Python site-packages subtree under opt/rocm/lib is not mapped",
                        "Add a path ownership override or define a new Python-facing ROCm package mapping.",
                    )
                    return None
            else:
                candidates.update(self._classify_library(path.name))
        elif top in {"include", "share", "libexec", "clients", "tests"} and len(inner) > 1:
            if top == "include" and len(inner) == 2 and "." in inner[1]:
                candidates.update(self._classify_include_file(inner[1]))
            elif top == "share" and inner[1] == "pkgconfig" and len(inner) > 2:
                candidates.update(self._classify_pkgconfig(inner[2]))
            else:
                candidates.update(self._lookup_component(inner[1], relpath))

        candidates.discard(None)
        if len(candidates) == 1:
            return next(iter(candidates))
        if len(candidates) > 1:
            self.failures.append(
                Failure(
                    "ambiguous",
                    relpath,
                    f"matched multiple package candidates: {', '.join(sorted(candidates))}",
                    "Add an exact path owner override or tighten the component/prefix mapping.",
                )
            )
            return None

        self.failures.append(
            Failure(
                "unmapped",
                relpath,
                "no ownership rule matched this path",
                "Add a path override, binary prefix rule, library prefix rule, or component alias.",
            )
        )
        return None

    def is_ignored(self, relpath: str) -> bool:
        return any(fnmatch.fnmatch(relpath, pattern) for pattern in self.ignore_globs)

    def _lookup_component(self, component: str, relpath: str) -> set[str]:
        owner = self.component_dirs.get(component)
        if owner:
            return {owner}
        self._record_new_class(
            component,
            f"component directory from {relpath} has no package alias",
            "Add this component to aliases.component_dirs or an exact path override if it belongs to an existing package.",
        )
        return set()

    def _record_new_class(self, subject: str, detail: str, hint: str) -> None:
        if subject in self._new_class_seen:
            return
        self._new_class_seen.add(subject)
        self.failures.append(Failure("new_class", subject, detail, hint))

    @staticmethod
    def _match_prefix(name: str, mapping: dict[str, str]) -> set[str]:
        exact = {pkg for prefix, pkg in mapping.items() if name == prefix}
        if exact:
            return exact
        matched = [(prefix, pkg) for prefix, pkg in mapping.items() if name.startswith(prefix)]
        if not matched:
            return set()
        longest = max(len(prefix) for prefix, _pkg in matched)
        return {pkg for prefix, pkg in matched if len(prefix) == longest}

    @staticmethod
    def _is_bin_noise(inner_parts: tuple[str, ...]) -> bool:
        name = inner_parts[1]
        noisy_suffixes = (".hip", ".yaml", ".txt", ".data", ".py", ".cmake")
        noisy_fragments = ("test", "bench", "perf", "validate")
        if name.endswith(noisy_suffixes):
            return True
        if any(fragment in name.lower() for fragment in noisy_fragments):
            return True
        if len(inner_parts) > 2:
            if inner_parts[1].startswith("gfx"):
                return True
            if inner_parts[2].endswith(noisy_suffixes):
                return True
        return False

    def _classify_library(self, filename: str) -> set[str]:
        stem = filename
        if stem.startswith("lib"):
            stem = stem[3:]
        stem = stem.split(".so")[0].split(".a")[0]
        return self._match_prefix(stem, self.library_prefixes)

    def _classify_pkgconfig(self, filename: str) -> set[str]:
        stem = filename.removesuffix(".pc")
        candidates = self._match_prefix(stem, self.library_prefixes)
        if candidates:
            return candidates
        return self._lookup_component(stem, f"pkgconfig/{filename}")

    def _classify_include_file(self, filename: str) -> set[str]:
        stem = filename
        for suffix in (".hpp", ".h", ".f03", ".f", ".mod"):
            if stem.endswith(suffix):
                stem = stem[: -len(suffix)]
                break
        candidates = self._match_prefix(stem, self.library_prefixes)
        if candidates:
            return candidates
        return self._lookup_component(stem, f"include/{filename}")


ELF_MAGIC = b"\x7fELF"
ELFCLASS64 = 2
ELFDATA2LSB = 1
SHT_DYNAMIC = 6
DT_NULL = 0
DT_NEEDED = 1


class ElfError(ValueError):
    pass


def is_elf(path: Path) -> bool:
    try:
        with path.open("rb") as fh:
            return fh.read(4) == ELF_MAGIC
    except OSError:
        return False


def read_elf_sections(path: Path) -> list[dict]:
    """Return the section headers of a little-endian ELF64 file.

    Only the headers and the section-name string table are read, so this stays
    cheap on multi-GiB payload files.
    """
    with path.open("rb") as fh:
        ident = fh.read(16)
        if ident[:4] != ELF_MAGIC:
            raise ElfError(f"{path} is not an ELF file")
        if ident[4] != ELFCLASS64 or ident[5] != ELFDATA2LSB:
            raise ElfError(f"{path} is not a little-endian ELF64 file")
        header = fh.read(48)
        if len(header) < 48:
            raise ElfError(f"{path} has a truncated ELF header")
        (e_shoff,) = struct.unpack_from("<Q", header, 0x28 - 16)
        e_shentsize, e_shnum, e_shstrndx = struct.unpack_from("<HHH", header, 0x3A - 16)
        if e_shoff == 0:
            return []

        def section_header(index: int) -> dict:
            fh.seek(e_shoff + index * e_shentsize)
            raw = fh.read(64)
            if len(raw) < 64:
                raise ElfError(f"{path} has a truncated section header table")
            name, sh_type, _flags, _addr, offset, size, link, _info, _align, _entsize = struct.unpack(
                "<IIQQQQIIQQ", raw
            )
            return {"name_offset": name, "type": sh_type, "offset": offset, "size": size, "link": link}

        if e_shnum == 0:
            e_shnum = section_header(0)["size"]
        if e_shstrndx == 0xFFFF:
            e_shstrndx = section_header(0)["link"]
        sections = [section_header(index) for index in range(e_shnum)]
        if e_shstrndx >= len(sections):
            raise ElfError(f"{path} has no usable section-name string table")
        strtab = sections[e_shstrndx]
        fh.seek(strtab["offset"])
        names = fh.read(strtab["size"])
    for section in sections:
        section["name"] = c_string(names, section["name_offset"])
    return sections


def c_string(table: bytes, offset: int) -> str:
    end = table.find(b"\0", offset)
    return table[offset : end if end >= 0 else None].decode("utf-8", "replace")


def read_section_bytes(path: Path, section: dict) -> bytes:
    with path.open("rb") as fh:
        fh.seek(section["offset"])
        return fh.read(section["size"])


def read_elf_section(path: Path, name: str) -> bytes | None:
    for section in read_elf_sections(path):
        if section["name"] == name:
            return read_section_bytes(path, section)
    return None


def read_elf_needed(path: Path) -> list[str]:
    """Return the DT_NEEDED entries of an ELF64 shared object or executable."""
    sections = read_elf_sections(path)
    needed: list[str] = []
    for section in sections:
        if section["type"] != SHT_DYNAMIC:
            continue
        dynamic = read_section_bytes(path, section)
        dynstr = read_section_bytes(path, sections[section["link"]])
        for offset in range(0, len(dynamic) - 15, 16):
            tag, value = struct.unpack_from("<qQ", dynamic, offset)
            if tag == DT_NULL:
                break
            if tag == DT_NEEDED:
                needed.append(c_string(dynstr, value))
    return needed


def msgpack_decode(data: bytes) -> object:
    """Decode the msgpack subset that TheRock writes into .rocm_kpack_ref markers."""

    def take(pos: int, count: int) -> tuple[bytes, int]:
        if pos + count > len(data):
            raise ValueError("truncated msgpack data")
        return data[pos : pos + count], pos + count

    def unpack(fmt: str, pos: int) -> tuple[int, int]:
        raw, pos = take(pos, struct.calcsize(fmt))
        return struct.unpack(fmt, raw)[0], pos

    def decode_str(pos: int, length: int) -> tuple[str, int]:
        raw, pos = take(pos, length)
        return raw.decode("utf-8"), pos

    def decode_array(pos: int, length: int) -> tuple[list, int]:
        items = []
        for _ in range(length):
            item, pos = decode(pos)
            items.append(item)
        return items, pos

    def decode_map(pos: int, length: int) -> tuple[dict, int]:
        items = {}
        for _ in range(length):
            key, pos = decode(pos)
            value, pos = decode(pos)
            items[key] = value
        return items, pos

    lengths = {0xC4: ">B", 0xC5: ">H", 0xC6: ">I", 0xD9: ">B", 0xDA: ">H", 0xDB: ">I", 0xDC: ">H", 0xDD: ">I", 0xDE: ">H", 0xDF: ">I"}
    ints = {0xCC: ">B", 0xCD: ">H", 0xCE: ">I", 0xCF: ">Q", 0xD0: ">b", 0xD1: ">h", 0xD2: ">i", 0xD3: ">q"}

    def decode(pos: int) -> tuple[object, int]:
        raw, pos = take(pos, 1)
        byte = raw[0]
        if byte <= 0x7F:
            return byte, pos
        if byte >= 0xE0:
            return byte - 0x100, pos
        if byte <= 0x8F:
            return decode_map(pos, byte & 0x0F)
        if byte <= 0x9F:
            return decode_array(pos, byte & 0x0F)
        if byte <= 0xBF:
            return decode_str(pos, byte & 0x1F)
        if byte == 0xC0:
            return None, pos
        if byte in (0xC2, 0xC3):
            return byte == 0xC3, pos
        if byte in ints:
            return unpack(ints[byte], pos)
        if byte in lengths:
            length, pos = unpack(lengths[byte], pos)
            if byte <= 0xC6:
                return take(pos, length)
            if byte <= 0xDB:
                return decode_str(pos, length)
            if byte <= 0xDD:
                return decode_array(pos, length)
            return decode_map(pos, length)
        raise ValueError(f"unsupported msgpack type byte 0x{byte:02x}")

    value, _pos = decode(0)
    return value


def gfx_arch(policy: dict) -> str:
    return policy.get("payload", {}).get("gfx_arch") or policy["repo"].get("suffix", "").lstrip("-")


def resolve_kpack_search_path(elf_relpath: str, search_path: str, arch: str) -> str:
    search_path = search_path.replace(GFXARCH_TOKEN, arch)
    if search_path.startswith("/"):
        return posixpath.normpath(search_path.lstrip("/"))
    return posixpath.normpath(posixpath.join(posixpath.dirname(elf_relpath), search_path))


def check_kpack_refs(root: Path, policy: dict, owners: dict[str, str | None], failures: list[Failure]) -> None:
    """Fail when a kpack-split ELF cannot reach its device-code archive.

    TheRock kpack-split libraries carry no device code on disk. The HIP runtime
    loads their kernels from the archives named in the .rocm_kpack_ref marker,
    which resolve relative to the library directory. An archive that is
    missing, ignored, or owned by a package that the library's package does not
    depend on directly would render and build cleanly and then fail at the
    first kernel launch.
    """
    arch = gfx_arch(policy)
    packages = policy["packages"]
    hint = (
        "Own the archive with an exact [overrides.path_owners] entry, keep it out of "
        "[filters].ignore_globs, and make the library's package depend directly on the archive's owner."
    )
    for relpath, owner in sorted(owners.items()):
        if owner is None or owner == IGNORED:
            continue
        path = root / relpath
        if path.is_symlink() or not path.is_file() or not is_elf(path):
            continue
        try:
            marker = read_elf_section(path, KPACK_REF_SECTION)
        except (ElfError, OSError, struct.error) as exc:
            failures.append(Failure("kpack_ref_unowned", relpath, f"could not read ELF sections: {exc}", hint))
            continue
        if marker is None:
            continue
        try:
            decoded = msgpack_decode(marker)
            search_paths = decoded.get("kpack_search_paths") if isinstance(decoded, dict) else None
            if not search_paths or not isinstance(search_paths, list) or not all(isinstance(p, str) for p in search_paths):
                raise ValueError("kpack_search_paths is missing or is not a list of strings")
        except (ValueError, UnicodeDecodeError) as exc:
            failures.append(Failure("kpack_ref_unowned", relpath, f"unreadable {KPACK_REF_SECTION} marker: {exc}", hint))
            continue

        archives = [resolve_kpack_search_path(relpath, item, arch) for item in search_paths]
        present = [archive for archive in archives if archive in owners]
        if not present:
            failures.append(
                Failure(
                    "kpack_ref_unowned",
                    relpath,
                    f"{owner} ships no device code on disk, and no kpack archive from {', '.join(archives)} is in the scanned payload",
                    hint,
                )
            )
            continue
        allowed = {owner, *packages.get(owner, {}).get("depends", [])}
        for archive in present:
            archive_owner = owners[archive]
            if archive_owner is None:
                continue  # already reported as UNMAPPED_COMPONENT
            if archive_owner == IGNORED:
                detail = f"kpack archive {archive} is ignored by policy filters, so {owner} would ship no device code"
            elif archive_owner not in allowed:
                detail = f"kpack archive {archive} is owned by {archive_owner}, which {owner} does not depend on"
            else:
                continue
            failures.append(Failure("kpack_ref_unowned", relpath, detail, hint))


def derive_soname_depends(
    root: Path,
    policy: dict,
    package_files: dict[str, list[str]],
    failures: list[Failure],
    *,
    skip_missing: bool = False,
) -> dict[str, list[str]]:
    """Render pacman soname depends such as ``libprotobuf.so=36.1.0-64`` from staged ELF files.

    Each ``soname_depends`` entry names a staged ELF and a library stem. The
    rendered depend takes its version from that ELF's DT_NEEDED entry, so a
    rebuild against a different protobuf moves the depend without a policy
    edit. Packages with no payload in the staged root are skipped.

    ``skip_missing`` turns a missing staged ELF into a warning and omits that
    depend. It exists only for a dry render taken before the ELF is built (the
    MIGraphX parsers are added to the stage after the TheRock payload), and
    output rendered with it must not be committed.
    """
    derived: dict[str, list[str]] = {}
    for pkg, meta in sorted(policy["packages"].items()):
        entries = meta.get("soname_depends", [])
        if not entries or not package_files.get(pkg):
            continue
        for entry in entries:
            library = entry["library"]
            stem = entry["needed"]
            hint = f"Rebuild {library} against the intended {stem}, or fix [packages.\"{pkg}\"].soname_depends."
            path = root / library
            if not path.is_file():
                if skip_missing:
                    print(f"SONAME_DEPEND_SKIPPED: {pkg}: staged ELF {library} is missing", file=sys.stderr)
                    continue
                failures.append(Failure("soname_depend", pkg, f"staged ELF {library} is missing", hint))
                continue
            try:
                needed = read_elf_needed(path)
            except (ElfError, OSError, struct.error) as exc:
                failures.append(Failure("soname_depend", pkg, f"could not read DT_NEEDED from {library}: {exc}", hint))
                continue
            versions = sorted({name.removeprefix(f"{stem}.") for name in needed if name.startswith(f"{stem}.")})
            if len(versions) != 1:
                failures.append(
                    Failure(
                        "soname_depend",
                        pkg,
                        f"{library} needs {len(versions)} {stem} SONAMEs; DT_NEEDED: {', '.join(needed) or '(none)'}",
                        hint,
                    )
                )
                continue
            derived.setdefault(pkg, []).append(f"{stem}={versions[0]}-64")
    return derived


def walk_scan_roots(root: Path, scan_roots: list[str]) -> list[str]:
    relpaths: list[str] = []
    for scan_root in scan_roots:
        start = root / scan_root
        if not start.exists():
            continue
        for current, dirs, files in os.walk(start, topdown=True, followlinks=False):
            dirs.sort()
            files.sort()
            for file_name in files:
                full = Path(current) / file_name
                relpaths.append(full.relative_to(root).as_posix())
            for dir_name in dirs:
                full = Path(current) / dir_name
                if full.is_symlink():
                    relpaths.append(full.relative_to(root).as_posix())
    relpaths.sort()
    return relpaths


def ensure_package_metadata(packages: dict, owners: set[str], failures: list[Failure]) -> None:
    for owner in sorted(owners):
        if owner not in packages:
            failures.append(
                Failure(
                    "missing_pkg_meta",
                    owner,
                    "a file was assigned to a package that has no metadata definition",
                    "Add a [packages.<name>] entry to the policy file.",
                )
            )


def render_pkgbuild(
    policy: dict,
    package_files: dict[str, list[str]],
    output_dir: Path,
    template_path: Path,
    render_meta: dict[str, str],
) -> None:
    template = read_template(template_path)
    pkg_defs = policy["packages"]
    pkg_names = sorted(pkg for pkg, meta in pkg_defs.items() if meta.get("fileless") or package_files.get(pkg))
    pkgname_block = "\n".join(f"  '{name}'" for name in pkg_names)
    license_block = render_array(policy["repo"]["license"])
    package_functions: list[str] = []
    bundle_conflict = policy["repo"]["bundle_conflict"]

    for pkg in pkg_names:
        meta = pkg_defs[pkg]
        provides = meta.get("provides", [])
        replaces = meta.get("replaces", [])
        depends = meta.get("depends", [])
        conflicts = derive_pkg_conflicts(pkg, meta, bundle_conflict)
        body = [
            f"package_{pkgfunc_name(pkg)}() {{",
            f"    pkgdesc='{meta['desc']}'",
            f"    provides=({render_array(provides)})" if provides else "    provides=()",
            f"    conflicts=({render_array(conflicts)})" if conflicts else "    conflicts=()",
        ]
        if replaces:
            body.append(f"    replaces=({render_array(replaces)})")
        body.append(f"    depends=({render_array(depends)})" if depends else "    depends=()")
        if meta.get("fileless"):
            body.append("    return 0")
        else:
            body.extend(
                [
                    "    _require_therock_root",
                    f"    _copy_from_filelist '{pkg}'",
                ]
            )
            for command in meta.get("post_copy_commands", []):
                body.append(f"    {command}")
            synthetic = policy.get("synthetic_files", {}).get(pkg, [])
            for entry in synthetic:
                text = entry["text"]
                body.append(f"    install -Dm644 /dev/stdin \"${{pkgdir}}/{entry['path']}\" <<'EOF'")
                body.append(text.rstrip("\n"))
                body.append("EOF")
        body.append("}")
        package_functions.append("\n".join(body))

    rendered = (
        template.replace("{{pkgbase}}", policy["repo"]["pkgbase"])
        .replace("{{pkgname_block}}", pkgname_block)
        .replace("{{pkgver}}", render_meta["pkgver"])
        .replace("{{pkgrel}}", str(policy["repo"].get("pkgrel", 1)))
        .replace("{{license_block}}", license_block)
        .replace("{{url}}", policy["repo"]["url"])
        .replace("{{recipe_repo_url}}", render_meta["recipe_repo_url"])
        .replace("{{recipe_subdir}}", render_meta["recipe_subdir"])
        .replace("{{recipe_author}}", render_meta["recipe_author"])
        .replace("{{recipe_commit}}", render_meta["recipe_commit"])
        .replace("{{recipe_date}}", render_meta["recipe_date"])
        .replace("{{package_functions}}", "\n\n".join(package_functions))
    )
    (output_dir / "PKGBUILD").write_text(rendered)


def write_filelists(package_files: dict[str, list[str]], output_dir: Path) -> None:
    filelist_dir = output_dir / "filelists"
    filelist_dir.mkdir(parents=True, exist_ok=True)
    expected = {f"{pkg}.txt" for pkg in package_files}
    for path in filelist_dir.glob("*.txt"):
        if path.name not in expected:
            path.unlink()
    for pkg, files in sorted(package_files.items()):
        (filelist_dir / f"{pkg}.txt").write_text("\n".join(sorted(files)) + "\n")


def write_manifest(
    policy: dict,
    package_files: dict[str, list[str]],
    output_dir: Path,
    render_meta: dict[str, str],
) -> None:
    def package_entry(meta: dict, *, files: int, rendered: bool) -> dict[str, object]:
        entry: dict[str, object] = {
            "files": files,
            "provides": meta.get("provides", []),
            "depends": meta.get("depends", []),
            "fileless": bool(meta.get("fileless")),
            "rendered": rendered,
        }
        if meta.get("replaces"):
            entry["replaces"] = meta["replaces"]
        return entry

    manifest = {
        "pkgbase": policy["repo"]["pkgbase"],
        "pkgver": render_meta["pkgver"],
        "upstream_pkgver": policy["repo"]["pkgver"],
        "recipe": {
            "repo_url": render_meta["recipe_repo_url"],
            "subdir": render_meta["recipe_subdir"],
            "author": render_meta["recipe_author"],
            "commit": render_meta["recipe_commit"],
            "date": render_meta["recipe_date"],
        },
        "packages": {
            pkg: package_entry(policy["packages"][pkg], files=len(files), rendered=True)
            for pkg, files in sorted(package_files.items())
        },
    }
    for pkg, meta in sorted(policy["packages"].items()):
        if pkg not in manifest["packages"]:
            manifest["packages"][pkg] = package_entry(
                meta,
                files=0,
                rendered=bool(meta.get("fileless")),
            )
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Generate split-package scaffolding from a TheRock install tree")
    parser.add_argument("--root", default="/", help="filesystem root containing opt/rocm")
    parser.add_argument("--policy", default="policies/therock-packages.toml", help="policy TOML file")
    parser.add_argument("--output", default="generated/therock/therock-gfx1151", help="output directory")
    parser.add_argument("--template", default="templates/PKGBUILD.in", help="PKGBUILD template")
    parser.add_argument("--pkgver-override", default="", help="override pkgver rendered into the generated PKGBUILD")
    parser.add_argument("--recipe-repo-url", default="", help="recipe repository URL for attribution")
    parser.add_argument("--recipe-subdir", default="", help="recipe subdirectory within the recipe repository")
    parser.add_argument("--recipe-author", default="", help="recipe author attribution string")
    parser.add_argument("--recipe-commit", default="", help="recipe commit used for this render")
    parser.add_argument("--recipe-date", default="", help="recipe commit date in YYYYMMDD form")
    parser.add_argument(
        "--skip-missing-soname-depends",
        action="store_true",
        help="warn instead of failing when a soname_depends ELF is not staged yet (dry renders only)",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    repo_root = Path(__file__).resolve().parents[1]
    policy_path = (repo_root / args.policy).resolve()
    template_path = (repo_root / args.template).resolve()
    output_dir = (repo_root / args.output).resolve()
    root = Path(args.root).resolve()

    policy = load_policy(policy_path)
    render_meta = {
        "pkgver": args.pkgver_override or policy["repo"]["pkgver"],
        "recipe_repo_url": args.recipe_repo_url or "UNKNOWN",
        "recipe_subdir": args.recipe_subdir or ".",
        "recipe_author": args.recipe_author or "UNKNOWN",
        "recipe_commit": args.recipe_commit or "UNKNOWN",
        "recipe_date": args.recipe_date or "UNKNOWN",
    }
    classifier = Classifier(policy)
    relpaths = walk_scan_roots(root, policy["repo"]["scan_roots"])

    owners: dict[str, str | None] = {}
    for relpath in relpaths:
        owner = classifier.classify(relpath)
        owners[relpath] = owner
        if owner and owner != IGNORED:
            classifier.package_files[owner].append(relpath)

    ensure_package_metadata(policy["packages"], set(classifier.package_files), classifier.failures)
    check_kpack_refs(root, policy, owners, classifier.failures)
    derived = derive_soname_depends(
        root,
        policy,
        classifier.package_files,
        classifier.failures,
        skip_missing=args.skip_missing_soname_depends,
    )
    for pkg, extra in derived.items():
        meta = policy["packages"][pkg]
        meta["depends"] = [*meta.get("depends", []), *extra]

    if classifier.failures:
        for failure in classifier.failures:
            print(failure.render(), file=sys.stderr)
        return 2

    output_dir.mkdir(parents=True, exist_ok=True)
    write_filelists(classifier.package_files, output_dir)
    write_manifest(policy, classifier.package_files, output_dir, render_meta)
    render_pkgbuild(policy, classifier.package_files, output_dir, template_path, render_meta)
    print(f"Generated {policy['repo']['pkgbase']} scaffolding in {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
