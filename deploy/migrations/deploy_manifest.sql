-- Controle de sincronização dos artefatos publicados pelo mbft-deploy.
CREATE TABLE IF NOT EXISTS deploy_manifest (
    resource_type TEXT NOT NULL,
    resource_name TEXT NOT NULL,
    content_hash TEXT NOT NULL,
    status TEXT NOT NULL,
    item_count INTEGER,
    updated_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    error_message TEXT,
    PRIMARY KEY (resource_type, resource_name)
);
