"""Path-resolution helper for app/files.py. This is the only thing standing
between a logged-in client and the raw filesystem, so it errs toward
rejecting anything ambiguous rather than trying to be clever.
"""
import os


def resolve_within_root(root, relpath):
    """Resolve relpath against root and return the absolute path only if it
    is a real, existing file that stays inside root. Returns None otherwise
    (traversal attempt, symlink escape, missing file, or a directory).
    """
    root_real = os.path.realpath(root)
    candidate_real = os.path.realpath(os.path.join(root, relpath))

    if candidate_real != root_real and not candidate_real.startswith(root_real + os.sep):
        return None
    if not os.path.isfile(candidate_real):
        return None
    return candidate_real
