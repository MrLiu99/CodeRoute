import hashlib
import os
import shutil
import subprocess
from pathlib import Path


EXCLUDED = {".git", ".venv", "venv", "__pycache__", ".pytest_cache", "runs", ".env"}


def files(root):
    root = Path(root).resolve()
    for directory, dirs, names in os.walk(root, followlinks=False):
        dirs[:] = sorted(d for d in dirs if d not in EXCLUDED
                         and not Path(directory, d).is_symlink())
        for name in sorted(names):
            path = Path(directory, name)
            if name not in EXCLUDED and not name.startswith(".env.") and not path.is_symlink():
                yield path


class Workspace:
    def __init__(self, source, run_dir):
        self.source = Path(source).resolve()
        self.root = Path(run_dir).absolute().resolve() / "workspace"
        if not self.source.is_dir():
            raise ValueError("Repository directory does not exist")
        if self.root == self.source or self.source in self.root.parents:
            raise ValueError("Run output must be outside the input repository")
        self.root.mkdir(parents=True, exist_ok=False)
        for path in files(self.source):
            relative = path.relative_to(self.source)
            destination = self.root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, destination)
        self.git("init", "--quiet")
        self.git("config", "core.autocrlf", "false")
        # An index snapshot avoids changing the source repo or needing Git identity.
        self.git("add", "--all", "--force")
        self.initial_revision = self.revision()

    def git(self, *args):
        result = subprocess.run(["git", "-C", str(self.root), *args],
                                capture_output=True, text=True, encoding="utf-8",
                                errors="replace", timeout=30)
        if result.returncode:
            raise RuntimeError("Git operation failed: " + result.stderr[:2000])
        return result.stdout

    def revision(self):
        digest = hashlib.sha256()
        for path in files(self.root):
            digest.update(path.relative_to(self.root).as_posix().encode())
            digest.update(b"\0")
            digest.update(hashlib.sha256(path.read_bytes()).digest())
        return digest.hexdigest()

    def diff(self):
        # Register new source files without staging their content.
        for path in files(self.root):
            relative = path.relative_to(self.root).as_posix()
            tracked = subprocess.run(["git", "-C", str(self.root), "ls-files",
                                      "--error-unmatch", "--", relative],
                                     capture_output=True, timeout=10)
            if tracked.returncode:
                self.git("add", "--intent-to-add", "--force", "--", relative)
        return self.git("diff", "--no-ext-diff", "--no-color", "--binary")

    def modified_files(self):
        self.diff()
        return [p for p in self.git("diff", "--name-only", "-z").split("\0") if p]
