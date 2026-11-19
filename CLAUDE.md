# CLAUDE.md: working on djr_batchpost

An Autodesk Fusion add-in (Python) that posts every operation in the chosen CAM setups and merges them into **one G-code file**, or one per setup, tool or operation. The owner uses it with **Fusion Personal**, which can't post multi-tool programs by itself, and a **LinuxCNC** mill (`.ngc` output). The project is a fork of the Makera Community Fusion Plugin. Read `README.md` for the user-facing behaviour and `CHANGELOG.md` for history.

## Where things live

| What | Where |
|---|---|
| GitHub repo | `jayem1427/djr_batchpost` (renamed from `miniMonster_djr_batch_post`; old URLs redirect). Default branch `main`. |
| Installed add-in (owner's Windows PC) | `%APPDATA%\Autodesk\Autodesk Fusion 360\API\AddIns\djr_batchpost\` |
| Old pre-rename add-in | `%APPDATA%\...\API\AddIns\Batch Post\`. Stopped, with *Run on startup* off. **Keep it** unless the owner asks to remove it. |
| Defaults for new documents | `commands/postProcessor/settings/settings.settings` inside the add-in folder. Gitignored; written at runtime. |
| Remembered post processor | `commands/postProcessor/settings/remembered_post.json` (description/vendor/extension + output folder). Gitignored; deleting it makes the add-in forget. |
| Per-document settings | Inside each `.f3d`, as the document attribute group `BatchPost_Post_Processor`, name `settings` (JSON). |
| Release zips | Built into `dist/` (gitignored) by `tools/build_release.py`. |

**The add-in folder must be named `djr_batchpost`**, because Fusion loads `<folder>/<folder>.py` and `<folder>.manifest`. Command IDs are derived from the folder name.

## Code map

```
djr_batchpost.py / .manifest / .svg   entry point (run/stop), metadata, Scripts-and-Add-Ins icon
config.py                             PLUGIN_VERSION, DEBUG (console logging; False for releases)
commands/commands.py                  registers PostDialog, then QuickPostCommand (order matters)
commands/postProcessor/
  config.py                           command IDs/names, incl. QUICK_CMD_ID and QUICK_CTX_CMD_ID
  const.py                            ATTR_GROUP etc. (see invariants)
  dialog/                             the "DJR Batch Post" dialog (+ resources/ toolbar icons)
  quick_post.py                       "Post Combined" toolbar button + setup right-click entry
  post_runner.py                      shared run: safety prompts, post, overwrite prompt, report, remember post
  auto_program.py                     create an NC Program when the document has none (Fusion API side)
  post_memory.py                      remember/find the post processor (pure, no adsk)
  quick_post_helpers.py               pure helpers: program preselection, output paths, file naming
  run_report.py                       records which output files a run wrote
  program.py / programs.py            wrapper around Fusion NCProgram(s); Process() and Generate()
  setups/ operations/                 posting each operation to a temp file, parsing, merging
  operations/operation/rapidsParser.py  "Restore rapid moves" (links, entries, exits)
  operations/operation/body.py        writes each operation body (rapid rewriting happens here)
  gcode_helpers.py                    pure G-code helpers (end codes, rapids, A-axis, post output)
  settings/                           Settings store (document + defaults)
  resources/i18n/en.json, sv.json     UI strings; keys are the English text
resources/branding/                   logo and icon SVG sources (README uses these)
resources/readme/                     README screenshots (not shipped in the zip)
tools/build_release.py                builds dist/djr_batchpost-vX.Y.Z.zip + RELEASE_NOTES.md
tools/fusion_sim/                     end-to-end simulation against a fake Fusion API
tests/                                pytest; tests/adsk_stub.py stubs the Fusion API
```

**How a post works:** `Program.Process` → `Setups.Parse` → each `Operation.Parse` points the NC Program at one group of operations and calls Fusion's `postProcess()` into a temp folder. The temp file is then parsed into header, body and tail. `Program.Generate` merges everything into the final file(s) according to the grouping, injecting tool changes, A-axis moves and rapid restoration along the way.

## Testing (run all three before pushing)

```bash
python -m pytest                       # unit tests, Fusion API stubbed
python tools/fusion_sim/run_all.py     # builds the zip, runs both end-to-end sims
python tools/build_release.py --check  # manifest/config versions match, CHANGELOG has the section
```

- The sims (`sim_core.py`, `sim_one_click.py`) exercise start/stop, toolbar and right-click wiring, NC Program auto-creation, posting, overwrite prompts and output files. Extend `fake_fusion.py` when you touch new Fusion API surface.
- `*.ngc` captures (`1001.ngc`, `Setup1.ngc`) are gitignored, so the tests that use them are skipped in CI. Put new G-code cases **inline** in the tests (see `tests/test_rapid_entries_exits.py`).
- None of this replaces a real Fusion run. Be explicit about what you verified in Fusion versus only in tests or the simulation.

## Releasing

1. Bump `"version"` in `djr_batchpost.manifest` **and** `PLUGIN_VERSION` in `config.py`.
2. Add `## vX.Y.Z — date` to `CHANGELOG.md`. Its body becomes the release notes.
3. Push to `main`, then push a tag: `git tag vX.Y.Z && git push origin vX.Y.Z`.
4. `.github/workflows/release.yml` runs the tests, checks that the tag matches the version, builds the zip, and creates the release (or updates an existing release with that tag).

A tag that doesn't match the code version makes the workflow fail without uploading anything. That's deliberate. Because this repo is a fork, Actions may need enabling in the Actions tab.

**Cloud Claude sessions (claude.ai) cannot push tags, create or edit releases, delete branches, or change repo settings.** The session proxy blocks it. A local Claude Code session using the owner's `git`/`gh` can do all of these.

## Installing a dev build on the owner's PC

Copy the changed files (or the unzipped `dist/` build) into the installed add-in folder. Then reload: in Fusion, open **Utilities → Add-Ins → Scripts and Add-Ins** (Shift+S) and toggle **djr_batchpost** off and on, or restart Fusion.

- Starting the add-in closes the Scripts and Add-Ins dialog. That's expected (`PostDialog.start` resets the active command).
- The version shown in that list is cached until Fusion restarts.
- A quick check that it loaded: right-click a setup in the CAM browser. **Post Combined (DJR)** should be at the bottom of the menu.

## Invariants: don't break these

- **`Const.ATTR_GROUP` must stay `"BatchPost_Post_Processor"`** (via `CMD_DEF_ID`). Every saved document's settings live under that key. A test guards it.
- `Settings.Set()` changes only the document copy. The defaults file is written by `SaveDefault()` (the *Save as default settings* button), or once on first run.
- `Settings.Load()` on a document with no saved settings starts from the defaults, never from the previously used document.
- `Program.Process()` restores the NC Program's operation list afterwards. Posting changes it one group at a time.
- Post Combined overrides grouping (Single file) and turns off *clear output folder* **for that run only**, then restores both. A single right-clicked setup temporarily sets the NC Program's file name to the setup name, then restores it.
- Overwrite is never silent: the user is asked first. For Single file output, the check happens before anything is posted.
- File names go through `Utils.sanitizeFilename`, which turns spaces into underscores. Comment text is sanitized too: `(` and `)` inside comments become `[` and `]`.

### Restore rapid moves: safety rules (issue #5)

Converting a move that cuts into a `G0` can crash the machine, so these rules are intentionally conservative:

- **Link:** G1 Z-only up → 1 to 3 XY moves → Z-only down, with no arcs. The end moves back off a feed plunge. *Minimum rapid move distance* applies.
- **Entry:** the run must start right after a G0 move with a Z-only G1 descent that has an F word. Lines are rapids up to (but not including) the line that sets a **different** F. If no different F follows, nothing is converted, so a single feed plunge after a rapid (drilling) stays G1.
- **Exit:** Z-only G1 rise(s) that are the last motion before a G0 move, `G53`/`G28`/`G30`, or the end of the operation.
- Entries and exits ignore the minimum distance. Links take priority when segments overlap.
- The end marker restores the last F that was removed: `G1 F<value> (Rapid movement end)`. This keeps the active feed exactly as the original program had it.
- `force_rapid_start_line` replaces G0/G1 anywhere on the line (`G94 G1 Z40.` → `G94 G0 Z40.`).

## Fusion API notes (checked against Autodesk docs)

- A command that adds **no inputs** in `commandCreated` executes immediately with no dialog. Post Combined relies on this.
- Right-click menu: `ui.markingMenuDisplaying` → `args.selectedEntities` and `args.linearMarkingMenu.controls`. Guard against adding the same entry twice with `itemById`. Setups have `objectType == "adsk::cam::Setup"`.
- Posts: `adsk.cam.CAMManager.get().libraryManager.postLibrary` provides `urlByLocation(LibraryLocations.X)`, `childPostConfigurations(url)` and `childFolderURLs(url)`. `PostConfiguration` has **no URL**, so a post is matched by description + vendor + extension.
- NC Program creation: `cam.ncPrograms.createInput()` → set `displayName`, `parameters` (`nc_program_filename`, `nc_program_output_folder`, `nc_program_openInEditor`) and `operations = [setups]` → `cam.ncPrograms.add(input)`, then `program.postConfiguration = post`.

## Status as of v1.1.0 (2026-11-19)

- **Verified in the real Fusion:** both toolbar buttons appear, the setup right-click entry appears, and the add-in starts and stops cleanly.
- **Verified only in tests and the simulation:** automatic NC Program creation and the post library search, an actual right-click post, and the issue #5 rapid rules. The first real post should be checked in a G-code viewer and air-cut.
- **Released:** `v1.1.0` is tagged at `31eae75` with `djr_batchpost-v1.1.0.zip` attached, built by the Release workflow and matching `main` file for file.
- **Branches:** only `main`. The old `djr_batchpost` and `cursor/4th-axis-without-machine-d9ab` branches were merged into it and then deleted.
- The Swedish strings (`sv.json`) for the newer messages were written without a native-speaker review.
