#!/usr/bin/env python3
# desc: Gestionnaire local de scripts
# Source:   B:\app\scripts\  (par défaut, override via --path)
# Shims:    %USERPROFILE%\bin\  (shims .py)
# man:
#   darktan — gestionnaire local de scripts et shims .py
#
#   DESCRIPTION
#       Gère les scripts Python locaux (par défaut B:\app\scripts)
#       et crée des shims .py dans %USERPROFILE%\bin pour les exécuter
#       depuis n’importe où. Chaque shim relaye les arguments au script
#       d’origine via runpy.run_path().
#
#   USAGE
#       darktan [--path PATH] [--json PATH] <commande> [options]
#
#   COMMANDES DISPONIBLES
#       backup, clean, diff, doctor, edit, editor, info, install,
#       list, new, purge, recent, remove, restore, search, stats,
#       touch, update, upgrade
#
#   COMMANDES PRINCIPALES
#       list              Liste les scripts avec description et taille
#       install <name>    Crée un shim (option --as alias, --force)
#       remove <name>     Supprime le shim
#       purge <name>      Supprime le shim ET le script
#       update / upgrade  Gère les shims manquants
#
#   MAINTENANCE
#       doctor            Vérifie la config et le PATH
#       clean             Supprime les shims orphelins
#       diff              Compare dates et cibles
#       backup --out ZIP  Archive scripts + shims + config
#       restore ZIP       Restaure une archive (--force écrase)
#
#   CRÉATION / ÉDITION
#       new <name>        Crée un script + shim (option --desc)
#       edit <name>       Ouvre dans l’éditeur (Geany par défaut)
#       editor [PATH]     Définit ou affiche l’éditeur
#       touch <name>      Met à jour la date du script
#
#   INFO / RECHERCHE
#       info <name>       Détails d’un script (taille, dates, desc)
#       stats             Résumé global (nombre, taille, orphelins)
#       recent [N]        Derniers scripts modifiés (10 par défaut)
#       search <term>     Recherche par nom ou description
#
#   OPTIONS
#       --path PATH       Définit le dossier des scripts
#       --json PATH       (pour list) export JSON
#
#   FICHIERS
#       %USERPROFILE%\bin\            — shims créés
#       %USERPROFILE%\.darktan\config.json — config et éditeur
#
#   EXEMPLES
#       darktan list
#       darktan install todo
#       darktan doctor
#       darktan backup --out B:\scripts.zip
#       darktan new sync_tool --desc "outil réseau"
#       darktan edit sync_tool
#       darktan stats
#       darktan search convert
#


import argparse
import json
import os
import re
import subprocess
import sys
import zipfile
from pathlib import Path
from datetime import datetime

from rich.console import Console
from rich.table import Table
from rich import box

# ---------------------------------------------------------------------
# Configs et chemins
# ---------------------------------------------------------------------

DEFAULT_SCRIPTS_DIR = Path(r"B:\app\scripts")
BIN_DIR = Path(os.path.expanduser(r"~\bin"))
STATE_DIR = Path(os.path.expanduser(r"~\.darktan"))
CONFIG_FILE = STATE_DIR / "config.json"

console = Console(width=98, soft_wrap=False)

# ---------------------------------------------------------------------
# Help (source unique: section # man:)
# ---------------------------------------------------------------------

def extract_own_man_section() -> str | None:
    try:
        lines = Path(__file__).read_text(encoding="utf-8", errors="ignore").splitlines()
    except Exception:
        return None

    man_lines = []
    inside = False

    for line in lines:
        s = line.strip()
        if s.startswith("# man:"):
            inside = True
            content = line.split("# man:", 1)[1].strip()
            if content:
                man_lines.append(content)
            continue

        if inside:
            if s.startswith("#"):
                man_lines.append(s.lstrip("#").lstrip())
            else:
                break

    out = "\n".join(man_lines).rstrip()
    return out if out.strip() else None

def print_help_from_man():
    txt = extract_own_man_section()
    if not txt:
        console.print("[red]No manual section found (# man:).[/red]")
        return

    lines = txt.splitlines()

    def is_section_header(line: str) -> bool:
        s = line.strip()
        if not s:
            return False
        # titres en MAJUSCULES
        if s.upper() != s:
            return False
        # évite le titre principal
        if s.startswith("darktan"):
            return False
        return True

    for i, raw in enumerate(lines):
        line = raw.rstrip()

        # Titre principal
        if i == 0:
            console.print(line, style="bold bright_cyan")
            continue

        # Ligne vide
        if not line.strip():
            console.print()
            continue

        # Titres de section
        if is_section_header(line):
            console.print(line, style="bold white")
            continue

        s = line.strip()

        # Ligne USAGE (darktan ...)
        if s.startswith("darktan "):
            console.print(line, style="bold cyan")
            continue

        # Options (--path, --json)
        if s.startswith("--") or s.startswith("-"):
            console.print(line, style="yellow")
            continue

        # Exemples (darktan ...)
        if s.startswith("darktan"):
            console.print(line, style="green")
            continue

        # Texte standard
        console.print(line, style="grey70")


def print_unknown_help_hint():
    console.print("[red]Unknown argument.[/red] Do you mean [bold]-h[/bold] ?")

# ---------------------------------------------------------------------
# Utilitaires communs
# ---------------------------------------------------------------------

def ensure_dirs():
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

def load_config():
    ensure_dirs()
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}

def save_config(cfg: dict):
    ensure_dirs()
    CONFIG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def in_path_hint():
    path = os.environ.get("PATH", "")
    parts = [p.strip().rstrip("\\") for p in path.split(";") if p.strip()]
    if str(BIN_DIR).rstrip("\\").lower() not in [p.lower() for p in parts]:
        console.print(f"[yellow][!] {BIN_DIR} n’est pas dans PATH. Ajoute-le pour appeler les shims partout.[/yellow]")

def find_script_py(scripts_dir: Path, name: str) -> Path | None:
    base = scripts_dir / name
    if base.suffix.lower() == ".py":
        return base if base.exists() else None
    cand = scripts_dir / f"{name}.py"
    return cand if cand.exists() else None

def shim_path(name_or_alias: str) -> Path:
    return BIN_DIR / f"{name_or_alias}.py"

def list_scripts_py(scripts_dir: Path) -> dict[str, Path]:
    out = {}
    if not scripts_dir.exists():
        return out
    for p in scripts_dir.iterdir():
        if p.is_file() and p.suffix.lower() == ".py" and not p.name.startswith("_"):
            out[p.stem.lower()] = p
    return out

def list_shims_py() -> dict[str, Path]:
    ensure_dirs()
    out = {}
    for p in BIN_DIR.iterdir():
        if p.is_file() and p.suffix.lower() == ".py":
            out[p.stem.lower()] = p
    return out

def generate_py_shim_content(target: Path) -> str:
    t = str(target)
    return (
        "import runpy, sys\n"
        f"sys.argv = [r\"{t}\"] + sys.argv[1:]\n"
        f"runpy.run_path(r\"{t}\", run_name=\"__main__\")\n"
    )

def write_shim(name_or_alias: str, target: Path, force: bool = False):
    ensure_dirs()
    sp = shim_path(name_or_alias)
    if sp.exists() and not force:
        raise SystemExit(f"Shim existe déjà: {sp} (utilise --force).")
    sp.write_text(generate_py_shim_content(target), encoding="utf-8", newline="\n")
    print(f"[OK] Shim créé: {sp} → {target}")

def remove_shim(name_or_alias: str):
    sp = shim_path(name_or_alias)
    if sp.exists():
        sp.unlink()
        print(f"[OK] Shim supprimé: {sp}")
    else:
        print(f"[i] Aucun shim: {sp}")

def purge_script(scripts_dir: Path, name: str):
    shim = shim_path(name)
    script = find_script_py(scripts_dir, name)
    ok = False
    if shim.exists():
        shim.unlink()
        print(f"[OK] Shim supprimé: {shim}")
        ok = True
    else:
        print(f"[i] Aucun shim trouvé pour {name}")
    if script and script.exists():
        script.unlink()
        print(f"[OK] Script supprimé: {script}")
        ok = True
    else:
        print(f"[i] Aucun script trouvé dans {scripts_dir} pour {name}")
    if not ok:
        print(f"[!] Rien à supprimer pour {name}")

# ---------------------------------------------------------------------
# Partie "tools" (list) – mise en page et extraction desc
# ---------------------------------------------------------------------

DESC_PAT = re.compile(r"^\s*#\s*(?:desc|description)\s*:?\s*(.+)$", re.IGNORECASE)
SHIM_TARGET_PAT = re.compile(r'runpy\.run_path\(r"([^"]+)"')

def first_lines(path: Path, n=120) -> list[str]:
    lines = []
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as f:
            for _ in range(n):
                try:
                    lines.append(next(f))
                except StopIteration:
                    break
    except Exception:
        return []
    return lines

def get_desc(path: Path) -> str:
    lines = first_lines(path, 80)
    for line in lines[:60]:
        m = DESC_PAT.match(line)
        if m:
            return (m.group(1) or "-").strip()[:120] or "-"
    try:
        import ast
        mod = ast.parse("".join(lines))
        doc = ast.get_docstring(mod)
        if doc:
            return doc.strip().splitlines()[0][:120]
    except Exception:
        pass
    return "-"

def human_size(n: int) -> str:
    size = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if size < 1024 or unit == "TB":
            return f"{int(size)}{unit}" if unit == "B" else f"{size:.1f}{unit}"
        size /= 1024.0

def scan_for_list(dir_path: Path):
    tools = []
    for p in sorted(dir_path.iterdir(), key=lambda x: x.name.lower()):
        if not p.is_file() or p.suffix.lower() != ".py" or p.name.startswith("_"):
            continue
        desc = get_desc(p)
        stat = p.stat()
        tools.append({
            "name": p.stem,
            "ext": p.suffix.lower().lstrip("."),
            "desc": desc if desc else "-",
            "size": human_size(stat.st_size),
            "mtime": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
            "path": str(p),
        })
    return tools

def render_tools_table(tools, root: Path):
    t = Table(
        title=f"tools · {root}",
        box=box.MINIMAL_DOUBLE_HEAD,
        show_lines=False,
        pad_edge=False
    )
    t.add_column("Name", no_wrap=True, style="bold")
    t.add_column("Type", no_wrap=True, style="cyan")
    t.add_column("Size", no_wrap=True, justify="right", style="magenta")
    t.add_column("Description", overflow="fold")
    for it in tools:
        t.add_row(it["name"], it["ext"], it["size"], it["desc"])
    console.print(t)
    if not tools:
        console.print("[yellow]No tools found.[/yellow]")

# ---------------------------------------------------------------------
# Commandes
# ---------------------------------------------------------------------

def cmd_list(scripts_dir: Path, json_path: str | None):
    if not scripts_dir.exists():
        console.print(f"[red]Not found:[/] {scripts_dir}")
        raise SystemExit(1)
    tools = scan_for_list(scripts_dir)
    render_tools_table(tools, scripts_dir)
    if json_path:
        out = {"root": str(scripts_dir), "count": len(tools), "items": tools}
        jp = Path(json_path)
        jp.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[OK] Export JSON: {jp}")

def cmd_install(scripts_dir: Path, name: str, alias: str | None, force: bool):
    target = find_script_py(scripts_dir, name)
    if not target:
        raise SystemExit(f"Introuvable (script .py) dans {scripts_dir}: {name}")
    write_shim(alias or name, target, force=force)
    in_path_hint()

def cmd_remove(name: str):
    remove_shim(name)

def cmd_purge(scripts_dir: Path, name: str):
    purge_script(scripts_dir, name)

def cmd_update(scripts_dir: Path):
    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    pending = sorted([n for n in scripts if n not in shims])
    if not pending:
        print("[i] Aucun script .py en attente. Tous les shims existent déjà.")
        return
    print("Scripts .py sans shim :")
    for n in pending:
        print(f"  - {n}  → {scripts[n].name}")

def cmd_upgrade(scripts_dir: Path):
    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    pending = sorted([n for n in scripts if n not in shims])
    if not pending:
        print("[i] Rien à faire, tous les shims .py sont déjà présents.")
        return
    for n in pending:
        write_shim(n, scripts[n], force=False)
    in_path_hint()

def cmd_doctor(scripts_dir: Path):
    issues = 0
    if not scripts_dir.exists():
        console.print(f"[red]Scripts dir manquant:[/] {scripts_dir}")
        issues += 1
    if not BIN_DIR.exists():
        console.print(f"[red]Bin dir manquant:[/] {BIN_DIR}")
        issues += 1

    path = os.environ.get("PATH", "")
    if str(BIN_DIR).rstrip("\\").lower() not in [p.strip().rstrip("\\").lower() for p in path.split(";") if p.strip()]:
        console.print(f"[yellow][!] {BIN_DIR} absent de PATH[/yellow]")
        issues += 1

    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    orphan_shims = [k for k in shims if k not in scripts]
    pending = [k for k in scripts if k not in shims]

    console.print(f"[bold]Scripts:[/bold] {len(scripts)}  | [bold] Shims:[/bold] {len(shims)}")
    if pending:
        console.print(f"[yellow]Sans shim ({len(pending)}):[/yellow] " + ", ".join(sorted(pending)))
    if orphan_shims:
        console.print(f"[yellow]Shims orphelins ({len(orphan_shims)}):[/yellow] " + ", ".join(sorted(orphan_shims)))
    if issues == 0 and not pending and not orphan_shims:
        console.print("[green]OK — configuration saine.[/green]")

def parse_shim_target(shim_file: Path) -> Path | None:
    try:
        txt = shim_file.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        return None
    m = SHIM_TARGET_PAT.search(txt)
    if not m:
        return None
    return Path(m.group(1))

def cmd_clean(scripts_dir: Path):
    shims = list_shims_py()
    removed = 0
    for name, sf in shims.items():
        target = parse_shim_target(sf)
        if not target or not Path(target).exists():
            try:
                sf.unlink()
                removed += 1
                print(f"[OK] Shim orphelin supprimé: {sf}")
            except Exception as e:
                print(f"[!] Impossible de supprimer {sf}: {e}")
    if removed == 0:
        print("[i] Aucun shim orphelin.")

def cmd_backup(scripts_dir: Path, out_zip: Path):
    ensure_dirs()
    with zipfile.ZipFile(out_zip, "w", compression=zipfile.ZIP_DEFLATED) as z:
        for name, sp in list_scripts_py(scripts_dir).items():
            arc = f"scripts/{sp.name}"
            z.write(sp, arcname=arc)
        for name, sh in list_shims_py().items():
            arc = f"shims/{sh.name}"
            z.write(sh, arcname=arc)
        if CONFIG_FILE.exists():
            z.write(CONFIG_FILE, arcname="state/config.json")
    print(f"[OK] Backup créé: {out_zip}")

def cmd_restore(scripts_dir: Path, zip_path: Path, force: bool):
    if not zip_path.exists():
        raise SystemExit(f"Archive introuvable: {zip_path}")
    ensure_dirs()
    with zipfile.ZipFile(zip_path, "r") as z:
        for info in z.infolist():
            if info.is_dir():
                continue
            if info.filename.startswith("scripts/") and info.filename.endswith(".py"):
                dst = scripts_dir / Path(info.filename).name
                if dst.exists() and not force:
                    print(f"[i] Skip (existe): {dst}")
                else:
                    dst.write_bytes(z.read(info.filename))
                    print(f"[OK] Restored script: {dst}")
            elif info.filename.startswith("shims/") and info.filename.endswith(".py"):
                dst = BIN_DIR / Path(info.filename).name
                if dst.exists() and not force:
                    print(f"[i] Skip (existe): {dst}")
                else:
                    dst.write_bytes(z.read(info.filename))
                    print(f"[OK] Restored shim:   {dst}")
            elif info.filename == "state/config.json":
                if CONFIG_FILE.exists() and not force:
                    print(f"[i] Skip (config existe): {CONFIG_FILE}")
                else:
                    CONFIG_FILE.write_bytes(z.read(info.filename))
                    print(f"[OK] Restored config: {CONFIG_FILE}")

def cmd_diff(scripts_dir: Path):
    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    stale = []
    mismatch = []
    for name, sp in scripts.items():
        sh = shims.get(name)
        if not sh:
            continue
        tgt = parse_shim_target(sh)
        if not tgt or Path(tgt).resolve().as_posix().lower() != sp.resolve().as_posix().lower():
            mismatch.append(name)
            continue
        if sp.stat().st_mtime > sh.stat().st_mtime + 1e-6:
            stale.append(name)
    if not stale and not mismatch:
        print("[i] Pas de divergence: shims alignés.")
        return
    if mismatch:
        print("Cibles divergentes (alias ou mauvaises cibles):")
        for n in sorted(mismatch):
            print(f"  - {n}")
    if stale:
        print("Shims plus vieux que scripts (regénération conseillée):")
        for n in sorted(stale):
            print(f"  - {n}")

def cmd_new(scripts_dir: Path, name: str, desc: str | None):
    scripts_dir.mkdir(parents=True, exist_ok=True)
    target = scripts_dir / (name if name.endswith(".py") else f"{name}.py")
    if target.exists():
        raise SystemExit(f"Existe déjà: {target}")
    header = [
        "#!/usr/bin/env python3",
        f"# desc: {desc.strip() if desc else name}",
        "",
        "import argparse",
        "",
        "def build_parser():",
        "    p = argparse.ArgumentParser(prog=\"%s\")" % target.stem,
        "    return p",
        "",
        "def main():",
        "    parser = build_parser(True)",
        "    args = parser.parse_args()",
        "    # TODO: implement",
        "    print(\"%s ready.\" )" % target.stem,
        "",
        "if __name__ == \"__main__\":",
        "    main()",
        ""
    ]
    target.write_text("\n".join(header), encoding="utf-8", newline="\n")
    write_shim(target.stem, target, force=False)
    print(f"[OK] Nouveau script: {target}")

def resolve_editor():
    cfg = load_config()
    editor = cfg.get("editor")
    if editor and Path(editor).exists():
        return editor
    candidates = [
        r"C:\Program Files\Geany\bin\geany.exe",
        r"C:\Program Files (x86)\Geany\bin\geany.exe",
        r"C:\Windows\System32\notepad.exe",
        "notepad.exe",
    ]
    for c in candidates:
        if Path(c).exists():
            return c
    return "notepad.exe"

def cmd_editor_set(path: str | None):
    cfg = load_config()
    if path:
        p = Path(path)
        if not p.exists():
            raise SystemExit(f"Éditeur introuvable: {p}")
        cfg["editor"] = str(p)
        save_config(cfg)
        print(f"[OK] Éditeur défini: {p}")
    else:
        cur = cfg.get("editor")
        print(cur if cur else resolve_editor())

def cmd_edit(scripts_dir: Path, name: str):
    target = find_script_py(scripts_dir, name)
    if not target:
        raise SystemExit(f"Introuvable (script .py) dans {scripts_dir}: {name}")
    editor = resolve_editor()
    try:
        subprocess.Popen([editor, str(target)])
        print(f"[OK] Ouvert dans l’éditeur: {target}")
    except Exception as e:
        raise SystemExit(f"Erreur lancement éditeur: {e}")

def cmd_touch(scripts_dir: Path, name: str):
    target = find_script_py(scripts_dir, name)
    if not target:
        raise SystemExit(f"Introuvable (script .py) dans {scripts_dir}: {name}")
    now = datetime.now().timestamp()
    os.utime(target, (now, now))
    print(f"[OK] Touch: {target}")

def cmd_info(scripts_dir: Path, name: str):
    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    key = name.lower().removesuffix(".py")
    sp = scripts.get(key)
    sh = shims.get(key)
    table = Table(box=box.SIMPLE_HEAVY)
    table.add_column("Field", style="bold")
    table.add_column("Value")
    table.add_row("Name", key)
    table.add_row("Script", str(sp) if sp else "-")
    table.add_row("Shim", str(sh) if sh else "-")
    if sp and Path(sp).exists():
        stat = sp.stat()
        table.add_row("Size", human_size(stat.st_size))
        table.add_row("Modified", datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
        table.add_row("Desc", get_desc(sp))
    if sh and Path(sh).exists():
        tgt = parse_shim_target(sh)
        table.add_row("Shim→Target", str(tgt) if tgt else "?")
        stat2 = sh.stat()
        table.add_row("Shim mtime", datetime.fromtimestamp(stat2.st_mtime).strftime("%Y-%m-%d %H:%M:%S"))
    console.print(table)

def cmd_stats(scripts_dir: Path):
    scripts = list_scripts_py(scripts_dir)
    shims = list_shims_py()
    total_size = sum(p.stat().st_size for p in scripts.values())
    table = Table(title="darktan stats", box=box.SIMPLE_HEAVY)
    table.add_column("Metric", style="bold")
    table.add_column("Value")
    table.add_row("Scripts", str(len(scripts)))
    table.add_row("Shims", str(len(shims)))
    table.add_row("Total size (scripts)", human_size(total_size))
    pending = len([n for n in scripts if n not in shims])
    orph = len([n for n in shims if n not in scripts])
    table.add_row("Pending shims", str(pending))
    table.add_row("Orphan shims", str(orph))
    console.print(table)

def cmd_recent(scripts_dir: Path, n: int):
    scripts = list_scripts_py(scripts_dir)
    items = sorted(scripts.values(), key=lambda p: p.stat().st_mtime, reverse=True)[:n]
    t = Table(title=f"recent · {n}", box=box.SIMPLE_HEAVY)
    t.add_column("Name", style="bold")
    t.add_column("Modified")
    t.add_column("Size", justify="right")
    for p in items:
        t.add_row(p.stem, datetime.fromtimestamp(p.stat().st_mtime).strftime("%Y-%m-%d %H:%M"), human_size(p.stat().st_size))
    console.print(t)

def cmd_search(scripts_dir: Path, term: str):
    term_l = term.lower()
    res = []
    for p in list_scripts_py(scripts_dir).values():
        desc = get_desc(p).lower()
        if term_l in p.stem.lower() or term_l in desc:
            res.append((p, desc))
    if not res:
        print("[i] Aucun résultat.")
        return
    t = Table(title=f"search · {term}", box=box.SIMPLE_HEAVY)
    t.add_column("Name", style="bold")
    t.add_column("Description")
    for p, d in res:
        t.add_row(p.stem, d if d else "-")
    console.print(t)

# ---------------------------------------------------------------------
# Argparse
# ---------------------------------------------------------------------

class ReplParseError(Exception):
    pass

class SilentArgumentParser(argparse.ArgumentParser):
    def error(self, message):
        raise ReplParseError(message)

    def exit(self, status=0, message=None):
        # Pas de sortie brutale dans le REPL
        if message:
            raise ReplParseError(message)
        raise ReplParseError(f"exit {status}")

def build_parser(repl: bool = False):
    Parser = SilentArgumentParser if repl else argparse.ArgumentParser

    p = Parser(
        prog="darktan",
        description="Shims .py + listing + maintenance: B:\\app\\scripts -> %USERPROFILE%\\bin",
        add_help=False
    )
    p.add_argument(
        "--path",
        dest="scripts_dir",
        default=str(DEFAULT_SCRIPTS_DIR),
        help="Répertoire des scripts (défaut: B:\\app\\scripts)"
    )
    p.add_argument(
        "--json",
        dest="json_path",
        default=None,
        help="Chemin de sortie JSON pour 'list'"
    )

    sub = p.add_subparsers(dest="cmd", required=True)

    sub.add_parser("list", help="Lister les scripts (mise en page tools)")

    pi = sub.add_parser("install", help="Créer le shim .py pour un script .py donné")
    pi.add_argument("name")
    pi.add_argument("--as", dest="alias")
    pi.add_argument("--force", action="store_true")

    pr = sub.add_parser("remove", help="Supprimer le shim .py")
    pr.add_argument("name")

    pp = sub.add_parser("purge", help="Supprimer le shim ET le script")
    pp.add_argument("name")

    sub.add_parser("update", help="Lister les scripts .py sans shim")
    sub.add_parser("upgrade", help="Créer tous les shims .py manquants")

    sub.add_parser("doctor", help="Diagnostic de configuration")
    sub.add_parser("clean", help="Supprimer les shims orphelins")
    sub.add_parser("diff", help="Comparer dates et cibles (shims vs scripts)")

    pb = sub.add_parser("backup", help="Créer une archive ZIP de scripts+shims+config")
    pb.add_argument("--out", required=True, help="Chemin de l'archive ZIP de sortie")

    prst = sub.add_parser("restore", help="Restaurer depuis une archive ZIP")
    prst.add_argument("zipfile", help="Fichier ZIP à restaurer")
    prst.add_argument("--force", action="store_true")

    pn = sub.add_parser("new", help="Créer un nouveau script + shim")
    pn.add_argument("name")
    pn.add_argument("--desc")

    pe = sub.add_parser("edit", help="Ouvrir un script dans l'éditeur")
    pe.add_argument("name")

    ped = sub.add_parser("editor", help="Afficher/définir l’éditeur par défaut")
    ped.add_argument("path", nargs="?")

    pt = sub.add_parser("touch", help="Touch un script")
    pt.add_argument("name")

    pi2 = sub.add_parser("info", help="Infos détaillées d’un script")
    pi2.add_argument("name")

    sub.add_parser("stats", help="Statistiques globales")

    prc = sub.add_parser("recent", help="Derniers scripts modifiés")
    prc.add_argument("n", nargs="?", type=int, default=10)

    ps = sub.add_parser("search", help="Recherche par nom/description")
    ps.add_argument("term")

    return p


# ---------------------------------------------------------------------
# Dispatch
# ---------------------------------------------------------------------

def dispatch(args):
    scripts_dir = Path(args.scripts_dir)

    if args.cmd == "list":
        cmd_list(scripts_dir, args.json_path)
    elif args.cmd == "install":
        cmd_install(scripts_dir, args.name, args.alias, args.force)
    elif args.cmd == "remove":
        cmd_remove(args.name)
    elif args.cmd == "purge":
        cmd_purge(scripts_dir, args.name)
    elif args.cmd == "update":
        cmd_update(scripts_dir)
    elif args.cmd == "upgrade":
        cmd_upgrade(scripts_dir)
    elif args.cmd == "doctor":
        cmd_doctor(scripts_dir)
    elif args.cmd == "clean":
        cmd_clean(scripts_dir)
    elif args.cmd == "diff":
        cmd_diff(scripts_dir)
    elif args.cmd == "backup":
        cmd_backup(scripts_dir, Path(args.out))
    elif args.cmd == "restore":
        cmd_restore(scripts_dir, Path(args.zipfile), args.force)
    elif args.cmd == "new":
        cmd_new(scripts_dir, args.name, args.desc)
    elif args.cmd == "edit":
        cmd_edit(scripts_dir, args.name)
    elif args.cmd == "editor":
        cmd_editor_set(args.path)
    elif args.cmd == "touch":
        cmd_touch(scripts_dir, args.name)
    elif args.cmd == "info":
        cmd_info(scripts_dir, args.name)
    elif args.cmd == "stats":
        cmd_stats(scripts_dir)
    elif args.cmd == "recent":
        cmd_recent(scripts_dir, args.n)
    elif args.cmd == "search":
        cmd_search(scripts_dir, args.term)
    else:
        raise SystemExit(2)

# ---------------------------------------------------------------------
# Interactive mode
# ---------------------------------------------------------------------

def interactive_loop(parser):
    console.print("╔════════════════════════════╗", style="bright_green")
    console.print("║░░░ Welcome on Darktan ! ░░░║", style="bold bright_green")
    console.print("╚════════════════════════════╝", style="bright_green")
    console.print("Enter your command ([bold]-h[/bold] for help, [bold]q[/bold] to quit)", style="cyan") 
    console.print("and press Enter:", style="cyan")
    console.print()

    while True:
        try:
            line = input("darktan> ").strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break

        if not line:
            continue

        low = line.strip().lower()

        if low in ("q", "quit", "exit"):
            break

        if low == "--help":
            print_unknown_help_hint()
            continue

        if low == "-h" or low == "help" or low.startswith("help "):
            print_help_from_man()
            continue

        try:
            args = parser.parse_args(line.split())
            dispatch(args)
        except ReplParseError:
            console.print("[red]Unknown command.[/red] Type [bold]-h[/bold] for help !")

# ---------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------

def main():
    parser = build_parser(repl=True)
    argv = sys.argv[1:]

    if len(argv) == 0:
        interactive_loop(parser)
        return

    if "--help" in argv:
        print_unknown_help_hint()
        raise SystemExit(2)

    if "-h" in argv or (len(argv) >= 1 and argv[0].lower() == "help"):
        print_help_from_man()
        raise SystemExit(0)

    args = parser.parse_args()
    dispatch(args)

if __name__ == "__main__":
    main()
