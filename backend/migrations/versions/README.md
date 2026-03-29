# ⚠️ DEPRECATED - Migration Files

The SQL files in this directory are **no longer used**.

## Active Migration Mechanism

All database migrations are managed by the following K8s Job:

```
deployment/kubernetes-manifests/03-migrations-job.yaml
```

This job is automatically executed by the pipeline on every deployment.

## Files in This Directory

The legacy SQL files in this directory are kept for reference and can be deleted:

- `003_add_gadget_protocol.sql` → Already in K8s job
- `004_add_cluster_management.sql` → Already in K8s job  
- `004_add_multi_cluster_support.sql` → Already in K8s job
- `005_add_analysis_event_config.sql` → Already in K8s job
- `005_add_remote_cluster_support.sql` → Already in K8s job
- `006_add_analysis_timing_fields.sql` → Already in K8s job

## Adding New Migrations

To add a new migration:

1. Edit `deployment/kubernetes-manifests/03-migrations-job.yaml`
2. Add new migration in the appropriate place (must be idempotent - use `IF NOT EXISTS`)
3. Will be automatically applied when pipeline runs

## Emergency Manual Migration

If manual migration is needed:
```bash
./scripts/apply-missing-migrations.sh
```
