"""The migration chain a deploy will actually run must resolve, and must end in one head.

On 2026-08-06 a production deploy died in the ``moltrace-migrate`` Cloud Run job with
``KeyError: '0040_action_item_ownership'``. Migration 0041 was committed at 06:02 declaring
``down_revision = "0040_action_item_ownership"``; 0040 was committed at 06:25 by a different
parallel session. The image built in that 23-minute window held a migration pointing at a parent
that was not in the commit, so alembic died while assembling the revision map — before running
anything. Nothing reached the database, and the commit that *failed* (a marketing CSS change) was
not the commit that *broke* it, which is why this has to run on every commit rather than only on
the ones that touch ``alembic/``.

Two shapes matter, and they are not equally forgiving:

* A **dangling parent** heals by itself once the sibling lands — that deploy went green again on
  the next push, so the window is narrow but silent.
* A **fork** does not heal. Two sessions branching off the same parent leave two heads, and
  ``alembic upgrade head`` then fails with "Multiple head revisions are present" on every deploy
  until somebody writes a merge revision.

The checks below use alembic's own ``ScriptDirectory``, which is the same machinery the migration
job runs, so the chain is judged by alembic's rules rather than by a reimplementation of them that
could drift. ``ScriptDirectory`` reads only the version files — it never loads ``env.py`` (which
imports the whole app) and never opens a database connection.
"""

from __future__ import annotations

import ast
import subprocess
import warnings
from pathlib import Path

import pytest
from alembic.script import ScriptDirectory

# Resolved from this file, never from the working directory: several sibling git worktrees under
# .claude/worktrees/ each carry their own full alembic/versions/ tree, and some of them hold a
# different, older chain. Anchoring here grades the checkout the test itself lives in — which is
# the one that would be built and deployed.
BACKEND_ROOT = Path(__file__).resolve().parents[1]
ALEMBIC_DIR = BACKEND_ROOT / "alembic"
VERSIONS_DIR = ALEMBIC_DIR / "versions"

_REMEDY = (
    "This usually means a migration was committed while the parent it names was still "
    "uncommitted in another session. Commit the parent migration, or repoint down_revision "
    "at a revision that is actually here."
)


def _walk() -> tuple[int, list[str]]:
    """Assemble the revision map the way the migration job does, and report it readably.

    A missing parent is announced as a UserWarning and then, two lines later in alembic's
    ``_revision_map``, re-raised as a bare ``KeyError`` naming only the revision id. The warning
    carries the far more useful text — it names the *referencing* migration too — so it is
    captured and used for the failure message.
    """
    script = ScriptDirectory(str(ALEMBIC_DIR))
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        try:
            revisions = list(script.walk_revisions())
            heads = list(script.get_heads())
        except KeyError as exc:
            missing = [str(w.message) for w in caught if "is not present" in str(w.message)]
            detail = "\n  ".join(missing) or f"revision {exc} is referenced but not present"
            raise AssertionError(
                f"The migration chain does not resolve:\n  {detail}\n\n{_REMEDY}"
            ) from exc
    unresolved = [str(w.message) for w in caught if "is not present" in str(w.message)]
    assert not unresolved, (
        "The migration chain does not resolve:\n  "
        + "\n  ".join(unresolved)
        + f"\n\n{_REMEDY}"
    )
    return len(revisions), heads


def test_every_migration_names_a_parent_that_is_present() -> None:
    """The exact failure that reached production."""
    walked, _heads = _walk()
    # A file alembic did not walk is one it could not reach from the head, or -- when two files
    # claim the same revision id -- one it silently overwrote in the map.
    assert walked == len(list(VERSIONS_DIR.glob("*.py"))), (
        f"alembic walked {walked} revisions but alembic/versions/ holds "
        f"{len(list(VERSIONS_DIR.glob('*.py')))} migration files. A migration is unreachable from "
        "the head, or two files declare the same revision id."
    )


def test_the_chain_ends_in_exactly_one_head() -> None:
    """Two heads is the shape that never heals on its own."""
    _walked, heads = _walk()
    assert len(heads) == 1, (
        f"The migration chain has {len(heads)} heads: {sorted(heads)}.\n"
        "`alembic upgrade head` fails outright when more than one head is present, and unlike a "
        "missing parent this does not fix itself when the next commit lands. Two migrations are "
        "claiming the same parent — repoint one onto the other so the chain stays linear."
    )


def test_the_chain_starts_from_exactly_one_base() -> None:
    script = ScriptDirectory(str(ALEMBIC_DIR))
    bases = list(script.get_bases())
    assert len(bases) == 1, (
        f"The migration chain has {len(bases)} bases: {sorted(bases)}. Exactly one migration may "
        "declare `down_revision = None`; a second base is a disconnected chain that will never be "
        "applied."
    )


# --------------------------------------------------------------------------- #
# Catching it before the bad commit exists, not after
# --------------------------------------------------------------------------- #
def _declared(source: str) -> tuple[str | None, list[str]]:
    """The (revision, [down_revisions]) a migration declares, read without importing it."""
    tree = ast.parse(source)
    revision: str | None = None
    down: list[str] = []
    for node in tree.body:
        if not isinstance(node, ast.Assign) or len(node.targets) != 1:
            continue
        target = node.targets[0]
        if not isinstance(target, ast.Name):
            continue
        if target.id == "revision" and isinstance(node.value, ast.Constant):
            if isinstance(node.value.value, str):
                revision = node.value.value
        elif target.id == "down_revision":
            # A merge revision names several parents as a tuple; a base names None.
            if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                down = [node.value.value]
            elif isinstance(node.value, (ast.Tuple, ast.List)):
                down = [
                    element.value
                    for element in node.value.elts
                    if isinstance(element, ast.Constant) and isinstance(element.value, str)
                ]
    return revision, down


def _git(*args: str) -> subprocess.CompletedProcess[str] | None:
    try:
        return subprocess.run(
            ["git", *args], cwd=BACKEND_ROOT, capture_output=True, text=True, timeout=60
        )
    except (OSError, subprocess.SubprocessError):
        return None


def _head_migration_sources() -> dict[str, str] | None:
    """``{path: source}`` for every migration in the HEAD commit, or None outside a checkout.

    HEAD, deliberately — not the index, and not ``git ls-files``. The convention in this repo is
    to commit with an explicit pathspec (``git commit -F msg -- <paths>``) so that parallel
    sessions don't sweep up each other's work. That means a file can be ``git add``ed and still be
    left out of the commit: the index would call it present while the tree CI checks out does not
    have it. HEAD is exactly what ``actions/checkout`` produces and what the image is built from.
    """
    listing = _git("ls-tree", "-r", "--name-only", "HEAD", "--", "alembic/versions/")
    if listing is None or listing.returncode != 0:
        return None
    sources: dict[str, str] = {}
    for name in listing.stdout.split():
        if not name.endswith(".py"):
            continue
        # "HEAD:./x" resolves x relative to this directory; "HEAD:x" would look from the repo root.
        shown = _git("show", f"HEAD:./{name}")
        if shown is not None and shown.returncode == 0:
            sources[name] = shown.stdout
    return sources


def test_a_committed_migration_never_names_an_uncommitted_parent() -> None:
    """The preventive half — the one that fails on the author's machine rather than in CI.

    In CI the checkout *is* the commit, so the walk above already tells the truth. Locally it does
    not: the parent sits on disk as another session's untracked file, so the chain looks perfect
    right up until the commit that omits it. Comparing what git tracks against what the tracked
    files reference is what turns this from a report into a warning shot.

    A migration you are still writing is untracked and referenced by nothing, so it does not trip
    this — only a *committed* migration reaching for a parent git does not have.
    """
    committed = _head_migration_sources()
    if not committed:
        pytest.skip("no readable git HEAD")

    committed_revisions = {
        revision
        for source in committed.values()
        if (revision := _declared(source)[0]) is not None
    }

    # Only consulted to explain a failure: which revisions exist on disk but not in the commit.
    on_disk: dict[str, str] = {}
    for path in VERSIONS_DIR.glob("*.py"):
        revision, _ = _declared(path.read_text(encoding="utf-8"))
        if revision:
            on_disk[revision] = path.name

    offenders: list[str] = []
    for name, source in sorted(committed.items()):
        for parent in _declared(source)[1]:
            if parent not in committed_revisions:
                hint = (
                    f" -- which is sitting uncommitted on disk as {on_disk[parent]}"
                    if parent in on_disk
                    else " -- which is nowhere in this checkout"
                )
                offenders.append(f"{Path(name).name} names parent {parent!r}{hint}")

    assert not offenders, (
        "A committed migration names a parent that is not in the commit:\n  "
        + "\n  ".join(offenders)
        + "\n\nThe deploy builds from the commit, not from your working copy, so this passes "
        "every local check and then fails in production. Commit the parent migration alongside "
        "the one that references it."
    )
