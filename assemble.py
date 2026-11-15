"""Video assembly for the YouTube autopilot — FFmpeg only, no paid tools.

Video: every scene image gets a slow Ken Burns move (alternating zoom-in /
zoom-out keyframes) and 0.6s crossfades between images, exactly like the
earlier What If videos. One image shows for ~5 seconds (4 images per scene,
scene-matched), and the holds are sized to the narration so the video
length equals the spoken length.
Audio: scene narration (concatenated) + a synthesised ambient music bed
(sine pads + brown noise — original, never a paid library track) + a short
synthesised SFX at each scene start, matched to the scene's SFX cue.
Output: 1280x720, 30fps, H.264 + AAC, faststart for YouTube.
"""
import json
import os
import subprocess

W, H = 1280, 720
FPS = 30
XFADE = 0.6

# SFX cue keyword -> synth recipe
SFX_MAP = [
    ("rumble", "rumble"), ("earthquake", "rumble"), ("volcano", "rumble"),
    ("rain", "rain"), ("storm", "rain"), ("pour", "rain"),
    ("wind", "wind"), ("gust", "wind"), ("blizzard", "wind"),
    ("heartbeat", "heartbeat"), ("heart", "heartbeat"),
    ("impact", "impact"), ("explosion", "impact"), ("crash", "impact"),
    ("boom", "impact"), ("erupt", "impact"),
    ("wave", "whoosh"), ("whoosh", "whoosh"), ("rush", "whoosh"),
    ("silence", "silence"), ("quiet", "silence"),
]


def sfx_kind(cue):
    cue = (cue or "").lower()
    for keyword, kind in SFX_MAP:
        if keyword in cue:
            return kind
    return "whoosh"


def run(cmd, what):
    print(" ".join(cmd[:6]), "...", what)
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-2000:])
        raise RuntimeError("FFmpeg failed: %s" % what)
    return r


def synth_sfx(kind, out_path):
    """Synthesise one short SFX wav with lavfi. Silence -> tiny quiet file."""
    if kind == "silence":
        cmd = ["ffmpeg", "-y", "-v", "error", "-f", "lavfi",
               "-i", "anullsrc=r=44100:cl=stereo", "-t", "0.5", out_path]
        run(cmd, "silence sfx")
        return
    if kind == "rumble":
        src = ("sine=frequency=55:duration=2.0,"
               "anoisesrc=duration=2.0:color=brown")
        filt = "[0:a]volume=0.5[r];[1:a]lowpass=f=120,volume=0.4[n];[r][n]amix=inputs=2:normalize=0,afade=t=in:st=0:d=0.3,afade=t=out:st=1.5:d=0.5"
        inputs = ["-f", "lavfi", "-i", "sine=frequency=55:duration=2.0",
                  "-f", "lavfi", "-i", "anoisesrc=duration=2.0:color=brown"]
    elif kind == "rain":
        src = None
        filt = "[0:a]lowpass=f=1500,volume=0.30,afade=t=in:st=0:d=0.4,afade=t=out:st=2.0:d=0.5"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=2.5:color=white"]
    elif kind == "wind":
        src = None
        filt = "[0:a]bandpass=f=400:width_type=q:width=0.6,volume=0.35,afade=t=in:st=0:d=0.5,afade=t=out:st=1.8:d=0.7"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=2.5:color=brown"]
    elif kind == "heartbeat":
        src = None
        filt = ("[0:a]volume=0.9,atrim=0:0.14,adelay=0|0[h1];"
                "[0:a]volume=0.7,atrim=0:0.12,adelay=300|300[h2];"
                "[h1][h2]amix=inputs=2:normalize=0")
        inputs = ["-f", "lavfi", "-i", "sine=frequency=60:duration=0.6"]
    elif kind == "impact":
        src = None
        filt = "[0:a]volume=0.9,afade=t=out:st=0.4:d=0.3"
        inputs = ["-f", "lavfi", "-i",
                  "aevalsrc=0.9*sin(2*PI*(140-70*t)*t):duration=0.7"]
    else:  # whoosh
        src = None
        filt = "[0:a]bandpass=f=900:width_type=q:width=0.8,volume=0.30,afade=t=in:st=0:d=0.15,afade=t=out:st=0.7:d=0.5"
        inputs = ["-f", "lavfi", "-i", "anoisesrc=duration=1.2:color=white"]
    cmd = ["ffmpeg", "-y", "-v", "error"] + inputs + [
        "-filter_complex", filt, "-t", "3", out_path]
    run(cmd, "sfx %s" % kind)


def synth_bed(duration, out_path):
    """Synthesise a quiet ambient music bed (sine pads + brown noise)."""
    cmd = ["ffmpeg", "-y", "-v", "error",
           "-f", "lavfi", "-i", "sine=frequency=110:duration=%f" % duration,
           "-f", "lavfi", "-i", "sine=frequency=164.81:duration=%f" % duration,
           "-f", "lavfi", "-i", "sine=frequency=220:duration=%f" % duration,
           "-f", "lavfi", "-i", "anoisesrc=duration=%f:color=brown" % duration,
           "-filter_complex",
           "[0:a]volume=0.20[p1];[1:a]volume=0.14[p2];[2:a]volume=0.10[p3];"
           "[3:a]lowpass=f=200,volume=0.05[n];"
           "[p1][p2][p3][n]amix=inputs=4:normalize=0,"
           "tremolo=f=0.1:d=0.4,afade=t=in:st=0:d=2,afade=t=out:st=%f:d=3" % (duration - 3),
           "-t", str(duration), out_path]
    run(cmd, "music bed")


def assemble(scene_images, timings, scenes, work_dir, out_path):
    """scene_images: list of lists (one list per scene, ~4 images each).
    timings: [{duration}] per scene. scenes: script scenes (for SFX cues).
    Each image holds for scene_duration / images_in_scene (~5s).
    Builds out_path mp4."""
    n_scenes = len(timings)
    assert len(scene_images) == n_scenes, "need one image list per scene"
    images = [p for scene in scene_images for p in scene]
    total = sum(t["duration"] for t in timings)
    print("Assembling %.1fs video from %d images" % (total, len(images)))

    # --- base hold durations (scene duration split across its images) ---
    base = []
    for i, t in enumerate(timings):
        k = len(scene_images[i])
        base += [t["duration"] / k] * k
    n_img = len(images)

    # --- synthesise bed + SFX files ---
    bed = os.path.join(work_dir, "bed.wav")
    synth_bed(total + 1, bed)
    sfx_files = []
    scene_starts = []
    acc = 0.0
    for i, scene in enumerate(scenes):
        scene_starts.append(acc)
        acc += timings[i]["duration"]
        kind = sfx_kind(scene.get("sfx", ""))
        if kind == "silence":
            continue
        path = os.path.join(work_dir, "sfx_%02d.wav" % i)
        synth_sfx(kind, path)
        sfx_files.append((path, scene_starts[i]))

    # --- build ffmpeg command ---
    cmd = ["ffmpeg", "-y", "-v", "error"]
    for j, img in enumerate(images):
        seg = base[j] + (XFADE if j < n_img - 1 else 0.0)
        cmd += ["-loop", "1", "-framerate", str(FPS), "-t", "%.3f" % seg,
                "-i", img]
    audio_inputs = []
    for t in timings:
        audio_inputs.append(t["audio"])
    n_audio = len(audio_inputs)
    for a in audio_inputs:
        cmd += ["-i", a]
    cmd += ["-i", bed]
    sfx_start_idx = len(images) + n_audio + 1
    for path, _ in sfx_files:
        cmd += ["-i", path]

    filters = []
    # video: zoompan per image (alternate zoom-in / zoom-out)
    for j in range(n_img):
        if j % 2 == 0:
            zoom = "min(zoom+0.0012,1.18)"
        else:
            zoom = "if(eq(on,0),1.18,max(zoom-0.0012,1.0))"
        filters.append(
            "[%d:v]scale=1920:1080:force_original_aspect_ratio=increase,"
            "crop=1920:1080,"
            "zoompan=z='%s':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
            "s=%dx%d:fps=%d,format=yuv420p,settb=AVTB[v%d]"
            % (j, zoom, W, H, FPS, j))
    # xfade chain
    cur = "v0"
    acc_dur = base[0]
    for k in range(1, n_img):
        offset = acc_dur
        acc_dur += base[k]
        out_lbl = "xf%d" % k if k < n_img - 1 else "vout"
        filters.append("[%s][v%d]xfade=transition=fade:duration=%.2f:offset=%.3f[%s]"
                       % (cur, k, XFADE, offset, out_lbl))
        cur = out_lbl
    # audio: resample + concat narration (no apad: apad would pad forever
    # and stall the concat filter)
    for i in range(n_audio):
        filters.append("[%d:a]aresample=44100,aformat=channel_layouts=stereo[a%d]"
                       % (n_img + i, i))
    concat_inputs = "".join("[a%d]" % i for i in range(n_audio))
    filters.append("%sconcat=n=%d:v=0:a=1[narr]" % (concat_inputs, n_audio))
    # mix: narration + bed (quiet) + delayed SFX
    filters.append("[%d:a]volume=0.08,aformat=channel_layouts=stereo[bed]"
                   % (n_img + n_audio))
    for s_i, (path, start) in enumerate(sfx_files):
        idx = sfx_start_idx + s_i
        delay_ms = int(start * 1000)
        filters.append("[%d:a]volume=0.30,adelay=%d|%d,"
                       "aformat=channel_layouts=stereo[sfx%d]"
                       % (idx, delay_ms, delay_ms, s_i))
    labels = ["narr", "bed"] + ["sfx%d" % i for i in range(len(sfx_files))]
    filters.append("%samix=inputs=%d:normalize=0,alimiter=limit=0.95,"
                   "afade=t=out:st=%.1f:d=2[aout]"
                   % ("".join("[%s]" % l for l in labels), len(labels),
                      max(total - 2, 0)))
    cmd += ["-filter_complex", ";".join(filters),
            "-map", "[vout]", "-map", "[aout]",
            "-c:v", "libx264", "-preset", "veryfast", "-crf", "20",
            "-pix_fmt", "yuv420p", "-r", str(FPS),
            "-c:a", "aac", "-b:a", "160k",
            "-movflags", "+faststart", "-t", "%.3f" % total, out_path]
    run(cmd, "assemble video")
    size = os.path.getsize(out_path)
    print("Wrote %s (%.1f MB)" % (out_path, size / 1e6))
    return out_path


if __name__ == "__main__":
    print("Import OK. Use run_one.py to build a video.")
