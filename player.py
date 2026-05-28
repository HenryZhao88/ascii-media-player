import os
import sys
import time
import shutil
import subprocess


QUADRANTS = [c.encode() for c in " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"]


def fit_pixel_dimensions(src_w, src_h, max_cols, max_rows):
    max_px_w = max_cols * 2
    max_px_h = max_rows * 2
    aspect = src_w / src_h
    px_w = max_px_w
    px_h = int(px_w / (2 * aspect))
    if px_h > max_px_h:
        px_h = max_px_h
        px_w = int(px_h * 2 * aspect)
    px_w -= px_w % 2
    px_h -= px_h % 2
    return max(2, px_w), max(2, px_h)


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
            "-pix_fmt", "rgb24",
            "-f", "rawvideo", "-",
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        bufsize=0,
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
    px_w, px_h = fit_pixel_dimensions(src_w, src_h, term.columns, term.lines - 1)
    cols = px_w // 2
    rows = px_h // 2
    frame_size = px_w * px_h * 3
    row_size = px_w * 3

    try:
        proc = start_video(path, px_w, px_h)
    except FileNotFoundError:
        print("ffmpeg not found. install ffmpeg.")
        return
    assert proc.stdout is not None

    audio = start_audio(path)

    out = sys.stdout
    out_buf = out.buffer
    out.write("\x1b[?25l\x1b[2J")
    out.flush()

    start = time.time()
    index = 0
    line_end = b"\x1b[K\n"
    reset = b"\x1b[0m"

    try:
        while True:
            data = proc.stdout.read(frame_size)
            if len(data) < frame_size:
                break

            parts = [b"\x1b[H"]
            for y in range(rows):
                top = (y * 2) * row_size
                bot = (y * 2 + 1) * row_size
                last_fg = None
                last_bg = None
                for x in range(cols):
                    i = x * 6
                    j = i + 3
                    p0 = (data[top + i], data[top + i + 1], data[top + i + 2])
                    p1 = (data[top + j], data[top + j + 1], data[top + j + 2])
                    p2 = (data[bot + i], data[bot + i + 1], data[bot + i + 2])
                    p3 = (data[bot + j], data[bot + j + 1], data[bot + j + 2])
                    pix = (p0, p1, p2, p3)

                    lums = [p[0] * 299 + p[1] * 587 + p[2] * 114 for p in pix]
                    thr = (min(lums) + max(lums)) >> 1

                    bits = 0
                    fr = fg_g = fb = 0
                    br_ = bg_g = bb = 0
                    fc = bc = 0
                    for k in range(4):
                        p = pix[k]
                        if lums[k] > thr:
                            bits |= 1 << k
                            fr += p[0]; fg_g += p[1]; fb += p[2]; fc += 1
                        else:
                            br_ += p[0]; bg_g += p[1]; bb += p[2]; bc += 1
                    fg = (fr // fc, fg_g // fc, fb // fc) if fc else pix[0]
                    bgc = (br_ // bc, bg_g // bc, bb // bc) if bc else pix[0]

                    if fg != last_fg:
                        parts.append(b"\x1b[38;2;%d;%d;%dm" % fg)
                        last_fg = fg
                    if bgc != last_bg:
                        parts.append(b"\x1b[48;2;%d;%d;%dm" % bgc)
                        last_bg = bgc
                    parts.append(QUADRANTS[bits])
                parts.append(reset)
                parts.append(line_end)
            parts.append(b"\x1b[J")

            out_buf.write(b"".join(parts))
            out_buf.flush()

            index += 1
            target = start + index / fps
            now = time.time()
            if target > now:
                time.sleep(target - now)
            elif now - target > 0.5:
                skip = int((now - target) * fps)
                drop = skip * frame_size
                while drop > 0 and proc.stdout is not None:
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
