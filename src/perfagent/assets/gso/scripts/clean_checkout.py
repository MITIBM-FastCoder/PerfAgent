"""Remove Git history from a GSO agent checkout during setup. This is used to prevent reward hacking. """

import os
import subprocess
import sys
from pathlib import Path


def clean_repository(repo: Path) -> None:
    def git(*args) -> bytes:
        return subprocess.check_output(["git", *args], cwd=repo)

    # Keep branches and release tags reachable from the baseline. Some builds
    # derive their version from those tags. Work entirely on refs and objects
    # so the checked-out files, index and installed build dependencies survive.
    refs = set(git("for-each-ref", "--format=%(refname)").splitlines())
    keep = set(git("for-each-ref", "--merged=HEAD", "--format=%(refname)").splitlines())
    for ref in sorted(refs - keep):
        git("update-ref", "--no-deref", "-d", ref)

    # The image build resets a newer clone to the baseline. These pseudorefs
    # can still name the previous tip even after deleting branches and tags.
    for name in ("ORIG_HEAD", "FETCH_HEAD"):
        path = os.fsdecode(git("rev-parse", "--git-path", name).rstrip(b"\n"))
        (repo / path).unlink(missing_ok=True)
    git("reflog", "expire", "--expire=all", "--all")
    git("gc", "--prune=now", "--quiet")


def clean_checkout(repo: Path, setup_recipe: Path, reference_commit: str) -> None:
    setup_recipe.unlink(missing_ok=True)
    submodules = subprocess.check_output(
        ["git", "submodule", "foreach", "--quiet", "--recursive", 'printf "%s\\0" "$PWD"'],
        cwd=repo,
    )
    for path in submodules.split(b"\0"):
        if path:
            clean_repository(Path(os.fsdecode(path)))
    clean_repository(repo)

    # Check the object database itself. A kept pack or an alternate object
    # store could otherwise expose the answer even when no ref points to it.
    result = subprocess.check_output(
        ["git", "cat-file", "--batch-check"], cwd=repo, input=reference_commit + "\n", text=True
    )
    if result.rstrip("\n") != reference_commit + " missing":
        raise RuntimeError("GSO reference commit is still present after checkout cleanup")


if __name__ == "__main__":
    clean_checkout(Path("/testbed"), Path("/root/setup_repo.sh"), sys.argv[1])
