#!/usr/bin/env python3
"""Check every *_channels.tsv of on008257 (EMD) against its recording, and recompute rule emd-bads-v1.

usage:
    python code/check_channels.py [--data DIR] [--subjects 01,02] [--workers N] [--out DIR] [--headers-only]

Run from the root of this dataset. --data is a directory with the recordings (.vhdr/.vmrk/.eeg) and events in this
dataset's layout (default: this dataset; e.g. a `datalad get` of it, or a copy of OpenNeuro ds008257 1.0.0/1.0.1,
whose recordings are the same files). The channels.tsv files are always read from this dataset.

Checks, for every EEG run:
  1. Header. The `name` column equals the [Channel Infos] of the BrainVision header, in the same order (127
     channels), every `units` value equals the header unit (µV), and every `type` is EEG. The online reference
     (header "Reference Channel Name", Fz) is not a recorded channel and so has no row. With --headers-only, only
     this check runs and no signal is read.
  2. Rule emd-bads-v1, recomputed from the signal over the run's trial windows ([onset, onset + 3 s] for every
     events.tsv row with onset >= 0 and onset + duration inside the recording). A channel is bad if any holds:
       extreme_dc_offset  |raw| >= 0.25 V in >= 50% of the in-trial samples;
       flat               std < 0.1 µV in-trial, after 0.1-45 Hz filtering and resampling to 120 Hz;
       high_variance      robust std (1.4826 x MAD) in-trial after that filter > 5 x the run's median channel,
                          AND std > 5 x the across-channel median in >= 50% of the trials.
     The `status` column must be `bad` exactly for those channels, with the reason in `status_description`.
Prints the counts and exits 1 on any disagreement. --out writes the per-channel metrics (one TSV per subject).
"""
import argparse
import glob
import os
import re
import sys
from concurrent.futures import ProcessPoolExecutor

WIN = 3.0
RAIL = 0.25  # V


def read_tsv(path):
    import csv

    with open(path, newline="", encoding="utf-8") as f:
        return list(csv.DictReader(f, delimiter="\t"))


def header_channels(vhdr):
    """[(name, unit)] from [Channel Infos], and the reference channel name."""
    text = open(vhdr, encoding="utf-8", errors="replace").read()
    sec = re.search(r"\[Channel Infos\](.*?)(?:\n\[|\Z)", text, re.S).group(1)
    chans = []
    for line in sec.splitlines():
        m = re.match(r"Ch(\d+)=([^,]*),([^,]*),([^,]*),(.*)$", line.strip())
        if m:
            chans.append((int(m.group(1)), m.group(2), m.group(5).strip() or "µV"))
    chans.sort()
    ref = re.search(r"Reference Channel Name\s*=\s*(\S+)", text)
    n = re.search(r"NumberOfChannels=(\d+)", text)
    return [(c, u) for _, c, u in chans], (ref.group(1) if ref else None), (int(n.group(1)) if n else None)


def rule(vhdr, events_tsv):
    """{channel: reason} under emd-bads-v1, plus the per-channel metrics."""
    import mne
    import numpy as np

    mne.set_log_level("ERROR")
    raw = mne.io.read_raw_brainvision(vhdr, preload=True, verbose=False)
    sf = raw.info["sfreq"]
    ev = read_tsv(events_tsv)
    end = raw.n_times / sf
    onsets = [float(r["onset"]) for r in ev
              if float(r["onset"]) >= 0 and float(r["onset"]) + float(r["duration"]) <= end]
    x = raw.get_data()
    mask = np.zeros(raw.n_times, bool)
    for o in onsets:
        mask[int(round(o * sf)): int(round((o + WIN) * sf))] = True
    rail_frac = (np.abs(x[:, mask]) >= RAIL).mean(axis=1)
    f = raw.copy().filter(0.1, 45.0, verbose=False).resample(120.0, verbose=False).get_data()
    m120 = np.zeros(f.shape[1], bool)
    segs = []
    for o in onsets:
        a, b = int(round(o * 120)), min(int(round((o + WIN) * 120)), f.shape[1])
        m120[a:b] = True
        segs.append((a, b))
    fin = f[:, m120]
    fstd = fin.std(axis=1)
    med = np.median(fin, axis=1, keepdims=True)
    rstd = 1.4826 * np.median(np.abs(fin - med), axis=1)
    ratio = rstd / np.median(rstd)
    tstd = np.stack([f[:, a:b].std(axis=1) for a, b in segs], axis=1)
    frac5 = (tstd > 5 * np.median(tstd, axis=0, keepdims=True)).mean(axis=1)
    bad = {}
    for i, ch in enumerate(raw.ch_names):
        why = []
        if rail_frac[i] >= 0.5:
            why.append("extreme_dc_offset")
        if fstd[i] < 1e-7:
            why.append("flat")
        if ratio[i] > 5 and frac5[i] >= 0.5:
            why.append("high_variance")
        if why:
            bad[ch] = why
    metrics = [dict(channel=ch, n_trials=len(onsets), rail_frac=rail_frac[i], filt_std_V=fstd[i],
                    robust_std_ratio=ratio[i], frac_trials_std_gt5x=frac5[i]) for i, ch in enumerate(raw.ch_names)]
    return bad, metrics


def check_run(args):
    chan_tsv, data, headers_only = args
    rel = os.path.relpath(chan_tsv, ".")
    vhdr = os.path.join(data, rel.replace("_channels.tsv", "_eeg.vhdr"))
    events = os.path.join(data, rel.replace("_channels.tsv", "_events.tsv"))
    if not os.path.exists(events):
        events = rel.replace("_channels.tsv", "_events.tsv")
    rows = read_tsv(chan_tsv)
    out = dict(run=rel, problems=[], n_bad_tsv=sum(r["status"] == "bad" for r in rows), metrics=[])
    P = out["problems"].append
    hdr, ref, n = header_channels(vhdr)
    if [r["name"] for r in rows] != [c for c, _ in hdr]:
        P("names/order differ from the header")
    if n is not None and n != len(hdr):
        P(f"header NumberOfChannels {n} != {len(hdr)} channel lines")
    for r, (c, u) in zip(rows, hdr):
        if r["units"] != u:
            P(f"{c}: units {r['units']!r} != header {u!r}")
        if r["type"] != "EEG":
            P(f"{c}: type {r['type']!r}")
    if ref and ref in {r["name"] for r in rows}:
        P(f"reference {ref} listed as a recorded channel")
    out.update(n_channels=len(rows), reference=ref)
    if headers_only:
        return out
    bad, metrics = rule(vhdr, events)
    out["metrics"] = [dict(run=rel, **m) for m in metrics]
    out["n_bad_rule"] = len(bad)
    for r in rows:
        want = bad.get(r["name"])
        if want is None and r["status"] != "good":
            P(f"{r['name']}: status {r['status']} but the rule finds it good")
        elif want is not None:
            if r["status"] != "bad":
                P(f"{r['name']}: the rule finds it bad ({','.join(want)}) but status is {r['status']}")
            elif not all(w in r["status_description"] for w in want) or "emd-bads-v1" not in r["status_description"]:
                P(f"{r['name']}: status_description {r['status_description']!r} lacks {want}")
    return out


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--data", default=".")
    ap.add_argument("--subjects", default="")
    ap.add_argument("--workers", type=int, default=1)
    ap.add_argument("--out", default="")
    ap.add_argument("--headers-only", action="store_true")
    a = ap.parse_args()
    subs = [s for s in a.subjects.split(",") if s] or ["*"]
    files = sorted(f for s in subs for f in glob.glob(f"sub-{s}/ses-*/eeg/*_task-video_run-*_channels.tsv"))
    vhdrs = sorted(glob.glob(os.path.join(a.data, "sub-*/ses-*/eeg/*_task-video_run-*_eeg.vhdr")))
    if not files:
        sys.exit("no channels.tsv found; run from the dataset root")
    with ProcessPoolExecutor(a.workers) as ex:
        res = list(ex.map(check_run, [(f, a.data, a.headers_only) for f in files]))
    probs = [(r["run"], p) for r in res for p in r["problems"]]
    print(f"channels.tsv files: {len(files)}")
    if a.subjects == "":
        print(f"recordings (_eeg.vhdr) under --data: {len(vhdrs)}; without a channels.tsv: "
              f"{len({v.replace('_eeg.vhdr', '') for v in vhdrs} - {os.path.join(a.data, f).replace('_channels.tsv', '') for f in files})}")
    print(f"channels per file: {sorted({r['n_channels'] for r in res})}; online reference: {sorted({str(r['reference']) for r in res})}")
    print(f"channel-runs marked bad in channels.tsv: {sum(r['n_bad_tsv'] for r in res)} in "
          f"{sum(r['n_bad_tsv'] > 0 for r in res)} runs")
    if not a.headers_only:
        print(f"channel-runs bad under the recomputed rule: {sum(r['n_bad_rule'] for r in res)} in "
              f"{sum(r['n_bad_rule'] > 0 for r in res)} runs")
    print(f"runs with a disagreement: {len({r for r, _ in probs})}; problems: {len(probs)}")
    for r, p in probs[:50]:
        print("  ", r, p)
    if a.out and not a.headers_only:
        import csv

        os.makedirs(a.out, exist_ok=True)
        rows = [m for r in res for m in r["metrics"]]
        name = os.path.join(a.out, f"emd_bads_v1_metrics_{a.subjects.replace(',', '_') or 'all'}.tsv")
        with open(name, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]), delimiter="\t", lineterminator="\n")
            w.writeheader()
            w.writerows(rows)
        print("metrics:", name)
    return 1 if probs else 0


if __name__ == "__main__":
    sys.exit(main())
