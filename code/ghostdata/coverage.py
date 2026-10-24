"""Evidence-schema coverage contract for participant-visible collections."""

from __future__ import annotations

SUPPORTED_JSON_COLLECTIONS = {
    "backup_catalog",
    "connector_configurations",
    "customer_analytics_reports",
    "customer_export_jobs",
    "customer_profiles",
    "customer_search_documents",
    "deleted_customer_references",
    "operational_record_history",
    "retained_order_records",
    "security_audit_events",
    "support_conversations",
    "ticket_attachments",
}

SUPPORTED_JSON_SERVICE_BLOCKS = {
    "account_service/profile_lookups",
    "analytics_platform/profiles",
    "backup_service/restore_entries",
    "export_service/exports",
    "integration_service/connectors",
    "search_service/index_queries",
    "security_service/audit_records",
    "support_platform/tickets",
}

SUPPORTED_SQL_TABLES = {
    "backup_restore_entries",
    "connector_subscriptions",
    "customer_analytics_profiles",
    "customer_data_failover_replica",
    "customer_data_primary",
    "customer_data_read_replica",
    "customer_data_replica_ap_south",
    "customer_data_replica_eu_west",
    "customer_data_reporting_replica",
    "customer_exports",
    "customer_profiles",
    "customer_profiles_failover_replica",
    "customer_profiles_primary",
    "customer_search_documents",
    "search_documents_primary",
    "security_audit_records",
    "snapshot_scope",
    "support_records",
}


def unsupported_schema_items(
    collections: set[str],
    service_blocks: set[str],
    sql_tables: set[str],
) -> dict[str, set[str]]:
    """Return newly observed schema items not covered by the parser contract."""
    return {
        "collections": collections - SUPPORTED_JSON_COLLECTIONS,
        "service_blocks": service_blocks - SUPPORTED_JSON_SERVICE_BLOCKS,
        "sql_tables": sql_tables - SUPPORTED_SQL_TABLES,
    }
