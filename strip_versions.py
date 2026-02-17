
import re

input_file = 'requirements_temp.txt'
output_file = 'requirements_relaxed.txt'

with open(input_file, 'r') as f:
    lines = f.readlines()

new_lines = []
for line in lines:
    line = line.strip()
    if not line or line.startswith('#'):
        continue
    # Keep git URLs as is
    if 'git+' in line or '@ file://' in line:
        new_lines.append(line)
        continue
    # Remove version specifiers
    package = re.split(r'[=<>~]', line)[0]
    new_lines.append(package)

with open(output_file, 'w') as f:
    f.write('\n'.join(new_lines))
