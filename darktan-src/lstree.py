#!/usr/bin/env python3
# desc: Affiche l’arborescence
# man:
#   USAGE
#     lstree [path]               # affiche l’arborescence du dossier courant
#     lstree -o tree.txt          # export texte
#     lstree --json manifest.json # export JSON
#     lstree --max-depth 3        # limite la profondeur
#
#   OPTIONS
#     --files-only                # n’affiche que les fichiers
#     --dirs-only                 # n’affiche que les dossiers
#     --exclude NAME              # exclut un dossier/fichier (peut être répété)
#     --no-default-excludes       # désactive les exclusions par défaut
#
#   NOTES
#     - Les tailles sont affichées en unités lisibles.
#     - Les exclusions par défaut couvrent .git, __pycache__, node_modules, etc.
#     - Supporte l’écriture vers fichier texte ou JSON.
# ls_tree.py
# Liste l'arborescence d'un dossier avec tailles, exclusions et export facultatif.
# Usage rapide :
#   python ls_tree.py                          -> affiche l'arbo
#   python ls_tree.py -o tree.txt              -> export texte
#   python ls_tree.py --json manifest.json     -> export JSON
#   python ls_tree.py --max-depth 3            -> limite la profondeur

import os
import sys
import argparse
import json
from pathlib import Path
from typing import Iterable

DEFAULT_EXCLUDES = {
    ".git", ".hg", ".svn", ".idea", ".vscode", "__pycache__",
    ".mypy_cache", ".pytest_cache", ".ruff_cache", ".DS_Store",
    ".venv", "venv", "env", "node_modules", "dist", "build", ".cache"
}

def human_size(n: int) -> str:
    units = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    f = float(n)
    while f >= 1024 and i < len(units) - 1:
        f /= 1024.0
        i += 1
    return f"{f:.1f}{units[i]}"

def iter_dir(path: Path, excludes: set[str]) -> Iterable[Path]:
    for p in path.iterdir():
        name = p.name
        if name in excludes:
            continue
        yield p

def print_tree(root: Path, excludes: set[str], max_depth: int | None, files_only: bool, dirs_only: bool) -> list[dict]:
    manifest = []
    def walk(dir_path: Path, prefix: str = "", depth: int = 0):
        try:
            children = sorted(iter_dir(dir_path, excludes), key=lambda p: (p.is_file(), p.name.lower()))
        except PermissionError:
            print(prefix + "[PERMISSION DENIED] " + str(dir_path), file=sys.stderr)
            return

        total = len(children)
        for i, child in enumerate(children):
            if max_depth is not None and depth > max_depth:
                return
            is_last = (i == total - 1)
            branch = "└── " if is_last else "├── "
            next_prefix = prefix + ("    " if is_last else "│   ")

            try:
                if child.is_file():
                    if dirs_only:
                        continue
                    size = child.stat().st_size
                    line = f"{prefix}{branch}{child.name}  ({human_size(size)})"
                    print(line)
                    manifest.append({
                        "path": str(child.relative_to(root)),
                        "type": "file",
                        "size_bytes": size
                    })
                elif child.is_dir():
                    if files_only:
                        # On n'affiche pas les dossiers mais on descend quand même
                        walk(child, next_prefix, depth + 1)
                        continue
                    print(f"{prefix}{branch}{child.name}/")
                    manifest.append({
                        "path": str(child.relative_to(root)) + "/",
                        "type": "dir"
                    })
                    walk(child, next_prefix, depth + 1)
                else:
                    # liens, etc.
                    print(f"{prefix}{branch}{child.name}")
                    manifest.append({
                        "path": str(child.relative_to(root)),
                        "type": "other"
                    })
            except (PermissionError, OSError) as e:
                print(f"{prefix}{branch}{child.name}  [ERROR: {e}]", file=sys.stderr)

    print(root.resolve())
    print(root.name + "/")
    manifest.append({"path": root.name + "/", "type": "dir"})
    walk(root, "", 1)
    return manifest

def main():
    parser = argparse.ArgumentParser(description="Lister l'arborescence d'un dossier.")
    parser.add_argument("path", nargs="?", default=".", help="Dossier racine (par défaut: .)")
    parser.add_argument("-o", "--out", help="Écrire la sortie texte vers ce fichier.")
    parser.add_argument("--json", help="Écrire un manifeste JSON (chemins, types, tailles).")
    parser.add_argument("--exclude", action="append", default=[], help="Ajouter un dossier/fichier à exclure (peut être répété).")
    parser.add_argument("--no-default-excludes", action="store_true", help="Ne pas appliquer les exclusions par défaut.")
    parser.add_argument("--max-depth", type=int, help="Profondeur maximale (1 = seulement racine).")
    parser.add_argument("--files-only", action="store_true", help="N'afficher que les fichiers.")
    parser.add_argument("--dirs-only", action="store_true", help="N'afficher que les dossiers.")
    args = parser.parse_args()

    root = Path(args.path).resolve()
    if not root.exists():
        print(f"Chemin introuvable: {root}", file=sys.stderr)
        sys.exit(1)

    excludes = set(args.exclude)
    if not args.no_default_excludes:
        excludes |= DEFAULT_EXCLUDES

    # Redirection optionnelle vers fichier texte
    if args.out:
        sys_stdout = sys.stdout
        sys.stdout = open(args.out, "w", encoding="utf-8")

    try:
        manifest = print_tree(
            root=root,
            excludes=excludes,
            max_depth=args.max_depth,
            files_only=args.files_only,
            dirs_only=args.dirs_only
        )
    finally:
        if args.out:
            sys.stdout.close()
            sys.stdout = sys_stdout

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(manifest, f, ensure_ascii=False, indent=2)

if __name__ == "__main__":
    main()
