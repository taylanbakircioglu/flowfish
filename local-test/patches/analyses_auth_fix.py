#!/usr/bin/env python3
"""
Local test patch: Disable auth for analyses endpoints
This patch is ONLY for local testing, not for production
"""

import re

file_path = '/app/routers/analyses.py'

with open(file_path, 'r') as f:
    content = f.read()

# Remove auth dependency from endpoints
patterns = [
    (r'async def start_analysis\(\s*analysis_id: int,\s*current_user: dict = Depends\(get_current_user\)\s*\)',
     'async def start_analysis(analysis_id: int)'),
    (r'async def stop_analysis\(\s*analysis_id: int,\s*current_user: dict = Depends\(get_current_user\)\s*\)',
     'async def stop_analysis(analysis_id: int)'),
    (r'async def get_analysis\(\s*analysis_id: int,\s*current_user: dict = Depends\(get_current_user\)\s*\)',
     'async def get_analysis(analysis_id: int)'),
    (r'async def delete_analysis\(\s*analysis_id: int,\s*current_user: dict = Depends\(get_current_user\)\s*\)',
     'async def delete_analysis(analysis_id: int)'),
    (r'async def get_analysis_runs\(\s*analysis_id: int,\s*current_user: dict = Depends\(get_current_user\)\s*\)',
     'async def get_analysis_runs(analysis_id: int)'),
]

for pattern, replacement in patterns:
    content = re.sub(pattern, replacement, content, flags=re.MULTILINE)

with open(file_path, 'w') as f:
    f.write(content)

print("Patched analyses.py - auth disabled for local testing")

