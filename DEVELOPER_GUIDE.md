# Developer Guide for PTZ Preset Control

Welcome! This guide will help you get started developing on the PTZ Preset Control app. We assume basic git knowledge and familiarity with Python.

## Prerequisites

Before you start, have these installed:

- **Python 3.8+** (check with `python --version`)
- **Git** (check with `git --version`)
- **FFmpeg** (optional, for USB capture; check with `ffmpeg -version`)

For advanced features:
- Playwright (for URL capture): `pip install playwright && playwright install chromium`
- OpenCV (for USB fallback): `pip install opencv-python`

## First-Time Setup

### 1. Clone the repository

```bash
git clone https://github.com/witeshadow/ptz.git
cd ptz
```

### 2. Install optional dependencies (as needed)

The core app uses only Python's standard library. Optional features require additional packages:

```bash
# For URL-based preset capture (Playwright)
pip install playwright
playwright install chromium

# For USB capture fallback (OpenCV)
pip install opencv-python

# For primary USB capture (requires ffmpeg on system PATH)
# Install ffmpeg via: brew install ffmpeg (macOS) or apt install ffmpeg (Linux)
```

If you don't need these features, skip this step.

### 3. Run the app

```bash
python server.py
```

Open your browser to `http://localhost:5001`

The app loads and saves settings in `data/` folder. Camera presets and images are stored there.

---

## Understanding the Project

Read these files in order:

1. **CLAUDE.md** — Architecture, project constraints, and behavior that matters for live production
2. **server.py** — The main app (routes, VISCA control, ATEM integration, capture)
3. **public/index.html** — The frontend (single-file SPA with inline CSS/JS)

Key insight: This is **not Flask**. Routes are hand-written in `do_GET`, `do_POST`, and `do_DELETE`.

---

## Development Workflow

> **Note:** This repository uses `default` as its default branch name. Commands in this guide reference `default`; if you work on other repositories that use `main` or `master`, substitute accordingly.

### Step 1: Create a branch

Always create a new branch for your changes:

```bash
git switch -c feature/your-feature-name
```

**Branch naming:**
- `feature/add-preset-labels` (new feature)
- `fix/camera-not-moving` (bug fix)
- `docs/update-readme` (documentation)

### Step 2: Make changes

Edit files in your favorite editor. Test locally:

```bash
python server.py
# Visit http://localhost:5001 and manually test your changes
```

### Step 3: Check code quality

Before committing, run these checks:

```bash
ruff check server.py        # Linting
python -m py_compile server.py  # Syntax check
# If using uv:
uv run pytest tests/test_frontend_contracts.py
# If using pip:
pytest tests/test_frontend_contracts.py
```

If you get errors, fix them before moving on.

### Step 4: Commit your work

```bash
# See what you changed
git status

# Stage specific files (not everything)
git add server.py public/index.html

# Commit with a clear message
git commit -m "Add preset comparison feature

- Show differences between preset positions
- Help operators spot changes before recalling
- Improves live safety during rehearsal"
```

**Commit message tips:**
- First line: brief summary (under 70 characters)
- Blank line
- Then: why this change matters, not what the code does
- Reference issues: "Fixes #42" (GitHub will auto-close it)

### Step 5: Push to GitHub

```bash
git push -u origin feature/your-feature-name
```

The `-u` flag sets this branch to track GitHub (only needed once per branch).

### Step 6: Create a pull request

Visit GitHub and create a PR:
- **Title:** Copy your commit's first line
- **Description:** Explain what changed and why. Mention if it affects live production.
- **Label:** Add `bug`, `enhancement`, `docs` as appropriate

### Step 7: Request code review

1. **Optional:** Ask Claude Code to review your changes (use `/simplify` or ask Claude directly)
2. **GitHub AI:** Click "Request review" → "Copilot" (if available) for automated feedback
3. **Merge:** Once checks pass and you're satisfied, merge via GitHub web UI

### Step 8: Clean up

After merging, delete the remote branch on GitHub. Then locally:

```bash
git switch default
git pull origin default
git branch -d feature/your-feature-name
```

---

## Git Commands for Daily Work

### Checking status

```bash
git status                    # What files changed?
git diff                      # Show unstaged changes only
git diff --staged             # Show staged changes only
git log --oneline -5          # Last 5 commits
```

### Undoing changes

```bash
# Undo changes in a file (before staging)
git restore filename.py

# Unstage a file
git restore --staged filename.py

# Undo last commit (keeps your changes)
git reset --soft HEAD~1
# Then re-commit with a better message

# See what was undone
git reflog
```

### Switching branches

```bash
git switch default           # Go to default branch
git switch -c new-feature    # Create and switch to new branch
git branch -l                # List all branches
```

### Syncing with GitHub

```bash
# Fetch latest from GitHub (doesn't change your files)
git fetch origin

# Pull latest default branch before merging your changes
git switch default
git pull origin default
git switch -
git merge origin/default  # Integrate latest changes into your branch

# Push your work
git push origin your-branch
```

---

## Using Claude Code Effectively

Claude Code (this tool) is integrated into your workflow:

### Before starting a feature

Ask Claude:
- "Where in server.py would I add a new route?"
- "What does the ATEM integration do?"
- "How should I structure this change?"

Claude will read CLAUDE.md and understand the architecture.

### During development

Use Claude to:
- **Find code:** "Find where camera presets are loaded"
- **Explain code:** "What does this SSE event loop do?"
- **Generate code:** "Add a new route for X that does Y"
- **Run checks:** Claude can run `ruff`, `pytest`, etc.

### Before pushing

Ask Claude:
- "Review my changes for issues"
- "Check if I broke anything in the UI"
- "Make sure I followed CLAUDE.md guidelines"

Or use the `/simplify` skill for automated code review.

### After creating a PR

Claude can:
- Monitor your PR for feedback
- Respond to Copilot's review comments
- Fix CI failures automatically
- Keep the code quality high

---

## Common Tasks

### Add a new setting

Settings are persisted in `data/settings.json`. To add a new setting:

1. **server.py:** Add to `DEFAULT_SETTINGS` dict
2. **server.py:** Use it in your route (read/write as needed)
3. **public/index.html:** Add to frontend `state` object
4. **public/index.html:** Create UI controls to set it
5. **Test:** Reload app, verify setting persists

Example: Adding `maxCameras`
- CLAUDE.md has a "Common Change Pattern" section with more details

### Add a new camera control

All VISCA communication goes through `server.py`:

1. Find the `_camera_` functions that send commands
2. Add your new command there
3. Create a route in `do_GET` or `do_POST`
4. Add a button in `public/index.html` to call it

### Modify the UI

The entire frontend is in `public/index.html` — one file with:
- Inline HTML
- Inline CSS (in `<style>` block)
- Inline JavaScript (in `<script>` block)

Changes apply immediately when you save and reload the browser.

### Test capture flows

Capture has a priority order (see CLAUDE.md):
1. Configured USB device via FFmpeg
2. Configured stream URL via Playwright
3. Browser webcam fallback

Test locally by:
- Checking that presets save images
- Verifying thumbnails are correct
- Testing each capture source if available

---

## Testing Before You Push

**Always run these:**

```bash
ruff check server.py
python -m py_compile server.py
# If using uv:
uv run pytest tests/test_frontend_contracts.py
# If using pip:
pytest tests/test_frontend_contracts.py
```

**Manually test:**

```bash
python server.py
# Open http://localhost:5001
# Test your feature in the browser
# Test on mobile if possible (Safari on iOS)
```

**Check for regressions:**
- Does preset recall still work?
- Does preview/program switching work?
- Can you move cameras without issues?
- Do thumbnails update correctly?

---

## Live Production Safety

This app runs live production. Be extra careful:

### Don't

- Silently move the live camera
- Generate bad preset images without warning
- Bulk delete or overwrite presets without confirmation

### Do

- Show errors explicitly
- Confirm risky actions
- Test thoroughly before deployment
- Ask in code review if unsure about safety

See CLAUDE.md for more on live-production guardrails.

---

## Getting Help

### If you're stuck:

1. **Check CLAUDE.md** for architecture and constraints
2. **Ask Claude Code:** Paste code and ask "what does this do?"
3. **Read server.py comments** for tricky sections
4. **Look at recent commits** for examples of similar changes
5. **Check GitHub issues** for context on past decisions

### Before pushing:

1. Run all checks (see "Testing Before You Push")
2. Test in browser manually
3. Ask Claude to review your code
4. Create a clear PR description
5. Request Copilot review on GitHub

---

## Quick Reference

| Task | Command |
|------|---------|
| See changes | `git status` or `git diff` |
| Create branch | `git switch -c feature/name` |
| Commit | `git commit -m "message"` |
| Push | `git push -u origin feature/name` |
| Switch branch | `git switch default` |
| Pull latest | `git pull origin default` |
| See history | `git log --oneline -5` |
| Undo change | `git restore filename.py` |
| Undo commit | `git reset --soft HEAD~1` |
| Run app | `python server.py` |
| Check code | `ruff check server.py` |
| Run tests | `uv run pytest tests/` or `pytest tests/` |

---

## Next Steps

1. ✅ Set up your local environment (done!)
2. ✅ Read CLAUDE.md (10 minutes)
3. ✅ Run `python server.py` and explore the app
4. 🎯 Pick a small issue or feature
5. 🎯 Create a branch and make your first change
6. 🎯 Push to GitHub and create a PR

Happy coding!
