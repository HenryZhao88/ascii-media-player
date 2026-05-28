import os
import sys
import time
import shutil
import subprocess


RAMP = " .,:;i1tfLCG08@"


def fit_dimensions(src_w, src_h, max_w, max_h):
    aspect = src_w / src_h
    char_aspect = 0.5
    width = max_w
    height = int(width * char_aspect / aspect)
    if height > max_h:
        height = max_h
        width = int(height * aspect / char_aspect)
    return max(1, min(width, max_w)), max(1, min(height, max_h))


def probe_video(path):
    out = subprocess.check_output(
        [
            "ffprobe", "-v", "error",
            "-select_streams", "v:0",
            "-show_entries", "stream=width,height,r_frame_rate",
            "-of", "csv=p=0:s=,",
            path,
        ],
        text=True,
    ).strip()
    w_s, h_s, rate = out.split(",")[:3]
    num, den = rate.split("/")
    fps = float(num) / float(den) if float(den) else 24.0
    return int(w_s), int(h_s), fps


def start_video(path, width, height):
    return subprocess.Popen(
        [
            "ffmpeg", "-loglevel", "quiet", "-i", path,
            "-vf", f"scale={width}:{height}:flags=area",
            "-pix_fmt", "gray",
            "-f", "rawvideo", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
    )


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


def build_lut():
    last = len(RAMP) - 1
    return bytes(ord(RAMP[(v * last) // 255]) for v in range(256))


def play(path):
    if not os.path.exists(path):
        print(f"file not found: {path}")
        return

    try:
        src_w, src_h, fps = probe_video(path)
    except (FileNotFoundError, subprocess.CalledProcessError) as e:
        print(f"ffprobe failed (install ffmpeg): {e}")
        return

    term = shutil.get_terminal_size((80, 24))
    width, height = fit_dimensions(src_w, src_h, term.columns, term.lines - 1)
    frame_size = width * height

    try:
        proc = start_video(path, width, height)
    except FileNotFoundError:
        print("ffmpeg not found. install ffmpeg.")
        return

    audio = start_audio(path)
    lut = build_lut()

    out = sys.stdout
    out_buf = out.buffer
    out.write("\x1b[?25l\x1b[2J")
    out.flush()

    start = time.time()
    index = 0
    line_clear = b"\x1b[K\n"

    try:
        while True:
            data = proc.stdout.read(frame_size)
            if len(data) < frame_size:
                break

            pixels = data.translate(lut)
            rows = [pixels[i * width:(i + 1) * width] for i in range(height)]
            art = line_clear.join(rows) + b"\x1b[J"

            out_buf.write(b"\x1b[H" + art)
            out_buf.flush()

            index += 1
            target = start + index / fps
            now = time.time()
            if target > now:
                time.sleep(target - now)
            elif now - target > 0.5:
                skip = int((now - target) * fps)
                drop = skip * frame_size
                while drop > 0:
                    chunk = proc.stdout.read(min(drop, frame_size * 32))
                    if not chunk:
                        break
                    drop -= len(chunk)
                index += skip
    except KeyboardInterrupt:
        pass
    finally:
        if proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=1)
            except subprocess.TimeoutExpired:
                proc.kill()
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
