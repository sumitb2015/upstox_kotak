import os
import ast
import sys

def get_imports(path):
    with open(path, 'r', encoding='utf-8') as f:
        try:
            root = ast.parse(f.read(), filename=path)
        except Exception as e:
            return set()

    imports = set()
    for node in ast.walk(root):
        if isinstance(node, ast.Import):
            for n in node.names:
                imports.add(n.name.split('.')[0])
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                imports.add(node.module.split('.')[0])
    return imports

def main():
    root_dir = 'c:/algo/upstox'
    all_imports = set()
    
    # Standard library modules (approximate list to filter out)
    stdlib = {
        'os', 'sys', 're', 'json', 'time', 'datetime', 'math', 'random', 'logging', 
        'collections', 'itertools', 'functools', 'pathlib', 'typing', 'enum', 
        'dataclasses', 'abc', 'copy', 'traceback', 'threading', 'multiprocessing',
        'subprocess', 'shutil', 'glob', 'pickle', 'io', 'csv', 'warnings', 'unittest',
        'signal', 'contextlib', 'platform', 'inspect', 'ast', 'urllib', 'http',
        'email', 'socket', 'ssl', 'sqlite3', 'tempfile', 'gzip', 'zipfile', 'tarfile',
        'argparse', 'optparse', 'hashlib', 'hmac', 'base64', 'uuid', 'ctypes', 'weakref',
        'heapq', 'bisect', 'queue', 'mmap', 'struct', 'calendar', 'zoneinfo', 'types',
        'importlib', 'pkgutil', 'site', 'sysconfig', 'distutils', 'venv', 'ensurepip',
        'builtins', 'numbers', 'decimal', 'fractions', 'statistics', 'cmd', 'shlex',
        'tk', 'tkinter', 'unittest', 'doctest', 'pdb', 'profile', 'cProfile', 'timeit',
        'trace', 'tracemalloc', 'asyncio', 'socketserver', 'xml', 'html', 'http'
    }

    # Project local modules (to filter out)
    local_modules = {'lib', 'strategies', 'kotak_api', 'tools', 'tests', 'quick_help'}

    for dirpath, dirnames, filenames in os.walk(root_dir):
        # Exclude venv, .git, .agent, etc.
        if 'venv' in dirnames:
            dirnames.remove('venv')
        if '.git' in dirnames:
            dirnames.remove('.git')
        if '.agent' in dirnames:
            dirnames.remove('.agent')
        if '__pycache__' in dirnames:
            dirnames.remove('__pycache__')

        for filename in filenames:
            if filename.endswith('.py'):
                full_path = os.path.join(dirpath, filename)
                all_imports.update(get_imports(full_path))

    # Filter imports
    external_imports = {
        imp for imp in all_imports 
        if imp not in stdlib and imp not in local_modules and not imp.startswith('_')
    }

    print("External Imports Found:")
    for imp in sorted(external_imports):
        print(imp)

if __name__ == '__main__':
    main()
