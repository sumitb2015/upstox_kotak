---
description: Fetch and integrate updates from the GitHub repository.
---

# Sync GitHub Updates Workflow

Follow these steps to safely fetch and apply updates from the GitHub remote repository.

// turbo
1. **Check Local Status**: Run `git status` to ensure there are no uncommitted changes that might lead to conflicts during the pull.
2. **Fetch Remote Updates**: 
   // turbo
   ```bash
   git fetch origin
   ```
   *This downloads the latest information from the remote branch without modifying your local code.*

3. **Preview Changes**: 
   // turbo
   ```bash
   git log HEAD..origin/main --oneline
   git diff main origin/main --stat
   ```
   *Review the commit history and file modifications to understand what has changed on the remote.*

4. **Integrate Updates**: 
   Choose one of the following commands to merge the remote changes into your local branch:
   - **Standard Pull (Merge)**: `git pull origin main`
   - **Rebase Pull**: `git pull --rebase origin main` (Recommended for a cleaner commit history).

5. **Handle Potential Conflicts**: 
   If Git reports any merge conflicts:
   - Run `git status` to identify the files containing conflicts.
   - Open and resolve the conflicts (marked with `<<<<<<<`, `=======`, `>>>>>>>`).
   - After resolving, stage the files: `git add <file_path>`.
   - Conclude the process: `git merge --continue` or `git rebase --continue`.

6. **Verification**: 
   // turbo
   ```bash
   git log -1
   ```
   *Check the latest commit to confirm that your local repo is now synchronized with origin/main.*
