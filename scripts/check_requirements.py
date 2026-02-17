
import sys
import importlib.metadata
import os

def check_requirements(requirements_file='requirements.txt'):
    if not os.path.exists(requirements_file):
        print(f"Error: {requirements_file} not found.")
        sys.exit(1)

    with open(requirements_file, 'r') as f:
        lines = f.readlines()

    missing = []
    installed = []

    for line in lines:
        line = line.strip()
        if not line or line.startswith('#'):
            continue
        
        # Handle local file paths or git urls if any (basic handling)
        if line.startswith('./libs/'):
            package_name = line.split('/')[-1].replace('.whl', '').replace('.tar.gz', '')
            # Try to guess package name from path, usually it is the folder name
            # For ./libs/neo-api-client, package might be neo_api_client
            # This is heuristic.
            if 'neo-api-client' in line:
               package_name = 'neo_api_client' 
            else:
               package_name = line
        else:
             # Strip version specifiers if any, though file provided has none mostly
             package_name = line.split('==')[0].split('>=')[0].split('<=')[0].split('~=')[0].strip()

        try:
            dist = importlib.metadata.distribution(package_name)
            installed.append(f"{package_name} ({dist.version})")
        except importlib.metadata.PackageNotFoundError:
            # Try replacing - with _ as some packages differ
            try:
                dist = importlib.metadata.distribution(package_name.replace('-', '_'))
                installed.append(f"{package_name} ({dist.version})")
            except importlib.metadata.PackageNotFoundError:
                 missing.append(package_name)

    print(f"Checked {len(lines)} entries.")
    
    if installed:
        print(f"\nExample installed: {installed[:5]} ...")

    if missing:
        print("\nMissing packages:")
        for p in missing:
            print(f" - {p}")
        sys.exit(1)
    else:
        print("\nSUCCESS: All packages appear to be installed.")
        sys.exit(0)

if __name__ == "__main__":
    check_requirements()
