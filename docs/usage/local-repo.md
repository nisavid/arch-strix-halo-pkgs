# Local Repo Usage

The intended first-pass installation story is a local pacman repo on an Arch
system.

That keeps installs, repairs, and upgrades inside normal package-manager
behavior instead of long one-off `pacman -U` command lists.

## Build A Package

Build any package directory with normal `makepkg` usage:

```bash
(cd packages/<pkgname> && makepkg -f)
```

Do that for each package you want to publish into the local repo.

## Publish The Repo

The canonical package output inside the checkout is `repo/x86_64`. Pacman
should consume a world-traversable published copy, not a path buried inside a
private home directory.

Recommended published path:

- `/srv/pacman/strix-halo-gfx1151/x86_64`

Publish the current repo contents like this:

```bash
sudo install -d /srv/pacman/strix-halo-gfx1151
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
```

## Enable The Repo In Pacman

Create the repo stanza:

```bash
printf '%s\n' \
  '[strix-halo-gfx1151]' \
  'SigLevel = Optional TrustAll' \
  'Server = file:///srv/pacman/strix-halo-gfx1151/x86_64' \
  | sudo tee /etc/pacman.d/strix-halo-gfx1151.conf >/dev/null
```

Include it from `/etc/pacman.conf` if it is not already included:

```bash
grep -qxF 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' /etc/pacman.conf \
  || echo 'Include = /etc/pacman.d/strix-halo-gfx1151.conf' \
  | sudo tee -a /etc/pacman.conf >/dev/null
```

Refresh metadata:

```bash
sudo pacman -Sy
```

## Install The Stack

Use normal package-manager commands once the repo is enabled.

Example:

```bash
paru -S rocm-gfx1151 lemonade llama.cpp-hip-gfx1151 python-vllm-rocm-gfx1151
```

Prefer `paru` for everyday interactive use if that is already your habit. Drop
to raw `pacman` only when you need low-level repair or rehearsal behavior.

## Refresh The Repo After A Rebuild

After rebuilding a package, refresh the canonical repo metadata:

```bash
python tools/update_pacman_repo.py --package-dir packages/<pkgname> --repo-dir repo/x86_64
```

Then republish:

```bash
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
sudo pacman -Sy
```

## First Cutover

For an initial migration from an older monolithic replacement such as
`rocm-gfx1151-bin`:

1. publish the full replacement closure into the local repo
2. rehearse the transaction against a fake root
3. perform the live install from the local repo
4. run smoke tests immediately

That is the bring-up pattern used for the first successful cutover of this
stack.

## Repair Loop

For a narrow post-cutover fix:

```bash
python tools/update_pacman_repo.py --package-dir packages/<pkgname> --repo-dir repo/x86_64
sudo rsync -a --delete repo/x86_64/ /srv/pacman/strix-halo-gfx1151/x86_64/
sudo pacman -Sy
paru -S <pkgname>
```

Then rerun only the smoke tests that matter for the repaired package.
