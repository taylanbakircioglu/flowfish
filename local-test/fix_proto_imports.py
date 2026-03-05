#!/usr/bin/env python3
"""Fix proto import statements to use relative imports."""
import os
import re

proto_dir = './proto'

for filename in os.listdir(proto_dir):
    if filename.endswith('_pb2.py') or filename.endswith('_pb2_grpc.py'):
        filepath = os.path.join(proto_dir, filename)
        
        with open(filepath, 'r') as f:
            content = f.read()
        
        # Fix: import xxx_pb2 -> from . import xxx_pb2
        new_content = re.sub(
            r'^import ([a-z_]+_pb2)',
            r'from . import \1',
            content,
            flags=re.MULTILINE
        )
        
        with open(filepath, 'w') as f:
            f.write(new_content)
        
        if content != new_content:
            print(f'Fixed imports in: {filename}')
        else:
            print(f'No changes needed: {filename}')

