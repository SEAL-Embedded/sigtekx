#!/usr/bin/env python3
"""
Automated refactor script: batch → channels terminology
Phase 1 of terminology refactor for v0.9.4
"""

import re
from pathlib import Path

def refactor_file(file_path, replacements):
    """Apply regex replacements to a file."""
    try:
        content = file_path.read_text(encoding='utf-8')
        original = content

        for pattern, replacement in replacements:
            content = re.sub(pattern, replacement, content)

        if content != original:
            file_path.write_text(content, encoding='utf-8')
            print(f"[OK] Updated: {file_path}")
            return True
        return False
    except Exception as e:
        print(f"[ERROR] Error updating {file_path}: {e}")
        return False

def main():
    root = Path(__file__).parent.parent

    # Python source files
    python_files = list((root / 'src' / 'ionosense_hpc').rglob('*.py'))
    python_files += list((root / 'benchmarks').rglob('*.py'))
    python_files += list((root / 'tests').rglob('*.py'))
    python_files += list((root / 'experiments' / 'scripts').rglob('*.py'))

    python_replacements = [
        (r'\.batch\b', '.channels'),
        (r'engine_batch', 'engine_channels'),
        (r'"batch":', '"channels":'),
        (r"'batch':", "'channels':"),
        (r'config\.batch', 'config.channels'),
        (r'\bbatch=', 'channels='),
        (r'\(batch,', '(channels,'),
        (r'batch: int', 'channels: int'),
    ]

    print("="*60)
    print("PHASE 1: UPDATING PYTHON FILES")
    print("="*60)
    count = 0
    for f in python_files:
        if refactor_file(f, python_replacements):
            count += 1
    print(f"\nUpdated {count} Python files\n")

    # YAML config files
    yaml_files = list((root / 'experiments' / 'conf').rglob('*.yaml'))
    yaml_replacements = [
        (r'^batch:', 'channels:', re.MULTILINE),
        (r'engine\.batch', 'engine.channels'),
        (r'test_batch_sizes', 'test_channel_counts'),
    ]

    print("="*60)
    print("PHASE 2: UPDATING YAML CONFIG FILES")
    print("="*60)
    count = 0
    for f in yaml_files:
        if refactor_file(f, yaml_replacements):
            count += 1
    print(f"\nUpdated {count} YAML files\n")

    # C++ test files
    cpp_test_files = list((root / 'cpp' / 'tests').rglob('*.cpp'))
    cpp_test_files += list((root / 'cpp' / 'tests').rglob('*.hpp'))
    cpp_test_files += list((root / 'cpp' / 'benchmarks').rglob('*.cpp'))
    cpp_test_files += list((root / 'cpp' / 'benchmarks').rglob('*.hpp'))

    cpp_replacements = [
        (r'cfg\.batch\b', 'cfg.channels'),
        (r'config\.batch\b', 'config.channels'),
        (r'\.batch =', '.channels ='),
        (r'\(batch,', '(channels,'),
    ]

    print("="*60)
    print("PHASE 3: UPDATING C++ TEST/BENCHMARK FILES")
    print("="*60)
    count = 0
    for f in cpp_test_files:
        if refactor_file(f, cpp_replacements):
            count += 1
    print(f"\nUpdated {count} C++ test/benchmark files\n")

    print("="*60)
    print("REFACTOR COMPLETE!")
    print("="*60)
    print("\nNext steps:")
    print("1. Update version to 0.9.4 (run update_version.py)")
    print("2. Rebuild: iono build")
    print("3. Run tests: iono test")

if __name__ == '__main__':
    main()
