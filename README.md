<p align="center">
  <img src="resources/branding/logo.svg" alt="djr_batchpost" width="560">
</p>

<p align="center">
  An Autodesk Fusion add-in that posts every operation in your setups into <b>one combined G-code file</b>,<br>
  or one file per setup, per tool, or per operation. Works with any post-processor.
</p>

<p align="center">
  <a href="https://github.com/jayem1427/djr_batchpost/releases/latest">Download</a> ·
  <a href="#quick-start">Quick start</a> ·
  <a href="#the-two-buttons">The two buttons</a> ·
  <a href="#options-reference">Options</a> ·
  <a href="#troubleshooting">Troubleshooting</a> ·
  <a href="CHANGELOG.md">Changelog</a>
</p>

---

## Why

**Fusion Personal** can't post a multi-tool program in one go. djr_batchpost posts each operation on its own through your normal post-processor, then stitches the results into a single file with the header, tool changes, and program end in the right places.

It also helps on paid Fusion:

- It merges several setups into one program, and can write A-axis moves between them for indexed 4th-axis work.
- It can restore rapids: Fusion Personal posts retracts as `G1`, and this turns them back into `G0`.
- It can combine back-to-back operations that use the same tool.

## Quick start

1. **Install.** Download `djr_batchpost-vX.Y.Z.zip` from the [latest release](https://github.com/jayem1427/djr_batchpost/releases/latest) and unzip it. You get a folder named `djr_batchpost`.
2. In Fusion, open **Utilities → Add-Ins → Scripts and Add-Ins**, click **+ → Script or add-in from device**, and pick that `djr_batchpost` folder. Click **Run** and tick **Run on startup**.
3. **Right-click a setup → Post Combined (DJR)**, or click **Post Combined** in the toolbar. You get G-code.

The very first time, the add-in needs to learn your post-processor. If you only have one post in your own post library, it uses that automatically. Otherwise, post once from a document that has an NC Program with your post selected (with either button). From then on, documents without an NC Program get one created automatically, with that post and the same output folder.

> [!IMPORTANT]
> The add-in folder **must** be named `djr_batchpost`, because Fusion looks for `djr_batchpost/djr_batchpost.py`. If you clone with git, clone into that folder name (see [Install from source](#install-from-source)).

## The two buttons and the right-click menu

Both buttons are in the **Actions** panel of the Manufacture workspace, next to Fusion's own Post Process button.

| | Button | What it does |
|---|---|---|
| <img src="resources/branding/icon.svg" width="32"> | **DJR Batch Post** | Opens the full dialog. Here you choose the NC Program, setups, grouping, G-code options and output. Your choices are saved in the document. |
| <img src="resources/branding/icon-quick.svg" width="32"> | **Post Combined** | Posts with no dialog. It always writes **one combined file** and uses the NC Program, folder, file name and G-code options last saved by the dialog. |
| | **Right-click a setup → Post Combined (DJR)** | Same as Post Combined, but posts exactly the setup(s) you right-clicked. **One setup is written to a file named after the setup** (e.g. `Top_side.ngc`). Several setups go into the NC Program's file name. |

**Which setups does Post Combined post?** If you have setups selected in the CAM browser, only those (Ctrl/Cmd-click to select several). With nothing selected, it posts every setup that isn't suppressed or in error.

**No NC Program in the document?** Post Combined creates one called *DJR Batch Post* that covers every setup. It uses the post-processor and output folder from your last successful post, and names the file after the document (`Bracket v12` → `Bracket.ngc`). If that post can't be found in your post libraries, it tells you instead of guessing. Your own libraries (Local, Cloud, Network) are searched before Fusion's built-in posts. The post is remembered in `commands/postProcessor/settings/remembered_post.json` inside the add-in folder; delete that file to make it forget.

**What Post Combined never does:** it never clears the output folder, and it never changes your saved grouping. If the target file already exists, it asks before overwriting.

When posting finishes, both buttons show the files that were written and offer to open the folder.

### What happens when you post

```
NC Program (post-processor + output folder + file name)
        │
        ▼
for each selected setup ─► for each operation ─► post through your .cps ─► temp file
        │
        ▼
merge: one header ─► tool comments ─► bodies (+ tool changes, A-axis moves, rapid restore) ─► one tail
        │
        ▼
<output folder>/<file name>.<post extension>
```

The header of every file shows the version that wrote it: `(Generated with DJR Batch Post version 1.1.0)`.

## Options reference

The dialog has four tabs. Each change is saved to the document as you make it. **Save as default settings** stores the current settings as the starting point for new documents.

### Input Selection

- **NC Program.** This preselects the program you last used, or else the first program that has a post-processor. The dropdown only lists NC Programs with at least one operation, so it hides empty programs.
- **Machine.** Optional. A-axis moves are written by this add-in from each setup's WCS, so no 4-axis machine definition is required. If a machine *is* attached and has no A-axis, you get a warning before rotated setups are posted.
- **Post Processor.** Required.
- **Setups table.** Check the setups to post. Order matters for A-axis rotation. Origin, X-axis alignment and rotation are shown relative to the first checked setup. Misaligned WCS triggers a warning when you post rather than blocking the setup.

### G-code Options

| Option | Notes |
|---|---|
| Rotate A-Axis between setups | Writes A moves between setups from their WCS orientation. |
| Retract Y on A-axis rotation / coordinate | Optional `G53` Y retract before rotating. |
| Restore rapid moves | Rewrites Z-up → XY traverse → Z-down patterns from `G1` to `G0`, marked with `(Rapid movement start/end)`. Each operation gets a `(Rapid restore: N segment(s))` note. |
| Minimum rapid move distance (mm) | Links shorter than this are ignored. Raise it (20–30) if facing stepovers get converted. |
| Add line numbers | Optional N-word numbering. |
| G-code blocks | Tool-change preamble (`M9`), end-of-program codes (`M5 M9 M30`), and header-end codes (`G20 G21`). Codes match whole words, so `M3` never matches `M30`. |

### Output Options

| Option | Notes |
|---|---|
| Output folder / File name | Taken from the NC Program. The extension comes from the post-processor. |
| Operations grouping | **Single file** (default) · Group on setup · Group on setup and tool · One file per operation. |
| Combine operations using same tool | Posts consecutive operations that use the same tool together, so there's no repeated tool change between them. |
| Flat file structure | For multi-file groupings, writes the files straight into the output folder instead of into subfolders (named after the file name, and per setup for the setup-and-tool and per-operation groupings). |
| Prepend sequence number / Name must be numeric | File-naming helpers for controllers that need numbered programs. |
| Overwrite existing files | When it's off, you're asked before a file is overwritten. |
| Clear output folder | Empties the folder before writing. This requires Overwrite. **Post Combined never uses it.** |

### Misc

Language (English / Svenska) and setup search-and-replace renaming (optionally with regex).

## Troubleshooting

| Symptom | Fix |
|---|---|
| No buttons in Manufacture | Check that the folder is named `djr_batchpost` and that the add-in is running in *Scripts and Add-Ins*. Then restart Fusion. |
| You upgraded from "Batch Post" and now see two sets of buttons | Stop and remove the old `Batch Post` add-in in *Scripts and Add-Ins*. Your per-document settings carry over. |
| "No usable NC Program found" | Create an NC Program, pick a post-processor, and add at least one operation. |
| A file is missing in a multi-setup post | Make sure every setup's toolpaths are valid (no red ✕) and not suppressed. |
| Rapids weren't restored on a facing pass | Raise *Minimum rapid move distance*. |
| Want detailed logs | Set `DEBUG = True` in `config.py` and watch the *Text Commands* window. |

Always verify the result in a viewer such as [NCViewer](https://ncviewer.com) and air-cut before running new output on the machine.

## Install from source

```bash
git clone https://github.com/jayem1427/djr_batchpost.git djr_batchpost
```

Then add the `djr_batchpost` folder in Fusion as in the Quick start. After a `git pull`, stop and start the add-in (or restart Fusion) to load the new code.

## Development

```bash
pip install pytest
python -m pytest
```

The tests stub the Fusion `adsk` API, so they run anywhere. They cover the parsers, the G/M code matching, tail and rapid detection, A-axis injection, NC Program preselection, the overwrite prompt, and packaging checks (icons present, manifest and `config.py` versions in sync).

**Releasing:** bump `"version"` in `djr_batchpost.manifest` and `PLUGIN_VERSION` in `config.py`, add a section to `CHANGELOG.md`, then push a tag:

```bash
git tag v1.1.0 && git push origin v1.1.0
```

The *Release* workflow runs the tests, builds `djr_batchpost-v1.1.0.zip` with `tools/build_release.py`, and publishes a GitHub release with the changelog section as its notes. To build the zip locally, run `python tools/build_release.py` (it writes to `dist/`).

### Layout

```
djr_batchpost.py / .manifest / .svg   Fusion entry point, metadata, add-in icon
config.py                             PLUGIN_VERSION, DEBUG
commands/postProcessor/
  dialog/                             the DJR Batch Post dialog (+ resources/ icons)
  quick_post.py                       the Post Combined button (+ dialog/resources_quick/ icons)
  post_runner.py                      shared run: safety prompts, post, overwrite prompt, report
  setups/ operations/                 posting and merging
  resources/i18n/                     translations
resources/branding/                   logo and icon sources (SVG)
tools/build_release.py                release zip builder
```

## Acknowledgments

djr_batchpost is a fork of the [Makera Community Fusion Plugin](https://github.com/Carvera-Community/CarveraCommunity_FusionPlugin), which was itself inspired by Tim Paterson's [PostProcessAll](https://github.com/TimPaterson/Fusion360-Batch-Post). Thanks to both projects and their communities. This fork is machine-agnostic and carries no vendor branding.

## License

GNU General Public License v2.0, the same as the upstream project.
