#!/usr/bin/env python3
# desc: Convertit des vidéos vers MP4
# man:
#   USAGE
#     convert2mp4 -i input.avi              # convertit en MP4 (libx264 + AAC)
#     convert2mp4 -i folder/                # convertit tous les fichiers vidéo d’un dossier
#
#   OPTIONS
#     -o, --output_dir DIR                  # dossier de sortie
#     --overwrite                           # écrase les fichiers existants
#     --crf N                               # qualité vidéo (0–51, défaut 22)
#     --preset NAME                         # vitesse/qualité (ultrafast→veryslow)
#
#   NOTES
#     - Interface ASCII avec barre de progression Rich.
#     - Supporte Ctrl+C pour annuler proprement (safe kill).
#     - Détecte automatiquement les vidéos .mov/.avi/.mkv/.mpg/.mpeg dans le dossier courant.

# -*- coding: utf-8 -*-
"""
convert2mp4.py — ffmpeg frontend
version: 2.2 (Rich UI + safe kill)
"""

import argparse
import subprocess
import sys
import os
import signal
import re
import shutil
import time
from datetime import datetime, timedelta
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, BarColumn, TextColumn, TimeRemainingColumn
from rich.live import Live

console = Console(width=70)


# ─────────────────────────────────────────────────────────────────────────────
# UTILITAIRES
# ─────────────────────────────────────────────────────────────────────────────

def parse_time(tstr):
    """Convertit time=00:01:23.45 en secondes float."""
    try:
        h, m, s = tstr.split(':')
        return int(h) * 3600 + int(m) * 60 + float(s)
    except Exception:
        return 0.0


def get_duration(input_file):
    """Durée totale de la vidéo (via ffprobe)."""
    try:
        cmd = [
            "ffprobe", "-v", "error", "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1", input_file
        ]
        out = subprocess.check_output(cmd, stderr=subprocess.DEVNULL)
        return float(out.strip())
    except Exception:
        return 0.0


# ─────────────────────────────────────────────────────────────────────────────
# PROCESS STOP / CTRL+C SAFE
# ─────────────────────────────────────────────────────────────────────────────

def stop_ffmpeg_hard(process):
    """Tente de tuer ffmpeg proprement (Windows et Linux)."""
    try:
        if sys.platform.startswith("win"):
            os.kill(process.pid, signal.CTRL_BREAK_EVENT)
        else:
            process.terminate()
    except Exception:
        pass

    try:
        process.wait(timeout=2)
        return
    except Exception:
        pass

    try:
        process.terminate()
        process.wait(timeout=2)
        return
    except Exception:
        pass

    try:
        process.kill()
        process.wait(timeout=2)
        return
    except Exception:
        pass

    if sys.platform.startswith("win"):
        try:
            subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"],
                           stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except Exception:
            pass


# ─────────────────────────────────────────────────────────────────────────────
# RENDU ASCII / UI
# ─────────────────────────────────────────────────────────────────────────────

def format_time(seconds):
    return str(timedelta(seconds=int(seconds)))


def draw_box(info, percent, eta, fps, bitrate):
    """Construit le panneau ASCII avec Rich.Panel."""
    content = (
        f"[cyan]File       :[/cyan] {info['input']}\n"
        f"[cyan]Output     :[/cyan] {info['output']}\n"
        f"[cyan]Codec      :[/cyan] libx264 (CRF {info['crf']} · preset={info['preset']})\n"
        f"[cyan]Progress   :[/cyan] {percent:5.1f}%  ({info['time']}) ETA {eta}\n"
        f"[cyan]FPS        :[/cyan] {fps:<6} | [cyan]Bitrate:[/cyan] {bitrate:<10}\n"
        f"[cyan]Status     :[/cyan] {info['status']}"
    )
    return Panel.fit(content, title="convert2mp4", border_style="bright_blue")


# ─────────────────────────────────────────────────────────────────────────────
# CONVERSION
# ─────────────────────────────────────────────────────────────────────────────

def convert_one(input_path, output_path, overwrite=False, crf=22, preset="medium"):
    total_duration = get_duration(input_path)
    if total_duration == 0:
        console.print(f"[red]Erreur : impossible de lire {input_path}[/red]")
        return

    if os.path.exists(output_path) and not overwrite:
        console.print(f"[yellow]⚠ Fichier déjà existant :[/yellow] {output_path}")
        return

    cmd = [
        "ffmpeg", "-y" if overwrite else "-n",
        "-i", input_path,
        "-vcodec", "libx264",
        "-crf", str(crf),
        "-preset", preset,
        "-acodec", "aac", "-b:a", "192k",
        "-movflags", "+faststart",
        "-nostdin", output_path
    ]

    creationflags = 0
    if sys.platform.startswith("win"):
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

    process = subprocess.Popen(
        cmd,
        stderr=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        text=True,
        bufsize=1,
        creationflags=creationflags
    )

    cancel_requested = {"flag": False}

    def on_sigint(sig, frame):
        cancel_requested["flag"] = True

    signal.signal(signal.SIGINT, on_sigint)

    info = {
        "input": os.path.basename(input_path),
        "output": os.path.basename(output_path),
        "preset": preset,
        "crf": crf,
        "time": "00:00:00.00",
        "status": "Encoding..."
    }

    fps, bitrate = "-", "-"
    percent = 0
    start_time = time.time()

    with Live(console=console, refresh_per_second=5) as live:
        while True:
            line = process.stderr.readline()
            if not line:
                break
            if cancel_requested["flag"]:
                info["status"] = "Annulation..."
                live.update(draw_box(info, percent, "—", fps, bitrate))
                stop_ffmpeg_hard(process)
                info["status"] = "Annulé par utilisateur"
                live.update(draw_box(info, percent, "—", fps, bitrate))
                return

            m_time = re.search(r"time=(\d+:\d+:\d+\.\d+)", line)
            if m_time:
                current_time = parse_time(m_time.group(1))
                percent = (current_time / total_duration) * 100
                info["time"] = m_time.group(1)

            m_fps = re.search(r"fps=\s*([\d\.]+)", line)
            if m_fps:
                fps = m_fps.group(1)

            m_br = re.search(r"bitrate=\s*([\d\.kmbit]+)", line)
            if m_br:
                bitrate = m_br.group(1)

            elapsed = time.time() - start_time
            if percent > 0:
                est_total = elapsed / (percent / 100)
                eta = max(0, est_total - elapsed)
            else:
                eta = 0

            eta_str = format_time(eta)
            live.update(draw_box(info, percent, eta_str, fps, bitrate))

    process.wait()
    info["status"] = "✅ Terminé"
    live.update(draw_box(info, 100.0, "00:00", fps, bitrate))
    time.sleep(0.5)


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main():
    parser = argparse.ArgumentParser(description="Convertir une vidéo en MP4 (H.264/AAC)")
    parser.add_argument("-i", "--input", help="Fichier ou dossier source")
    parser.add_argument("-o", "--output_dir", help="Dossier de sortie", default=".")
    parser.add_argument("--overwrite", action="store_true", help="Écraser les fichiers existants")
    parser.add_argument("--crf", type=int, default=22, help="Qualité (0-51)")
    parser.add_argument("--preset", choices=[
        "ultrafast", "superfast", "veryfast", "faster", "fast",
        "medium", "slow", "slower", "veryslow"
    ], default="medium", help="Preset d'encodage")
    args = parser.parse_args()

    console.rule("[bold blue]convert2mp4 · ffmpeg frontend[/bold blue]")

    if not args.input:
        console.print("[yellow]Aucun fichier spécifié, recherche dans le dossier courant...[/yellow]")
        files = [f for f in os.listdir('.') if f.lower().endswith(('.mov', '.avi', '.mkv', '.mpg', '.mpeg'))]
    else:
        if os.path.isdir(args.input):
            files = [os.path.join(args.input, f) for f in os.listdir(args.input)
                     if f.lower().endswith(('.mov', '.avi', '.mkv', '.mpg', '.mpeg'))]
        else:
            files = [args.input]

    if not files:
        console.print("[red]Aucun fichier vidéo trouvé.[/red]")
        return

    for src in files:
        base = os.path.splitext(os.path.basename(src))[0]
        dst = os.path.join(args.output_dir, base + ".mp4")
        convert_one(src, dst, args.overwrite, args.crf, args.preset)

    console.rule("[green]Conversion terminée[/green]")


if __name__ == "__main__":
    main()
