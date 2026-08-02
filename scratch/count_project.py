import os

EXCLUDES = {'node_modules', 'venv', '.git', '__pycache__', 'dist', 'build', 'coverage', '.pytest_cache'}

total_size = 0
total_files = 0
py_files = 0
ts_files = 0
tsx_files = 0
js_files = 0
react_components = 0
lines_of_code = 0

for root, dirs, files in os.walk('.'):
    dirs[:] = [d for d in dirs if d not in EXCLUDES]
    for file in files:
        filepath = os.path.join(root, file)
        
        # skip binary files/lockfiles
        if file.endswith(('.lock', '.png', '.jpg', '.ico', '.pdf', '.docx', '.sqlite3', '.db')):
            continue
            
        try:
            size = os.path.getsize(filepath)
            total_size += size
            total_files += 1
            
            if file.endswith('.py'):
                py_files += 1
            elif file.endswith('.ts'):
                ts_files += 1
            elif file.endswith('.tsx'):
                tsx_files += 1
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                    if 'import React' in content or 'from \'react\'' in content or 'from "react"' in content:
                        react_components += 1
            elif file.endswith('.js'):
                js_files += 1
                
            with open(filepath, 'r', encoding='utf-8') as f:
                lines = f.readlines()
                lines_of_code += len(lines)
                
        except Exception:
            pass

print(f"Total Source Size (bytes): {total_size}")
print(f"Total Source Files: {total_files}")
print(f"Python Files: {py_files}")
print(f"TypeScript Files: {ts_files}")
print(f"TSX Files: {tsx_files}")
print(f"JavaScript Files: {js_files}")
print(f"React Components: {react_components}")
print(f"Lines of Code: {lines_of_code}")
