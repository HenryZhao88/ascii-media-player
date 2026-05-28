import os
import sys
import time
import shutil
import subprocess

import cv2


RAMP = " .,:;i1tfLCG08@"


def fit_dimensions(src_w, src_h, max_w, max_h):
    aspect = src_w / src_h
    char_aspect = 0.5
    height = max_h
    width = int(height * aspect / char_aspect)
    if width > max_w:
        width = max_w
        height = int(width * char_aspect / aspect)
    return max(1, width), max(1, height)


def frame_to_ascii(frame, width, height):
    resized = cv2.resize(frame, (width, height), interpolation=cv2.INTER_AREA)
    gray = cv2.cvtColor(resized, cv2.COLOR_BGR2GRAY)
    last = len(RAMP) - 1
    rows = []
    for row in gray:
        chars = [RAMP[(v * last) // 255] for v in row]
        rows.append("".join(chars))
    return "\n".join(rows)


def start_audio(path):
    try:
        return subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-loglevel", "quiet", path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        sys.stderr.write("ffplay not found. install ffmpeg to get audio.\n")
        return None


def play(path):
    if not os.path.exists(path):
        print(f"file not found: {path}")
        return

    cap = cv2.VideoCapture(path)
    if not cap.isOpened():
        print(f"could not open: {path}")
        return

    fps = cap.get(cv2.CAP_PROP_FPS) or 24.0
    audio = start_audio(path)

    out = sys.stdout
    out.write("\x1b[?25l\x1b[2J")
    out.flush()

    start = time.time()
    index = 0

    try:
        while True:
            ok, frame = cap.read()
            if not ok:
                break

            term = shutil.get_terminal_size((80, 24))
            src_h, src_w = frame.shape[:2]
            w, h = fit_dimensions(src_w, src_h, term.columns, term.lines - 1)
            art = frame_to_ascii(frame, w, h)

            out.write("\x1b[H" + art)
            out.flush()

            index += 1
            target = start + index / fps
            now = time.time()
            if target > now:
                time.sleep(target - now)
            elif now - target > 1.0:
                skip = int((now - target) * fps)
                for _ in range(skip):
                    cap.grab()
                    index += 1
    except KeyboardInterrupt:
        pass
    finally:
        cap.release()
        if audio and audio.poll() is None:
            audio.terminate()
            try:
                audio.wait(timeout=1)
            except subprocess.TimeoutExpired:
                audio.kill()
        out.write("\x1b[2J\x1b[H\x1b[?25h")
        out.flush()


def main():
    if len(sys.argv) < 2:
        print("usage: python player.py <media-file>")
        sys.exit(1)
    play(sys.argv[1])


main()
