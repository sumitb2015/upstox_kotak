
import os
import re

def robust_fix_paths():
    root_dir = "c:\\algo\\upstox"
    strat_root = os.path.join(root_dir, "strategies")
    tools_root = os.path.join(root_dir, "tools")
    
    files_to_process = []
    for d in [strat_root, tools_root]:
        for dirpath, dirnames, filenames in os.walk(d):
            if "__pycache__" in dirpath: continue
            for f in filenames:
                if f.endswith(".py"):
                    files_to_process.append(os.path.join(dirpath, f))

    count = 0
    for file_path in files_to_process:
        try:
            # Calculate depth from project root
            # e.g. strategies/directional/name/live.py -> depth 3
            # tools/debug/script.py -> depth 2
            rel_path = os.path.relpath(file_path, root_dir)
            depth = len(rel_path.split(os.sep)) - 1
            
            dots = ["'..'"] * depth
            dots_str = ", ".join(dots)
            
            with open(file_path, "r", encoding="utf-8") as f:
                content = f.read()
            
            modified = False
            new_content = content
            
            # 1. Fix sys.path patterns
            # Pattern: os.path.join(os.path.dirname(__file__), '..', ...)
            # We want to ensure it has the correct number of dots to reach root.
            
            # This regex looks for os.path.join(os.path.dirname(__file__), and any sequence of '..' or ".."
            # and replaces them with the correct number of dots.
            sys_path_regex = r"(os\.path\.join\s*\(\s*os\.path\.dirname\s*\(\s*__file__\s*\)\s*,\s*)(['\"].*?['\"]\s*,\s*)*(['\"]\.\.['\"])"
            
            # Actually, a simpler approach might be safer:
            # Look for lines containing sys.path.insert and '..'
            # and replace the join parts with the correct dots.
            
            # 2. Fix accessToken.txt patterns
            # Example: os.path.join(os.path.dirname(__file__), '..', '..', 'lib', 'core', 'accessToken.txt')
            
            # Strategy: Find any os.path.join that includes '..' and ends with 'accessToken.txt'
            token_regex = r"os\.path\.join\s*\(\s*os\.path\.dirname\s*\(\s*__file__\s*\)\s*,.*?'accessToken\.txt'\s*\)"
            
            # Let's use a targeted search and replace for the common "depth mismatch"
            
            # If depth 3, we expect 3 dots.
            if depth == 3:
                expected_dots = "'..', '..', '..'"
                if "os.path.join(os.path.dirname(__file__), '..', '..')" in content and expected_dots not in content:
                    new_content = new_content.replace("'..', '..'", expected_dots)
                    modified = True
            
            # Specific fix for futures_strategy.py token path
            # line 353: token_path = os.path.join(os.path.dirname(__file__), '..', '..', 'lib', 'core', 'accessToken.txt')
            old_token_path = "os.path.join(os.path.dirname(__file__), '..', '..', 'lib', 'core', 'accessToken.txt')"
            new_token_path = f"os.path.join(os.path.dirname(__file__), {dots_str}, 'lib', 'core', 'accessToken.txt')"
            
            if old_token_path in new_content:
                new_content = new_content.replace(old_token_path, new_token_path)
                modified = True
                
            # Generic catch-all for any lib/core/accessToken.txt with 2 dots that should be 3
            if depth == 3:
                wrong_token = "os.path.join(os.path.dirname(__file__), '..', '..', 'lib', 'core', 'accessToken.txt')"
                right_token = "os.path.join(os.path.dirname(__file__), '..', '..', '..', 'lib', 'core', 'accessToken.txt')"
                if wrong_token in new_content:
                    new_content = new_content.replace(wrong_token, right_token)
                    modified = True

            if new_content != content:
                with open(file_path, "w", encoding="utf-8") as f:
                    f.write(new_content)
                print(f"Fixed paths in: {rel_path} (Depth: {depth})")
                count += 1
                
        except Exception as e:
            print(f"Error fixing {file_path}: {e}")
            
    print(f"Robust Fix Complete. Updated {count} files.")

if __name__ == "__main__":
    robust_fix_paths()
