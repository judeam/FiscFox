-- Migration 001: Add deleted_at column to tables missing it
-- Run this on existing databases to add soft delete support

-- Add deleted_at to home_office_days if not exists
ALTER TABLE home_office_days ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL;

-- Add deleted_at to home_office_settings if not exists
ALTER TABLE home_office_settings ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL;

-- Add deleted_at to depreciation_records if not exists
ALTER TABLE depreciation_records ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL;

-- Add deleted_at to business_meals if not exists
ALTER TABLE business_meals ADD COLUMN deleted_at TIMESTAMP DEFAULT NULL;
