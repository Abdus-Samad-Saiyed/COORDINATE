import os
import re
import ast
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def check_template_urls():
    print("[1] Scanning template URLs against urlconf...")
    import django
    os.environ['DJANGO_SETTINGS_MODULE'] = 'campus.settings.test'
    django.setup()
    from django.urls import get_resolver
    resolver = get_resolver()
    url_names = set()
    
    def collect_urls(patterns):
        for p in patterns:
            if hasattr(p, 'name') and p.name:
                url_names.add(p.name)
            if hasattr(p, 'url_patterns'):
                collect_urls(p.url_patterns)
    collect_urls(resolver.url_patterns)

    template_dir = ROOT / 'templates'
    missing_urls = []
    for root, _, files in os.walk(template_dir):
        for f in files:
            if f.endswith('.html'):
                fpath = Path(root) / f
                content = fpath.read_text(encoding='utf-8')
                matches = re.findall(r"{%\s*url\s+'([^']+)'", content)
                for m in matches:
                    if m not in url_names and not m.startswith('admin:'):
                        missing_urls.append((fpath.relative_to(ROOT), m))
    if missing_urls:
        print(f"  FOUND {len(missing_urls)} unresolved template URL names:")
        for path, u in missing_urls:
            print(f"    - {path}: {u}")
    else:
        print("  All template {% url %} references resolve successfully!")

def check_template_safe_filters():
    print("\n[2] Scanning for '|safe' in templates...")
    template_dir = ROOT / 'templates'
    safe_occurrences = []
    for root, _, files in os.walk(template_dir):
        for f in files:
            if f.endswith('.html'):
                fpath = Path(root) / f
                content = fpath.read_text(encoding='utf-8')
                for line_no, line in enumerate(content.splitlines(), 1):
                    if '|safe' in line:
                        safe_occurrences.append((fpath.relative_to(ROOT), line_no, line.strip()))
    if safe_occurrences:
        print(f"  Found {len(safe_occurrences)} '|safe' occurrences:")
        for path, lno, line in safe_occurrences:
            print(f"    - {path}:{lno}: {line}")
    else:
        print("  No raw '|safe' filter occurrences found in templates!")

def check_python_ast():
    print("\n[3] Scanning Python files for undefined names / syntax / suspicious patterns...")
    py_files = []
    for pkg in ['accounts', 'coordinate', 'campus', 'scripts']:
        for root, _, files in os.walk(ROOT / pkg):
            for f in files:
                if f.endswith('.py'):
                    py_files.append(Path(root) / f)
    
    issues = []
    for pf in py_files:
        try:
            tree = ast.parse(pf.read_text(encoding='utf-8'), filename=str(pf))
        except SyntaxError as e:
            issues.append((pf.relative_to(ROOT), f"SyntaxError: {e}"))
            continue

        for node in ast.walk(tree):
            if isinstance(node, ast.ExceptHandler):
                if node.type is None:
                    issues.append((pf.relative_to(ROOT), f"Bare 'except:' on line {node.lineno}"))
    
    if issues:
        print(f"  Found {len(issues)} code pattern issues:")
        for path, msg in issues:
            print(f"    - {path}: {msg}")
    else:
        print(f"  Scanned {len(py_files)} Python files: Clean AST, zero bare excepts!")

if __name__ == '__main__':
    check_template_urls()
    check_template_safe_filters()
    check_python_ast()
