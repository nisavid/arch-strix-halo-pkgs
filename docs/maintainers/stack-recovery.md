# Prepare deployed-state rollback

`tools/stack_recovery.py` inventories the deployed package identities, retains
exact archives and selected configuration, verifies those retained files
offline, and writes a separate-root restore handoff. It never installs,
downloads, runs package hooks, starts services, attaches a GPU, or snapshots.

This procedure prepares a trial recovery capture for
[the recovery work](https://github.com/nisavid/arch-strix-halo-pkgs/issues/106).
The final pre-activation capture and root snapshot remain
[activation work](https://github.com/nisavid/arch-strix-halo-pkgs/issues/116).
A trial file capture is neither a final snapshot nor a successful restore.

## Inputs and entry conditions

Use Arch with Python 3.11 or newer, pacman, pacman-conf, findmnt, and bsdtar/libarchive.
Operate on an owner-quiesced package/configuration state. Repeated observations
detect changes; they do not provide an atomic filesystem snapshot or stop
another process from modifying inputs. Reobserve after any relevant change.

Keep reports, requests, bundles, digests, and handoffs in an existing mode-0700
owner-controlled directory outside Git. The tool refuses existing outputs,
symlink paths, public output directories, and Git checkouts. It writes files
with mode 0600 and bundles with mode 0700. Treat the entire bundle as private:
configuration can contain secrets, and inventory reveals host state. Public
reports contain aggregate counts and reviewed source identities only.

The package baseline is the whole `pacman -Q` inventory from the source root's
standard `var/lib/pacman` database, including the host's
partially upgraded state. Versions are matched from `.PKGINFO`, never from
filenames or the current sync databases. Architecture must be accepted by the
source root's pacman configuration or be `any`. This includes configured
microarchitecture variants such as `x86_64_v4`. That accepted set is pinned in
the bundle; offline verification does not consult the live configuration.
For a source root other than `/`, its pacman configuration must be
self-contained: `Include` directives are refused because the config reader
would otherwise resolve their paths in the caller's filesystem. Live-root
configuration includes follow the deployed host's normal pacman semantics.
Discovery checks retained archives, not their signatures
or payload digests. Capture subsequently hashes and retains the selected bytes.
Never substitute a newer package or silently narrow the baseline to this
repository's packages when an exact archive is missing.
Queries explicitly bind that database and an empty read-only configuration;
host configuration cannot redirect a separate-root query to another database.
A nonstandard source database needs an explicit procedure/tool extension before
capture rather than silently substituting the standard database.
Matching metadata does not prove an archive was the original installed build
or that package-owned files remain unmodified. The owner restore proof must
check those files where the complete target requires byte equality.

Select configuration explicitly, using root-relative paths. Include the
pacman configuration and repository includes, relevant account and service
configuration, the selected serving family's persisted state, and the pacman
local database when its install reasons and other database metadata must be
restored. Package names and versions alone do not retain install reasons.
The operator decides the selection and any exclusions for the actual
transaction; a tool success proves only that selection's retained files.

Directories are captured recursively. Regular files, directories, and contained
symlinks are supported, with numeric ownership, modes, contents, Linux POSIX
ACLs, and extended attributes checked against the configuration archive.
Libarchive retains filesystem flags in that archive. Hardlinked or special
configuration files, escaping links, unreadable files/metadata, and overlapping
selections are refused. Protected configuration remains an owner-run capture;
do not work around unreadable files by omitting them.

## Inventory and capture

Set `private_dir` to the private working directory and `source_root` to the
deployed root. Bindings belong in the private request, never in committed
instructions or a public issue comment.

```sh
python tools/stack_recovery.py inventory \
  --root "$source_root" --output "$private_dir/inventory.json"
```

The default discovery stores are `/var/cache/pacman/pkg` and
`/srv/pacman/strix-halo-gfx1151/x86_64`. Repeat `--archive-dir` to supply an
explicit set instead. Archive discovery is nonrecursive. Inventory exits 10
when exact archives are missing and still writes the private report; exit 0
means every installed identity has a matching metadata candidate. A refusal
exits 1. Inventory neither downloads nor copies artifacts.

Write a private request with `purpose: "trial"` and a nonempty `paths` array.
For example, a synthetic fixture can select `{"purpose":"trial","paths":["etc"]}`;
the real host selection must follow the preceding input requirements.

```sh
python tools/stack_recovery.py capture \
  --inventory "$private_dir/inventory.json" \
  --request "$private_dir/request.json" \
  --output "$private_dir/trial-bundle"
```

Capture refuses incomplete or changed installed inventories, archive identity
changes, unreadable inputs, configuration drift, and unsafe destinations.
It retains matching detached signatures when present without claiming their
authenticity. A failed capture removes its newly created incomplete output;
it never overwrites an existing bundle.

Retain the returned `manifest_sha256` separately as `manifest_digest`. This
digest pins the manifest and all mandatory file digests. Do not recompute it
from a changed bundle to make verification pass. A hash proves correspondence
to those selected bytes; it is not an independent signature, trust decision,
or proof that package contents are safe.

```sh
python tools/stack_recovery.py verify \
  --bundle "$private_dir/trial-bundle" --digest "$manifest_digest"
```

Verification reads only retained artifacts and compares their hashes, package
identities, complete inventory coverage, and selected configuration metadata.
It can succeed after the original source disappears. Its `verified-files`
result establishes file retention, not an installed system or backend health.

## Prepare the owner restore handoff

Create a new empty mode-0700 workspace outside Git and existing build roots.
Choose a nonexistent direct-child root in it. Neither an existing empty root
nor another worker's workspace is accepted. The bundle and handoff stay
outside this workspace. The tool records its device/inode identity and leaves
the target root uncreated.

Provide a private offline pacman configuration containing only `[options]`,
`Architecture`, `LocalFileSigLevel`, and optionally `SigLevel`. Includes,
repository stanzas, mirrors, alternate path settings, and other directives are
refused. The architecture list must cover every retained package architecture.
For a capture containing `x86_64_v4` packages, `Architecture = auto` alone is
insufficient; include the configured variant explicitly. The owner must choose
an explicit local signature policy; the tool
does not choose a weaker one. For example, `LocalFileSigLevel = Required
TrustedOnly` requires usable retained signatures and an isolated trusted
keyring. Missing signature/trust material remains a gate even when the file
hashes match.

```sh
python tools/stack_recovery.py prepare-restore \
  --bundle "$private_dir/trial-bundle" --digest "$manifest_digest" \
  --workspace "$restore_workspace" --root "$restore_root" \
  --pacman-config "$private_dir/offline-pacman.conf" \
  --output "$private_dir/restore-handoff.json"
```

The private handoff contains argument arrays for pacman archive installation,
configuration extraction, and package inventory comparison. Database, cache,
log, keyring, and custom hook paths are bound to the proposed root. It executes
none of them. A preparation result is not an execution-time safety guard.
Immediately before any mutation, the owner must reverify the separately pinned
bundle digest and config digest, recheck workspace identity and emptiness, and
establish an isolated execution environment with no live mounts, endpoints,
network, GPU, or service exposure. Rerun preparation if those inputs change.
Do not execute the argument arrays blindly on the host.

The owner sets up the isolated root and signature/keyring prerequisites, runs
the package transaction, and restores the selected configuration and metadata.
Inspect extraction destinations after package installation: package-created
links must not redirect configuration writes outside the isolated root.
The invocation environment and containment are part of the owner-run proof.
This tool does not provide a privileged executor or certify that containment.

Compare the entire restored package list to `installed` in the pinned
manifest, then compare the selected configuration contents, ownership, modes,
links, ACLs, and xattrs. Prove required service/backend health in the isolated
environment without exposing a mixed endpoint. Package equality alone cannot
establish that account setup, hooks, persisted state, and services recovered.
Failed or unknown restoration stays drained and open in the owning issue,
linked to its recovery/incident successor.

## Completion and activation join

Report the reviewed tooling revision, aggregate missing-input counts, file
verification result, actual isolated restore evidence, and remaining gates
separately. Keep private commands, package-by-package records, and secret bytes
out of Git and public trackers. Do not mark the recovery issue complete from
tool tests or a prepared handoff.

The activation owner consumes this published procedure and its reviewed
revision, makes a fresh exact capture immediately before the activation
transaction, and takes the pre-activation btrfs root snapshot. The current CLI
labels captures as trials; the activation record must explicitly bind its
timing-correct final capture and snapshot rather than treating that label as
acceptance evidence. No snapshot is taken by these commands.

Observe the actual mount layout and transaction writes. A root snapshot does
not cover separately mounted boot, home, package-cache, model, or runtime
stores. Record their separate coverage or the operator's justified exclusions.
Bootable recovery, fault injection, and a signing substrate remain deferred
to [the verification adoption work](https://github.com/nisavid/arch-strix-halo-pkgs/issues/143).

For tooling changes, exercise the public CLI with `pytest
tests/test_stack_recovery.py -q`, then run the repository suite and required
reviews on the final revision. Those tests use synthetic package/configuration
inputs and a fake read-only pacman boundary. They establish no host restoration,
snapshot, installed smoke, or live scenario evidence.
