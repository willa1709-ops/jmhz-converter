"""Verify the complete distribution against a separately pinned SHA256SUMS file."""
import argparse
from pathlib import Path
from wheel_inventory import digest


def verify(directory, approved):
    sums = directory / "SHA256SUMS.txt"
    if digest(sums) != approved:
        raise ValueError("Inventory differs from independently stored SHA-256.")
    expected, seen = {}, set()
    for line in sums.read_text(encoding="utf-8").splitlines():
        sha, name = line.split("  ", 1)
        parts = name.split("/")
        if (len(sha) != 64 or any(c not in "0123456789abcdef" for c in sha)
                or any(p in {"", ".", ".."} for p in parts) or "\\" in name or ":" in name
                or name.casefold() in seen or name == "SHA256SUMS.txt"):
            raise ValueError("Unsafe distribution inventory.")
        seen.add(name.casefold()); expected[name] = sha
    actual = {}
    for path in directory.rglob("*"):
        if path.is_symlink():
            raise ValueError("Links are not allowed in a distribution.")
        if path.is_file() and path != sums:
            actual[path.relative_to(directory).as_posix()] = digest(path)
    if actual != expected or not actual:
        raise ValueError("Missing, altered or unexpected distribution files.")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("directory", type=Path)
    parser.add_argument("--approved-sha256", required=True)
    args = parser.parse_args()
    verify(args.directory.resolve(), args.approved_sha256)
    print("Distribution matches the independent inventory pin; target acceptance is still required.")
