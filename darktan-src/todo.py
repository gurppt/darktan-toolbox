#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# desc: TODO minimaliste
# man:
#   USAGE
#     todo                         # liste la TODO (ordre de priorité 1..N)
#     todo add "Tâche A" "Tâche B" # ajoute une ou plusieurs tâches
#     todo move 5 2                # déplace la tâche #5 en position #2 (réindex auto)
#
#     todo done                    # liste les tâches terminées (DONE)
#     todo done 3                  # marque la tâche #3 comme faite (passe dans DONE)
#     todo done clear              # vide tout le DONE (confirmation)
#     todo done clear 4 7          # supprime du DONE les ids 4..7 (confirmation)
#     todo done clear -y           # idem, sans confirmation (-y)
#
#     todo clear                   # vide toute la TODO (confirmation)
#     todo clear 1 3               # supprime TODO ids 1..3 (confirmation)
#     todo clear -y                # idem, sans confirmation
#
#   NOTES
#     - Les listes TODO/DONE sont réindexées après chaque opération (1..N).
#     - Les plages acceptent deux bornes dans n'importe quel ordre (ex: "7 4").
#     - Stockage: %APPDATA%/todo_cli/todo.json (Windows) ou ~/.config/todo_cli/todo.json.

import argparse
import json
import os
import sys
from datetime import datetime
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

console = Console()
DB_FILE = os.path.join(os.path.dirname(__file__), "todo.json")

# ---------------------------------------------------------------------------
# UTILITAIRES
# ---------------------------------------------------------------------------

def load_db():
    if not os.path.exists(DB_FILE):
        return {"todo": [], "done": []}
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {"todo": [], "done": []}


def save_db(db):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, ensure_ascii=False)


def timestamp():
    return datetime.now().strftime("%Y-%m-%d %H:%M")


def parse_range_args(args, length):
    if not args:
        return []
    if len(args) == 1:
        try:
            i = int(args[0])
            return [i]
        except ValueError:
            return []
    if len(args) == 2:
        try:
            a, b = map(int, args)
            return list(range(a, b + 1))
        except ValueError:
            return []
    return []


# ---------------------------------------------------------------------------
# COMMANDES
# ---------------------------------------------------------------------------

def cmd_list(db):
    todo = db["todo"]
    if not todo:
        console.print("[bold cyan]No TODOs yet.[/bold cyan]")
        return
    table = Table(show_header=True, header_style="bold cyan", box=None)
    table.add_column("#", justify="right")
    table.add_column("Task", style="bold white")
    table.add_column("Added", style="dim")
    for i, t in enumerate(todo, 1):
        table.add_row(str(i), t["task"], t["added"])
    console.print(Panel(table, title="TODO", expand=False))


def cmd_add(db, tasks):
    for task in tasks:
        db["todo"].append({"task": task, "added": timestamp()})
    save_db(db)
    console.print(f"[green]Added {len(tasks)} task(s).[/green]")


def cmd_done_list(db):
    done = db["done"]
    if not done:
        console.print("[bold cyan]No DONE tasks.[/bold cyan]")
        return
    table = Table(show_header=True, header_style="bold green", box=None)
    table.add_column("#", justify="right")
    table.add_column("Task", style="bold white")
    table.add_column("Done", style="dim")
    for i, t in enumerate(done, 1):
        table.add_row(str(i), t["task"], t["done"])
    console.print(Panel(table, title="DONE", expand=False))


def cmd_done_mark(db, index):
    todo = db["todo"]
    if index < 1 or index > len(todo):
        console.print(f"[red]Invalid index {index}.[/red]")
        return
    task = todo.pop(index - 1)
    task["done"] = timestamp()
    db["done"].append(task)
    save_db(db)
    console.print(f"[green]Marked done:[/green] {task['task']}")


def cmd_done_clear(db, range_list, yes):
    done = db["done"]
    if not done:
        console.print("[cyan]DONE is empty.[/cyan]")
        return
    if range_list:
        # supprimer une plage spécifique
        new_done = [t for i, t in enumerate(done, 1) if i not in range_list]
        console.print(f"[yellow]Removed {len(done) - len(new_done)} task(s) from DONE.[/yellow]")
        db["done"] = new_done
    else:
        if not yes:
            console.print("[red]Use -y to confirm clearing DONE.[/red]")
            return
        db["done"] = []
        console.print("[yellow]DONE cleared.[/yellow]")
    save_db(db)


def cmd_remove(db, index):
    todo = db["todo"]
    if index < 1 or index > len(todo):
        console.print(f"[red]Invalid index {index}.[/red]")
        return
    task = todo.pop(index - 1)
    save_db(db)
    console.print(f"[yellow]Removed:[/yellow] {task['task']}")


def cmd_clear_all(db):
    db["todo"] = []
    db["done"] = []
    save_db(db)
    console.print("[red]All tasks cleared.[/red]")


# ---------------------------------------------------------------------------
# ARGPARSE
# ---------------------------------------------------------------------------

def build_parser():
    parser = argparse.ArgumentParser(prog="todo", description="Simple CLI TODO manager")
    sub = parser.add_subparsers(dest="cmd")

    # list
    sub.add_parser("list", help="Liste les TODO")

    # add
    pa = sub.add_parser("add", help="Ajoute une ou plusieurs tâches")
    pa.add_argument("tasks", nargs="+", help="Tâche(s) à ajouter")

    # done
    pd = sub.add_parser("done", help="Liste DONE, marque une tâche comme faite, ou nettoie DONE.")
    pd.add_argument("index_or_cmd", nargs="?", help="Indice à marquer comme fait, ou 'clear'.")
    pd.add_argument("range", nargs="*", help="Optionnel: A B pour effacer une plage (avec 'clear').")
    pd.add_argument("-y", "--yes", action="store_true", help="Confirmer sans demander (avec 'clear').")

    # remove
    pr = sub.add_parser("remove", help="Supprime une tâche par son index")
    pr.add_argument("index", type=int, help="Indice à supprimer")

    # clear
    sub.add_parser("clear", help="Efface toutes les tâches (TODO et DONE)")

    return parser


# ---------------------------------------------------------------------------
# MAIN
# ---------------------------------------------------------------------------

def main():
    db = load_db()
    parser = build_parser()
    args = parser.parse_args()

    if args.cmd is None:
        cmd_list(db)
    elif args.cmd == "list":
        cmd_list(db)
    elif args.cmd == "add":
        cmd_add(db, args.tasks)
    elif args.cmd == "done":
        token = getattr(args, "index_or_cmd", None)
        if token is None:
            # "todo done" -> lister DONE
            cmd_done_list(db)
        elif isinstance(token, str) and token.lower() == "clear":
            # "todo done clear [A B] [-y]" -> nettoyer DONE
            rng = parse_range_args(args.range, len(db["done"])) if getattr(args, "range", None) else []
            cmd_done_clear(db, rng, getattr(args, "yes", False))
        else:
            # "todo done N" -> marquer comme fait
            try:
                idx = int(token)
            except ValueError:
                parser.error("Utilisation: todo done [INDEX] | todo done clear [A B] [-y]")
            cmd_done_mark(db, idx)
    elif args.cmd == "remove":
        cmd_remove(db, args.index)
    elif args.cmd == "clear":
        cmd_clear_all(db)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
