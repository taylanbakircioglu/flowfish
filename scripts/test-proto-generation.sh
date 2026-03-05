#!/bin/bash
# Test proto generation with import fixes

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

echo "🔍 Testing Proto Generation..."
echo "Project root: $PROJECT_ROOT"

# Create temp directory
TEMP_DIR=$(mktemp -d)
trap "rm -rf $TEMP_DIR" EXIT

cd "$PROJECT_ROOT"

# Copy proto files
echo "📋 Copying proto files..."
cp -r proto "$TEMP_DIR/proto_source"

# Generate Python code
echo "🔧 Generating Python code..."
mkdir -p "$TEMP_DIR/proto_generated"
python3 -m grpc_tools.protoc \
    -I"$TEMP_DIR/proto_source" \
    --python_out="$TEMP_DIR/proto_generated" \
    --grpc_python_out="$TEMP_DIR/proto_generated" \
    "$TEMP_DIR/proto_source"/*.proto

# Fix imports
echo "🔄 Fixing imports..."
for file in "$TEMP_DIR/proto_generated"/*_pb2.py "$TEMP_DIR/proto_generated"/*_pb2_grpc.py; do
    if [ -f "$file" ]; then
        # macOS compatible sed
        sed -i '' 's/^import \(.*_pb2\)/from . import \1/' "$file" 2>/dev/null || \
        # Linux sed fallback
        sed -i 's/^import \(.*_pb2\)/from . import \1/' "$file"
        echo "  ✅ Fixed: $(basename $file)"
    fi
done

touch "$TEMP_DIR/proto_generated/__init__.py"

# Test imports
echo "🧪 Testing imports..."
cd "$TEMP_DIR"
python3 -c "
import sys
sys.path.insert(0, 'proto_generated')
from proto_generated import common_pb2
from proto_generated import analysis_orchestrator_pb2
from proto_generated import ingestion_service_pb2
print('✅ All proto imports successful!')
"

echo ""
echo "✅ Proto generation test PASSED!"
echo "📦 Generated files in: $TEMP_DIR/proto_generated"
ls -la "$TEMP_DIR/proto_generated"

