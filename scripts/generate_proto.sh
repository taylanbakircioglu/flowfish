#!/bin/bash

# Flowfish Proto Generation Script
# Generates Python code from .proto files

set -e

echo "🐟 Flowfish - Proto Generation Script"
echo "======================================"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Directories
PROTO_DIR="proto"
OUTPUT_DIR="shared/proto_generated"
PYTHON_OUT="$OUTPUT_DIR/python"

# Check if proto directory exists
if [ ! -d "$PROTO_DIR" ]; then
    echo -e "${RED}Error: proto/ directory not found${NC}"
    exit 1
fi

# Check if protoc is installed (check both PATH and user-local)
if ! command -v protoc &> /dev/null; then
    # Try user-local installation
    if [ -f "${HOME}/.local/bin/protoc" ]; then
        export PATH="${HOME}/.local/bin:${PATH}"
        echo -e "${GREEN}✓${NC} Using protoc from ${HOME}/.local/bin"
    else
        echo -e "${RED}Error: protoc (Protocol Buffers compiler) is not installed${NC}"
        echo "Install it with:"
        echo "  macOS:   brew install protobuf"
        echo "  Ubuntu:  sudo apt-get install -y protobuf-compiler"
        echo "  Fedora:  sudo dnf install protobuf-compiler"
        echo "  User:    Downloaded from https://github.com/protocolbuffers/protobuf/releases"
        exit 1
    fi
fi

# Check protoc version
PROTOC_VERSION=$(protoc --version | awk '{print $2}')
echo -e "${GREEN}✓${NC} protoc version: $PROTOC_VERSION"

# Check if grpcio-tools is installed (for Python gRPC)
if ! python3 -c "import grpc_tools" 2>/dev/null; then
    echo -e "${YELLOW}Warning: grpcio-tools not found. Installing...${NC}"
    
    # Use python3 -m pip (more reliable than pip3 command)
    if python3 -m pip --version &> /dev/null; then
        python3 -m pip install --user grpcio-tools
    elif command -v pip3 &> /dev/null; then
        pip3 install --user grpcio-tools
    else
        echo -e "${RED}Error: Neither 'python3 -m pip' nor 'pip3' is available${NC}"
        echo "Please install pip or run the build script which installs it automatically"
        exit 1
    fi
fi

# Create output directories
echo "Creating output directories..."
mkdir -p "$PYTHON_OUT"

# Clean previous generated files
echo "Cleaning previous generated files..."
rm -rf "$PYTHON_OUT"/*

# Generate Python code
echo ""
echo "Generating Python code from proto files..."
echo "-------------------------------------------"

# Find all .proto files
PROTO_FILES=$(find "$PROTO_DIR" -name "*.proto")

if [ -z "$PROTO_FILES" ]; then
    echo -e "${RED}Error: No .proto files found in $PROTO_DIR${NC}"
    exit 1
fi

# Generate Python code for each proto file
for proto_file in $PROTO_FILES; do
    echo -e "Processing: ${GREEN}$(basename $proto_file)${NC}"
    
    python3 -m grpc_tools.protoc \
        -I"$PROTO_DIR" \
        --python_out="$PYTHON_OUT" \
        --grpc_python_out="$PYTHON_OUT" \
        "$proto_file"
done

# Create __init__.py for Python package
echo "Creating __init__.py files..."
touch "$OUTPUT_DIR/__init__.py"
touch "$PYTHON_OUT/__init__.py"

# Fix imports in generated files (Python3 compatibility)
echo "Fixing imports in generated files..."
for file in "$PYTHON_OUT"/*_pb2_grpc.py; do
    if [ -f "$file" ]; then
        # Replace "import xxx_pb2" with "from . import xxx_pb2"
        sed -i.bak 's/^import \(.*_pb2\)/from . import \1/' "$file"
        rm -f "$file.bak"
    fi
done

# Create a summary
echo ""
echo "======================================"
echo -e "${GREEN}✓ Proto generation completed!${NC}"
echo "======================================"
echo ""
echo "Generated files:"
ls -lh "$PYTHON_OUT"
echo ""
echo "Next steps:"
echo "  1. Copy generated files to each service:"
echo "     cp -r $PYTHON_OUT/* services/<service-name>/proto/"
echo ""
echo "  2. Or use as shared module:"
echo "     from shared.proto_generated.python import common_pb2"
echo ""

