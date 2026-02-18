---
name: Branch-Based Development
description: Prevents direct commits to the main branch and ensures a clean, professional git history.
---

# Branch-Based Development

**Mandatory for all project contributions.**

## Overview
This skill ensures that the development process follows industry-standard Git practices to maintain a stable `main` branch and a clean history.

## Instructions

1. **No Direct Main Commits**: 
   - **Never** commit directly to the `main` or `master` branches.
   - All changes must originate from a dedicated feature, fix, or refactor branch.

2. **Branch Creation**: 
   Before modifying any files, create a descriptive branch from the latest `main`:
   - `feature/<name>`: For new features or work.
   - `fix/<name>`: For bug fixes.
   - `refactor/<name>`: For code improvements or performance optimizations.

3. **Commit Standards**: 
   Use the **Conventional Commits** format:
   - `feat: <description>` (e.g., `feat: add login logic`)
   - `fix: <description>` (e.g., `fix: resolve timeout issue`)
   - `refactor: <description>`
   - `docs: <description>`
   - `chore: <description>`

4. **Task Completion**: 
   Once a task is complete:
   - Push the branch to the remote: `git push origin <branch-name>`.
   - Inform the user that the code is ready for a Pull Request (PR).
