"""Capture/verify a complete offline wheelhouse. The manifest pin is external."""
import argparse
import hashlib
import json
import re
from email.parser import BytesParser
from pathlib import Path
from zipfile import ZipFile


def digest(path):
    result = hashlib.sha256()
    with path.open("rb") as stream:
        for part in iter(lambda: stream.read(1024 * 1024), b""):
            result.update(part)
    return result.hexdigest()


def inventory(directory):
    result, packages = [], set()
    for path in sorted(directory.iterdir()):
        if path.is_symlink() or not path.is_file() or path.suffix != ".whl":
            raise ValueError("Wheelhouse may contain only regular wheel files.")
        with ZipFile(path) as archive:
            names = [i for i in archive.infolist() if i.filename.endswith(".dist-info/METADATA")]
            if len(names) != 1 or names[0].file_size > 1024 * 1024:
                raise ValueError("Invalid wheel metadata.")
            metadata = BytesParser().parsebytes(archive.read(names[0]))
            name, version = metadata["Name"], metadata["Version"]
        if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._-]*", name)
                or not isinstance(version, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9.+!_-]*", version)):
            raise ValueError("Unsafe distribution name or version.")
        key = re.sub(r"[-_.]+", "-", name).lower()
        if key in packages:
            raise ValueError("Keep exactly one reviewed version/wheel per distribution and platform.")
        packages.add(key)
        result.append({"filename": path.name, "name": name, "version": version, "sha256": digest(path)})
    if not result:
        raise ValueError("Wheelhouse is empty.")
    return {"format_version": 1, "origin_review": "required_separately", "wheels": result}


def verify(directory, manifest, pin):
    if digest(manifest) != pin:
        raise ValueError("Manifest does not match independent approved SHA-256.")
    expected = json.loads(manifest.read_text(encoding="utf-8"))
    if expected != inventory(directory):
        raise ValueError("Wheelhouse differs from reviewed manifest.")
    return expected


def lock_text(manifest):
    return "\n".join("{name}=={version} --hash=sha256:{sha256}".format(**w) for w in manifest["wheels"]) + "\n"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("command", choices=["capture", "verify"])
    parser.add_argument("directory", type=Path)
    parser.add_argument("manifest", type=Path)
    parser.add_argument("--approved-sha256")
    args = parser.parse_args()
    if args.command == "capture":
        data = inventory(args.directory)
        with args.manifest.open("x", encoding="utf-8") as stream:
            json.dump(data, stream, indent=2)
        print("Review candidate SHA-256:", digest(args.manifest))
    else:
        verify(args.directory, args.manifest, args.approved_sha256)
        print("Wheel bytes match the independent manifest pin; origin still requires review.")
