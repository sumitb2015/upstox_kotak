import os
import ast
import sys

def check_file(filepath):
    """
    Parses a python file and checks for syntax errors.
    """
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        return True, None
    except SyntaxError as e:
        return False, f"{e.msg} at line {e.lineno}, col {e.offset}"
    except Exception as e:
        return False, str(e)

def scan_directory(root_dir, skip_dirs=None):
    """
    Recursively scans a directory for python files and checks them.
    """
    if skip_dirs is None:
        skip_dirs = ["venv", "__pycache__", ".git"]
    
    results = []
    
    for root, dirs, files in os.walk(root_dir):
        # Skip directories
        dirs[:] = [d for d in dirs if d not in skip_dirs]
        
        for file in files:
            if file.endswith(".py"):
                filepath = os.path.join(root, file)
                success, error = check_file(filepath)
                if not success:
                    results.append((filepath, error))
                else:
                    # Optional: Check for basic issues like print statements in production code?
                    pass
    
    return results

def main():
    root_dir = os.getcwd()
    print(f"Scanning {root_dir} for Python syntax errors...")
    
    errors = scan_directory(root_dir)
    
    if errors:
        print("\n❌ Found Syntax Errors:")
        for path, err in errors:
            print(f"  - {os.path.relpath(path, root_dir)}: {err}")
        sys.exit(1)
    else:
        print("\n✅ No syntax errors found in scanned files.")
        sys.exit(0)

if __name__ == "__main__":
    main()
