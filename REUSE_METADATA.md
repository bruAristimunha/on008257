# EMD metadata reuse and enrichment notes

## Source and archive identity

This is NEMAR `on008257`, the existing mirror of OpenNeuro `ds008257`.
Do not deposit the same recordings under a second accession. The archived signal
source remains OpenNeuro 1.0.0. Upstream 1.0.1 (commit
`266a3a6ab3ca7ebf8879f62289debb1b428a31c3`) changes only CHANGES, README and
dataset_description.json: it adds the paper citation and a subject-3 eye-tracker
calibration caveat. These corrections can be adopted without claiming that the
recordings were converted again or reprocessed.

## Join EEG events to stimuli

`task-video_events.json` defines onset in seconds relative to the start of each
EEG recording. `stim_id` is the native integer video identity: 1–1000 are training
videos and 1001–1102 are test videos. Join this field to the zero-padded four-digit
keys of `derivatives/stimuli_metadata/annotations.json`. Retain subject, session,
run and trial_num as the trial key, plus is_task and correct. Durations are three
seconds; use recorded onset values, not a synthetic evenly spaced timeline.

The original identity-disjoint split must remain distinguishable from a newly
derived semantic split. Repeated observations of the same video are not
independent stimulus identities and must not leak across identity-held-out folds.
Human multi-label annotations do not define a single canonical class; do not
select the first annotation as if it were the experiment's ground-truth category.

## Available annotation assets

All 1,102 entries contain bmd_matrixfilename, MiT_url, MiT_filename, set, objects,
scenes, actions, text_descriptions, spoken_transcription, memorability_score,
memorability_decay, THINGS_uniqueID, PLACES365_classID and MiT_classID.

Preserve nested annotator responses and paired label/ontology IDs. The inspected
release contains 5–7 object-annotation groups, 5–25 scene annotations, 5–9 action
annotations, and five human text descriptions per stimulus; do not truncate all
fields to five entries. `--` denotes an absent additional object, not a category.
Do not clip positive memorability-decay estimates silently.

`llm_frame_annotations.json` contains five model-generated middle-frame captions
per stimulus under `GIT-git-large-coco`. These are not human annotations and not
full-video captions. `ME_feats_matlab/` contains computed motion-energy features,
not acquisition-raw data. `videos_with_no_audio.csv` lists 34 videos without an
audio track; an audiovisual task must retain this distinction.

The inherited BMD annotations_fieldnames.json describes **BMD** repetitions
(3 train / 10 test). EMD's experiment repeats training videos six times and test
videos 24 times per subject. Preserve the source file and record this contextual
correction rather than applying BMD repetition counts to EEG trials.

## Eye tracking and signal metadata

Raw gaze and pupil recordings are in `recording-eye1_physio` files, with
corresponding physioevents. The eye-tracker timestamp origin is system startup;
do not treat those timestamps as EEG-relative seconds without the source
synchronization information. Coordinates are pixels and pupil area is in arbitrary
units. Subject 3 has the upstream calibration caveat; additional truncated
recordings are enumerated in README.

The root sidecar describes 128 EEG channels, 1000 Hz, Fz reference and a 280 Hz
lowpass. The NEMAR measured channel-count summary is 127. Determine actual recorded
channels from each recording/header before choosing model inputs; do not invent a
128th recorded channel or treat a reference reconstruction as acquisition data.
Any filtering, resampling, rereferencing, frame sampling or feature generation is
a versioned derivative with its own provenance, not a raw BIDS conversion.

## Stimulus rights are separate from EEG rights

The EEG dataset_description license is CC0. This does **not** authorize distributing
the source video stimuli. `stimuli/stimuli_download.txt` points to the official
[BOLD Moments stimulus access page](https://boldmomentsdataset.csail.mit.edu/stimuli_metadata).
Read its [terms](https://boldmomentsdataset.csail.mit.edu/stimuli_metadata/stimuli_access.txt)
before access. Those terms limit use to non-commercial research/education and
prohibit redistribution, including videos, images, tags and text on public sites.
Consequently this enrichment includes no video/frame bytes, passwords, newly
copied stimulus tags/text, or implication that CC0 covers third-party stimuli.
Follow the source access mechanism for private eligible research. Public benchmark
metadata should reference these existing source assets rather than silently
relicense or redistribute them. Derived features also require a separate rights
assessment; transformation alone does not establish redistribution permission.

## Channel status (`*_channels.tsv`)

The source release has no `channels.tsv`. This enrichment adds one per EEG run
(768 files) with `name`, `type`, `units` and `status`, in the order of the
BrainVision header (127 channels, µV, as recorded). Channel names, order and units
were checked against the headers. Nothing in the recordings is changed:
`status` only flags channels; no channel is dropped, interpolated or rescaled.

88 channel-runs in 74 runs are `bad` under rule `emd-bads-v1`, judged over the
trial windows of each run:

- `extreme_dc_offset`: |raw| >= 0.25 V in >= 50% of in-trial samples. Channel
  offsets form a clear gap: almost all are below 0.053 V and none lie between
  0.2 and 0.3 V.
- `high_variance`: robust std after a 0.1-45 Hz filter > 5x the run's median
  channel, and > 5x the median in >= 50% of trials.
- `flat` (std < 0.1 µV after filtering) was tested and matched no channel.

Most flags are session-long electrode problems: C1 in sub-05 ses-08 and sub-06
ses-06 (all 16 runs), C1 and P6 in sub-06 ses-01, C1 in sub-04 ses-08 runs
10-16. Per channel: C1 51, P6 11, AFp2 4, FTT10h 4, others fewer. The reason is
in `status_description`. Brief artifacts (blinks, eye movements, short
excursions) are not flagged; handle them per analysis.

## References

- https://doi.org/10.48550/arXiv.2608.28768
- https://doi.org/10.1038/s41467-024-50310-3
- https://github.com/gifale95/EMD
- https://github.com/OpenNeuroDatasets/ds008257/compare/1.0.0...1.0.1
- https://data.nemar.org/on008257/v1.0.0/manifest.json

Metadata and public source evidence inspected 2026-10-06. This note is not an
end-to-end benchmark-validation claim or a change to the original study protocol.
