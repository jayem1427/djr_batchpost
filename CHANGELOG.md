# Changelog

## v1.4.0 — 2026-11-26

### New
- **Post Combined dialog** ([#7](https://github.com/jayem1427/djr_batchpost/issues/7)). Post Combined (toolbar and right-click) now asks before posting:
  - **File**: folder and name on one line, pre-filled (one right-clicked setup → its name). Edit it, or **Browse…** for the Save As window. New folders are created.
  - **Post options…**: keeps an NC Program in the document and selects it, so Fusion's own post settings (4th axis and so on) are one double-click away.
  - **Post** / **Cancel**. Post stays greyed out until the File line has a folder and a name.
- **No more leftover NC Programs** ([#6](https://github.com/jayem1427/djr_batchpost/issues/6)). Without an NC Program in the document, Post Combined posts through a temporary one and deletes it afterwards. (Fusion's API can't post without an NC Program at all: the call that did was retired in September 2025.)
- **New icons.** The "merge" icon: three toolpaths becoming one file. Dark for DJR Batch Post, orange for Post Combined, sliders for Configure.

### Fixed
- Configure: **Also apply to this document's NC Program** failed when an output folder was set.

### Changed
- When no post-processor has been chosen yet, Post Combined points you to Configure DJR Batch Post.

## v1.3.0 — 2026-11-24

### New
- **Configure DJR Batch Post** (Manufacture workspace → Utilities → Add-Ins). Choose the post processor and output folder that Post Combined uses when it creates an NC Program, without editing an NC Program first. Lists the posts in your own libraries, with an option to include Fusion's built-in posts.
  - Optionally applies the same post and folder to the open document's NC Program.
  - Also sets the defaults for new documents: Restore rapid moves, Minimum rapid move distance, and Rotate A-axis between setups. Documents that already have settings keep them.

## v1.2.1 — 2026-11-24

### Changed
- **File names keep their spaces.** A setup named `Top side` is now written as `Top side.ngc` instead of `Top_side.ngc`, and the same goes for document, operation and tool file names. Characters Windows doesn't allow in file names (`< > : " / \ | ? *`) are still replaced with `_`.

## v1.2.0 — 2026-11-19

Fixes: rapids restored at every operation's entry and exit, MillenniumOS posts, and NC Programs keeping their operations.

### Restore rapid moves: entries and exits ([#5](https://github.com/jayem1427/djr_batchpost/issues/5))
- **Operation entries are now rapids.** After a G0, Fusion Personal descends at a stand-in "rapid" feed before the real plunge. Those lines are now G0, up to the line where the feed changes (the real plunge, which stays G1). If the feed never changes, nothing is converted, so a G1 plunge straight into the part (for example drilling) is never turned into a rapid.
- **Operation exits are now rapids.** A G1 rise that is the last move before a G0, a `G53`/`G28`/`G30` move, or the end of the operation becomes G0, including two-step retracts.
- Entries and exits ignore *Minimum rapid move distance*, because they are usually 10–17 mm.
- `G94 G1 Z40.` used to become `G0 G94 G1 Z40.`, which still ran as a feed. The motion word is now replaced wherever it appears on the line.
- **Feed is restored after a restored rapid.** The end marker now puts back the last feed that was removed (`G1 F3600. (Rapid movement end)`), so a cutting line without its own F no longer runs at an older feed.

### Fixed
- Posts that don't end with `M30` (e.g. MillenniumOS, which ends with `M5.9`/`M0`) were reported as "output file was not created". A stable output file now counts as complete, and the add-in finds the file Fusion actually wrote.
- Posting overwrote the NC Program's operation list with the last operation posted, and never restored it. Your NC Program now keeps its operations.

### For developers
- `tools/fusion_sim/` runs the add-in end to end against a fake Fusion API (`python tools/fusion_sim/run_all.py`). It's part of the Tests workflow.
- `CLAUDE.md` documents the layout, file locations, release and install steps, and the invariants.

## v1.1.0 — 2026-11-18

Right-click a setup and get G-code, even in a document with no NC Program.

### New
- **Right-click a setup → Post Combined (DJR).** Posts exactly the right-clicked setup(s) into one file. A single setup is written to a file named after it.
- **Automatic NC Program.** When a document has no usable NC Program, Post Combined creates one covering every setup. It uses the post-processor and output folder remembered from your last successful post. If you've never posted, it uses the only post in your own library, when there is exactly one.

## v1.0.0 — 2026-11-18

The project is now **djr_batchpost**, and posting a combined file takes one click.

### New
- **Post Combined** button. It posts straight to one combined G-code file with no dialog, using the NC Program, folder, file name and G-code options last saved by the dialog. Setups selected in the CAM browser are posted; with none selected, every valid setup is. It never clears the output folder and never changes your saved grouping.
- After posting, both buttons list the files that were written and offer to open the output folder.
- When an output file already exists, you're asked whether to overwrite it, instead of getting an error. For Single file output the check happens *before* anything is posted.
- New logo and icons for the toolbar buttons and the Scripts and Add-Ins list. They replace the leftover Carvera artwork.
- A *Release* GitHub workflow and `tools/build_release.py` build an installable zip whenever a `v*` tag is pushed.

### Changed
- Renamed to `djr_batchpost`, with **DJR Batch Post** as the display name. The add-in folder must now be named `djr_batchpost`. Per-document settings saved by older versions are kept.
- The dialog preselects an NC Program: the last one used, or else the first one with a post-processor.
- New documents default to **Single file** grouping. Documents that already have settings, and any saved defaults, keep their choice.
- The add-in runs on startup by default.
- Debug console logging is off by default (`DEBUG = False` in `config.py`).
- The README has been rewritten, and the outdated Carvera-branded screenshots are removed.

### Fixed
- Any settings change silently overwrote the defaults for new documents when the dialog closed, so **Save as default settings** had no real effect. The defaults file now changes only through that button, or once on first run.
- The dialog's input tab used `from ast import Tuple` as a type annotation. That raises `TypeError` on import under Python 3.11–3.13.
- A document with no saved settings inherited the in-memory settings of the last document you used, such as its overwrite flag or grouping, instead of starting from the defaults.
- `is not -1` comparison in `operation.py` (a `SyntaxWarning`) replaced with `!=`.
- Tests: a stale parser expectation was updated. Tests that need local `.ngc` captures, which are gitignored, are now skipped when the files are missing.

## v0.9.2
- A-axis G-code is injected between setups without needing a Fusion 4-axis machine definition.
- Rapid restore, trailing end-code detection, and whole-word G/M code matching fixes.
