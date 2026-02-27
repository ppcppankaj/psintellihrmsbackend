
import os
import re

def scan_file(filepath):
    violations = []
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        content = f.read()
        lines = content.splitlines()
        
        for i, line in enumerate(lines):
            # Pattern 1: queryset = Model.objects... at class level
            if re.search(r'^\s{4}queryset\s*=\s*.*objects\.(all|filter|select_related|prefetch_related)', line):
                violations.append({
                    'line': i + 1,
                    'content': line.strip(),
                    'reason': 'Class-level queryset assignment executes at import time.'
                })
            
            # Pattern 2: RelatedField(queryset=Model.objects...)
            if re.search(r'RelatedField\(.*queryset\s*=\s*.*objects\.', line):
                violations.append({
                    'line': i + 1,
                    'content': line.strip(),
                    'reason': 'Serializer field queryset executes at import time.'
                })
            
            # Pattern 3: URL patterns with direct queries
            if 'urls.py' in filepath and re.search(r'objects\.(all|filter|get)', line):
                violations.append({
                    'line': i + 1,
                    'content': line.strip(),
                    'reason': 'URL pattern executes query at import time.'
                })

    return violations

def main():
    root_dir = r'c:\Users\ruchi\ppcp\hrms\backend\apps'
    results_path = r'c:\Users\ruchi\ppcp\hrms\backend\scripts\audit_results.txt'
    
    with open(results_path, 'w', encoding='utf-8') as out:
        all_violations_count = 0
        for root, dirs, files in os.walk(root_dir):
            for file in files:
                if file.endswith('.py'):
                    filepath = os.path.join(root, file)
                    violations = scan_file(filepath)
                    if violations:
                        out.write(f"\nFile: {filepath}\n")
                        for v in violations:
                            out.write(f"  Line {v['line']}: {v['content']}\n")
                            out.write(f"    Reason: {v['reason']}\n")
                            all_violations_count += 1
        
        if all_violations_count == 0:
            out.write("✅ PASS: No import-time database queries found.\n")
        else:
            out.write(f"\n❌ FAIL: {all_violations_count} import-time database queries detected.\n")

if __name__ == "__main__":
    main()
