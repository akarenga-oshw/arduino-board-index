#!/usr/bin/env python3
"""Merge a single-version index fragment into the published board index.

package_akarenga.sh in the core repository writes a fragment describing one
version. The published index lists every version ever released, so that Boards
Manager can offer them all and users can go back to an older one. This merges a
fragment in, and can take a version back out again.

    ./merge-index.py ../ArduinoCore-renesas/extras/package_akarenga_1.6.0_index.json
    ./merge-index.py --remove 1.5.3-akarenga.1

Re-merging a version that is already listed replaces it, which is what you want
after rebuilding and re-uploading an archive under the same version number.
"""

import argparse
import json
import os
import sys

INDEX = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                     "package_akarenga_index.json")


def die(msg):
    sys.exit("merge-index: " + msg)


def load(path):
    try:
        with open(path) as f:
            return json.load(f)
    except FileNotFoundError:
        die("no such file: " + path)
    except json.JSONDecodeError as e:
        die("%s is not valid JSON: %s" % (path, e))


def find_package(doc, name, where):
    for p in doc.get("packages", []):
        if p.get("name") == name:
            return p
    die("no package named %r in %s" % (name, where))


def version_key(v):
    """Sort key roughly matching relaxed-semver ordering.

    X.Y.Z sorts by number, and a release sorts above its own pre-releases, so
    1.6.0 comes before 1.6.0-akarenga.1. Anything unparseable sorts last rather
    than raising: the index is still readable, just ordered oddly, and Boards
    Manager does its own comparison anyway.
    """
    main, _, pre = str(v).partition("-")
    try:
        nums = tuple(int(n) for n in main.split("."))
    except ValueError:
        return ((-1,), "", str(v))
    # no pre-release sorts before any pre-release of the same X.Y.Z, and we
    # emit newest first, so invert with an empty string being "greatest"
    return (nums, "" if not pre else pre, "")


def sort_platforms(platforms):
    # newest first, matching how Arduino publishes package_index.json
    return sorted(platforms,
                  key=lambda p: (version_key(p.get("version", "")),
                                 p.get("architecture", "")),
                  reverse=True)


def describe(platforms):
    by_arch = {}
    for p in platforms:
        by_arch.setdefault(p.get("architecture", "?"), []).append(
            p.get("version", "?"))
    return by_arch


def main():
    ap = argparse.ArgumentParser(
        description="Merge a version into the published board index.")
    ap.add_argument("fragment", nargs="?",
                    help="single-version index written by package_akarenga.sh")
    ap.add_argument("--remove", metavar="VERSION",
                    help="drop this version from the index instead")
    ap.add_argument("--index", default=INDEX,
                    help="index to edit (default: %(default)s)")
    ap.add_argument("-n", "--dry-run", action="store_true",
                    help="report what would change, write nothing")
    args = ap.parse_args()

    if bool(args.fragment) == bool(args.remove):
        ap.error("give either a fragment to merge or --remove VERSION")

    index = load(args.index)
    pkg_name = index["packages"][0]["name"]
    pkg = find_package(index, pkg_name, args.index)
    platforms = pkg.setdefault("platforms", [])
    before = len(platforms)

    if args.remove:
        kept = [p for p in platforms if p.get("version") != args.remove]
        if len(kept) == before:
            die("%s is not in %s" % (args.remove, os.path.basename(args.index)))
        pkg["platforms"] = sort_platforms(kept)
        action = "removed %s" % args.remove
    else:
        frag = load(args.fragment)
        fpkg = find_package(frag, pkg_name, args.fragment)
        fplatforms = fpkg.get("platforms", [])
        if len(fplatforms) != 1:
            die("expected exactly one platform in the fragment, found %d"
                % len(fplatforms))
        new = fplatforms[0]
        arch, version = new.get("architecture"), new.get("version")
        if not arch or not version:
            die("the fragment's platform has no architecture or version")

        replaced = any(p.get("architecture") == arch and
                       p.get("version") == version for p in platforms)
        kept = [p for p in platforms
                if not (p.get("architecture") == arch and
                        p.get("version") == version)]
        pkg["platforms"] = sort_platforms(kept + [new])

        # tools and the builtin package are not versioned per release, so the
        # fragment is always the more recent description of them
        pkg["tools"] = fpkg.get("tools", pkg.get("tools", []))
        for fp in frag.get("packages", []):
            if fp.get("name") == pkg_name:
                continue
            index["packages"] = [p for p in index["packages"]
                                 if p.get("name") != fp.get("name")] + [fp]

        action = "%s %s %s" % ("replaced" if replaced else "added",
                               arch, version)

    for arch, versions in sorted(describe(pkg["platforms"]).items()):
        print("%-16s %2d  %s" % (arch, len(versions), ", ".join(versions)))
    print()
    print("%s (%d -> %d entries)" % (action, before, len(pkg["platforms"])))

    if args.dry_run:
        print("dry run, %s not written" % os.path.basename(args.index))
        return

    text = json.dumps(index, indent=2, ensure_ascii=False) + "\n"
    json.loads(text)  # refuse to write anything we cannot read back
    with open(args.index, "w") as f:
        f.write(text)
    print("wrote %s" % args.index)


if __name__ == "__main__":
    main()
