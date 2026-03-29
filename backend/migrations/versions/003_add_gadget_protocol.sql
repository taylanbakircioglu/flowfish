-- Migration: Add gadget_protocol and gadget_endpoint to clusters table
-- Date: 2025-01-24
-- Description: Support for multiple Inspektor Gadget protocols (gRPC, HTTP, Agent)

-- Add gadget_endpoint column (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'clusters' 
        AND column_name = 'gadget_endpoint'
    ) THEN
        ALTER TABLE clusters ADD COLUMN gadget_endpoint TEXT;
        COMMENT ON COLUMN clusters.gadget_endpoint IS 'Inspektor Gadget endpoint URL';
    END IF;
END $$;

-- Add gadget_protocol column (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'clusters' 
        AND column_name = 'gadget_protocol'
    ) THEN
        ALTER TABLE clusters ADD COLUMN gadget_protocol VARCHAR(20) DEFAULT 'grpc';
        COMMENT ON COLUMN clusters.gadget_protocol IS 'Inspektor Gadget protocol: grpc, http, agent';
    END IF;
END $$;

-- Add gadget_health_status column (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'clusters' 
        AND column_name = 'gadget_health_status'
    ) THEN
        ALTER TABLE clusters ADD COLUMN gadget_health_status VARCHAR(50) DEFAULT 'unknown';
        COMMENT ON COLUMN clusters.gadget_health_status IS 'Inspektor Gadget health status';
    END IF;
END $$;

-- Add gadget_version column (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'clusters' 
        AND column_name = 'gadget_version'
    ) THEN
        ALTER TABLE clusters ADD COLUMN gadget_version VARCHAR(50);
        COMMENT ON COLUMN clusters.gadget_version IS 'Inspektor Gadget version';
    END IF;
END $$;

-- Add gadget_auth_method column (if not exists)
DO $$ 
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns 
        WHERE table_name = 'clusters' 
        AND column_name = 'gadget_auth_method'
    ) THEN
        ALTER TABLE clusters ADD COLUMN gadget_auth_method VARCHAR(50) DEFAULT 'token';
        COMMENT ON COLUMN clusters.gadget_auth_method IS 'Authentication method: token, api_key, cert, none';
    END IF;
END $$;

-- Update existing clusters to have default gadget_endpoint
UPDATE clusters 
SET gadget_endpoint = 'inspektor-gadget.flowfish:16060',
    gadget_protocol = 'grpc'
WHERE gadget_endpoint IS NULL;

