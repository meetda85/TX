#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
autoedit.py - Edicion automatica de video con estilo dinamico para redes sociales.

Aplica, por cada video encontrado:
  1. Cortes rapidos: elimina silencios prolongados (jump cuts limpios).
  2. Zoom dinamico: zoom in/out suave y alterno (5%-10%) en cada plano.
  3. Transiciones con motion: glitch sutil (desplazamiento RGB + grano) en cada corte.
  4. Color: contraste, gamma y saturacion ligeramente realzados.

Solo usa la libreria estandar de Python + FFmpeg/ffprobe.
"""

import argparse
import json
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import time

VIDEO_EXTS = (".mp4", ".mov", ".m4v", ".avi", ".mkv", ".webm", ".wmv", ".flv", ".mpg", ".mpeg")

# ---------------------------------------------------------------- utilidades

class C:
    """Colores ANSI (se desactivan si la terminal no los soporta)."""
    on = sys.stdout.isatty() and os.environ.get("TERM") != "dumb"
    B = "\033[1m" if on else ""
    D = "\033[2m" if on else ""
    G = "\033[32m" if on else ""
    Y = "\033[33m" if on else ""
    R = "\033[31m" if on else ""
    C_ = "\033[36m" if on else ""
    X = "\033[0m" if on else ""


def hms(seconds):
    seconds = max(0, int(round(seconds)))
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"


def prog(msg):
    """Progreso transitorio: se reescribe in situ; se omite si la salida es un log."""
    if C.on:
        print("\r" + msg.ljust(72), end="", flush=True)


def line(msg):
    """Linea definitiva: sustituye al progreso en terminal, se imprime siempre."""
    print(("\r" + msg.ljust(72)) if C.on else msg)


def clear_prog():
    if C.on:
        print("\r" + " " * 72 + "\r", end="", flush=True)


def run(cmd):
    """Ejecuta un comando y devuelve (returncode, stdout, stderr)."""
    p = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    return p.returncode, p.stdout.decode("utf-8", "replace"), p.stderr.decode("utf-8", "replace")


# ------------------------------------------------- localizar carpeta Documentos

def find_documents_dir():
    """Devuelve la carpeta de Documentos del usuario, o None si no la encuentra."""
    home = os.path.expanduser("~")
    candidates = []

    # Linux: respetar XDG user-dirs (traducido segun el idioma del sistema).
    xdg = os.path.join(home, ".config", "user-dirs.dirs")
    if os.path.isfile(xdg):
        try:
            with open(xdg, "r", encoding="utf-8", errors="replace") as fh:
                for line in fh:
                    m = re.match(r'\s*XDG_DOCUMENTS_DIR\s*=\s*"(.*)"', line)
                    if m:
                        candidates.append(os.path.expandvars(
                            m.group(1).replace("$HOME", home)))
        except OSError:
            pass

    # Windows: el shell folder puede estar redirigido a OneDrive.
    if platform.system() == "Windows":
        try:
            import winreg  # noqa: F401  (solo existe en Windows)
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\CurrentVersion\Explorer\Shell Folders")
            val, _ = winreg.QueryValueEx(key, "Personal")
            candidates.append(os.path.expandvars(val))
        except Exception:
            pass
        for od in (os.environ.get("OneDrive"), os.environ.get("OneDriveConsumer")):
            if od:
                candidates += [os.path.join(od, "Documents"), os.path.join(od, "Documentos")]

    candidates += [os.path.join(home, "Documents"), os.path.join(home, "Documentos")]

    for c in candidates:
        if c and os.path.isdir(c):
            return os.path.abspath(c)
    return None


def find_videos(root, recursive, exts):
    found = []
    if recursive:
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames
                           if not d.startswith(".") and d != OUTPUT_DIRNAME]
            for fn in filenames:
                if fn.lower().endswith(exts) and not fn.startswith("."):
                    found.append(os.path.join(dirpath, fn))
    else:
        for fn in sorted(os.listdir(root)):
            full = os.path.join(root, fn)
            if os.path.isfile(full) and fn.lower().endswith(exts) and not fn.startswith("."):
                found.append(full)
    return sorted(found)


# ------------------------------------------------------------------ analisis

def probe(path):
    """Metadatos del video via ffprobe. Devuelve dict o None."""
    rc, out, _ = run(["ffprobe", "-v", "error", "-print_format", "json",
                      "-show_format", "-show_streams", path])
    if rc != 0:
        return None
    try:
        data = json.loads(out)
    except json.JSONDecodeError:
        return None

    v = next((s for s in data.get("streams", []) if s.get("codec_type") == "video"), None)
    a = next((s for s in data.get("streams", []) if s.get("codec_type") == "audio"), None)
    if v is None:
        return None

    # fps a partir de r_frame_rate ("30000/1001")
    fps = 30.0
    try:
        num, den = v.get("r_frame_rate", "30/1").split("/")
        if float(den) != 0:
            fps = float(num) / float(den)
    except (ValueError, ZeroDivisionError):
        pass
    if not (1.0 <= fps <= 240.0):
        fps = 30.0

    dur = 0.0
    for src in (data.get("format", {}).get("duration"), v.get("duration")):
        try:
            dur = float(src)
            if dur > 0:
                break
        except (TypeError, ValueError):
            continue

    return {
        "width": int(v.get("width") or 0),
        "height": int(v.get("height") or 0),
        "fps": fps,
        "duration": dur,
        "has_audio": a is not None,
        "vcodec": v.get("codec_name", "?"),
    }


def detect_silences(path, noise_db, min_silence):
    """Devuelve [(inicio, fin), ...] de los tramos silenciosos."""
    rc, _, err = run([
        "ffmpeg", "-hide_banner", "-nostats", "-i", path,
        "-af", f"silencedetect=noise={noise_db}dB:d={min_silence}",
        "-f", "null", "-",
    ])
    if rc != 0:
        return []

    silences, start = [], None
    for line in err.splitlines():
        ms = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if ms:
            start = float(ms.group(1))
            continue
        me = re.search(r"silence_end:\s*(-?[\d.]+)", line)
        if me and start is not None:
            silences.append((max(0.0, start), float(me.group(1))))
            start = None
    if start is not None:                       # silencio hasta el final
        silences.append((max(0.0, start), None))
    return silences


def build_segments(duration, silences, padding, min_clip):
    """Invierte los silencios para obtener los tramos que se conservan."""
    keep, cursor = [], 0.0
    for s_start, s_end in silences:
        # Se recorta el silencio pero se deja 'padding' de aire a cada lado.
        cut_start = s_start + padding
        if cut_start > cursor:
            keep.append((cursor, min(cut_start, duration)))
        cursor = duration if s_end is None else max(cursor, s_end - padding)
    if cursor < duration:
        keep.append((cursor, duration))

    # Fusiona tramos pegados y descarta los demasiado cortos.
    merged = []
    for start, end in keep:
        start, end = max(0.0, start), min(duration, end)
        if end - start <= 0:
            continue
        if merged and start - merged[-1][1] < 0.02:
            merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return [(s, e) for s, e in merged if e - s >= min_clip]


def chunk_segments(segments, max_len):
    """Parte los tramos largos para que el patron de zoom cambie periodicamente."""
    if max_len <= 0:
        return segments
    out = []
    for start, end in segments:
        length = end - start
        if length <= max_len:
            out.append((start, end))
            continue
        n = int(length // max_len) + 1
        step = length / n
        for i in range(n):
            out.append((start + i * step, start + (i + 1) * step if i < n - 1 else end))
    return out


# ------------------------------------------------------ construccion de filtros

def video_filter(idx, seg_dur, meta, o):
    """Cadena de filtros de video para un tramo."""
    w = meta["width"] - (meta["width"] % 2)
    h = meta["height"] - (meta["height"] % 2)
    fps = meta["fps"]
    parts = []

    # --- Zoom dinamico -------------------------------------------------
    # Alterna acercar / alejar en cada corte y varia la intensidad para que
    # el patron no se siente mecanico.
    span = o.zoom_max - o.zoom_min
    amount = o.zoom_min + span * (0.35 + 0.65 * ((idx * 7) % 5) / 4.0)
    frames = max(2, int(round(seg_dur * fps)))
    if idx % 2 == 0:                                   # zoom in
        z = f"1+{amount:.5f}*on/{frames}"
    else:                                              # zoom out
        z = f"{1 + amount:.5f}-{amount:.5f}*on/{frames}"

    if o.zoom_quality == "smooth":
        # Sobremuestrear reduce el temblor de zoompan (x/y son enteros).
        parts.append(f"scale={w * 2}:{h * 2}:flags=bicubic")
    parts.append(
        f"zoompan=z='{z}':d=1:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)'"
        f":s={w}x{h}:fps={fps:.6f}"
    )

    # --- Color y contraste ---------------------------------------------
    if not o.no_color:
        parts.append(
            f"eq=contrast={o.contrast}:saturation={o.saturation}"
            f":brightness={o.brightness}:gamma={o.gamma}"
        )
        parts.append(f"vibrance=intensity={o.vibrance}")
        if o.sharpen > 0:
            parts.append(f"unsharp=5:5:{o.sharpen}:5:5:0.0")

    # --- Glitch sutil en la entrada del corte ---------------------------
    # No se aplica al primer tramo: ahi no hay corte entrante.
    if not o.no_glitch and idx > 0:
        g = min(o.glitch_dur, seg_dur / 2.0)
        if g > 0:
            en = f"enable='lt(t,{g:.3f})'"
            parts.append(f"rgbashift=rh=-{o.glitch_shift}:bh={o.glitch_shift}:{en}")
            parts.append(f"noise=alls={o.glitch_noise}:allf=t+u:{en}")

    # --- Formato vertical opcional (9:16 con fondo desenfocado) ---------
    if o.vertical:
        parts.append(
            "split=2[vbg][vfg];"
            "[vbg]scale=1080:1920:force_original_aspect_ratio=increase,"
            "crop=1080:1920,gblur=sigma=28[vbgb];"
            "[vfg]scale=1080:-2[vfgs];"
            "[vbgb][vfgs]overlay=(W-w)/2:(H-h)/2"
        )

    parts.append("setsar=1")
    parts.append("format=yuv420p")
    return ",".join(parts)


def audio_filter(seg_dur, o):
    """Fundidos muy cortos en cada extremo para evitar chasquidos en el corte."""
    f = min(0.012, max(0.001, seg_dur / 8.0))
    return (f"afade=t=in:st=0:d={f:.4f},"
            f"afade=t=out:st={max(0.0, seg_dur - f):.4f}:d={f:.4f},"
            f"aresample=async=1:first_pts=0")


# --------------------------------------------------------------- procesamiento

def encode_segment(src, dst, start, seg_dur, idx, meta, o):
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
           "-ss", f"{start:.4f}", "-t", f"{seg_dur:.4f}", "-i", src,
           "-map", "0:v:0", "-vf", video_filter(idx, seg_dur, meta, o)]
    if meta["has_audio"]:
        cmd += ["-map", "0:a:0", "-af", audio_filter(seg_dur, o),
                "-c:a", "aac", "-b:a", o.abitrate, "-ar", "48000", "-ac", "2"]
    else:
        cmd += ["-an"]
    cmd += ["-c:v", "libx264", "-preset", o.preset, "-crf", str(o.crf),
            "-pix_fmt", "yuv420p", "-r", f"{meta['fps']:.6f}",
            "-movflags", "+faststart", dst]
    return run(cmd)


def concat_segments(files, dst, workdir):
    list_path = os.path.join(workdir, "concat.txt")
    with open(list_path, "w", encoding="utf-8") as fh:
        for f in files:
            fh.write("file '%s'\n" % f.replace("\\", "/").replace("'", r"'\''"))
    return run(["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
                "-f", "concat", "-safe", "0", "-i", list_path,
                "-c", "copy", "-movflags", "+faststart", dst])


def process_video(src, outdir, o, index, total):
    name = os.path.basename(src)
    stem = os.path.splitext(name)[0]
    dst = os.path.join(outdir, f"{stem}_editado.mp4")

    print(f"\n{C.B}[{index}/{total}] {name}{C.X}")

    if os.path.exists(dst) and not o.overwrite and not o.dry_run:
        print(f"  {C.Y}- Ya existe {os.path.basename(dst)}; se omite (usa --overwrite).{C.X}")
        return {"status": "omitido", "name": name}

    meta = probe(src)
    if not meta or meta["duration"] <= 0:
        print(f"  {C.R}x No se pudo leer el video (ffprobe fallo).{C.X}")
        return {"status": "error", "name": name}

    print(f"  {C.D}Origen : {meta['width']}x{meta['height']} @ {meta['fps']:.2f}fps, "
          f"{hms(meta['duration'])}, audio: {'si' if meta['has_audio'] else 'no'}{C.X}")

    # --- 1. Cortes rapidos ---------------------------------------------
    if meta["has_audio"] and not o.no_cuts:
        prog("  - Analizando silencios...")
        silences = detect_silences(src, o.noise_db, o.min_silence)
        segments = build_segments(meta["duration"], silences, o.padding, o.min_clip)
        line(f"  - Silencios detectados: {len(silences)}")
    else:
        reason = "sin pista de audio" if not meta["has_audio"] else "cortes desactivados"
        print(f"  - Sin deteccion de silencios ({reason}).")
        segments = [(0.0, meta["duration"])]

    if not segments:
        # Pista muda o casi inaudible: cortar por silencio dejaria el video vacio,
        # asi que se conserva entero y se aplica solo el estilo visual.
        print(f"  {C.Y}! Audio inaudible en todo el video: no se aplican cortes.{C.X}")
        print(f"    (para cortar igualmente, baja el umbral: --noise-db {o.noise_db - 12:.0f}){C.X}")
        segments = [(0.0, meta["duration"])]

    # Trocea planos largos para que el zoom cambie de forma periodica.
    segments = chunk_segments(segments, o.max_shot)
    kept = sum(e - s for s, e in segments)
    removed = meta["duration"] - kept
    pct = (removed / meta["duration"] * 100.0) if meta["duration"] else 0.0
    print(f"  - Planos: {len(segments)} | conservado {hms(kept)} | "
          f"eliminado {hms(removed)} ({pct:.1f}%)")

    if o.dry_run:
        print(f"  {C.C_}(simulacion: no se genera archivo){C.X}")
        return {"status": "simulado", "name": name, "kept": kept, "removed": removed}

    # --- 2-4. Zoom + color + glitch por plano, luego union --------------
    t0 = time.time()
    workdir = tempfile.mkdtemp(prefix="autoedit_")
    seg_files = []
    try:
        for i, (start, end) in enumerate(segments):
            seg_dur = end - start
            seg_path = os.path.join(workdir, f"seg_{i:05d}.mp4")
            bar_w = 28
            done = int(bar_w * (i + 1) / len(segments))
            bar = "#" * done + "-" * (bar_w - done)
            prog(f"  - Renderizando [{bar}] {i + 1}/{len(segments)} planos")

            rc, _, err = encode_segment(src, seg_path, start, seg_dur, i, meta, o)
            if rc != 0 or not os.path.exists(seg_path) or os.path.getsize(seg_path) == 0:
                clear_prog()
                print(f"  {C.R}x Fallo al renderizar el plano {i + 1} "
                      f"({start:.2f}s-{end:.2f}s).{C.X}")
                print("    " + (err.strip().splitlines() or ["sin detalle"])[-1][:300])
                return {"status": "error", "name": name}
            seg_files.append(seg_path)

        line(f"  - Renderizados {len(seg_files)} planos")
        prog("  - Uniendo planos...")
        rc, _, err = concat_segments(seg_files, dst, workdir)
        if rc != 0:
            clear_prog()
            print(f"  {C.R}x Fallo al unir los planos.{C.X}")
            print("    " + (err.strip().splitlines() or ["sin detalle"])[-1][:300])
            return {"status": "error", "name": name}

        size_mb = os.path.getsize(dst) / (1024 * 1024)
        elapsed = time.time() - t0
        line(f"  {C.G}OK{C.X} {os.path.basename(dst)} "
             f"({hms(kept)}, {size_mb:.1f} MB, en {hms(elapsed)})")
        return {"status": "ok", "name": name, "out": dst,
                "kept": kept, "removed": removed, "elapsed": elapsed}
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


# -------------------------------------------------------------------- entrada

OUTPUT_DIRNAME = "Videos_Editados"


def check_tools():
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if not missing:
        return True
    print(f"{C.R}Falta: {', '.join(missing)}.{C.X}\n")
    sysname = platform.system()
    if sysname == "Darwin":
        print("  Instalalo con:  brew install ffmpeg")
    elif sysname == "Windows":
        print("  Instalalo con:  winget install Gyan.FFmpeg")
        print("  (despues cierra y vuelve a abrir la terminal)")
    else:
        print("  Instalalo con:  sudo apt install ffmpeg")
    return False


def main():
    p = argparse.ArgumentParser(
        description="Edicion automatica de video: jump cuts, zoom dinamico, "
                    "glitch sutil y realce de color.",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter)
    p.add_argument("--input-dir", help="Carpeta con los videos (por defecto: Documentos)")
    p.add_argument("--output-dir", help=f"Carpeta de salida (por defecto: <entrada>/{OUTPUT_DIRNAME})")
    p.add_argument("--recursive", action="store_true", help="Buscar en subcarpetas")
    p.add_argument("--limit", type=int, default=0, help="Procesar como maximo N videos (0 = todos)")
    p.add_argument("--dry-run", action="store_true", help="Analizar sin generar archivos")
    p.add_argument("--overwrite", action="store_true", help="Rehacer videos ya editados")

    g = p.add_argument_group("cortes")
    g.add_argument("--noise-db", type=float, default=-32.0, help="Umbral de silencio en dB")
    g.add_argument("--min-silence", type=float, default=0.45, help="Silencio minimo a cortar (s)")
    g.add_argument("--padding", type=float, default=0.06, help="Aire conservado en cada corte (s)")
    g.add_argument("--min-clip", type=float, default=0.30, help="Duracion minima de un plano (s)")
    g.add_argument("--max-shot", type=float, default=4.0, help="Trocear planos mas largos que (s); 0 = no")
    g.add_argument("--no-cuts", action="store_true", help="No eliminar silencios")

    g = p.add_argument_group("zoom")
    g.add_argument("--zoom-min", type=float, default=0.05, help="Zoom minimo (0.05 = 5%%)")
    g.add_argument("--zoom-max", type=float, default=0.10, help="Zoom maximo (0.10 = 10%%)")
    g.add_argument("--zoom-quality", choices=("fast", "smooth"), default="fast",
                   help="'smooth' sobremuestrea: mas suave pero ~3x mas lento")

    g = p.add_argument_group("glitch")
    g.add_argument("--glitch-dur", type=float, default=0.07, help="Duracion del glitch (s)")
    g.add_argument("--glitch-shift", type=int, default=5, help="Desplazamiento RGB (px)")
    g.add_argument("--glitch-noise", type=int, default=14, help="Grano del glitch (0-100)")
    g.add_argument("--no-glitch", action="store_true", help="Desactivar el glitch")

    g = p.add_argument_group("color")
    g.add_argument("--contrast", type=float, default=1.06)
    g.add_argument("--saturation", type=float, default=1.12)
    g.add_argument("--brightness", type=float, default=0.012)
    g.add_argument("--gamma", type=float, default=1.02)
    g.add_argument("--vibrance", type=float, default=0.15)
    g.add_argument("--sharpen", type=float, default=0.4, help="0 = sin enfoque")
    g.add_argument("--no-color", action="store_true", help="Desactivar el ajuste de color")

    g = p.add_argument_group("salida")
    g.add_argument("--vertical", action="store_true",
                   help="Exportar 1080x1920 (9:16) con fondo desenfocado")
    g.add_argument("--crf", type=int, default=20, help="Calidad H.264 (menor = mejor)")
    g.add_argument("--preset", default="medium", help="Preset de x264")
    g.add_argument("--abitrate", default="192k", help="Bitrate de audio")

    o = p.parse_args()

    print(f"{C.B}== Edicion automatica de video =={C.X}")

    if not check_tools():
        return 2
    if o.zoom_max < o.zoom_min:
        print(f"{C.R}--zoom-max no puede ser menor que --zoom-min.{C.X}")
        return 2

    # 1. Localizar la carpeta de entrada.
    if o.input_dir:
        indir = os.path.abspath(os.path.expanduser(o.input_dir))
        if not os.path.isdir(indir):
            print(f"{C.R}No existe la carpeta: {indir}{C.X}")
            return 2
    else:
        indir = find_documents_dir()
        if not indir:
            print(f"{C.R}No encontre tu carpeta de Documentos.{C.X}")
            print("  Indicala a mano:  python3 autoedit.py --input-dir \"/ruta/a/tus/videos\"")
            return 2

    outdir = (os.path.abspath(os.path.expanduser(o.output_dir))
              if o.output_dir else os.path.join(indir, OUTPUT_DIRNAME))

    print(f"  Entrada : {indir}")
    print(f"  Salida  : {outdir}")

    # 2. Localizar los videos.
    videos = find_videos(indir, o.recursive, VIDEO_EXTS)
    videos = [v for v in videos if os.path.abspath(os.path.dirname(v)) != os.path.abspath(outdir)]
    if o.limit > 0:
        videos = videos[:o.limit]

    if not videos:
        print(f"\n{C.Y}No encontre videos {'/'.join(VIDEO_EXTS)} en esa carpeta.{C.X}")
        if not o.recursive:
            print("  Prueba con --recursive para buscar tambien en subcarpetas.")
        return 1

    print(f"  Videos  : {len(videos)}")
    for v in videos:
        print(f"    {C.D}. {os.path.relpath(v, indir)}{C.X}")

    if not o.dry_run:
        os.makedirs(outdir, exist_ok=True)

    # 3. Procesar en secuencia.
    started = time.time()
    results = []
    for i, v in enumerate(videos, 1):
        try:
            results.append(process_video(v, outdir, o, i, len(videos)))
        except KeyboardInterrupt:
            print(f"\n{C.Y}Interrumpido por el usuario.{C.X}")
            break

    # 4. Resumen.
    ok = [r for r in results if r["status"] == "ok"]
    print(f"\n{C.B}== Resumen =={C.X}")
    for r in results:
        mark = {"ok": f"{C.G}OK   {C.X}", "error": f"{C.R}ERROR{C.X}"}.get(
            r["status"], f"{C.Y}{r['status'][:5].upper():5}{C.X}")
        print(f"  {mark} {r['name']}")
    if ok:
        saved = sum(r["removed"] for r in ok)
        print(f"\n  {len(ok)}/{len(videos)} videos editados en {hms(time.time() - started)}.")
        print(f"  Tiempo muerto eliminado: {hms(saved)}.")
        print(f"  Resultados en: {outdir}")
    return 0 if ok or o.dry_run else 1


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(130)
