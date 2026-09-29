from pathlib import Path

from .workspace import EXCLUDED, files


class FileTools:
    def __init__(self, workspace, limit=12000):
        self.workspace = workspace
        self.limit = limit

    def resolve(self, name, write=False):
        relative = Path(name)
        if relative.is_absolute() or relative.drive or ".." in relative.parts:
            raise ValueError("Path must be relative and inside the workspace")
        if any(p in EXCLUDED or p.startswith(".env.") for p in relative.parts):
            raise ValueError("Protected path")
        path = self.workspace.root / relative
        current = path
        while current != self.workspace.root:
            if current.is_symlink():
                raise ValueError("Symlinks are not supported")
            current = current.parent
        resolved = path.resolve()
        if self.workspace.root not in resolved.parents:
            raise ValueError("Path outside workspace")
        if write and (resolved.suffix != ".py" or "tests" in relative.parts
                      or resolved.name.startswith("test_")
                      or resolved.name.endswith("_test.py")
                      or resolved.name in {"conftest.py", "setup.py"}):
            raise ValueError("Stage one permits source .py edits only; tests/config are read-only")
        return resolved

    def read_file(self, path):
        target = self.resolve(path)
        with target.open(encoding="utf-8") as handle:
            content = handle.read(self.limit + 1)
        return {"path": path, "content": content[:self.limit], "truncated": len(content) > self.limit}

    def search_code(self, query):
        if not isinstance(query, str) or not query:
            raise ValueError("query must be a nonempty string")
        hits = []
        length = 0
        for path in files(self.workspace.root):
            if path.stat().st_size > 1_000_000:
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except UnicodeError:
                continue
            for number, line in enumerate(lines, 1):
                if query in line:
                    hit = {"path": path.relative_to(self.workspace.root).as_posix(),
                           "line": number, "text": line[:1000]}
                    hits.append(hit)
                    length += len(str(hit))
                    if length >= self.limit:
                        return {"matches": hits, "truncated": True}
        return {"matches": hits, "truncated": False}

    def edit_file(self, path, old, new):
        target = self.resolve(path, write=True)
        if not isinstance(old, str) or not old or not isinstance(new, str):
            raise ValueError("old must be nonempty text and new must be text")
        if len(new) > 50000:
            raise ValueError("Replacement exceeds size limit")
        original = target.read_bytes().decode("utf-8")
        # read_file uses universal newlines; accept those exact snippets for CRLF sources too.
        newline = "\r\n" if "\r\n" in original and "\n" not in original.replace("\r\n", "") else "\n"
        original_text = original.replace("\r\n", "\n")
        old = old.replace("\r\n", "\n")
        new = new.replace("\r\n", "\n")
        if original_text.count(old) != 1:
            raise ValueError("old must match exactly once; read the current file before editing")
        updated = original_text.replace(old, new, 1).replace("\n", newline)
        if updated == original:
            raise ValueError("Edit makes no change")
        target.write_bytes(updated.encode("utf-8"))
        return {"path": path, "changed": True}

    def apply_edits(self, edits):
        if not isinstance(edits, list) or not 1 <= len(edits) <= 20:
            raise ValueError('Provide one to twenty edits')
        originals, staged = {}, {}
        total = 0
        for edit in edits:
            if not isinstance(edit, dict) or set(edit) != {'path', 'old', 'new'}:
                raise ValueError('Each edit needs path, old, new')
            path, old, new = edit['path'], edit['old'], edit['new']
            if not isinstance(path, str) or not isinstance(old, str) or not old or not isinstance(new, str):
                raise ValueError('Use a relative path, nonempty old text and new text')
            total += len(new)
            if total > 80000:
                raise ValueError('Batch replacement exceeds size limit')
            target = self.resolve(path, write=True)
            if target not in originals:
                originals[target] = target.read_bytes()
                staged[target] = originals[target]
            raw = staged[target].decode('utf-8')
            newline = '\r\n' if '\r\n' in raw and '\n' not in raw.replace('\r\n', '') else '\n'
            text = raw.replace('\r\n', '\n')
            old, new = old.replace('\r\n', '\n'), new.replace('\r\n', '\n')
            if text.count(old) != 1:
                raise ValueError('Every old snippet must match exactly once; no edits were applied')
            staged[target] = text.replace(old, new, 1).replace('\n', newline).encode('utf-8')
        changed = [p for p in staged if staged[p] != originals[p]]
        if not changed:
            raise ValueError('Batch makes no change')
        written = []
        try:
            for target in changed:
                written.append(target)
                target.write_bytes(staged[target])
        except OSError:
            for target in written:
                target.write_bytes(originals[target])
            raise
        return {'changed_files': [p.relative_to(self.workspace.root).as_posix() for p in changed], 'changed': True}
