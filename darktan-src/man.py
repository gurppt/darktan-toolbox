#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# desc: Affiche les pages d’aide
# man:
#   USAGE
#     man                         # liste les outils dispos avec man
#     man toolname                # affiche la page d’aide d’un outil (ex: man todo)
#
#   OPTIONS
#     -l, --list                  # liste seulement les outils documentés
#     -p, --path PATH             # spécifie un autre dossier de scripts
#
#   NOTES
#     - Les sections sont détectées via le tag "# man:" dans chaque script.
#     - Formate les blocs d’aide avec Rich pour une lecture claire.
#     - Compatible avec les scripts Python (.py) de ton dossier /scripts.
#     - Inspiré du comportement UNIX `man`, adapté à ton écosystème local.

import argparse
import textwrap
from pathlib import Path

from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import box

console = Console(width=100)

# ---------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------
DEFAULT_SCRIPTS_PATH = Path("B:/app/scripts").resolve()

# ---------------------------------------------------------------------
# Extraction de la section # man:
# ---------------------------------------------------------------------
def extract_man_section(path: Path) -> str | None:
    """Lit le fichier et renvoie le texte sous # man: si trouvé."""
    try:
        lines = path.read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None

    man_lines = []
    inside = False
    for line in lines:
        if line.strip().startswith("# man:"):
            inside = True
            content = line.split("# man:", 1)[1].strip()
            if content:
                man_lines.append(content)
            continue
        if inside:
            if line.strip().startswith("#"):
                man_lines.append(line.strip("# ").rstrip())
            else:
                break

    out = "\n".join(man_lines).rstrip()
    return out if out.strip() else None

# ---------------------------------------------------------------------
# Rendu stylé (même logique que darktan help)
# ---------------------------------------------------------------------
def render_man_text(txt: str, tool_name: str | None = None):
    lines = txt.splitlines()

    def is_section_header(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        if s.upper() != s:
            return False
        if s.startswith("darktan"):
            return False
        return True

    console.rule(f"[bold cyan]{tool_name}[/bold cyan]" if tool_name else "[bold cyan]man[/bold cyan]")

    for i, raw in enumerate(lines):
        line = raw.rstrip()

        if i == 0:
            console.print(line, style="bold bright_cyan")
            continue

        if not line.strip():
            console.print()
            continue

        if is_section_header(line):
            console.print(line, style="bold white")
            continue

        s = line.strip()

        if s.startswith("darktan ") or (tool_name and s.startswith(f"{tool_name} ")):
            console.print(line, style="bold cyan")
            continue

        if s.startswith("--") or s.startswith("-"):
            console.print(line, style="yellow")
            continue

        if (tool_name and s.startswith(tool_name)) or s.startswith("darktan"):
            console.print(line, style="green")
            continue

        console.print(line, style="grey70")

    console.rule(style="dim")

# ---------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------
def render_list(scripts_path: Path, only_documented: bool = True):
    rows = []
    for f in sorted(scripts_path.glob("*.py")):
        man = extract_man_section(f)
        if only_documented and not man:
            continue
        first_line = man.splitlines()[0] if man else "-"
        rows.append((f.stem, first_line, "yes" if man else "no"))

    if not rows:
        console.print("[yellow]Aucune page man trouvée.[/yellow]")
        return

    t = Table(title=f"MAN pages — {scripts_path}", box=box.MINIMAL_DOUBLE_HEAD)
    t.add_column("Tool", style="bold cyan", no_wrap=True)
    t.add_column("Résumé", style="dim")
    t.add_column("man", style="green", no_wrap=True, justify="right")
    for name, line, has in rows:
        t.add_row(name, line, has)
    console.print(t)

# ---------------------------------------------------------------------
# Page man
# ---------------------------------------------------------------------
def render_tool_man(name: str, scripts_path: Path):
    file = scripts_path / f"{name}.py"
    if not file.exists():
        console.print(f"[red]Aucun script nommé '{name}' trouvé dans {scripts_path}[/red]")
        return

    section = extract_man_section(file)
    if not section:
        console.print(f"[yellow]Pas de section man trouvée dans {file.name}[/yellow]")
        return

    wrapped = textwrap.dedent(section).strip()
    render_man_text(wrapped, tool_name=name)

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------
def main():
    p = argparse.ArgumentParser(prog="man", description="Affiche les man pages des scripts internes.")
    p.add_argument("tool", nargs="?", help="Nom du script à afficher.")
    p.add_argument("-l", "--list", action="store_true", help="Liste uniquement les pages disponibles.")
    p.add_argument("-p", "--path", help="Chemin du dossier contenant les scripts.")
    p.add_argument("--raw", action="store_true", help="Affiche le texte brut (sans couleur).")
    args = p.parse_args()

    scripts_path = Path(args.path).resolve() if args.path else DEFAULT_SCRIPTS_PATH

    if args.list or not args.tool:
        render_list(scripts_path, only_documented=True)
        if args.tool:
            if args.raw:
                section = extract_man_section(scripts_path / f"{args.tool}.py")
                if section:
                    console.print(Panel.fit(textwrap.dedent(section).strip(), title=f"{args.tool}.py", border_style="cyan", width=95))
                else:
                    console.print(f"[yellow]Pas de section man trouvée pour {args.tool}[/yellow]")
            else:
                render_tool_man(args.tool, scripts_path)
        return

    if args.raw:
        file = scripts_path / f"{args.tool}.py"
        section = extract_man_section(file)
        if not file.exists():
            console.print(f"[red]Aucun script nommé '{args.tool}' trouvé dans {scripts_path}[/red]")
            return
        if not section:
            console.print(f"[yellow]Pas de section man trouvée dans {file.name}[/yellow]")
            return
        console.print(Panel.fit(textwrap.dedent(section).strip(), title=f"{args.tool}.py", border_style="cyan", width=95))
        return

    render_tool_man(args.tool, scripts_path)

if __name__ == "__main__":
    main()
