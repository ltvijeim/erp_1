Platform Infrastructure: The Global Layer (Technical Architecture Blueprint)
This document establishes the physical, relational, and behavioral blueprints for the core engine of the ERP: The Recursive Node Hierarchy (The Global Layer).

1. Architectural Topology & Execution Boundary
The diagram below maps out how the Recursive Node Hierarchy functions as the spatial and security boundaries of the GCP cloud infrastructure. It details how requests traverse VPC boundaries, interact with Redis cache locks, and execute queries against the Cloud SQL PostgreSQL instance using the ltree extension.
graph TB
    subgraph Public Internet
        Client[Client API / Scanner / Web]
    end

    subgraph Google Cloud Platform VPC
        subgraph Load Balancing & Edge
            GFW[Cloud Armor & HTTPS Load Balancer]
        end

        subgraph Serverless Compute Container GAE
            Django[GAE Backend Instances - Django Web/Workers]
            subgraph Cloud Memorystore
                Redis[(Redis Cache & Session Store)]
            end
        end

        subgraph Cloud SQL PostgreSQL Database Cluster
            subgraph Primary DB Instance
                SchemaPlatform[Schema: platform]
                TableNodes[Table: platform.nodes]
                TableSettings[Table: platform.node_settings]
                TableAccess[Table: platform.node_access_assignments]
                
                LtreeExt[[PostgreSQL ltree Extension]]
                TriggerEngine[[PL/pgSQL Trigger Engine]]
                
                LtreeExt --> TableNodes
                TriggerEngine --> TableNodes
            end
            
            subgraph Read Replica DB Instance
                Replica[(Read Replica)]
            end
        end
    end

    %% Network Routing Paths
    Client -->|HTTPS / WSS| GFW
    GFW -->|Intra-VPC Serverless Connector| Django
    Django -->|Fetch Session / Lock Mutex| Redis
    Django -->|Write: Read-Write Connection| Primary DB Instance
    Django -->|Read: Read-Only Connection| Replica
    Primary DB Instance -->|Asynchronous Streaming Replication| Replica


2. Entity Relationship Diagram (Physical Data Model)
This physical schema defines the structural layout of the tables, including explicit data types, indexes, database-level defaults, and foreign key rules.
erDiagram
    "platform.nodes" {
        UUID node_id PK "DEFAULT gen_random_uuid()"
        UUID parent_node_id FK "NULL for Root"
        VARCHAR node_type "CHECK (node_type IN ('ENTERPRISE', 'LEGAL_ENTITY', 'REGION', 'SITE', 'ZONE', 'BIN', 'WORK_CENTER', 'LPN'))"
        VARCHAR node_name "VARCHAR(255) NOT NULL"
        ltree lineage_path "INDEXED (GiST)"
        VARCHAR status "DEFAULT 'PLANNED' CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'PLANNED'))"
        TIMESTAMPTZ created_at "DEFAULT NOW()"
        TIMESTAMPTZ updated_at "DEFAULT NOW()"
    }

    "platform.node_settings" {
        UUID setting_id PK "DEFAULT gen_random_uuid()"
        UUID node_id FK "ON DELETE CASCADE"
        VARCHAR setting_key "VARCHAR(100) NOT NULL"
        JSONB setting_value "NOT NULL"
        BOOLEAN is_override "DEFAULT FALSE NOT NULL"
        TIMESTAMPTZ updated_at "DEFAULT NOW()"
    }

    "platform.node_access_assignments" {
        UUID assignment_id PK "DEFAULT gen_random_uuid()"
        UUID user_id "NOT NULL (System Auth User ID)"
        UUID node_id FK "ON DELETE CASCADE"
        VARCHAR role "VARCHAR(100) NOT NULL"
        BOOLEAN cascade_access "DEFAULT TRUE NOT NULL"
        TIMESTAMPTZ assigned_at "DEFAULT NOW()"
    }

    "platform.nodes" ||--o| "platform.nodes" : "parent_node_id : self-references"
    "platform.nodes" ||--o{ "platform.node_settings" : "has settings"
    "platform.nodes" ||--o{ "platform.node_access_assignments" : "controls access"



3. Physical Database Schema (PostgreSQL DDL)
This DDL script initializes the PostgreSQL environment. It activates the ltree extension, establishes a isolated schema, configures tables with explicit constraints, and deploys high-performance index topologies (B-Tree and GiST).
-- Ensure database possesses PG-Crypto for UUID generation and Ltree for hierarchical operations
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS "pgcrypto";
CREATE EXTENSION IF NOT EXISTS "ltree";

CREATE SCHEMA IF NOT EXISTS platform;

-- =========================================================================
-- TABLE: platform.nodes
-- =========================================================================
CREATE TABLE platform.nodes (
    node_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_node_id UUID,
    node_type VARCHAR(50) NOT NULL,
    node_name VARCHAR(255) NOT NULL,
    lineage_path ltree NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_nodes_parent 
        FOREIGN KEY (parent_node_id) 
        REFERENCES platform.nodes(node_id) 
        ON DELETE RESTRICT, -- Prevent deletion of parents containing active sub-hierarchies
        
    CONSTRAINT chk_node_type 
        CHECK (node_type IN ('ENTERPRISE', 'LEGAL_ENTITY', 'REGION', 'SITE', 'ZONE', 'BIN', 'WORK_CENTER', 'LPN')),
        
    CONSTRAINT chk_status 
        CHECK (status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED', 'PLANNED'))
);

-- Indexing Strategy for ultra-fast spatial search and hierarchy resolution
CREATE INDEX idx_nodes_parent_id ON platform.nodes (parent_node_id) WHERE parent_node_id IS NOT NULL;
CREATE INDEX idx_nodes_node_type ON platform.nodes (node_type);
CREATE INDEX idx_nodes_status ON platform.nodes (status);
-- GiST Index specifically for indexing the lineage_path of type ltree
CREATE INDEX idx_nodes_lineage_gist ON platform.nodes USING gist (lineage_path);

-- =========================================================================
-- TABLE: platform.node_settings
-- =========================================================================
CREATE TABLE platform.node_settings (
    setting_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL,
    setting_key VARCHAR(100) NOT NULL,
    setting_value JSONB NOT NULL,
    is_override BOOLEAN NOT NULL DEFAULT FALSE,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_node_settings_node 
        FOREIGN KEY (node_id) 
        REFERENCES platform.nodes(node_id) 
        ON DELETE CASCADE,
        
    -- Restrict duplicate setting keys at the node boundary level
    CONSTRAINT uq_node_setting_key 
        UNIQUE (node_id, setting_key)
);

CREATE INDEX idx_node_settings_lookup ON platform.node_settings (node_id, setting_key);
CREATE INDEX idx_node_settings_value_jsonb ON platform.node_settings USING gin (setting_value);

-- =========================================================================
-- TABLE: platform.node_access_assignments
-- =========================================================================
CREATE TABLE platform.node_access_assignments (
    assignment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID NOT NULL, -- References the master enterprise auth identity
    node_id UUID NOT NULL,
    role VARCHAR(100) NOT NULL,
    cascade_access BOOLEAN NOT NULL DEFAULT TRUE,
    assigned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    
    CONSTRAINT fk_node_access_node 
        FOREIGN KEY (node_id) 
        REFERENCES platform.nodes(node_id) 
        ON DELETE CASCADE,
        
    -- No duplicate roles for the same user on a single node
    CONSTRAINT uq_user_node_role 
        UNIQUE (user_id, node_id, role)
);

CREATE INDEX idx_access_user_node ON platform.node_access_assignments (user_id, node_id);


4. Tree Data Structure & Query Resolution Strategy
We utilize a hybrid approach combining an Adjacency List (parent_node_id foreign key) for transactional writes and a Materialized Path (lineage_path using the native ltree extension) for fast hierarchical reads.
Storing UUIDs inside PostgreSQL ltree
The ltree extension expects labels to match the regex ^[A-Za-z0-9_]{1,256}$. Raw UUIDs contain hyphens (e.g., 4af62cb8-9df2-4da4-8e14-722146eb4cb9), which are illegal in ltree formatting.
Solution: We strip the hyphens from the UUID to generate a clean, safe hexadecimal string (e.g., 4af62cb89df24da48e14722146eb4cb9). Under this standard, a path looks like this:
4af62cb89df24da48e14722146eb4cb9.390a3821098b2cd729381a3821aa8d10
Automated Path Generation and Propagation Trigger
This database trigger intercepts write operations to guarantee that any insertion or relocation of a node automatically calculates its exact lineage_path using the stripped hexadecimal UUID formats.
CREATE OR REPLACE FUNCTION platform.fn_trg_preserve_and_build_lineage()
RETURNS TRIGGER AS $$
DECLARE
    v_parent_path ltree;
    v_cleaned_uuid VARCHAR(32);
BEGIN
    -- Clean hyphens from the current node's UUID
    v_cleaned_uuid := REPLACE(NEW.node_id::TEXT, '-', '');

    IF NEW.parent_node_id IS NULL THEN
        -- Root Node is the parent of itself in its own path
        NEW.lineage_path := v_cleaned_uuid::ltree;
    ELSE
        -- Retrieve the lineage path of the parent node
        SELECT lineage_path INTO v_parent_path 
        FROM platform.nodes 
        WHERE node_id = NEW.parent_node_id;
        
        IF v_parent_path IS NULL THEN
            RAISE EXCEPTION 'Parent node % does not exist or has no defined path.', NEW.parent_node_id;
        END IF;
        
        -- Append current cleaned UUID to parent path
        NEW.lineage_path := (v_parent_path::text || '.' || v_cleaned_uuid)::ltree;
    END IF;

    -- Ensure updated_at timestamp is bumped on every write
    NEW.updated_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nodes_build_lineage
BEFORE INSERT OR UPDATE OF parent_node_id, node_id ON platform.nodes
FOR EACH ROW
EXECUTE FUNCTION platform.fn_trg_preserve_and_build_lineage();


5. Pure Database-Level Implementations of Business Rules
To protect data integrity, these strict rules are enforced at the database layer using transactions, triggers, and indices rather than relying on application code.
Rule 1: "The Law of the Root" (Strict Single Root Enforcement)
This constraint ensures that there is only ever exactly one logical root node in the system.
-- Enforcement of exactly one root node globally via a partial unique index
CREATE UNIQUE INDEX uq_one_root_node_allowed
ON platform.nodes ((parent_node_id IS NULL))
WHERE parent_node_id IS NULL;

Rule 2: Acyclic Hierarchy Enforcement (Infinite Loop Protection)
This trigger prevents circular inheritance when updating hierarchical configurations.
CREATE OR REPLACE FUNCTION platform.fn_trg_prevent_circular_dependency()
RETURNS TRIGGER AS $$
DECLARE
    v_cleaned_target_id VARCHAR(32);
    v_parent_path_text TEXT;
BEGIN
    -- Do not evaluate unless parent is modified
    IF (TG_OP = 'UPDATE' AND OLD.parent_node_id IS NOT DISTINCT FROM NEW.parent_node_id) THEN
        RETURN NEW;
    END IF;

    IF NEW.parent_node_id IS NOT NULL THEN
        -- Format the current node ID for match verification inside the ancestor path
        v_cleaned_target_id := REPLACE(NEW.node_id::TEXT, '-', '');
        
        SELECT lineage_path::TEXT INTO v_parent_path_text 
        FROM platform.nodes 
        WHERE node_id = NEW.parent_node_id;

        -- Check if the target node ID exists as an ancestor in the parent's path
        IF v_parent_path_text ~ ('(^|\.)' || v_cleaned_target_id || '($|\.)') THEN
            RAISE EXCEPTION 'Cyclic Reference Violation: Node % is an ancestor of target parent %.', 
                NEW.node_id, NEW.parent_node_id;
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_nodes_prevent_loops
BEFORE UPDATE ON platform.nodes
FOR EACH ROW
EXECUTE FUNCTION platform.fn_trg_prevent_circular_dependency();


6. Contextual Inheritance Engine
This highly optimized PL/pgSQL function implements the Inheritance Fallback business rule. It uses ltree ancestor paths to resolve settings values dynamically in a single index-backed database lookup.
CREATE OR REPLACE FUNCTION platform.fn_resolve_node_setting(
    p_node_id UUID,
    p_setting_key VARCHAR(100)
)
RETURNS JSONB AS $$
DECLARE
    v_resolved_value JSONB;
BEGIN
    -- Query traverses down the lineage path hierarchy and picks the closest definition
    SELECT s.setting_value INTO v_resolved_value
    FROM platform.nodes n
    JOIN platform.node_settings s ON s.node_id = n.node_id
    WHERE n.lineage_path @> (SELECT lineage_path FROM platform.nodes WHERE node_id = p_node_id)
      AND s.setting_key = p_setting_key
      -- If override is false, lookups fallback to parent setting configurations unless set
      AND (n.node_id = p_node_id OR s.is_override = FALSE OR (SELECT count(*) from platform.node_settings where node_id = p_node_id and setting_key = p_setting_key) = 0)
    ORDER BY nlevel(n.lineage_path) DESC -- Pick the closest ancestor value (longest path Match)
    LIMIT 1;

    -- Return NULL if no setting is configured at any node level in the hierarchy path
    RETURN v_resolved_value;
END;
$$ LANGUAGE plpgsql STABLE;


7. Security Scoping & Data Isolation Engine
This security interface ensures user access is verified only within authorized paths.
CREATE OR REPLACE FUNCTION platform.fn_check_user_node_authorization(
    p_user_id UUID,
    p_target_node_id UUID,
    p_required_role VARCHAR(100) DEFAULT NULL
)
RETURNS BOOLEAN AS $$
DECLARE
    v_has_access BOOLEAN := FALSE;
BEGIN
    EXISTS (
        SELECT 1 
        FROM platform.node_access_assignments auth
        JOIN platform.nodes auth_node ON auth_node.node_id = auth.node_id
        JOIN platform.nodes target_node ON target_node.node_id = p_target_node_id
        WHERE auth.user_id = p_user_id
          AND (p_required_role IS NULL OR auth.role = p_required_role)
          AND (
              -- Scenario A: Direct matching node access
              auth.node_id = p_target_node_id
              OR 
              -- Scenario B: Cascading access where auth node path is an ancestor of target node path
              (auth.cascade_access = TRUE AND auth_node.lineage_path @> target_node.lineage_path)
          )
    ) INTO v_has_access;
    
    RETURN v_has_access;
END;
$$ LANGUAGE plpgsql STABLE;


8. Verification Testing Suite (Unit Sandbox)
This script populates a sandbox environment to verify circular reference locks, setting fallbacks, and security policies.
DO $$
DECLARE
    v_ent_id UUID;
    v_region_na_id UUID;
    v_site_wh_id UUID;
    v_bin_01_id UUID;
    v_user_clerk UUID := gen_random_uuid();
    v_user_admin UUID := gen_random_uuid();
    v_resolved_setting JSONB;
    v_authorized BOOLEAN;
BEGIN
    RAISE NOTICE 'Initializing Sandbox Node Testing Scenario...';

    -- 1. Create a Root Enterprise Node
    INSERT INTO platform.nodes (node_type, node_name)
    VALUES ('ENTERPRISE', 'Global Enterprise HQ')
    RETURNING node_id INTO v_ent_id;
    
    -- 2. Create Region Node under Root Enterprise
    INSERT INTO platform.nodes (parent_node_id, node_type, node_name)
    VALUES (v_ent_id, 'REGION', 'North America')
    RETURNING node_id INTO v_region_na_id;

    -- 3. Create Site Node under Region Node
    INSERT INTO platform.nodes (parent_node_id, node_type, node_name)
    VALUES (v_region_na_id, 'SITE', 'Austin Warehouse Site A')
    RETURNING node_id INTO v_site_wh_id;

    -- 4. Create Bin Node under Site Node
    INSERT INTO platform.nodes (parent_node_id, node_type, node_name)
    VALUES (v_site_wh_id, 'BIN', 'Inbound Receiving Bin 01')
    RETURNING node_id INTO v_bin_01_id;

    RAISE NOTICE 'Sandbox Nodes Generated Successfully.';

    -- =========================================================================
    -- VERIFICATION: INHERITANCE TEST
    -- =========================================================================
    -- Apply Base Currency at Root Node
    INSERT INTO platform.node_settings (node_id, setting_key, setting_value)
    VALUES (v_ent_id, 'BASE_CURRENCY', '"USD"'::jsonb);

    -- Apply Tax Jurisdiction Override at the Site Node
    INSERT INTO platform.node_settings (node_id, setting_key, setting_value, is_override)
    VALUES (v_site_wh_id, 'TAX_JURISDICTION', '{"jurisdiction": "TX_TRAVIS"}'::jsonb, TRUE);

    -- Verify that Bin 01 inherits BASE_CURRENCY from Root Node
    v_resolved_setting := platform.fn_resolve_node_setting(v_bin_01_id, 'BASE_CURRENCY');
    RAISE NOTICE 'Currency inherited by Bin 01: % (Expected: "USD")', v_resolved_setting;

    -- Verify that Bin 01 inherits TAX_JURISDICTION from Site Node
    v_resolved_setting := platform.fn_resolve_node_setting(v_bin_01_id, 'TAX_JURISDICTION');
    RAISE NOTICE 'Tax Jurisdiction inherited by Bin 01: % (Expected: TX_TRAVIS)', v_resolved_setting;

    -- =========================================================================
    -- VERIFICATION: SECURITY ACCESS SCENARIO
    -- =========================================================================
    -- Grant User A (Clerk) access to Region Node with cascade = TRUE
    INSERT INTO platform.node_access_assignments (user_id, node_id, role, cascade_access)
    VALUES (v_user_clerk, v_region_na_id, 'INVENTORY_CLERK', TRUE);

    -- Check if Clerk has cascading access to Bin 01 (should be TRUE)
    v_authorized := platform.fn_check_user_node_authorization(v_user_clerk, v_bin_01_id, 'INVENTORY_CLERK');
    RAISE NOTICE 'Clerk authorized for Bin 01: % (Expected: t)', v_authorized;

    -- Check if Clerk has access to Enterprise Node (should be FALSE)
    v_authorized := platform.fn_check_user_node_authorization(v_user_clerk, v_ent_id);
    RAISE NOTICE 'Clerk authorized for Root Enterprise: % (Expected: f)', v_authorized;

    -- =========================================================================
    -- VERIFICATION: CYCLIC INTEGRITY LOCK CHECK
    -- =========================================================================
    BEGIN
        RAISE NOTICE 'Attempting circular update. Expecting validation exception...';
        -- Attempt to set Root Enterprise's parent to the Region Node (circular dependency)
        UPDATE platform.nodes 
        SET parent_node_id = v_region_na_id 
        WHERE node_id = v_ent_id;
    EXCEPTION WHEN OTHERS THEN
        RAISE NOTICE 'Circular dependency check passed! Error caught as expected: %', SQLERRM;
    END;

END;
$$;


Master Data Management (MDM): The "Who" and "What" Layer
This document establishes the physical, relational, and behavioral blueprints for Master Data Management (MDM).
In a distributed enterprise, Master Data is subject to intense read-heavy concurrency. Every transaction in MES, WMS, or Finance will query Items and Business Partners. To prevent database bottlenecking and N+1 query degradation, this design enforces a strict Hub and Spoke relational model and assumes an aggressive caching layer via Google Cloud Memorystore (Redis) for global entity definitions, while keeping local node extensions strictly transactional in Cloud SQL.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            Backend[Django API & Celery Workers]
        end

        subgraph Cloud Memorystore
            Redis[(Redis: MDM Cache)]
            %% Note: Global Item/BP definitions are cached here. Node Extensions are queried live.
        end

        subgraph Cloud SQL PostgreSQL
            SchemaPlatform[Schema: platform]
            SchemaMDM[Schema: mdm]

            SchemaMDM -->|Foreign Keys to node_id| SchemaPlatform
        end
    end

    Backend -->|1. Read Global Master (Cache Hit)| Redis
    Backend -->|2. Read Node Extension (Live)| SchemaMDM
    Backend -->|Write (Invalidate Cache)| SchemaMDM
    SchemaMDM -.->|Async Replication| Replica[(Read Replica)]



2. Entity Relationship Diagram (Physical Data Model)
This model explicitly decouples the Universal ("Global Master") from the Local ("Node Extension").
erDiagram
    "mdm.items" {
        UUID item_id PK "DEFAULT gen_random_uuid()"
        VARCHAR sku "UNIQUE NOT NULL"
        VARCHAR item_class "INVENTORY, SERVICE, RAW_MATERIAL, ASSEMBLY"
        VARCHAR base_uom "EACH, LITER, KG, etc."
        TEXT global_description 
        VARCHAR traceability_type "NONE, BATCH, SERIAL"
        VARCHAR global_status "ACTIVE, INACTIVE, IN_DEVELOPMENT"
    }

    "mdm.item_node_extensions" {
        UUID extension_id PK "DEFAULT gen_random_uuid()"
        UUID item_id FK "References mdm.items"
        UUID node_id FK "References platform.nodes"
        VARCHAR local_status "ACTIVE, DISCONTINUED, PHASE_OUT"
        VARCHAR costing_method "STANDARD, FIFO, MOVING_AVERAGE"
        VARCHAR replenishment_rule "MAKE_TO_STOCK, MAKE_TO_ORDER, BUY_TO_ORDER"
    }

    "mdm.business_partners" {
        UUID bp_id PK "DEFAULT gen_random_uuid()"
        VARCHAR bp_number "UNIQUE NOT NULL"
        VARCHAR legal_name "NOT NULL"
        VARCHAR tax_vat_id 
        UUID parent_bp_id FK "Self-referencing Corporate Hierarchy"
    }

    "mdm.bp_node_roles" {
        UUID role_id PK "DEFAULT gen_random_uuid()"
        UUID bp_id FK "References mdm.business_partners"
        UUID node_id FK "References platform.nodes"
        VARCHAR bp_role "CUSTOMER, SUPPLIER, CARRIER, EMPLOYEE"
        VARCHAR financial_terms "e.g., NET_30"
    }

    "mdm.items" ||--o{ "mdm.item_node_extensions" : "extended to"
    "platform.nodes" ||--o{ "mdm.item_node_extensions" : "hosts item"
    
    "mdm.business_partners" ||--o| "mdm.business_partners" : "corporate parent"
    "mdm.business_partners" ||--o{ "mdm.bp_node_roles" : "acts as"
    "platform.nodes" ||--o{ "mdm.bp_node_roles" : "interacts with"


3. Physical Database Schema (PostgreSQL DDL)
We isolate MDM into its own schema to enforce boundary contexts. Categorical constraints are explicitly handled via CHECK constraints to ensure strict data validation without the overhead of custom ENUM types, which require exclusive locks to modify in production.
CREATE SCHEMA IF NOT EXISTS mdm;

-- =========================================================================
-- TABLE: mdm.items (The Universal "What")
-- =========================================================================
CREATE TABLE mdm.items (
    item_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    sku VARCHAR(100) UNIQUE NOT NULL,
    item_class VARCHAR(50) NOT NULL,
    base_uom VARCHAR(20) NOT NULL,
    global_description TEXT NOT NULL,
    traceability_type VARCHAR(20) NOT NULL DEFAULT 'NONE',
    global_status VARCHAR(30) NOT NULL DEFAULT 'IN_DEVELOPMENT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_item_class 
        CHECK (item_class IN ('INVENTORY', 'SERVICE', 'RAW_MATERIAL', 'ASSEMBLY', 'PHANTOM')),
    CONSTRAINT chk_traceability 
        CHECK (traceability_type IN ('NONE', 'BATCH', 'SERIAL')),
    CONSTRAINT chk_global_status 
        CHECK (global_status IN ('ACTIVE', 'INACTIVE', 'IN_DEVELOPMENT'))
);

CREATE INDEX idx_items_status ON mdm.items (global_status);
CREATE INDEX idx_items_class ON mdm.items (item_class);

-- =========================================================================
-- TABLE: mdm.item_node_extensions (The Local "How")
-- =========================================================================
CREATE TABLE mdm.item_node_extensions (
    extension_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL,
    node_id UUID NOT NULL, -- Cross-schema FK to Global Layer
    local_status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    costing_method VARCHAR(30) NOT NULL,
    replenishment_rule VARCHAR(30) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_extension_item 
        FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE CASCADE,
    CONSTRAINT fk_extension_node 
        FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
        
    -- An item can only have ONE extension per node
    CONSTRAINT uq_item_node UNIQUE (item_id, node_id),

    CONSTRAINT chk_local_status 
        CHECK (local_status IN ('ACTIVE', 'DISCONTINUED', 'PHASE_OUT', 'INACTIVE')),
    CONSTRAINT chk_costing_method 
        CHECK (costing_method IN ('STANDARD', 'FIFO', 'MOVING_AVERAGE')),
    CONSTRAINT chk_replenishment 
        CHECK (replenishment_rule IN ('MAKE_TO_STOCK', 'MAKE_TO_ORDER', 'BUY_TO_ORDER', 'NONE'))
);

CREATE INDEX idx_item_ext_node ON mdm.item_node_extensions (node_id);
CREATE INDEX idx_item_ext_lookup ON mdm.item_node_extensions (item_id, node_id);

-- =========================================================================
-- TABLE: mdm.business_partners (The Universal "Who")
-- =========================================================================
CREATE TABLE mdm.business_partners (
    bp_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bp_number VARCHAR(100) UNIQUE NOT NULL,
    legal_name VARCHAR(255) NOT NULL,
    tax_vat_id VARCHAR(100),
    parent_bp_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_bp_parent 
        FOREIGN KEY (parent_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE SET NULL
);

CREATE INDEX idx_bp_parent ON mdm.business_partners (parent_bp_id) WHERE parent_bp_id IS NOT NULL;

-- =========================================================================
-- TABLE: mdm.bp_node_roles (The Local Relationship)
-- =========================================================================
CREATE TABLE mdm.bp_node_roles (
    role_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bp_id UUID NOT NULL,
    node_id UUID NOT NULL, -- Cross-schema FK to Global Layer
    bp_role VARCHAR(50) NOT NULL,
    financial_terms VARCHAR(50) NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_role_bp 
        FOREIGN KEY (bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE CASCADE,
    CONSTRAINT fk_role_node 
        FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,

    -- A BP can be a Supplier AND Customer at the same node, but cannot be duplicate roles
    CONSTRAINT uq_bp_node_role UNIQUE (bp_id, node_id, bp_role),

    CONSTRAINT chk_bp_role 
        CHECK (bp_role IN ('CUSTOMER', 'SUPPLIER', 'CARRIER', 'EMPLOYEE'))
);

CREATE INDEX idx_bp_role_node ON mdm.bp_node_roles (node_id);


4. Database-Level Enforcement of Business Rules
Rule: Global vs. Local Status Conflict Resolution
To adhere strictly to the rule where a Global "Inactive" setting mathematically forces a Local "Inactive" behavior (regardless of the local database column), we instantiate an Effective Status View. The application API must always query this view when verifying if an item can be transacted.
CREATE OR REPLACE VIEW mdm.vw_effective_item_status AS
SELECT 
    ext.extension_id,
    ext.item_id,
    ext.node_id,
    i.global_status,
    ext.local_status AS raw_local_status,
    -- THE CONFLICT RESOLUTION ENGINE:
    CASE 
        WHEN i.global_status = 'INACTIVE' THEN 'INACTIVE'
        WHEN i.global_status = 'IN_DEVELOPMENT' THEN 'IN_DEVELOPMENT'
        WHEN ext.local_status = 'INACTIVE' THEN 'INACTIVE'
        WHEN ext.local_status = 'DISCONTINUED' THEN 'DISCONTINUED'
        ELSE 'ACTIVE'
    END AS effective_status,
    i.traceability_type -- Pulled through because traceability is universally enforced
FROM mdm.item_node_extensions ext
JOIN mdm.items i ON i.item_id = ext.item_id;

Rule: Acyclic Business Partner Enforcement
Just like the Node Hierarchy, Corporate entities cannot have infinite loops (e.g., Company A owns Company B, which owns Company A).
CREATE OR REPLACE FUNCTION mdm.fn_trg_prevent_bp_circular_dependency()
RETURNS TRIGGER AS $$
DECLARE
    v_current_parent UUID;
BEGIN
    IF (TG_OP = 'UPDATE' AND OLD.parent_bp_id IS NOT DISTINCT FROM NEW.parent_bp_id) THEN
        RETURN NEW;
    END IF;

    v_current_parent := NEW.parent_bp_id;
    
    WHILE v_current_parent IS NOT NULL LOOP
        IF v_current_parent = NEW.bp_id THEN
            RAISE EXCEPTION 'Cyclic Reference Violation: BP % cannot be an ancestor of itself.', NEW.bp_id;
        END IF;
        
        SELECT parent_bp_id INTO v_current_parent 
        FROM mdm.business_partners 
        WHERE bp_id = v_current_parent;
    END LOOP;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bp_prevent_loops
BEFORE UPDATE ON mdm.business_partners
FOR EACH ROW
EXECUTE FUNCTION mdm.fn_trg_prevent_bp_circular_dependency();

Rule: The Law of Base UoM Immutability (Protective Trigger)
Once inventory exists or transactions occur, changing the base_uom causes catastrophic mathematical failure in the ERP. We deploy an auditing trigger to lock this down. (Note: In a full deployment, this trigger checks the wms.inventory_positions table; here we establish the boundary restriction).
CREATE OR REPLACE FUNCTION mdm.fn_trg_protect_base_uom()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.base_uom IS DISTINCT FROM NEW.base_uom THEN
        -- ARCHITECTURAL WARNING: In the WMS phase, we will alter this trigger 
        -- to query IF EXISTS (SELECT 1 FROM wms.inventory_positions WHERE item_id = OLD.item_id).
        -- For now, we enforce strict immutability once created.
        IF OLD.global_status = 'ACTIVE' THEN
            RAISE EXCEPTION 'Architectural Hard-Stop: Base UoM cannot be modified once an Item is moved to ACTIVE status to prevent historical ledger corruption.';
        END IF;
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_items_protect_uom
BEFORE UPDATE ON mdm.items
FOR EACH ROW
EXECUTE FUNCTION mdm.fn_trg_protect_base_uom();


Architectural Warning: Concurrency & The "Phantom Read" Problem
When evaluating Extension Prerequisite (checking if an extension exists before allowing a Purchase Order), we must avoid race conditions where a local Node Manager deletes an item_node_extension exactly while a Sales Order is being processed.
Mitigation Strategy for Future Modules (e.g., Commercial/Procurement):
When writing transactions against an Item, the backend must execute a Row-Level Lock:
SELECT 1 FROM mdm.item_node_extensions WHERE item_id = X AND node_id = Y FOR SHARE;
This ensures the extension remains locked and undeletable for the few milliseconds it takes to commit the transactional order in the adjacent tables.

Product Lifecycle & Engineering: The "Recipe" Layer
This document establishes the physical, relational, and behavioral blueprints for the Product Lifecycle & Engineering module.
In enterprise architectures, Bill of Materials (BOM) explosions (traversing deep multi-level BOMs) are notorious for causing exponential database load. To mitigate this, we enforce strict relational constraints, leverage PostgreSQL's native daterange types for temporal effectivity, and utilize Recursive Common Table Expressions (CTEs) at the DB layer to prevent acyclic loops before they corrupt the production schedule.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            Backend[Django API: Engineering / ECO Service]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaPlatform[Schema: platform]
            SchemaMDM[Schema: mdm]
            SchemaEng[Schema: eng]

            Backend -->|Reads/Writes| SchemaEng
            
            SchemaEng -->|1. FK: Item Validations| SchemaMDM
            SchemaEng -->|2. FK: Node/Work Center Checks| SchemaPlatform
            
            TriggerAcyclic[[Trigger: Acyclic BOM Lock]]
            TriggerNode[[Trigger: Component Node Validation]]
            
            TriggerAcyclic --> SchemaEng
            TriggerNode --> SchemaEng
            TriggerNode -.-> SchemaMDM
        end
    end



2. Entity Relationship Diagram (Physical Data Model)
This model defines the triad of manufacturing: The Master (BOM Header), the Ingredients (BOM Lines), and the Instructions (Routing), all governed by the ECO.
erDiagram
    "eng.bom_headers" {
        UUID bom_id PK
        UUID item_id FK "References mdm.items"
        UUID node_id FK "References platform.nodes"
        VARCHAR revision_level "e.g., 'Rev A'"
        VARCHAR bom_type "MANUFACTURING, ENGINEERING, KIT, PHANTOM"
        VARCHAR status "DRAFT, ACTIVE, OBSOLETE"
    }

    "eng.bom_lines" {
        UUID bom_line_id PK
        UUID bom_id FK "References eng.bom_headers"
        UUID component_item_id FK "References mdm.items"
        DECIMAL quantity "DECIMAL(19,4)"
        DECIMAL scrap_factor "DECIMAL(5,4) Percentage"
        DATERANGE effectivity_dates "PostgreSQL native temporal range"
    }

    "eng.routings" {
        UUID routing_id PK
        UUID bom_id FK "References eng.bom_headers"
        UUID node_id FK "References platform.nodes (Site/Zone)"
        INTEGER operation_seq "10, 20, 30"
        UUID work_center_id FK "References platform.nodes (Type: WORK_CENTER)"
        DECIMAL standard_time "DECIMAL(19,4) Hours"
    }

    "eng.ecos" {
        UUID eco_id PK
        UUID node_id FK "References platform.nodes"
        VARCHAR reason_code "COST_REDUCTION, QUALITY_FIX, etc."
        UUID target_bom_id FK "References eng.bom_headers"
        VARCHAR approval_status "PENDING, APPROVED, REJECTED, EXECUTED"
        TIMESTAMPTZ effectivity_date
    }

    "eng.bom_headers" ||--o{ "eng.bom_lines" : "contains"
    "eng.bom_headers" ||--o| "eng.routings" : "assembled via"
    "eng.ecos" ||--o{ "eng.bom_headers" : "governs"
    
    %% Cross-schema references implied
    %% MDM Item -> BOM Header
    %% MDM Item -> BOM Line Component


3. Physical Database Schema (PostgreSQL DDL)
We isolate Engineering data into the eng schema. Notice the heavy use of DECIMAL(19,4) to prevent floating-point arithmetic errors during cost rollups, and the use of PostgreSQL's daterange for temporal overlapping constraints.
CREATE SCHEMA IF NOT EXISTS eng;

-- =========================================================================
-- TABLE: eng.bom_headers
-- =========================================================================
CREATE TABLE eng.bom_headers (
    bom_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    item_id UUID NOT NULL,          -- Cross-schema to mdm.items
    node_id UUID NOT NULL,          -- Cross-schema to platform.nodes
    revision_level VARCHAR(50) NOT NULL,
    bom_type VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_bom_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT fk_bom_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    
    -- An item cannot have the same revision level duplicated at the same Node
    CONSTRAINT uq_item_node_revision UNIQUE (item_id, node_id, revision_level),

    CONSTRAINT chk_bom_type CHECK (bom_type IN ('MANUFACTURING', 'ENGINEERING', 'KIT', 'PHANTOM')),
    CONSTRAINT chk_bom_status CHECK (status IN ('DRAFT', 'ACTIVE', 'OBSOLETE'))
);

CREATE INDEX idx_bom_headers_item_node ON eng.bom_headers (item_id, node_id);
CREATE INDEX idx_bom_headers_status ON eng.bom_headers (status);

-- =========================================================================
-- TABLE: eng.bom_lines
-- =========================================================================
CREATE TABLE eng.bom_lines (
    bom_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bom_id UUID NOT NULL,
    component_item_id UUID NOT NULL, -- Cross-schema to mdm.items
    quantity DECIMAL(19,4) NOT NULL CHECK (quantity > 0),
    scrap_factor DECIMAL(5,4) NOT NULL DEFAULT 0.0000 CHECK (scrap_factor >= 0 AND scrap_factor < 1),
    effectivity_dates daterange NOT NULL DEFAULT '[,)'::daterange, -- infinite bounds by default
    
    CONSTRAINT fk_bom_line_header FOREIGN KEY (bom_id) REFERENCES eng.bom_headers(bom_id) ON DELETE CASCADE,
    CONSTRAINT fk_bom_line_comp FOREIGN KEY (component_item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT
);

CREATE INDEX idx_bom_lines_bom_id ON eng.bom_lines (bom_id);
CREATE INDEX idx_bom_lines_component ON eng.bom_lines (component_item_id);
-- GiST index for ultra-fast temporal range querying
CREATE INDEX idx_bom_lines_effectivity ON eng.bom_lines USING gist (effectivity_dates);

-- =========================================================================
-- TABLE: eng.routings
-- =========================================================================
CREATE TABLE eng.routings (
    routing_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    bom_id UUID NOT NULL,
    node_id UUID NOT NULL,
    operation_seq INTEGER NOT NULL CHECK (operation_seq > 0),
    work_center_id UUID NOT NULL, -- Cross-schema to platform.nodes (must be WORK_CENTER)
    standard_time DECIMAL(19,4) NOT NULL CHECK (standard_time >= 0),
    
    CONSTRAINT fk_routing_bom FOREIGN KEY (bom_id) REFERENCES eng.bom_headers(bom_id) ON DELETE CASCADE,
    CONSTRAINT fk_routing_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_routing_wc FOREIGN KEY (work_center_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    
    CONSTRAINT uq_routing_seq UNIQUE (bom_id, operation_seq)
);

CREATE INDEX idx_routings_bom ON eng.routings (bom_id);

-- =========================================================================
-- TABLE: eng.ecos
-- =========================================================================
CREATE TABLE eng.ecos (
    eco_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL,
    reason_code VARCHAR(50) NOT NULL,
    target_bom_id UUID NOT NULL,
    approval_status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    effectivity_date TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_eco_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_eco_bom FOREIGN KEY (target_bom_id) REFERENCES eng.bom_headers(bom_id) ON DELETE RESTRICT,

    CONSTRAINT chk_eco_reason CHECK (reason_code IN ('COST_REDUCTION', 'QUALITY_FIX', 'OBSOLESCENCE', 'NPI')),
    CONSTRAINT chk_eco_status CHECK (approval_status IN ('PENDING', 'APPROVED', 'REJECTED', 'EXECUTED'))
);


4. Database-Level Enforcement of Business Rules
Rule 1: Component Node Validation (Cross-Schema MDM Check)
You cannot add a part to a local BOM if the factory isn't authorized to stock it. This trigger executes on eng.bom_lines and verifies the component against mdm.item_node_extensions.
CREATE OR REPLACE FUNCTION eng.fn_trg_validate_component_node_extension()
RETURNS TRIGGER AS $$
DECLARE
    v_parent_node_id UUID;
    v_extension_exists BOOLEAN;
BEGIN
    -- 1. Identify the Node ID of the BOM Header this line belongs to
    SELECT node_id INTO v_parent_node_id 
    FROM eng.bom_headers 
    WHERE bom_id = NEW.bom_id;

    -- 2. Check if the component has an active node extension at this specific Node
    SELECT EXISTS (
        SELECT 1 
        FROM mdm.item_node_extensions ext
        JOIN mdm.vw_effective_item_status v_status ON ext.extension_id = v_status.extension_id
        WHERE ext.item_id = NEW.component_item_id
          AND ext.node_id = v_parent_node_id
          AND v_status.effective_status = 'ACTIVE'
    ) INTO v_extension_exists;

    IF NOT v_extension_exists THEN
        RAISE EXCEPTION 'Component Validation Failed: Component % does not have an ACTIVE Node Extension at Node %.', 
            NEW.component_item_id, v_parent_node_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bom_lines_node_validation
BEFORE INSERT OR UPDATE OF component_item_id ON eng.bom_lines
FOR EACH ROW
EXECUTE FUNCTION eng.fn_trg_validate_component_node_extension();

Rule 2: Acyclic BOM Enforcement (No Infinite Loops)
A parent item cannot exist inside its own recipe, nor can any sub-assembly loop back to the parent. We enforce this with a Recursive CTE during insert/update.
CREATE OR REPLACE FUNCTION eng.fn_trg_prevent_bom_circular_dependency()
RETURNS TRIGGER AS $$
DECLARE
    v_parent_item_id UUID;
    v_is_circular BOOLEAN;
BEGIN
    -- Get the target item of the BOM we are modifying
    SELECT item_id INTO v_parent_item_id 
    FROM eng.bom_headers 
    WHERE bom_id = NEW.bom_id;

    -- Recursive CTE to explode the BOM downwards and check if the parent item appears
    WITH RECURSIVE bom_explosion AS (
        -- Base Case: The component we are currently adding
        SELECT component_item_id
        FROM eng.bom_lines
        WHERE bom_id = NEW.bom_id AND bom_line_id = NEW.bom_line_id
        
        UNION ALL
        
        -- Recursive Case: Find BOMs where the component is the parent item, and get their components
        SELECT bl.component_item_id
        FROM eng.bom_lines bl
        JOIN eng.bom_headers bh ON bh.bom_id = bl.bom_id
        JOIN bom_explosion be ON bh.item_id = be.component_item_id
        WHERE bh.status = 'ACTIVE' -- Only explode active sub-assemblies to prevent massive tree scans
    )
    SELECT EXISTS (
        SELECT 1 FROM bom_explosion WHERE component_item_id = v_parent_item_id
    ) INTO v_is_circular;

    IF v_is_circular THEN
        RAISE EXCEPTION 'Acyclic BOM Violation: Inserting component % creates an infinite loop back to parent item %.', 
            NEW.component_item_id, v_parent_item_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

-- Execute AFTER insert/update so the row exists for the CTE to evaluate
CREATE TRIGGER trg_bom_lines_prevent_loops
AFTER INSERT OR UPDATE OF component_item_id ON eng.bom_lines
FOR EACH ROW
EXECUTE FUNCTION eng.fn_trg_prevent_bom_circular_dependency();

Rule 3: The Law of Released Immutability
Once a BOM is "ACTIVE", you cannot alter its lines. It requires an ECO to draft a new Revision.
CREATE OR REPLACE FUNCTION eng.fn_trg_enforce_bom_immutability()
RETURNS TRIGGER AS $$
DECLARE
    v_bom_status VARCHAR;
BEGIN
    -- For headers
    IF TG_TABLE_NAME = 'bom_headers' THEN
        IF OLD.status = 'ACTIVE' AND NEW.status = 'ACTIVE' THEN
            -- Allow non-structural updates (like descriptions if they existed), but block physical recipe changes
            IF OLD.item_id != NEW.item_id OR OLD.bom_type != NEW.bom_type THEN
                RAISE EXCEPTION 'Immutability Lock: Cannot modify core fields of an ACTIVE BOM Header. Issue an ECO.';
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    -- For lines
    IF TG_TABLE_NAME = 'bom_lines' THEN
        SELECT status INTO v_bom_status FROM eng.bom_headers WHERE bom_id = OLD.bom_id;
        IF v_bom_status = 'ACTIVE' THEN
            RAISE EXCEPTION 'Immutability Lock: Cannot add, edit, or delete lines on an ACTIVE BOM. Draft a new revision via ECO.';
        END IF;
        RETURN NEW;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_bom_headers_immutability BEFORE UPDATE ON eng.bom_headers FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_enforce_bom_immutability();
CREATE TRIGGER trg_bom_lines_immutability BEFORE UPDATE OR DELETE ON eng.bom_lines FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_enforce_bom_immutability();

Architectural Warning: ECO Execution & Locking
When an ECO is executed (Status changed from APPROVED to EXECUTED), it triggers the "Strict Effectivity Handoffs" rule (Old Rev -> OBSOLETE, New Rev -> ACTIVE).
Cloud Architect Directive: Do not process this synchronously in the Django view. Updating BOM status triggers cascading downstream recalculations (e.g., standard cost rollups, MRP invalidation).
Solution: The ECO Execution API must write to a transaction outbox, triggering an asynchronous Celery Task to handle the DB lock and status flip during off-peak execution boundaries, ensuring front-end clients do not face connection timeouts.

Manufacturing Execution System (MES): The "Making" Layer
This document establishes the physical, relational, and behavioral blueprints for the Manufacturing Execution System (MES).
In an enterprise environment, the shop floor is highly concurrent. Hundreds of operators and automated PLCs (Programmable Logic Controllers) concurrently report yield, scrap, and material consumption. If not architected correctly, this leads to severe database deadlocks and race conditions. We will rely on strict PostgreSQL Row-Level Locking (SELECT FOR UPDATE) for material allocation and decouple financial cost rollups into asynchronous Celery queues to keep API latency sub-100ms for barcode scanners.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Shop Floor
        Scanner[Operator Scanner / HMI Tablet]
        PLC[IoT / PLC Automated Feed]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            DjangoAPI[Django MES API - Sync]
            Celery[Celery Async Workers]
        end

        subgraph Cloud Memorystore
            RedisBroker[(Redis: Task Broker & Mutex)]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaMES[Schema: mes]
            SchemaPlatform[Schema: platform]
            SchemaEng[Schema: eng]
            
            TriggerSeq[[Trigger: Sequence Enforcement]]
            TriggerAlloc[[Trigger: Strict Allocation]]
        end
    end

    %% Execution Flow
    Scanner -->|1. POST Transaction| DjangoAPI
    PLC -->|1. POST Yield| DjangoAPI
    
    DjangoAPI -->|2. Mutex Lock / FOR UPDATE| SchemaMES
    DjangoAPI -->|3. Sync Response (Sub-100ms)| Scanner
    
    DjangoAPI -->|4. Queue Cost Rollup Task| RedisBroker
    RedisBroker -->|5. Consume| Celery
    Celery -->|6. Async Financial Update| SchemaMES



2. Entity Relationship Diagram (Physical Data Model)
This model instantiates the Engineering "Recipe" into immutable, transactional execution records.
erDiagram
    "mes.work_centers" {
        UUID node_id PK "FK to platform.nodes"
        VARCHAR resource_type "MACHINE, LABOR_POOL, SUBCONTRACTOR"
        DECIMAL standard_cost_rate "DECIMAL(19,4)"
        DECIMAL capacity_hrs_day "DECIMAL(5,2)"
    }

    "mes.work_orders" {
        UUID wo_id PK "DEFAULT gen_random_uuid()"
        UUID node_id FK "References platform.nodes"
        UUID item_id FK "References mdm.items"
        DECIMAL target_quantity "DECIMAL(19,4)"
        VARCHAR status "PLANNED, RELEASED, IN_PROGRESS, COMPLETED, CLOSED"
        DECIMAL actual_cost "DECIMAL(19,4)"
    }

    "mes.wo_material_requirements" {
        UUID requirement_id PK
        UUID wo_id FK "References mes.work_orders"
        UUID component_item_id FK "References mdm.items"
        DECIMAL required_qty "DECIMAL(19,4)"
        DECIMAL consumed_qty "DECIMAL(19,4)"
    }

    "mes.wo_operations" {
        UUID wo_op_id PK
        UUID wo_id FK "References mes.work_orders"
        INTEGER operation_seq 
        UUID work_center_id FK "References mes.work_centers"
        DECIMAL yield_qty "DECIMAL(19,4)"
        DECIMAL scrap_qty "DECIMAL(19,4)"
    }

    "mes.production_transactions" {
        UUID transaction_id PK
        UUID wo_id FK "References mes.work_orders"
        UUID work_center_id FK "References mes.work_centers"
        VARCHAR event_type "SETUP, RUN, MATERIAL_ISSUE, SCRAP, YIELD"
        DECIMAL quantity "DECIMAL(19,4)"
        DECIMAL labor_hours "DECIMAL(19,4)"
        VARCHAR batch_serial_ref 
        UUID operator_id FK "References platform.users"
    }

    "platform.nodes" ||--o| "mes.work_centers" : "is extended as"
    "mes.work_orders" ||--o{ "mes.wo_material_requirements" : "picks"
    "mes.work_orders" ||--o{ "mes.wo_operations" : "routes"
    "mes.work_orders" ||--o{ "mes.production_transactions" : "logs"
    "mes.work_centers" ||--o{ "mes.production_transactions" : "executes"


3. Physical Database Schema (PostgreSQL DDL)
CREATE SCHEMA IF NOT EXISTS mes;

-- =========================================================================
-- TABLE: mes.work_centers (The Resource Node)
-- =========================================================================
-- Work Centers are Nodes. We extend the global platform.nodes table directly via 1:1 FK PK.
CREATE TABLE mes.work_centers (
    node_id UUID PRIMARY KEY,
    resource_type VARCHAR(50) NOT NULL,
    standard_cost_rate DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    capacity_hrs_day DECIMAL(5,2) NOT NULL CHECK (capacity_hrs_day >= 0 AND capacity_hrs_day <= 24),
    
    CONSTRAINT fk_wc_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT chk_resource_type CHECK (resource_type IN ('MACHINE', 'LABOR_POOL', 'SUBCONTRACTOR'))
);

-- =========================================================================
-- TABLE: mes.work_orders (WO Header)
-- =========================================================================
CREATE TABLE mes.work_orders (
    wo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL, -- The Facility/Site
    item_id UUID NOT NULL, -- Finished Good
    target_quantity DECIMAL(19,4) NOT NULL CHECK (target_quantity > 0),
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
    actual_cost DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_wo_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_wo_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT chk_wo_status CHECK (status IN ('PLANNED', 'RELEASED', 'IN_PROGRESS', 'COMPLETED', 'CLOSED'))
);

CREATE INDEX idx_wo_status ON mes.work_orders (status);
CREATE INDEX idx_wo_node ON mes.work_orders (node_id);

-- =========================================================================
-- TABLE: mes.wo_operations (The Execution Steps)
-- Implicitly required to track seq, yield, and routing progression.
-- =========================================================================
CREATE TABLE mes.wo_operations (
    wo_op_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wo_id UUID NOT NULL,
    operation_seq INTEGER NOT NULL CHECK (operation_seq > 0),
    work_center_id UUID NOT NULL,
    yield_qty DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    scrap_qty DECIMAL(19,4) NOT NULL DEFAULT 0.0000,

    CONSTRAINT fk_wo_op_wo FOREIGN KEY (wo_id) REFERENCES mes.work_orders(wo_id) ON DELETE CASCADE,
    CONSTRAINT fk_wo_op_wc FOREIGN KEY (work_center_id) REFERENCES mes.work_centers(node_id) ON DELETE RESTRICT,
    CONSTRAINT uq_wo_op_seq UNIQUE (wo_id, operation_seq)
);

CREATE INDEX idx_wo_op_wo_id ON mes.wo_operations (wo_id);

-- =========================================================================
-- TABLE: mes.wo_material_requirements (The Pick List)
-- =========================================================================
CREATE TABLE mes.wo_material_requirements (
    requirement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wo_id UUID NOT NULL,
    component_item_id UUID NOT NULL,
    required_qty DECIMAL(19,4) NOT NULL CHECK (required_qty >= 0),
    consumed_qty DECIMAL(19,4) NOT NULL DEFAULT 0.0000,

    CONSTRAINT fk_wo_req_wo FOREIGN KEY (wo_id) REFERENCES mes.work_orders(wo_id) ON DELETE CASCADE,
    CONSTRAINT fk_wo_req_item FOREIGN KEY (component_item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT uq_wo_req_item UNIQUE (wo_id, component_item_id)
);

-- =========================================================================
-- TABLE: mes.production_transactions (The Immutable Execution Log)
-- =========================================================================
CREATE TABLE mes.production_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    wo_id UUID NOT NULL,
    work_center_id UUID NOT NULL,
    event_type VARCHAR(30) NOT NULL,
    quantity DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    labor_hours DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    batch_serial_ref VARCHAR(100),
    operator_id UUID NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pt_wo FOREIGN KEY (wo_id) REFERENCES mes.work_orders(wo_id) ON DELETE RESTRICT,
    CONSTRAINT fk_pt_wc FOREIGN KEY (work_center_id) REFERENCES mes.work_centers(node_id) ON DELETE RESTRICT,
    CONSTRAINT chk_pt_event CHECK (event_type IN ('SETUP', 'RUN', 'MATERIAL_ISSUE', 'SCRAP', 'YIELD'))
);

CREATE INDEX idx_pt_wo_id ON mes.production_transactions (wo_id);
CREATE INDEX idx_pt_batch ON mes.production_transactions (batch_serial_ref) WHERE batch_serial_ref IS NOT NULL;


4. Database-Level Enforcement of Business Rules
Rule 1: The Law of Sequential Enforcement
An operator cannot yield parts on Operation 20 if Operation 10 hasn't produced them yet. This trigger ensures mathematical sequence adherence.
CREATE OR REPLACE FUNCTION mes.fn_trg_enforce_operation_sequence()
RETURNS TRIGGER AS $$
DECLARE
    v_previous_yield DECIMAL(19,4);
    v_previous_seq INTEGER;
BEGIN
    -- We only care about YIELD tracking
    IF NEW.yield_qty > OLD.yield_qty THEN
        
        -- Find the immediately preceding operation sequence for this WO
        SELECT operation_seq, yield_qty INTO v_previous_seq, v_previous_yield
        FROM mes.wo_operations
        WHERE wo_id = NEW.wo_id AND operation_seq < NEW.operation_seq
        ORDER BY operation_seq DESC
        LIMIT 1;

        -- If a previous operation exists, enforce the bottleneck limit
        IF FOUND AND NEW.yield_qty > v_previous_yield THEN
            RAISE EXCEPTION 'Sequence Violation: Cannot report % yield on Op %. Max available from preceding Op % is %.',
                NEW.yield_qty, NEW.operation_seq, v_previous_seq, v_previous_yield;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wo_op_sequence
BEFORE UPDATE OF yield_qty ON mes.wo_operations
FOR EACH ROW
EXECUTE FUNCTION mes.fn_trg_enforce_operation_sequence();

Rule 2: Strict Material Allocation Hard-Stop
You cannot mark a Work Order as COMPLETED unless all required components have been physically consumed.
CREATE OR REPLACE FUNCTION mes.fn_trg_enforce_material_allocation()
RETURNS TRIGGER AS $$
DECLARE
    v_unfulfilled_components INTEGER;
BEGIN
    IF OLD.status != 'COMPLETED' AND NEW.status = 'COMPLETED' THEN
        -- Count how many components have consumed_qty < required_qty
        SELECT COUNT(*) INTO v_unfulfilled_components
        FROM mes.wo_material_requirements
        WHERE wo_id = NEW.wo_id AND consumed_qty < required_qty;

        IF v_unfulfilled_components > 0 THEN
            RAISE EXCEPTION 'Material Allocation Hard-Stop: Work Order cannot be COMPLETED. % component(s) have unmet material requirements.', 
                v_unfulfilled_components;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_wo_completion_allocation
BEFORE UPDATE OF status ON mes.work_orders
FOR EACH ROW
EXECUTE FUNCTION mes.fn_trg_enforce_material_allocation();


5. Architectural Directives for the Application Layer
Concurrency Directive: The Race Condition on Material Issue
When two operators attempt to scan and issue the same material to the same Work Order at the exact same millisecond, a standard UPDATE mes.wo_material_requirements SET consumed_qty = consumed_qty + 1 will result in a lost update (race condition).
Mandatory Django Implementation Pattern:
Whenever an API endpoint records a MATERIAL_ISSUE transaction, it MUST lock the requirement row using PostgreSQL's SELECT ... FOR UPDATE before applying the increment:
# Conceptual Architecture Logic (Not application code execution, but architectural constraint)
with transaction.atomic():
    # 1. Lock the row strictly for this transaction's thread
    req = WOMaterialRequirement.objects.select_for_update().get(
        wo_id=wo_uuid, component_item_id=scanned_item_uuid
    )
    
    # 2. Safely apply addition
    req.consumed_qty += scanned_qty
    req.save()
    
    # 3. Log the immutable transaction
    ProductionTransaction.objects.create(...)

Asynchronous Architecture: Cost Rollup Execution
The conceptual blueprint demands: "As Production Transactions are logged, the system multiplies the time spent by the Work Center Standard Cost Rate, and adds the cost of the Consumed Qty of materials."
Cloud Architect Warning: Costing math requires joining mdm.item_node_extensions (for material cost) and mes.work_centers (for labor rates). Executing this math synchronously on every scanner beep will cause severe database CPU spiking.
Solution: The Celery Boundary
Operator submits YIELD or MATERIAL_ISSUE.
Django API strictly updates mes.wo_operations.yield_qty and inserts mes.production_transactions.
Django returns 201 Created instantly.
Django pushes a message to Redis: {"task": "mes.cost_rollup", "wo_id": "uuid", "transaction_id": "uuid"}
A background Celery Worker picks up the task, performs the multi-table JOIN math to calculate variance, and applies a single asynchronous UPDATE mes.work_orders SET actual_cost = X.

Supply Chain & Warehouse (WMS): The "Storing & Moving" Layer
This document establishes the physical, relational, and behavioral blueprints for the Warehouse Management System (WMS).
The WMS layer is the most concurrency-heavy module in the ERP. Hundreds of RF scanners constantly read, lock, and deduct inventory. To prevent double-allocation and scanner deadlocks, this architecture strictly enforces database-level Zero-Negative constraints and mandates the use of PostgreSQL SELECT FOR UPDATE SKIP LOCKED for the Allocation Engine.
Furthermore, we will natively leverage the Global Layer's ltree extension to treat Handling Units (LPNs) as Mobile Nodes, allowing massive pallets of inventory to be moved with a single foreign key update.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Warehouse Shop Floor
        Scanner[RF Barcode Scanner / Android]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            WMSApi[Django WMS API]
            AllocEngine[Django Allocation Engine]
        end

        subgraph Cloud Memorystore
            RedisCache[(Redis: Bin Capacity / Pick Path Cache)]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaWMS[Schema: wms]
            SchemaPlatform[Schema: platform]
            
            AllocLock[[Row-Level Lock: FOR UPDATE SKIP LOCKED]]
            ZeroNegTrigger[[Constraint: Zero-Negative Prevention]]
            
            SchemaWMS -->|LPN Parent Update| SchemaPlatform
        end
    end

    Scanner -->|1. Request Pick Task| WMSApi
    WMSApi -->|2. Query Next Task| SchemaWMS
    Scanner -->|3. Scan Bin & Item| AllocEngine
    AllocEngine -->|4. Lock Position| AllocLock
    AllocLock --> SchemaWMS
    SchemaWMS --> ZeroNegTrigger


2. Entity Relationship Diagram (Physical Data Model)
Because an LPN is a "Mobile Node", the wms.lpns table acts as a specific extension of platform.nodes, just like mes.work_centers.
erDiagram
    "wms.lpns" {
        UUID node_id PK "FK to platform.nodes (node_type = 'LPN')"
        UUID parent_lpn_id FK "Recursive nesting"
        VARCHAR container_type "PALLET, TOTE, PARCEL"
        DECIMAL max_weight "DECIMAL(10,2)"
        DECIMAL max_volume "DECIMAL(10,2)"
    }

    "wms.inventory_positions" {
        UUID position_id PK "DEFAULT gen_random_uuid()"
        UUID node_id FK "References platform.nodes (Bin or LPN)"
        UUID item_id FK "References mdm.items"
        VARCHAR batch_serial_id 
        DECIMAL quantity "DECIMAL(19,4) CHECK (>= 0)"
        VARCHAR stock_status "AVAILABLE, ALLOCATED, QA_HOLD, BLOCKED"
    }

    "wms.warehouse_tasks" {
        UUID task_id PK "DEFAULT gen_random_uuid()"
        UUID source_node_id FK "References platform.nodes"
        UUID target_node_id FK "References platform.nodes"
        UUID item_id FK "NULL if moving whole LPN"
        UUID lpn_id FK "NULL if moving loose items"
        DECIMAL task_qty "DECIMAL(19,4)"
        VARCHAR task_type "PUTAWAY, PICK, REPLENISHMENT, CYCLE_COUNT"
        VARCHAR status "PENDING, IN_PROGRESS, COMPLETED, CANCELLED"
        UUID assigned_user_id FK "References platform.users"
    }

    "platform.nodes" ||--o| "wms.lpns" : "extends as Mobile Node"
    "wms.lpns" ||--o{ "wms.lpns" : "nests inside"
    "platform.nodes" ||--o{ "wms.inventory_positions" : "holds"
    "wms.inventory_positions" ||--o{ "wms.warehouse_tasks" : "moves"


3. Physical Database Schema (PostgreSQL DDL)
We isolate the WMS tables. The most critical constraint here is CHECK (quantity >= 0), which physically prevents the ERP from bleeding into mathematical impossibilities.
CREATE SCHEMA IF NOT EXISTS wms;

-- =========================================================================
-- TABLE: wms.lpns (The Handling Unit / License Plate)
-- =========================================================================
CREATE TABLE wms.lpns (
    node_id UUID PRIMARY KEY, -- Extends platform.nodes directly
    parent_lpn_id UUID, -- For Box inside a Pallet
    container_type VARCHAR(50) NOT NULL,
    max_weight DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    max_volume DECIMAL(10,2) NOT NULL DEFAULT 0.00,
    
    CONSTRAINT fk_lpn_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT fk_lpn_parent FOREIGN KEY (parent_lpn_id) REFERENCES wms.lpns(node_id) ON DELETE SET NULL,
    CONSTRAINT chk_container_type CHECK (container_type IN ('PALLET', 'TOTE', 'GAYLORD', 'PARCEL'))
);

-- =========================================================================
-- TABLE: wms.inventory_positions (The Ledger of Reality)
-- =========================================================================
CREATE TABLE wms.inventory_positions (
    position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL, -- The specific Bin OR the LPN holding it
    item_id UUID NOT NULL, -- Cross-schema to mdm.items
    batch_serial_id VARCHAR(100),
    quantity DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    stock_status VARCHAR(30) NOT NULL DEFAULT 'AVAILABLE',
    last_counted_at TIMESTAMPTZ,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_inv_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_inv_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    
    -- RULE 5: Zero-Negative Inventory Enforcement (The ultimate safety net)
    CONSTRAINT chk_quantity_positive CHECK (quantity >= 0),
    
    CONSTRAINT chk_stock_status CHECK (stock_status IN ('AVAILABLE', 'ALLOCATED', 'QA_HOLD', 'BLOCKED'))
);

-- Indexing Strategy: Allocation engines query strictly by Item, Status, and Node proximity
CREATE INDEX idx_inv_alloc_engine ON wms.inventory_positions (item_id, stock_status, quantity) WHERE quantity > 0;
CREATE INDEX idx_inv_node ON wms.inventory_positions (node_id);
CREATE INDEX idx_inv_batch ON wms.inventory_positions (batch_serial_id) WHERE batch_serial_id IS NOT NULL;

-- =========================================================================
-- TABLE: wms.warehouse_tasks (The Work Queue)
-- =========================================================================
CREATE TABLE wms.warehouse_tasks (
    task_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    source_node_id UUID NOT NULL,
    target_node_id UUID NOT NULL,
    item_id UUID,
    lpn_id UUID,
    task_qty DECIMAL(19,4),
    task_type VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    assigned_user_id UUID,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_task_source FOREIGN KEY (source_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_target FOREIGN KEY (target_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT fk_task_lpn FOREIGN KEY (lpn_id) REFERENCES wms.lpns(node_id) ON DELETE RESTRICT,

    CONSTRAINT chk_task_type CHECK (task_type IN ('PUTAWAY', 'PICK', 'REPLENISHMENT', 'CYCLE_COUNT', 'TRANSFER')),
    CONSTRAINT chk_task_status CHECK (status IN ('PENDING', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED', 'EXCEPTION'))
);

CREATE INDEX idx_tasks_queue ON wms.warehouse_tasks (status, task_type);


4. Database-Level Enforcement of Business Rules
Rule: Status-Based Isolation (The Allocation View)
To mathematically hide inventory with "QA Hold" or "Blocked" status from the outbound fulfillment engine without writing complex application logic, we enforce a strict View. The Sales Order / ATP engine must query this view, never the base table.
CREATE OR REPLACE VIEW wms.vw_allocatable_inventory AS
SELECT 
    ip.position_id,
    ip.node_id,
    ip.item_id,
    ip.batch_serial_id,
    ip.quantity,
    n.lineage_path -- Inherited from the Global Node Layer for spatial querying
FROM wms.inventory_positions ip
JOIN platform.nodes n ON n.node_id = ip.node_id
WHERE ip.stock_status = 'AVAILABLE' 
  AND ip.quantity > 0;

Rule: Conservation of Inventory (Protection Trigger)
Inventory cannot be "deleted" from the database. If it reaches 0, the record can be archived, but manual deletion of a position containing stock is blocked.
CREATE OR REPLACE FUNCTION wms.fn_trg_prevent_inventory_deletion()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.quantity > 0 THEN
        RAISE EXCEPTION 'Law of Conservation: Cannot delete an Inventory Position containing % units. An explicit Adjustment or Pick task must drive it to 0 first.', OLD.quantity;
    END IF;
    RETURN OLD;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_protect_inv_deletion
BEFORE DELETE ON wms.inventory_positions
FOR EACH ROW
EXECUTE FUNCTION wms.fn_trg_prevent_inventory_deletion();


5. Architectural Directives for the Application Layer
Concurrency Directive 1: The Allocation Engine (SKIP LOCKED)
When the system tries to fulfill an order for 100 units, it queries the DB. In high-volume warehouses, multiple orders might query the exact same Bin at the same time. If they both SELECT FOR UPDATE, Order 2 will hang and wait for Order 1 to finish (bottleneck).
Mandatory Django Implementation Pattern for Allocation:
We must use PostgreSQL's SKIP LOCKED feature. This tells the database: "Grab the oldest batches (FIFO) you can find, but if another thread is currently looking at Batch A, skip it immediately and grab Batch B instead."
# Conceptual Architecture Logic for Allocation Engine
with transaction.atomic():
    # 1. Fetch available positions, strictly ordered by FIFO, skipping locked rows
    available_positions = InventoryPosition.objects.raw('''
        SELECT position_id, quantity 
        FROM wms.vw_allocatable_inventory
        WHERE item_id = %s
        ORDER BY batch_serial_id ASC -- (FIFO Logic)
        FOR UPDATE SKIP LOCKED
    ''', [target_item_uuid])
    
    # 2. Iterate and update to 'ALLOCATED' until demand is met
    # ...

Concurrency Directive 2: LPN as a Mobile Node
The brilliance of treating an LPN as a Node is that inventory never has to be updated when a pallet moves.
If a pallet (LPN A) holds 50 unique Inventory Positions (different items/batches), and a forklift moves the pallet from the Receiving Dock to Aisle 4, the application does not execute 50 UPDATE wms.inventory_positions queries.
Instead, it executes exactly one query:
UPDATE platform.nodes 
SET parent_node_id = 'Aisle_4_Node_UUID' 
WHERE node_id = 'Pallet_LPN_UUID';

The Global Layer's ltree trigger instantly recalculates the spatial path. Any subsequent query for "What is in Aisle 4?" will perfectly return all 50 inventory positions because their lineage_path dynamically resolves to Aisle 4. This cuts database write-load by magnitudes during physical movement.

Commercial & Logistics: The "Selling & Shipping" Layer
This document establishes the physical, relational, and behavioral blueprints for the Commercial & Logistics module.
In an enterprise Order-to-Cash (O2C) cycle, the system must bridge the gap between commercial promises (Sales Orders) and physical realities (Deliveries and Shipments). To prevent double-selling inventory and ensure accurate revenue recognition, this architecture strictly separates the Commercial Entity (who owns the revenue) from the Logistics Entity (who executes the pick/pack/ship).
We will enforce mathematical locking on Post Goods Issue (PGI) transactions and mandate asynchronous processing for revenue recognition to protect API latency.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph External
        Customer[Customer Portal / EDI]
        Carrier[Carrier API / EDI]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            O2C_API[Django Commercial API]
            ATP_Engine[Django ATP Engine]
            Celery[Celery Async Workers: PGI & AR Bridge]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaCom[Schema: com]
            SchemaWMS[Schema: wms]
            SchemaMDM[Schema: mdm]
            
            SchemaCom -->|Validates Carrier| SchemaMDM
            SchemaCom -->|Deducts Inventory on PGI| SchemaWMS
            
            TriggerCarrier[[Trigger: Carrier Validation]]
            TriggerPGI[[Trigger: PGI Immutability Lock]]
        end
    end

    Customer -->|1. Submit Order| O2C_API
    O2C_API -->|2. Check Stock| ATP_Engine
    ATP_Engine -->|3. Read| SchemaWMS
    O2C_API -->|4. Generate Deliveries| SchemaCom
    Carrier -->|5. Confirm Dispatch| O2C_API
    O2C_API -->|6. Queue PGI Task| Celery
    Celery -->|7. Deduct Stock & Trigger AR| SchemaWMS


2. Entity Relationship Diagram (Physical Data Model)
This model explicitly decouples the Sales Order (Commercial Contract) from the Outbound Delivery (Warehouse Task) and the Shipment (Freight Vehicle).
erDiagram
    "com.sales_orders" {
        UUID so_id PK
        UUID selling_node_id FK "References platform.nodes"
        UUID customer_bp_id FK "References mdm.business_partners"
        VARCHAR order_status "DRAFT, CONFIRMED, PROCESSING, SHIPPED, INVOICED, CREDIT_HOLD"
        VARCHAR incoterms "EXW, FOB, DDP, etc."
        DECIMAL total_value "DECIMAL(19,4)"
    }

    "com.so_lines" {
        UUID so_line_id PK
        UUID so_id FK "References com.sales_orders"
        UUID item_id FK "References mdm.items"
        UUID fulfilling_node_id FK "References platform.nodes"
        DECIMAL requested_qty "DECIMAL(19,4)"
        DATE promised_date "Temporal commitment"
    }

    "com.shipments" {
        UUID shipment_id PK
        UUID origin_node_id FK "References platform.nodes (Dock)"
        UUID carrier_bp_id FK "References mdm.business_partners"
        VARCHAR tracking_number 
        DECIMAL freight_cost "DECIMAL(19,4)"
        TIMESTAMPTZ dispatch_time 
        VARCHAR status "PLANNED, STAGED, DISPATCHED, DELIVERED"
    }

    "com.outbound_deliveries" {
        UUID delivery_id PK
        UUID so_line_id FK "References com.so_lines"
        UUID shipment_id FK "References com.shipments (Nullable until consolidated)"
        UUID node_id FK "References platform.nodes (Warehouse execution)"
        UUID packed_lpn_id FK "References wms.lpns"
        VARCHAR delivery_status "PENDING_WMS, PICKING, PACKED, SHIPPED"
        DECIMAL delivered_qty "DECIMAL(19,4)"
    }

    "com.sales_orders" ||--o{ "com.so_lines" : "contains"
    "com.so_lines" ||--o{ "com.outbound_deliveries" : "fulfilled by"
    "com.shipments" ||--o{ "com.outbound_deliveries" : "transports"


3. Physical Database Schema (PostgreSQL DDL)
We establish the com schema. Notice the careful use of DECIMAL(19,4) for financial values and DATE for promised dates (which are decoupled from absolute timezone timestamps until execution).
CREATE SCHEMA IF NOT EXISTS com;

-- =========================================================================
-- TABLE: com.sales_orders (The Commercial Contract)
-- =========================================================================
CREATE TABLE com.sales_orders (
    so_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    selling_node_id UUID NOT NULL, -- Commercial Entity (e.g., EU Sales Branch)
    customer_bp_id UUID NOT NULL,  -- Cross-schema to mdm.business_partners
    order_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    incoterms VARCHAR(3) NOT NULL, -- Standard 3-letter ICC Incoterms
    total_value DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_so_node FOREIGN KEY (selling_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_so_customer FOREIGN KEY (customer_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE RESTRICT,
    
    CONSTRAINT chk_so_status 
        CHECK (order_status IN ('DRAFT', 'CONFIRMED', 'PROCESSING', 'SHIPPED', 'INVOICED', 'CREDIT_HOLD'))
);

CREATE INDEX idx_so_customer ON com.sales_orders (customer_bp_id);
CREATE INDEX idx_so_status ON com.sales_orders (order_status);

-- =========================================================================
-- TABLE: com.so_lines (The Demand)
-- =========================================================================
CREATE TABLE com.so_lines (
    so_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    so_id UUID NOT NULL,
    item_id UUID NOT NULL,
    fulfilling_node_id UUID NOT NULL, -- Logistics Entity (e.g., German Warehouse)
    requested_qty DECIMAL(19,4) NOT NULL CHECK (requested_qty > 0),
    promised_date DATE NOT NULL,

    CONSTRAINT fk_sol_so FOREIGN KEY (so_id) REFERENCES com.sales_orders(so_id) ON DELETE CASCADE,
    CONSTRAINT fk_sol_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT fk_sol_node FOREIGN KEY (fulfilling_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT
);

CREATE INDEX idx_sol_node_item ON com.so_lines (fulfilling_node_id, item_id);
CREATE INDEX idx_sol_promised ON com.so_lines (promised_date);

-- =========================================================================
-- TABLE: com.shipments (The Freight Manifest)
-- =========================================================================
CREATE TABLE com.shipments (
    shipment_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    origin_node_id UUID NOT NULL, -- Physical Dock Node
    carrier_bp_id UUID NOT NULL,  -- Freight Provider
    tracking_number VARCHAR(100),
    freight_cost DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    dispatch_time TIMESTAMPTZ,
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_shipment_node FOREIGN KEY (origin_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_shipment_carrier FOREIGN KEY (carrier_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE RESTRICT,

    CONSTRAINT chk_shipment_status 
        CHECK (status IN ('PLANNED', 'STAGED', 'DISPATCHED', 'DELIVERED'))
);

CREATE INDEX idx_shipment_carrier ON com.shipments (carrier_bp_id);

-- =========================================================================
-- TABLE: com.outbound_deliveries (The Logistical Bridge)
-- =========================================================================
CREATE TABLE com.outbound_deliveries (
    delivery_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    so_line_id UUID NOT NULL,
    shipment_id UUID, -- Assigned during consolidation
    node_id UUID NOT NULL, -- Must match fulfilling_node_id
    packed_lpn_id UUID, -- Updated by WMS when packed
    delivery_status VARCHAR(30) NOT NULL DEFAULT 'PENDING_WMS',
    delivered_qty DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_dlv_sol FOREIGN KEY (so_line_id) REFERENCES com.so_lines(so_line_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dlv_shipment FOREIGN KEY (shipment_id) REFERENCES com.shipments(shipment_id) ON DELETE SET NULL,
    CONSTRAINT fk_dlv_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_dlv_lpn FOREIGN KEY (packed_lpn_id) REFERENCES platform.nodes(node_id) ON DELETE SET NULL,

    CONSTRAINT chk_dlv_status 
        CHECK (delivery_status IN ('PENDING_WMS', 'PICKING', 'PACKED', 'SHIPPED'))
);

CREATE INDEX idx_dlv_shipment ON com.outbound_deliveries (shipment_id) WHERE shipment_id IS NOT NULL;
CREATE INDEX idx_dlv_status ON com.outbound_deliveries (delivery_status);


4. Database-Level Enforcement of Business Rules
Rule 1: Post Goods Issue (PGI) Immutability Lock
When a Shipment is marked as DISPATCHED, the execution is final. The truck has left the yard. No user can alter the Shipment or its attached Deliveries.
CREATE OR REPLACE FUNCTION com.fn_trg_enforce_pgi_immutability()
RETURNS TRIGGER AS $$
BEGIN
    -- Protect the Shipment
    IF TG_TABLE_NAME = 'shipments' THEN
        IF OLD.status = 'DISPATCHED' THEN
            -- Allow tracking number updates (often arrive late via API), but block physical/cost changes
            IF OLD.origin_node_id != NEW.origin_node_id OR OLD.carrier_bp_id != NEW.carrier_bp_id OR OLD.freight_cost != NEW.freight_cost THEN
                RAISE EXCEPTION 'PGI Immutability Lock: Cannot modify physical or financial traits of a DISPATCHED shipment.';
            END IF;
        END IF;
    END IF;

    -- Protect the Deliveries inside the Shipment
    IF TG_TABLE_NAME = 'outbound_deliveries' THEN
        IF OLD.delivery_status = 'SHIPPED' THEN
            RAISE EXCEPTION 'PGI Immutability Lock: Cannot modify a SHIPPED outbound delivery. Issue an RMA/Return Order instead.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_shipment_immutability 
BEFORE UPDATE ON com.shipments 
FOR EACH ROW EXECUTE FUNCTION com.fn_trg_enforce_pgi_immutability();

CREATE TRIGGER trg_delivery_immutability 
BEFORE UPDATE OR DELETE ON com.outbound_deliveries 
FOR EACH ROW EXECUTE FUNCTION com.fn_trg_enforce_pgi_immutability();

Rule 2: Carrier BP Validation Check
A shipment can only be assigned to a BP that is explicitly authorized as a 'CARRIER' at the Origin Node.
CREATE OR REPLACE FUNCTION com.fn_trg_validate_carrier_bp()
RETURNS TRIGGER AS $$
DECLARE
    v_is_valid_carrier BOOLEAN;
BEGIN
    SELECT EXISTS (
        SELECT 1 
        FROM mdm.bp_node_roles role
        JOIN platform.nodes role_node ON role.node_id = role_node.node_id
        JOIN platform.nodes origin_node ON origin_node.node_id = NEW.origin_node_id
        WHERE role.bp_id = NEW.carrier_bp_id
          AND role.bp_role = 'CARRIER'
          -- Check if the Origin Node is within the inherited path of the Carrier's authorized node
          AND role_node.lineage_path @> origin_node.lineage_path
    ) INTO v_is_valid_carrier;

    IF NOT v_is_valid_carrier THEN
        RAISE EXCEPTION 'Carrier Validation Failed: BP % is not an authorized CARRIER for Node % or its ancestors.', 
            NEW.carrier_bp_id, NEW.origin_node_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_shipment_carrier_validation
BEFORE INSERT OR UPDATE OF carrier_bp_id, origin_node_id ON com.shipments
FOR EACH ROW
EXECUTE FUNCTION com.fn_trg_validate_carrier_bp();


5. Architectural Directives for the Application Layer
Concurrency Directive 1: The ATP (Available-to-Promise) Engine
Calculating real-time availability across multiple warehouses is a notoriously heavy query.
Architectural Rule: Do not execute SUM(quantity) across WMS tables synchronously during customer checkout.
Instead, the ATP Engine must rely on a CQRS (Command Query Responsibility Segregation) pattern:
WMS triggers an asynchronous materialization task upon any inventory change.
The materialized view (or Redis Hash) maintains a running integer of (Total On-Hand) - (Total Allocated) + (Incoming POs).
The Commercial API queries Redis in O(1) time.
Asynchronous Architecture: The Post Goods Issue (PGI)
When a Logistics Manager clicks "Dispatch" on a Shipment, massive database transactions are triggered across boundaries:
It must traverse the outbound_deliveries attached to the shipment.
It must query the WMS to deduct the physical inventory_positions matching the packed_lpn_id.
It must evaluate Incoterms (e.g., if EXW, immediately trigger Revenue Recognition via the Subledger Bridge).
Cloud Architect Warning: Executing a PGI synchronously will cause HTTP timeout errors (504 Gateway Timeout) on the GCP Load Balancer because the Subledger Bridge and WMS deduction can take several seconds.
Mandatory Django Implementation Pattern:
# API View (Synchronous Boundary)
def dispatch_shipment(request, shipment_id):
    shipment = Shipment.objects.get(pk=shipment_id)
    shipment.status = 'STAGED' # Intermediate status
    shipment.save()
    
    # Fire and Forget
    celery_app.send_task('com.tasks.execute_pgi', args=[shipment_id])
    
    return Response({"status": "Dispatch Queued", "job_id": ...}, status=202)

# Celery Worker (Asynchronous Boundary)
@celery_app.task(bind=True)
def execute_pgi(self, shipment_id):
    with transaction.atomic():
        # 1. Lock Shipment
        shipment = Shipment.objects.select_for_update().get(pk=shipment_id)
        
        # 2. Iterate deliveries, deduct wms.inventory_positions via Subledger Bridge
        # 3. Update Statuses to DISPATCHED / SHIPPED
        # 4. Trigger Finance Event


Financial & Compliance: The "Scorekeeper" Layer
This document establishes the physical, relational, and behavioral blueprints for the Financial & Compliance layer.
In a true enterprise ERP, the General Ledger (GL) is never a bottleneck for operational throughput. To ensure sub-100ms response times for warehouse scanners and shop-floor machines, operational transactions do not post Journal Entries synchronously. Instead, this architecture enforces the Subledger Bridge pattern—a strictly asynchronous, queue-based mechanism that translates physical movements into financial realities while enforcing unbreakable DB-level double-entry auditing.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Operational Execution (Synchronous)
        WMS[WMS: Post Goods Issue]
        MES[MES: Material Consumption]
        Proc[Procurement: Goods Receipt]
    end

    subgraph GCP VPC Internal Network
        subgraph Cloud Memorystore
            Redis[(Redis: Subledger Event Queue)]
        end

        subgraph Serverless Compute GAE
            Celery[Celery: Subledger Bridge Worker]
            Django[Django: Finance & Period Close API]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaFin[Schema: fin]
            SchemaPlatform[Schema: platform]
            
            TriggerZeroSum[[Trigger: Double-Entry Zero-Sum]]
            TriggerImmutable[[Trigger: Ledger Immutability]]
        end
    end

    %% Execution Flow
    WMS -->|1. Fire Event| Redis
    MES -->|1. Fire Event| Redis
    Proc -->|1. Fire Event| Redis
    
    Redis -->|2. Consume Event| Celery
    Celery -->|3. Evaluate Cost & Rules| SchemaPlatform
    Celery -->|4. Post Balanced JE| SchemaFin
    SchemaFin --> TriggerZeroSum
    SchemaFin --> TriggerImmutable


2. Entity Relationship Diagram (Physical Data Model)
This schema defines the absolute truth of financial value. The je_headers and je_lines represent the immutable ledger.
erDiagram
    "fin.gl_accounts" {
        UUID account_id PK
        VARCHAR account_number "UNIQUE (e.g., '1000')"
        VARCHAR account_class "ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE"
        VARCHAR global_name "VARCHAR(255)"
        BOOLEAN reconciliation_flag "TRUE = Auto-post only"
    }

    "fin.je_headers" {
        UUID je_id PK
        UUID legal_entity_node_id FK "References platform.nodes"
        VARCHAR source_module "WMS, MES, COM, MANUAL"
        UUID source_document_id "Polymorphic UUID (e.g., Shipment ID)"
        DATE posting_date 
        VARCHAR currency "CHAR(3)"
        VARCHAR status "DRAFT, POSTED, REVERSED"
        UUID created_by FK "References platform.users"
        UUID approved_by FK "References platform.users"
    }

    "fin.je_lines" {
        UUID je_line_id PK
        UUID je_id FK "References fin.je_headers"
        UUID account_id FK "References fin.gl_accounts"
        UUID cost_center_node_id FK "References platform.nodes"
        DECIMAL debit_amount "DECIMAL(19,4)"
        DECIMAL credit_amount "DECIMAL(19,4)"
    }

    "fin.tax_compliance_rules" {
        UUID rule_id PK
        UUID jurisdiction_node_id FK "References platform.nodes"
        VARCHAR tax_type "VAT, SALES_TAX, WITHHOLDING"
        DECIMAL effective_rate_pct "DECIMAL(7,4)"
        UUID liability_account_id FK "References fin.gl_accounts"
    }

    "fin.je_headers" ||--o{ "fin.je_lines" : "contains"
    "fin.gl_accounts" ||--o{ "fin.je_lines" : "allocates to"
    "platform.nodes" ||--o{ "fin.je_lines" : "incurs cost/profit"
    "fin.gl_accounts" ||--o{ "fin.tax_compliance_rules" : "parks liability"


3. Physical Database Schema (PostgreSQL DDL)
Financial amounts are strictly enforced as DECIMAL(19,4) to prevent any floating-point truncation.
CREATE SCHEMA IF NOT EXISTS fin;

-- =========================================================================
-- TABLE: fin.gl_accounts (Chart of Accounts)
-- =========================================================================
CREATE TABLE fin.gl_accounts (
    account_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    account_number VARCHAR(50) UNIQUE NOT NULL,
    account_class VARCHAR(50) NOT NULL,
    global_name VARCHAR(255) NOT NULL,
    reconciliation_flag BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT chk_account_class 
        CHECK (account_class IN ('ASSET', 'LIABILITY', 'EQUITY', 'REVENUE', 'EXPENSE'))
);

CREATE INDEX idx_gl_class ON fin.gl_accounts (account_class);

-- =========================================================================
-- TABLE: fin.je_headers (The Financial Event)
-- =========================================================================
CREATE TABLE fin.je_headers (
    je_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    legal_entity_node_id UUID NOT NULL, -- The specific balance sheet owner
    source_module VARCHAR(30) NOT NULL,
    source_document_id UUID, -- Polymorphic reference for Audit Trail
    posting_date DATE NOT NULL,
    currency CHAR(3) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_by UUID NOT NULL, -- SoD Tracking
    approved_by UUID,         -- SoD Tracking
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_je_legal_entity FOREIGN KEY (legal_entity_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    
    CONSTRAINT chk_je_status CHECK (status IN ('DRAFT', 'POSTED', 'REVERSED')),
    CONSTRAINT chk_je_source CHECK (source_module IN ('WMS', 'MES', 'COM', 'PROC', 'MANUAL', 'SYSTEM'))
);

CREATE INDEX idx_je_legal_entity ON fin.je_headers (legal_entity_node_id);
CREATE INDEX idx_je_posting_date ON fin.je_headers (posting_date);
CREATE INDEX idx_je_source_doc ON fin.je_headers (source_document_id) WHERE source_document_id IS NOT NULL;

-- =========================================================================
-- TABLE: fin.je_lines (The Debits & Credits)
-- =========================================================================
CREATE TABLE fin.je_lines (
    je_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    je_id UUID NOT NULL,
    account_id UUID NOT NULL,
    cost_center_node_id UUID, -- Nullable for balance sheet accounts, required for P&L
    debit_amount DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (debit_amount >= 0),
    credit_amount DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (credit_amount >= 0),

    CONSTRAINT fk_jel_header FOREIGN KEY (je_id) REFERENCES fin.je_headers(je_id) ON DELETE CASCADE,
    CONSTRAINT fk_jel_account FOREIGN KEY (account_id) REFERENCES fin.gl_accounts(account_id) ON DELETE RESTRICT,
    CONSTRAINT fk_jel_cost_center FOREIGN KEY (cost_center_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,

    -- A line must be strictly a Debit OR a Credit, never both, never neither.
    CONSTRAINT chk_debit_or_credit 
        CHECK ((debit_amount > 0 AND credit_amount = 0) OR (credit_amount > 0 AND debit_amount = 0))
);

CREATE INDEX idx_jel_je_id ON fin.je_lines (je_id);
CREATE INDEX idx_jel_account_cost_center ON fin.je_lines (account_id, cost_center_node_id);

-- =========================================================================
-- TABLE: fin.tax_compliance_rules (The Regulatory Engine)
-- =========================================================================
CREATE TABLE fin.tax_compliance_rules (
    rule_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    jurisdiction_node_id UUID NOT NULL, -- Regional or Legal Entity Node
    tax_type VARCHAR(50) NOT NULL,
    effective_rate_pct DECIMAL(7,4) NOT NULL CHECK (effective_rate_pct >= 0 AND effective_rate_pct <= 100),
    liability_account_id UUID NOT NULL,
    
    CONSTRAINT fk_tax_node FOREIGN KEY (jurisdiction_node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT fk_tax_account FOREIGN KEY (liability_account_id) REFERENCES fin.gl_accounts(account_id) ON DELETE RESTRICT,
    
    CONSTRAINT chk_tax_type CHECK (tax_type IN ('VAT', 'SALES_TAX', 'WITHHOLDING'))
);


4. Database-Level Enforcement of Business Rules
Rule 1: The Law of Double-Entry (Zero-Sum Enforcement)
A Journal Entry cannot be moved to POSTED status unless Total Debits exactly equal Total Credits.
CREATE OR REPLACE FUNCTION fin.fn_trg_enforce_zero_sum()
RETURNS TRIGGER AS $$
DECLARE
    v_total_debits DECIMAL(19,4);
    v_total_credits DECIMAL(19,4);
BEGIN
    IF OLD.status != 'POSTED' AND NEW.status = 'POSTED' THEN
        
        SELECT COALESCE(SUM(debit_amount), 0), COALESCE(SUM(credit_amount), 0)
        INTO v_total_debits, v_total_credits
        FROM fin.je_lines
        WHERE je_id = NEW.je_id;

        IF v_total_debits != v_total_credits THEN
            RAISE EXCEPTION 'Double-Entry Violation: Cannot post JE %. Debits (%) do not equal Credits (%).', 
                NEW.je_id, v_total_debits, v_total_credits;
        END IF;

        IF v_total_debits = 0 THEN
            RAISE EXCEPTION 'Empty Ledger Violation: Cannot post a JE with zero financial value.';
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_je_zero_sum
BEFORE UPDATE OF status ON fin.je_headers
FOR EACH ROW
EXECUTE FUNCTION fin.fn_trg_enforce_zero_sum();

Rule 2: Strict Immutability of Posted Ledgers
Once posted, a Journal Entry is mathematically sealed. It cannot be altered or deleted.
CREATE OR REPLACE FUNCTION fin.fn_trg_enforce_ledger_immutability()
RETURNS TRIGGER AS $$
DECLARE
    v_header_status VARCHAR;
BEGIN
    -- Check Header edits
    IF TG_TABLE_NAME = 'je_headers' THEN
        IF OLD.status = 'POSTED' THEN
            -- Only allow transition from POSTED to REVERSED (which flags it, but data remains intact)
            IF NEW.status NOT IN ('POSTED', 'REVERSED') OR OLD.posting_date != NEW.posting_date OR OLD.currency != NEW.currency THEN
                RAISE EXCEPTION 'Immutability Lock: Cannot modify core fields of a POSTED Journal Entry.';
            END IF;
        END IF;
        RETURN NEW;
    END IF;

    -- Check Line edits/deletes
    IF TG_TABLE_NAME = 'je_lines' THEN
        IF TG_OP = 'DELETE' THEN
            SELECT status INTO v_header_status FROM fin.je_headers WHERE je_id = OLD.je_id;
        ELSE
            SELECT status INTO v_header_status FROM fin.je_headers WHERE je_id = NEW.je_id;
        END IF;

        IF v_header_status = 'POSTED' THEN
            RAISE EXCEPTION 'Immutability Lock: Cannot add, edit, or delete lines on a POSTED Journal Entry.';
        END IF;

        IF TG_OP = 'DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_je_headers_immutability BEFORE UPDATE ON fin.je_headers FOR EACH ROW EXECUTE FUNCTION fin.fn_trg_enforce_ledger_immutability();
CREATE TRIGGER trg_je_lines_immutability BEFORE UPDATE OR DELETE ON fin.je_lines FOR EACH ROW EXECUTE FUNCTION fin.fn_trg_enforce_ledger_immutability();

Rule 3: Subledger Control Lock
You cannot post a manual Journal Entry directly to a Reconciliation Account (e.g., Inventory Valuation). It must come from the system.
CREATE OR REPLACE FUNCTION fin.fn_trg_enforce_subledger_lock()
RETURNS TRIGGER AS $$
DECLARE
    v_is_reconciliation BOOLEAN;
    v_source_module VARCHAR;
BEGIN
    -- Look up the account flag
    SELECT reconciliation_flag INTO v_is_reconciliation 
    FROM fin.gl_accounts WHERE account_id = NEW.account_id;

    IF v_is_reconciliation THEN
        -- Look up the header source
        SELECT source_module INTO v_source_module 
        FROM fin.je_headers WHERE je_id = NEW.je_id;

        IF v_source_module = 'MANUAL' THEN
            RAISE EXCEPTION 'Subledger Control Lock: Account % is a Reconciliation Account. Manual Journal Entries are strictly prohibited.', NEW.account_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_je_lines_subledger_lock
BEFORE INSERT OR UPDATE OF account_id ON fin.je_lines
FOR EACH ROW
EXECUTE FUNCTION fin.fn_trg_enforce_subledger_lock();


5. Architectural Directives for the Application Layer
Concurrency & Performance: The Subledger Bridge (Celery)
The process of evaluating standard costs, applying exchange rates, and posting fin.je_headers and fin.je_lines is computationally expensive.
Cloud Architect Directive:
When a WMS operator triggers a Goods Receipt (Procurement) or a PGI (Logistics), the Django API must NOT instantiate the Journal Entry synchronously.
The operational API commits its local schema changes (e.g., wms.inventory_positions), pushes an event payload to Redis, and returns 200 OK to the scanner.
A dedicated Celery queue (queue='finance_bridge') consumes the event, traverses the platform.nodes hierarchy to find the closest Cost Center, creates the JE, and flips it to POSTED.
Security Directive: Segregation of Duties (SOX Compliance)
To pass global financial audits, the system must enforce Segregation of Duties. A user cannot approve their own manual Journal Entry.
Django Implementation Logic:
# Django application layer logic enforcing SoD
def approve_journal_entry(request, je_id):
    je = JournalEntryHeader.objects.get(pk=je_id)
    
    if je.source_module == 'MANUAL':
        if je.created_by == request.user.id:
            raise PermissionDenied(
                "SOX Compliance Violation: The creator of a Manual Journal Entry cannot be the approver."
            )
            
    je.status = 'POSTED'
    je.approved_by = request.user.id
    je.save() # Will trigger PostgreSQL trg_je_zero_sum


Maintenance & Asset Management (CMMS): The "Infrastructure" Layer
This document establishes the physical, relational, and behavioral blueprints for the Maintenance & Asset Management (CMMS) module.
In an industrial ERP, assets are not static ledgers; they are living machines that degrade, break, and consume resources. The architectural challenge here is managing the Operational Interlock. When an asset undergoes maintenance, it directly impacts MES production capacity and consumes WMS inventory (MRO spares). We will leverage strict cross-schema triggers to mathematically guarantee that production cannot occur on a locked-out machine, and enforce hierarchical inheritance so that when a parent assembly (e.g., a Conveyor) goes down, all child components (e.g., Motors, Belts) inherit the downtime.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Shop Floor / Facilities
        IoT[IoT Sensors / PLC Meters]
        TechTablet[Technician Mobile Tablet]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            DjangoAPI[Django CMMS API]
            Celery[Celery: PM Auto-Generator & Subledger]
        end

        subgraph Cloud Memorystore
            RedisCache[(Redis: Asset State / Meter Cache)]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaCMMS[Schema: cmms]
            SchemaMES[Schema: mes]
            SchemaWMS[Schema: wms]
            SchemaPlatform[Schema: platform]

            SchemaCMMS -->|1. Interlock Trigger| SchemaMES
            SchemaCMMS -->|2. Downtime Cascade| SchemaCMMS
            
            TriggerMonotonic[[Trigger: Meter Monotonicity]]
            TriggerMonotonic --> SchemaCMMS
        end
    end

    IoT -->|1. High-Freq Meter Read| DjangoAPI
    DjangoAPI -->|2. Buffer| RedisCache
    RedisCache -->|3. Flush to DB| SchemaCMMS
    TechTablet -->|4. Start MWO (Lockout)| DjangoAPI
    DjangoAPI -->|5. Update MWO & Lock MES| SchemaCMMS


2. Entity Relationship Diagram (Physical Data Model)
To support Asset Lineage and swap-outs, the cmms.assets table utilizes a self-referencing hierarchy, mirroring the Global Layer's Node architecture.
erDiagram
    "cmms.assets" {
        UUID asset_id PK
        UUID parent_asset_id FK "Recursive (Child Assets)"
        UUID node_id FK "References platform.nodes"
        UUID work_center_id FK "References mes.work_centers (Nullable)"
        VARCHAR asset_class "MACHINERY, VEHICLE, HVAC"
        VARCHAR status "OPERATIONAL, DEGRADED, DOWN, DECOMMISSIONED"
        DECIMAL capitalized_value "DECIMAL(19,4)"
    }

    "cmms.asset_meters" {
        UUID meter_id PK
        UUID asset_id FK "References cmms.assets"
        VARCHAR meter_type "HOURS, CYCLES, ODOMETER"
        DECIMAL current_reading "DECIMAL(19,4)"
        TIMESTAMPTZ last_read_at 
    }

    "cmms.maintenance_plans" {
        UUID plan_id PK
        UUID asset_id FK "References cmms.assets"
        VARCHAR trigger_type "CALENDAR, METER"
        DECIMAL trigger_interval "Numeric interval"
        UUID standard_bom_id FK "References eng.bom_headers (Spares)"
    }

    "cmms.mwos" {
        UUID mwo_id PK
        UUID asset_id FK "References cmms.assets"
        VARCHAR mwo_type "PREVENTIVE, CORRECTIVE, OVERHAUL"
        BOOLEAN downtime_required 
        VARCHAR status "OPEN, WAITING_PARTS, IN_PROGRESS, COMPLETED"
        UUID safety_signature_id FK "References platform.users"
        DECIMAL total_cost "DECIMAL(19,4)"
    }

    "cmms.mwo_transactions" {
        UUID transaction_id PK
        UUID mwo_id FK "References cmms.mwos"
        UUID item_id FK "References mdm.items (Spare Part)"
        DECIMAL labor_hours "DECIMAL(19,4)"
        VARCHAR failure_code "e.g., MOTOR_BURNOUT"
    }

    "cmms.assets" ||--o{ "cmms.assets" : "contains"
    "cmms.assets" ||--o{ "cmms.asset_meters" : "tracked by"
    "cmms.assets" ||--o{ "cmms.maintenance_plans" : "governed by"
    "cmms.assets" ||--o{ "cmms.mwos" : "repaired via"
    "cmms.mwos" ||--o{ "cmms.mwo_transactions" : "logs"


3. Physical Database Schema (PostgreSQL DDL)
We isolate Maintenance into the cmms schema. Notice the explicit CHECK constraints on financial and meter values to prevent negative readings or costs.
CREATE SCHEMA IF NOT EXISTS cmms;

-- =========================================================================
-- TABLE: cmms.assets (The Physical Equipment)
-- =========================================================================
CREATE TABLE cmms.assets (
    asset_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    parent_asset_id UUID,
    node_id UUID NOT NULL, -- Physical location
    work_center_id UUID,   -- MES linkage (if this asset powers a Work Center)
    asset_class VARCHAR(50) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'OPERATIONAL',
    capitalized_value DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (capitalized_value >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_asset_parent FOREIGN KEY (parent_asset_id) REFERENCES cmms.assets(asset_id) ON DELETE RESTRICT,
    CONSTRAINT fk_asset_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_asset_wc FOREIGN KEY (work_center_id) REFERENCES mes.work_centers(node_id) ON DELETE SET NULL,

    CONSTRAINT chk_asset_class CHECK (asset_class IN ('MACHINERY', 'FLEET_VEHICLE', 'HVAC', 'FACILITY')),
    CONSTRAINT chk_asset_status CHECK (status IN ('OPERATIONAL', 'DEGRADED', 'DOWN', 'DECOMMISSIONED'))
);

CREATE INDEX idx_assets_node ON cmms.assets (node_id);
CREATE INDEX idx_assets_wc ON cmms.assets (work_center_id) WHERE work_center_id IS NOT NULL;

-- =========================================================================
-- TABLE: cmms.asset_meters (The Wear & Tear Trackers)
-- =========================================================================
CREATE TABLE cmms.asset_meters (
    meter_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    meter_type VARCHAR(50) NOT NULL,
    current_reading DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (current_reading >= 0),
    last_read_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_meter_asset FOREIGN KEY (asset_id) REFERENCES cmms.assets(asset_id) ON DELETE CASCADE
);

-- =========================================================================
-- TABLE: cmms.maintenance_plans (The Preventive Rules)
-- =========================================================================
CREATE TABLE cmms.maintenance_plans (
    plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    trigger_type VARCHAR(30) NOT NULL,
    trigger_interval DECIMAL(19,4) NOT NULL CHECK (trigger_interval > 0),
    standard_bom_id UUID, -- Links to eng.bom_headers for required MRO spares
    
    CONSTRAINT fk_plan_asset FOREIGN KEY (asset_id) REFERENCES cmms.assets(asset_id) ON DELETE CASCADE,
    CONSTRAINT chk_trigger_type CHECK (trigger_type IN ('CALENDAR_DAYS', 'METER_UNITS'))
);

-- =========================================================================
-- TABLE: cmms.mwos (Maintenance Work Orders)
-- =========================================================================
CREATE TABLE cmms.mwos (
    mwo_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    asset_id UUID NOT NULL,
    mwo_type VARCHAR(30) NOT NULL,
    downtime_required BOOLEAN NOT NULL DEFAULT FALSE,
    status VARCHAR(30) NOT NULL DEFAULT 'OPEN',
    safety_signature_id UUID, -- Captured user ID during LOTO (Lockout/Tagout)
    total_cost DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (total_cost >= 0),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ,

    CONSTRAINT fk_mwo_asset FOREIGN KEY (asset_id) REFERENCES cmms.assets(asset_id) ON DELETE RESTRICT,
    
    CONSTRAINT chk_mwo_type CHECK (mwo_type IN ('PREVENTIVE', 'CORRECTIVE', 'PREDICTIVE', 'OVERHAUL', 'SAFETY')),
    CONSTRAINT chk_mwo_status CHECK (status IN ('OPEN', 'WAITING_PARTS', 'IN_PROGRESS', 'COMPLETED', 'CANCELLED'))
);

CREATE INDEX idx_mwos_status ON cmms.mwos (status);
CREATE INDEX idx_mwos_asset ON cmms.mwos (asset_id);

-- =========================================================================
-- TABLE: cmms.mwo_transactions (The Execution Log)
-- =========================================================================
CREATE TABLE cmms.mwo_transactions (
    transaction_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    mwo_id UUID NOT NULL,
    item_id UUID, -- Consumed spare part
    labor_hours DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (labor_hours >= 0),
    failure_code VARCHAR(100),
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_mwot_mwo FOREIGN KEY (mwo_id) REFERENCES cmms.mwos(mwo_id) ON DELETE CASCADE
);


4. Database-Level Enforcement of Business Rules
Rule 1: The MES-CMMS Interlock (Cross-Schema Capacity Zeroing)
If a machine requires downtime for maintenance, the MES module must instantly be blocked from scheduling or executing Work Orders against it. This trigger enforces the mathematical link between CMMS status and MES capacity.
CREATE OR REPLACE FUNCTION cmms.fn_trg_enforce_mes_interlock()
RETURNS TRIGGER AS $$
DECLARE
    v_work_center_id UUID;
BEGIN
    -- 1. Check if the MWO requires downtime and is moving to IN_PROGRESS
    IF NEW.downtime_required = TRUE AND OLD.status != 'IN_PROGRESS' AND NEW.status = 'IN_PROGRESS' THEN
        
        -- 2. Find the linked MES Work Center
        SELECT work_center_id INTO v_work_center_id 
        FROM cmms.assets WHERE asset_id = NEW.asset_id;

        -- 3. If linked to production, physically alter the MES capacity to zero to halt scheduling
        IF v_work_center_id IS NOT NULL THEN
            UPDATE mes.work_centers 
            SET capacity_hrs_day = 0 
            WHERE node_id = v_work_center_id;
            
            -- Cascade Asset status to DOWN
            UPDATE cmms.assets SET status = 'DOWN' WHERE asset_id = NEW.asset_id;
        END IF;

    -- 4. Restore Capacity upon Completion
    ELSIF OLD.status = 'IN_PROGRESS' AND NEW.status = 'COMPLETED' AND OLD.downtime_required = TRUE THEN
        SELECT work_center_id INTO v_work_center_id 
        FROM cmms.assets WHERE asset_id = NEW.asset_id;

        IF v_work_center_id IS NOT NULL THEN
            -- Revert Asset Status
            UPDATE cmms.assets SET status = 'OPERATIONAL' WHERE asset_id = NEW.asset_id;
            -- Note: In a full implementation, the previous capacity is restored from a historical log.
            -- Here we restore a baseline 24hr or trigger a scheduler recalculation.
            UPDATE mes.work_centers SET capacity_hrs_day = 24 WHERE node_id = v_work_center_id;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_mwo_mes_interlock
BEFORE UPDATE OF status ON cmms.mwos
FOR EACH ROW
EXECUTE FUNCTION cmms.fn_trg_enforce_mes_interlock();

Rule 2: Meter Monotonicity
A physical machine meter (like an odometer or cycle count) can never run backwards. If a lower reading is submitted (e.g., due to a faulty PLC sensor or API retry anomaly), the database must reject it to protect PM scheduling logic.
CREATE OR REPLACE FUNCTION cmms.fn_trg_enforce_meter_monotonicity()
RETURNS TRIGGER AS $$
BEGIN
    IF NEW.current_reading < OLD.current_reading THEN
        RAISE EXCEPTION 'Monotonicity Violation: New meter reading (%) cannot be lower than the previous reading (%). If the meter was replaced, execute a Meter Swap transaction.', 
            NEW.current_reading, OLD.current_reading;
    END IF;
    
    NEW.last_read_at := CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_meter_monotonicity
BEFORE UPDATE OF current_reading ON cmms.asset_meters
FOR EACH ROW
EXECUTE FUNCTION cmms.fn_trg_enforce_meter_monotonicity();

Rule 3: Hierarchical Downtime (Parent-Child Cascade)
If a Conveyor Belt (Parent) is marked DOWN, the Motor (Child) attached to it cannot remain OPERATIONAL.
CREATE OR REPLACE FUNCTION cmms.fn_trg_cascade_asset_downtime()
RETURNS TRIGGER AS $$
BEGIN
    IF OLD.status != 'DOWN' AND NEW.status = 'DOWN' THEN
        -- Cascade the DOWN status to all immediate children
        UPDATE cmms.assets 
        SET status = 'DOWN' 
        WHERE parent_asset_id = NEW.asset_id AND status != 'DECOMMISSIONED';
    END IF;
    
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_asset_downtime_cascade
AFTER UPDATE OF status ON cmms.assets
FOR EACH ROW
EXECUTE FUNCTION cmms.fn_trg_cascade_asset_downtime();


5. Architectural Directives for the Application Layer
Concurrency Directive: High-Frequency IoT Ingestion
If an MES machine publishes cycle counts every 5 seconds to cmms.asset_meters, updating a PostgreSQL row 17,280 times a day per machine will cause catastrophic Write-Ahead Log (WAL) bloat.
Mandatory Cloud Implementation Pattern:
IoT gateways hit a fast, stateless endpoint on GAE.
The endpoint updates an in-memory key in Google Cloud Memorystore (Redis): HINCRBY meter:uuid reading 1.
A Celery Beat periodic task runs every 15 minutes, pulls the aggregated delta from Redis, and performs a single UPDATE cmms.asset_meters query.
Only the Celery task evaluates if the new reading exceeds a cmms.maintenance_plans.trigger_interval to generate an MWO.
Security Directive: The Law of Lockout/Tagout (LOTO)
An MWO cannot be safely executed if power is still running to the machine.
The API must enforce a hard-stop block before transitioning an MWO to IN_PROGRESS if downtime_required is True:
# Conceptual Architecture Logic for LOTO Enforcement
def start_mwo(request, mwo_id):
    mwo = MWO.objects.get(pk=mwo_id)
    
    if mwo.downtime_required and not mwo.safety_signature_id:
        # Require secondary biometric or password auth
        if not verify_secondary_auth(request):
            raise SecurityException("Lockout/Tagout protocol requires digital signature before commencement.")
            
        mwo.safety_signature_id = request.user.id
        
    mwo.status = 'IN_PROGRESS'
    mwo.save() # Fires MES Interlock Trigger


Procurement & Sourcing: The "Buying" Layer
This document establishes the physical, relational, and behavioral blueprints for the Procurement & Sourcing module.
Procurement governs the financial outflow and physical inbound of the enterprise. In a distributed node architecture, sourcing is often centralized (Global Master Agreements) while execution is decentralized (Local Site Purchase Orders). This architecture leverages the Global Layer's ltree indexing to resolve pricing hierarchies in milliseconds and enforces strict cross-schema validation to prevent rogue spending and unapproved supplier risks.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph WMS Shop Floor
        Scanner[WMS Receiving Dock Scanner]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            ProcAPI[Django Procurement API]
            PricingEngine[Django Sourcing & DoA Engine]
            Celery[Celery: Subledger & Encumbrance]
        end

        subgraph Cloud Memorystore
            Redis[(Redis: Subledger Event Queue)]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaProc[Schema: proc]
            SchemaMDM[Schema: mdm]
            SchemaWMS[Schema: wms]
            SchemaPlatform[Schema: platform]

            SchemaProc -->|1. Validate Supplier/Item| SchemaMDM
            SchemaProc -->|2. Traverses Hierarchy| SchemaPlatform
            
            TriggerASL[[Trigger: ASL Validation]]
            TriggerOverReceipt[[Trigger: Over-Receipt Hard-Stop]]
            
            TriggerASL --> SchemaProc
            TriggerOverReceipt --> SchemaProc
        end
    end

    Scanner -->|1. Post Goods Receipt| ProcAPI
    ProcAPI -->|2. Mutex Lock PO Line| SchemaProc
    ProcAPI -->|3. Create Inventory| SchemaWMS
    ProcAPI -->|4. Queue GR/IR Subledger Event| Redis
    Redis -->|5. Consume| Celery


2. Entity Relationship Diagram (Physical Data Model)
This model separates internal operational demands (purchase_requisitions) from external legal commitments (po_headers) and pre-negotiated commercial rules (supplier_agreements).
erDiagram
    "proc.purchase_requisitions" {
        UUID pr_id PK
        UUID requesting_node_id FK "References platform.nodes"
        UUID item_id FK "References mdm.items"
        DECIMAL requested_qty "DECIMAL(19,4)"
        UUID pegged_demand_id "Polymorphic (WO, SO)"
        VARCHAR approval_status "DRAFT, APPROVED, CONVERTED"
    }

    "proc.approved_supplier_list" {
        UUID asl_id PK
        UUID supplier_bp_id FK "References mdm.business_partners"
        UUID item_id FK "References mdm.items"
        UUID node_id FK "References platform.nodes"
        VARCHAR status "ACTIVE, REVOKED"
    }

    "proc.supplier_agreements" {
        UUID agreement_id PK
        UUID supplier_bp_id FK "References mdm.business_partners"
        UUID valid_node_id FK "References platform.nodes"
        UUID item_id FK "References mdm.items"
        DECIMAL unit_price "DECIMAL(19,4)"
        DECIMAL over_receipt_tol_pct "DECIMAL(5,4)"
        DATERANGE effectivity_dates 
    }

    "proc.po_headers" {
        UUID po_id PK
        UUID purchasing_node_id FK "References platform.nodes"
        UUID supplier_bp_id FK "References mdm.business_partners"
        DECIMAL total_po_value "DECIMAL(19,4)"
        VARCHAR incoterms "EXW, DDP, FOB"
        VARCHAR status "DRAFT, ISSUED, PARTIAL_RECEIPT, CLOSED"
    }

    "proc.po_lines" {
        UUID po_line_id PK
        UUID po_id FK "References proc.po_headers"
        UUID receiving_node_id FK "References platform.nodes"
        UUID item_id FK "References mdm.items"
        DECIMAL ordered_qty "DECIMAL(19,4)"
        DECIMAL received_qty "DECIMAL(19,4)"
        DECIMAL unit_price "DECIMAL(19,4)"
        DATE promised_date 
    }

    "platform.nodes" ||--o{ "proc.purchase_requisitions" : "requests"
    "proc.supplier_agreements" ||--o{ "proc.po_lines" : "dictates price"
    "proc.po_headers" ||--o{ "proc.po_lines" : "commits"
    "proc.approved_supplier_list" ||--o{ "proc.po_headers" : "governs"


3. Physical Database Schema (PostgreSQL DDL)
We establish the proc schema. Pricing agreements use daterange to allow precise temporal validity enforcement, and numeric percentages are constrained securely.
CREATE SCHEMA IF NOT EXISTS proc;

-- =========================================================================
-- TABLE: proc.purchase_requisitions (Internal Demand)
-- =========================================================================
CREATE TABLE proc.purchase_requisitions (
    pr_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    requesting_node_id UUID NOT NULL,
    item_id UUID NOT NULL,
    requested_qty DECIMAL(19,4) NOT NULL CHECK (requested_qty > 0),
    pegged_demand_id UUID, -- E.g., tied to an MES Work Order ID
    approval_status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pr_node FOREIGN KEY (requesting_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_pr_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT,
    CONSTRAINT chk_pr_status CHECK (approval_status IN ('DRAFT', 'PENDING_APPROVAL', 'APPROVED', 'REJECTED', 'CONVERTED'))
);

-- =========================================================================
-- TABLE: proc.approved_supplier_list (ASL)
-- =========================================================================
CREATE TABLE proc.approved_supplier_list (
    asl_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_bp_id UUID NOT NULL,
    item_id UUID NOT NULL,
    node_id UUID NOT NULL, -- Defines at what level this supplier is approved (Global vs Local)
    status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',

    CONSTRAINT fk_asl_bp FOREIGN KEY (supplier_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE CASCADE,
    CONSTRAINT fk_asl_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE CASCADE,
    CONSTRAINT fk_asl_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT chk_asl_status CHECK (status IN ('ACTIVE', 'REVOKED')),
    
    -- Prevent duplicate ASL definitions for the same BP/Item at the same Node
    CONSTRAINT uq_asl_bp_item_node UNIQUE (supplier_bp_id, item_id, node_id)
);

CREATE INDEX idx_asl_lookup ON proc.approved_supplier_list (supplier_bp_id, item_id);

-- =========================================================================
-- TABLE: proc.supplier_agreements (Sourcing Contracts)
-- =========================================================================
CREATE TABLE proc.supplier_agreements (
    agreement_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    supplier_bp_id UUID NOT NULL,
    valid_node_id UUID NOT NULL, -- The node hierarchy level this pricing applies to
    item_id UUID NOT NULL,
    unit_price DECIMAL(19,4) NOT NULL CHECK (unit_price >= 0),
    over_receipt_tol_pct DECIMAL(5,4) NOT NULL DEFAULT 0.0000 CHECK (over_receipt_tol_pct >= 0),
    effectivity_dates daterange NOT NULL,

    CONSTRAINT fk_sa_bp FOREIGN KEY (supplier_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE CASCADE,
    CONSTRAINT fk_sa_node FOREIGN KEY (valid_node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT fk_sa_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE CASCADE
);

CREATE INDEX idx_sa_gist ON proc.supplier_agreements USING gist (effectivity_dates);

-- =========================================================================
-- TABLE: proc.po_headers (External Commitments)
-- =========================================================================
CREATE TABLE proc.po_headers (
    po_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    purchasing_node_id UUID NOT NULL,
    supplier_bp_id UUID NOT NULL,
    total_po_value DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    incoterms VARCHAR(3) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_po_node FOREIGN KEY (purchasing_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_po_supplier FOREIGN KEY (supplier_bp_id) REFERENCES mdm.business_partners(bp_id) ON DELETE RESTRICT,
    CONSTRAINT chk_po_status CHECK (status IN ('DRAFT', 'ISSUED', 'PARTIAL_RECEIPT', 'RECEIVED', 'CLOSED'))
);

CREATE INDEX idx_po_status ON proc.po_headers (status);

-- =========================================================================
-- TABLE: proc.po_lines (Specific Deliverables)
-- =========================================================================
CREATE TABLE proc.po_lines (
    po_line_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    po_id UUID NOT NULL,
    receiving_node_id UUID NOT NULL, -- Physical destination
    item_id UUID NOT NULL,
    ordered_qty DECIMAL(19,4) NOT NULL CHECK (ordered_qty > 0),
    received_qty DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (received_qty >= 0),
    unit_price DECIMAL(19,4) NOT NULL CHECK (unit_price >= 0),
    promised_date DATE NOT NULL,

    CONSTRAINT fk_pol_po FOREIGN KEY (po_id) REFERENCES proc.po_headers(po_id) ON DELETE CASCADE,
    CONSTRAINT fk_pol_node FOREIGN KEY (receiving_node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT fk_pol_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE RESTRICT
);


4. Database-Level Enforcement of Business Rules
Rule 1: The Law of the Approved Supplier List (ASL)
A PO cannot be generated unless the supplier is vetted and approved for that specific item at that specific Node (or inherited from a parent node, like Global HQ).
CREATE OR REPLACE FUNCTION proc.fn_trg_enforce_asl()
RETURNS TRIGGER AS $$
DECLARE
    v_purchasing_node_id UUID;
    v_is_approved BOOLEAN;
BEGIN
    -- Get the purchasing node for this line's header
    SELECT purchasing_node_id INTO v_purchasing_node_id 
    FROM proc.po_headers WHERE po_id = NEW.po_id;

    -- Traverse the ltree to see if an ACTIVE ASL record exists for this BP/Item at this node OR any ancestor
    SELECT EXISTS (
        SELECT 1 
        FROM proc.approved_supplier_list asl
        JOIN platform.nodes asl_node ON asl.node_id = asl_node.node_id
        JOIN platform.nodes po_node ON po_node.node_id = v_purchasing_node_id
        WHERE asl.supplier_bp_id = (SELECT supplier_bp_id FROM proc.po_headers WHERE po_id = NEW.po_id)
          AND asl.item_id = NEW.item_id
          AND asl.status = 'ACTIVE'
          -- Ltree operator: Is the ASL node an ancestor of (or equal to) the PO purchasing node?
          AND asl_node.lineage_path @> po_node.lineage_path
    ) INTO v_is_approved;

    IF NOT v_is_approved THEN
        RAISE EXCEPTION 'ASL Violation: Supplier is not approved to supply Item % to Node % (or its ancestors).', 
            NEW.item_id, v_purchasing_node_id;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_po_lines_asl_check
BEFORE INSERT OR UPDATE OF item_id ON proc.po_lines
FOR EACH ROW
EXECUTE FUNCTION proc.fn_trg_enforce_asl();

Rule 2: Over-Receipt Tolerance Hard-Stop
The WMS receiving dock cannot physically receive more goods than ordered unless a tolerance percentage explicitly allows it (e.g., bulk liquid chemicals where exact weights vary).
CREATE OR REPLACE FUNCTION proc.fn_trg_enforce_receipt_tolerance()
RETURNS TRIGGER AS $$
DECLARE
    v_tolerance_pct DECIMAL(5,4);
    v_max_allowable_qty DECIMAL(19,4);
BEGIN
    -- Only evaluate if quantity increased
    IF NEW.received_qty > OLD.received_qty THEN
        
        -- Find the applicable tolerance from the most specific agreement in the node hierarchy
        SELECT COALESCE(sa.over_receipt_tol_pct, 0.0000) INTO v_tolerance_pct
        FROM proc.po_headers h
        JOIN platform.nodes po_node ON h.purchasing_node_id = po_node.node_id
        LEFT JOIN platform.nodes sa_node ON TRUE
        LEFT JOIN proc.supplier_agreements sa 
            ON sa.supplier_bp_id = h.supplier_bp_id 
            AND sa.item_id = NEW.item_id 
            AND sa.valid_node_id = sa_node.node_id
            AND CURRENT_DATE <@ sa.effectivity_dates
        WHERE h.po_id = NEW.po_id
          AND sa_node.lineage_path @> po_node.lineage_path
        ORDER BY nlevel(sa_node.lineage_path) DESC
        LIMIT 1;

        -- Default to 0 if no agreement found
        IF v_tolerance_pct IS NULL THEN v_tolerance_pct := 0.0000; END IF;

        v_max_allowable_qty := NEW.ordered_qty * (1 + v_tolerance_pct);

        IF NEW.received_qty > v_max_allowable_qty THEN
            RAISE EXCEPTION 'Over-Receipt Hard-Stop: Attempting to receive % units. Max allowable based on % tolerance is %.', 
                NEW.received_qty, (v_tolerance_pct * 100), v_max_allowable_qty;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_po_lines_tolerance_check
BEFORE UPDATE OF received_qty ON proc.po_lines
FOR EACH ROW
EXECUTE FUNCTION proc.fn_trg_enforce_receipt_tolerance();


5. Architectural Directives for the Application Layer
Concurrency Directive: The WMS Goods Receipt (GR) Race Condition
When trucks arrive, multiple warehouse workers might scan pallets off the same Purchase Order line simultaneously.
Mandatory Cloud Architecture Pattern:
Updating proc.po_lines.received_qty during a WMS scan must be protected by a strict database lock to prevent lost updates.
# Conceptual execution flow for a WMS Goods Receipt API
with transaction.atomic():
    # 1. Lock the PO Line specifically
    po_line = POLine.objects.select_for_update().get(pk=scanned_po_line_id)
    
    # 2. Update Procurement tracking
    po_line.received_qty += scanned_pallet_qty
    po_line.save() # Will trigger Over-Receipt DB validation
    
    # 3. Create physical WMS inventory position
    InventoryPosition.objects.create(...)
    
    # 4. Fire Async Event for Finance
    celery_app.send_task('fin.tasks.post_gr_ir_subledger', kwargs={
        "po_id": str(po_line.po_id),
        "value": float(scanned_pallet_qty * po_line.unit_price)
    })

Financial Directive: Delegation of Authority (DoA) Traversal
A Purchase Requisition (PR) or PO cannot simply be approved by anyone. The Django backend must utilize the Node Hierarchy to dynamically resolve the approval chain.
Algorithm requirement:
Look up the Purchasing Node ID.
Find the user with a Node Access Assignment role of PROCUREMENT_MANAGER for that node.
Check their configured DoA financial limit against the Total PO Value.
If the value exceeds their limit, query platform.nodes for the parent_node_id and repeat until an authorized executive is found at a higher structural level (e.g., Regional VP or Global CFO).

Quality Assurance & Control (QMS): The "Gatekeeper" Layer
This document establishes the physical, relational, and behavioral blueprints for the Quality Assurance & Control (QMS) module.
In highly regulated environments (e.g., FDA 21 CFR Part 11, ISO-9001), QMS is the ultimate authority. It acts as an event-driven overlay that silences the execution of WMS, MES, and Procurement operations until strict compliance conditions are met. This architecture enforces Cross-Schema Veto Power, utilizing database triggers to mathematically lock inventory and halt production routing without requiring the application layer to write complex, error-prone verification loops.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Quality Control Lab / Shop Floor
        QA_Tech[QA Technician Tablet / LIMS]
        Equip[Connected Digital Calipers / Scales]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            QMSApi[Django QMS API]
            RuleEngine[Django QMS Rule Engine]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaQMS[Schema: qms]
            SchemaWMS[Schema: wms]
            SchemaMES[Schema: mes]
            SchemaCMMS[Schema: cmms]
            
            TriggerWMSLock[[Trigger: WMS QA Hold Veto]]
            TriggerEquip[[Trigger: CMMS Calibration Check]]
            TriggerMESBlock[[Trigger: MES Sequence Block]]
            
            SchemaQMS --> TriggerWMSLock
            TriggerWMSLock -->|Force Status| SchemaWMS
            
            SchemaQMS --> TriggerEquip
            TriggerEquip -->|Validate Tool| SchemaCMMS
        end
    end

    Equip -->|1. Transmit Data| QMSApi
    QA_Tech -->|2. Dual-Auth Submit| QMSApi
    QMSApi -->|3. Evaluate Limits| RuleEngine
    RuleEngine -->|4. Post Usage Decision| SchemaQMS
    SchemaQMS -.->|5. Async NCR Gen| QMSApi


2. Entity Relationship Diagram (Physical Data Model)
To support structured testing, we must add the physical inspection_results table, which bridges the abstract parameters (Characteristics) with the execution ticket (Inspection Order).
erDiagram
    "qms.inspection_plans" {
        UUID plan_id PK
        UUID node_id FK "References platform.nodes"
        UUID item_id FK "References mdm.items"
        VARCHAR trigger_event "GOODS_RECEIPT, ROUTING_STEP, DISPATCH"
        VARCHAR sample_size_rule "100_PCT, FIXED_QTY, AQL"
        VARCHAR status "DRAFT, ACTIVE, RETIRED"
    }

    "qms.inspection_characteristics" {
        UUID characteristic_id PK
        UUID plan_id FK "References qms.inspection_plans"
        VARCHAR test_type "QUANTITATIVE, QUALITATIVE"
        VARCHAR target_value "Ideal reading"
        DECIMAL lower_limit "DECIMAL(19,4)"
        DECIMAL upper_limit "DECIMAL(19,4)"
    }

    "qms.inspection_orders" {
        UUID inspection_id PK
        UUID plan_id FK "References qms.inspection_plans"
        UUID source_document_id "Polymorphic (PO, WO, Shipment)"
        VARCHAR batch_serial_id "Traced physical inventory"
        VARCHAR usage_decision "PENDING, ACCEPTED, REJECTED, CONCESSION"
        UUID inspector_user_id FK "References platform.users"
    }

    "qms.inspection_results" {
        UUID result_id PK
        UUID inspection_id FK "References qms.inspection_orders"
        UUID characteristic_id FK "References qms.inspection_characteristics"
        DECIMAL numeric_result "DECIMAL(19,4) (If Quant)"
        VARCHAR text_result "(If Qual)"
        UUID test_equipment_asset_id FK "References cmms.assets"
    }

    "qms.ncrs" {
        UUID ncr_id PK
        UUID inspection_id FK "References qms.inspection_orders"
        VARCHAR defect_code "SCRATCHED, OUT_OF_TOLERANCE, etc."
        VARCHAR disposition "SCRAP, REWORK, RTV, DOWNGRADE"
        DECIMAL financial_impact "DECIMAL(19,4)"
    }

    "qms.inspection_plans" ||--o{ "qms.inspection_characteristics" : "defines tests"
    "qms.inspection_plans" ||--o{ "qms.inspection_orders" : "spawns"
    "qms.inspection_orders" ||--o{ "qms.inspection_results" : "captures"
    "qms.inspection_characteristics" ||--o{ "qms.inspection_results" : "measured against"
    "qms.inspection_orders" ||--o| "qms.ncrs" : "triggers on failure"


3. Physical Database Schema (PostgreSQL DDL)
We establish the qms schema, strictly typed for highly regulated metric data capture.
CREATE SCHEMA IF NOT EXISTS qms;

-- =========================================================================
-- TABLE: qms.inspection_plans (The Rules)
-- =========================================================================
CREATE TABLE qms.inspection_plans (
    plan_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL,
    item_id UUID NOT NULL,
    trigger_event VARCHAR(50) NOT NULL,
    sample_size_rule VARCHAR(30) NOT NULL,
    status VARCHAR(30) NOT NULL DEFAULT 'DRAFT',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_plan_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE CASCADE,
    CONSTRAINT fk_plan_item FOREIGN KEY (item_id) REFERENCES mdm.items(item_id) ON DELETE CASCADE,
    
    CONSTRAINT chk_plan_trigger CHECK (trigger_event IN ('GOODS_RECEIPT', 'ROUTING_STEP', 'POST_PRODUCTION', 'DISPATCH')),
    CONSTRAINT chk_plan_status CHECK (status IN ('DRAFT', 'ACTIVE', 'RETIRED'))
);

CREATE INDEX idx_qms_plan_lookup ON qms.inspection_plans (item_id, trigger_event, status);

-- =========================================================================
-- TABLE: qms.inspection_characteristics (The Parameters)
-- =========================================================================
CREATE TABLE qms.inspection_characteristics (
    characteristic_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL,
    test_type VARCHAR(30) NOT NULL,
    target_value VARCHAR(255),
    lower_limit DECIMAL(19,4),
    upper_limit DECIMAL(19,4),

    CONSTRAINT fk_char_plan FOREIGN KEY (plan_id) REFERENCES qms.inspection_plans(plan_id) ON DELETE CASCADE,
    CONSTRAINT chk_test_type CHECK (test_type IN ('QUANTITATIVE', 'QUALITATIVE')),
    
    -- Ensure limits make mathematical sense if quantitative
    CONSTRAINT chk_limits CHECK (
        (test_type = 'QUALITATIVE') OR 
        (test_type = 'QUANTITATIVE' AND lower_limit IS NOT NULL AND upper_limit IS NOT NULL AND lower_limit <= upper_limit)
    )
);

-- =========================================================================
-- TABLE: qms.inspection_orders (The Execution Ticket)
-- =========================================================================
CREATE TABLE qms.inspection_orders (
    inspection_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    plan_id UUID NOT NULL,
    source_document_id UUID NOT NULL, -- The specific WMS Receipt, MES Op, or Shipment
    batch_serial_id VARCHAR(100) NOT NULL,
    usage_decision VARCHAR(30) NOT NULL DEFAULT 'PENDING',
    inspector_user_id UUID,
    decision_timestamp TIMESTAMPTZ,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_io_plan FOREIGN KEY (plan_id) REFERENCES qms.inspection_plans(plan_id) ON DELETE RESTRICT,
    CONSTRAINT chk_usage_decision CHECK (usage_decision IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CONCESSION'))
);

CREATE INDEX idx_io_source ON qms.inspection_orders (source_document_id);
CREATE INDEX idx_io_batch ON qms.inspection_orders (batch_serial_id);

-- =========================================================================
-- TABLE: qms.inspection_results (The Captured Data)
-- =========================================================================
CREATE TABLE qms.inspection_results (
    result_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id UUID NOT NULL,
    characteristic_id UUID NOT NULL,
    numeric_result DECIMAL(19,4),
    text_result VARCHAR(255),
    test_equipment_asset_id UUID, -- Links to cmms.assets to verify calibration
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_res_io FOREIGN KEY (inspection_id) REFERENCES qms.inspection_orders(inspection_id) ON DELETE CASCADE,
    CONSTRAINT fk_res_char FOREIGN KEY (characteristic_id) REFERENCES qms.inspection_characteristics(characteristic_id) ON DELETE RESTRICT,
    CONSTRAINT fk_res_asset FOREIGN KEY (test_equipment_asset_id) REFERENCES cmms.assets(asset_id) ON DELETE RESTRICT
);

-- =========================================================================
-- TABLE: qms.ncrs (Non-Conformance Reports)
-- =========================================================================
CREATE TABLE qms.ncrs (
    ncr_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    inspection_id UUID NOT NULL,
    defect_code VARCHAR(50) NOT NULL,
    disposition VARCHAR(50) NOT NULL DEFAULT 'PENDING_REVIEW',
    financial_impact DECIMAL(19,4) NOT NULL DEFAULT 0.0000,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_ncr_io FOREIGN KEY (inspection_id) REFERENCES qms.inspection_orders(inspection_id) ON DELETE RESTRICT,
    CONSTRAINT chk_disposition CHECK (disposition IN ('PENDING_REVIEW', 'SCRAP', 'REWORK', 'RETURN_TO_VENDOR', 'DOWNGRADE'))
);


4. Database-Level Enforcement of Business Rules
Rule 1: The WMS Veto Power (Cross-Schema Status Injection)
When a Usage Decision is executed, QMS exercises its "Ultimate Gatekeeper" authority over WMS. This trigger reaches across schemas to release or block inventory, rendering it mathematically invisible to the WMS Allocation Engine if rejected.
CREATE OR REPLACE FUNCTION qms.fn_trg_qms_wms_status_sync()
RETURNS TRIGGER AS $$
BEGIN
    -- Only act if the usage decision transitions from PENDING
    IF OLD.usage_decision = 'PENDING' AND NEW.usage_decision != 'PENDING' THEN
        
        -- If accepted, release QA Hold to Available
        IF NEW.usage_decision IN ('ACCEPTED', 'CONCESSION') THEN
            UPDATE wms.inventory_positions 
            SET stock_status = 'AVAILABLE' 
            WHERE batch_serial_id = NEW.batch_serial_id 
              AND stock_status = 'QA_HOLD';
              
        -- If rejected, permanently block the inventory
        ELSIF NEW.usage_decision = 'REJECTED' THEN
            UPDATE wms.inventory_positions 
            SET stock_status = 'BLOCKED' 
            WHERE batch_serial_id = NEW.batch_serial_id;
        END IF;
        
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_sync_qms_wms
AFTER UPDATE OF usage_decision ON qms.inspection_orders
FOR EACH ROW
EXECUTE FUNCTION qms.fn_trg_qms_wms_status_sync();

Rule 2: Strict Traceability of Test Equipment (CMMS Interlock)
If a QA technician uses a digital scale or caliper to record a result, the database must verify that the tool is strictly active and not currently broken/down in the CMMS module.
CREATE OR REPLACE FUNCTION qms.fn_trg_verify_test_equipment()
RETURNS TRIGGER AS $$
DECLARE
    v_asset_status VARCHAR;
BEGIN
    IF NEW.test_equipment_asset_id IS NOT NULL THEN
        SELECT status INTO v_asset_status 
        FROM cmms.assets 
        WHERE asset_id = NEW.test_equipment_asset_id;

        IF v_asset_status != 'OPERATIONAL' THEN
            RAISE EXCEPTION 'Calibration / Equipment Failure: Asset % is in % status. Cannot record QA results with degraded or out-of-calibration tools.', 
                NEW.test_equipment_asset_id, v_asset_status;
        END IF;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_verify_test_equipment
BEFORE INSERT OR UPDATE ON qms.inspection_results
FOR EACH ROW
EXECUTE FUNCTION qms.fn_trg_verify_test_equipment();

Rule 3: The MES Routing Block (Implicit Constraint)
To ensure MES respects QMS, the MES routing progression trigger (previously defined in MES) must query the QMS schema.
(Architectural Note: In practice, the mes.fn_trg_enforce_operation_sequence trigger would be appended to include: IF EXISTS (SELECT 1 FROM qms.inspection_orders WHERE source_document_id = NEW.wo_id AND usage_decision = 'PENDING') THEN RAISE EXCEPTION 'QA Hold...'; END IF;)

5. Architectural Directives for the Application Layer
Compliance Directive: 21 CFR Part 11 Electronic Signatures
The database can store the user ID, but the application layer must enforce the non-repudiation intent required by pharmaceutical and aerospace standards.
Django API Implementation Blueprint:
When an endpoint receives a payload to flip usage_decision to ACCEPTED or REJECTED, the API must explicitly demand a secondary authentication payload. A bearer token is insufficient.
# Conceptual Architecture Logic
@transaction.atomic
def execute_usage_decision(request, inspection_id):
    payload = request.data
    
    # 1. 21 CFR Part 11: Re-authenticate intent
    if not authenticate(username=request.user.username, password=payload.get('signature_password')):
        raise PermissionDenied("Electronic Signature Failed: Invalid secondary credential.")
        
    inspection = InspectionOrder.objects.select_for_update().get(pk=inspection_id)
    
    # 2. Prevent tampering
    if inspection.usage_decision != 'PENDING':
        raise ValidationError("Inspection is already locked.")
        
    inspection.usage_decision = payload.get('usage_decision')
    inspection.inspector_user_id = request.user.id
    inspection.decision_timestamp = timezone.now()
    inspection.save() # Fires WMS Veto Trigger
    
    # 3. Trigger NCR if Rejected
    if inspection.usage_decision == 'REJECTED':
        celery_app.send_task('qms.tasks.generate_ncr', args=[str(inspection.id)])

Asynchronous Architecture: Dynamic Event Listening
QMS operates silently. The qms.inspection_orders are auto-generated.
Directive: The QMS module should not tightly couple itself to WMS or MES view code. Instead, use a Pub/Sub model via Redis or Django Signals.
When WMS executes a Goods Receipt, it broadcasts event: goods_receipt_posted. A decoupled QMS worker listens, traverses the Node Hierarchy ltree to find if an ACTIVE Inspection Plan exists for that Item/Node, and if so, quietly inserts the qms.inspection_order and forces WMS inventory to QA_HOLD.

Human Capital Management (HCM): The "People" Layer
This document establishes the physical, relational, and behavioral blueprints for the Human Capital Management (HCM) module.
In a highly operational ERP, HCM is not merely a backend HR system for payroll; it is a real-time operational constraint engine. It dictates production capacity in MES, compliance in QMS, and labor costing in Finance. To support this, we anchor Employees to Positions within the Recursive Node Hierarchy. We will leverage PostgreSQL's advanced EXCLUDE constraints to prevent overlapping timesheets and establish cross-schema views for sub-millisecond certification validation by shop-floor scanners.

1. Architectural Topology & Execution Boundary
graph TB
    subgraph Operational Execution
        WMS_Scanner[WMS Scanner]
        MES_HMI[MES Tablet]
    end

    subgraph GCP VPC Internal Network
        subgraph Serverless Compute GAE
            AuthMiddleware[Django Auth / IAM]
            HCMApi[Django HCM API]
        end

        subgraph Cloud Memorystore
            RedisCache[(Redis: Active Certifications Cache)]
        end

        subgraph Cloud SQL PostgreSQL
            SchemaHCM[Schema: hcm]
            SchemaPlatform[Schema: platform]
            SchemaMES[Schema: mes]
            
            TriggerGist[[Constraint: Overlapping Punch Lock]]
            ViewCerts[[View: vw_valid_certifications]]
            
            SchemaHCM --> ViewCerts
            SchemaMES -->|Reads| ViewCerts
        end
    end

    WMS_Scanner -->|1. Request Task| AuthMiddleware
    AuthMiddleware -->|2. Check Certs| RedisCache
    RedisCache -.->|Cache Miss| ViewCerts
    MES_HMI -->|3. Log Labor Hours| HCMApi
    HCMApi -->|4. Reconcile Time| SchemaHCM
    SchemaHCM --> TriggerGist


2. Entity Relationship Diagram (Physical Data Model)
This model separates the structural budget (Position) from the physical human (Employee), ensuring strict financial control.
erDiagram
    "hcm.positions" {
        UUID position_id PK
        UUID node_id FK "References platform.nodes (Department/Site)"
        VARCHAR job_title 
        DECIMAL standard_cost_rate "DECIMAL(19,4)"
        DECIMAL fte_value "DECIMAL(3,2)"
        VARCHAR status "PLANNED, ACTIVE, FROZEN"
    }

    "hcm.employees" {
        UUID employee_id PK
        UUID user_id FK "References platform.users (System Identity)"
        UUID position_id FK "References hcm.positions"
        VARCHAR employment_status "ACTIVE, LOA, TERMINATED"
        DATE hire_date 
        BYTEA pii_encrypted_data "AES-256 Encrypted Payload"
    }

    "hcm.certifications" {
        UUID certification_id PK
        UUID employee_id FK "References hcm.employees"
        VARCHAR skill_code "e.g., FORKLIFT, TIG_WELDING"
        DATE issue_date 
        DATE expiration_date 
    }

    "hcm.time_logs" {
        UUID log_id PK
        UUID employee_id FK "References hcm.employees"
        UUID node_id FK "References platform.nodes (Where worked)"
        TIMESTAMPTZ punch_in 
        TIMESTAMPTZ punch_out 
        VARCHAR pay_code "REGULAR, OVERTIME, SICK"
    }

    "platform.nodes" ||--o{ "hcm.positions" : "budgets"
    "hcm.positions" ||--o| "hcm.employees" : "filled by"
    "hcm.employees" ||--o{ "hcm.certifications" : "holds"
    "hcm.employees" ||--o{ "hcm.time_logs" : "punches"


3. Physical Database Schema (PostgreSQL DDL)
We isolate HCM data. Because Time Logs represent temporal periods, we utilize PostgreSQL's tstzrange combined with a GiST exclusion constraint to mathematically guarantee an employee cannot be clocked into two places at the exact same time.
-- Require btree_gist for temporal exclusion constraints
CREATE EXTENSION IF NOT EXISTS btree_gist;

CREATE SCHEMA IF NOT EXISTS hcm;

-- =========================================================================
-- TABLE: hcm.positions (The Seat / Budget)
-- =========================================================================
CREATE TABLE hcm.positions (
    position_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    node_id UUID NOT NULL, -- The specific Site or Department Node
    job_title VARCHAR(255) NOT NULL,
    standard_cost_rate DECIMAL(19,4) NOT NULL DEFAULT 0.0000 CHECK (standard_cost_rate >= 0),
    fte_value DECIMAL(3,2) NOT NULL DEFAULT 1.00 CHECK (fte_value > 0 AND fte_value <= 1.00),
    status VARCHAR(30) NOT NULL DEFAULT 'PLANNED',
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_pos_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT chk_pos_status CHECK (status IN ('PLANNED', 'ACTIVE', 'FROZEN', 'RETIRED'))
);

CREATE INDEX idx_pos_node ON hcm.positions (node_id);

-- =========================================================================
-- TABLE: hcm.employees (The Person)
-- =========================================================================
CREATE TABLE hcm.employees (
    employee_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id UUID UNIQUE NOT NULL, -- Links to central Auth/IAM system
    position_id UUID NOT NULL,
    employment_status VARCHAR(30) NOT NULL DEFAULT 'ACTIVE',
    hire_date DATE NOT NULL,
    pii_encrypted_data BYTEA NOT NULL, -- Application must AES-encrypt sensitive PII before DB insertion
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,

    CONSTRAINT fk_emp_pos FOREIGN KEY (position_id) REFERENCES hcm.positions(position_id) ON DELETE RESTRICT,
    CONSTRAINT chk_emp_status CHECK (employment_status IN ('ACTIVE', 'LOA', 'TERMINATED'))
);

CREATE INDEX idx_emp_pos ON hcm.employees (position_id);

-- =========================================================================
-- TABLE: hcm.certifications (The License to Operate)
-- =========================================================================
CREATE TABLE hcm.certifications (
    certification_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL,
    skill_code VARCHAR(100) NOT NULL,
    issue_date DATE NOT NULL,
    expiration_date DATE NOT NULL,
    
    CONSTRAINT fk_cert_emp FOREIGN KEY (employee_id) REFERENCES hcm.employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT chk_dates CHECK (expiration_date >= issue_date),
    
    -- An employee cannot hold two active records of the exact same skill simultaneously
    CONSTRAINT uq_emp_skill UNIQUE (employee_id, skill_code)
);

CREATE INDEX idx_cert_lookup ON hcm.certifications (employee_id, skill_code);

-- =========================================================================
-- TABLE: hcm.time_logs (The Timesheet)
-- =========================================================================
CREATE TABLE hcm.time_logs (
    log_id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    employee_id UUID NOT NULL,
    node_id UUID NOT NULL, -- Where the work occurred
    punch_in TIMESTAMPTZ NOT NULL,
    punch_out TIMESTAMPTZ, -- Nullable while currently clocked in
    pay_code VARCHAR(50) NOT NULL DEFAULT 'REGULAR',
    
    CONSTRAINT fk_time_emp FOREIGN KEY (employee_id) REFERENCES hcm.employees(employee_id) ON DELETE CASCADE,
    CONSTRAINT fk_time_node FOREIGN KEY (node_id) REFERENCES platform.nodes(node_id) ON DELETE RESTRICT,
    CONSTRAINT chk_time_order CHECK (punch_out IS NULL OR punch_out > punch_in),
    CONSTRAINT chk_pay_code CHECK (pay_code IN ('REGULAR', 'OVERTIME', 'DOUBLE_TIME', 'SICK', 'VACATION')),

    -- RULE: Overlapping Time Punch Lock (A human cannot be in two shifts at once)
    -- If punch_out is null, we treat it as 'infinity' for the sake of the constraint
    CONSTRAINT excl_overlapping_shifts EXCLUDE USING gist (
        employee_id WITH =,
        tstzrange(punch_in, COALESCE(punch_out, 'infinity'::timestamptz)) WITH &&
    )
);

CREATE INDEX idx_time_emp_dates ON hcm.time_logs (employee_id, punch_in);


4. Database-Level Enforcement of Business Rules
Rule 1: The Law of Position Control
An Employee Master record cannot be assigned to a Position unless that Position is explicitly ACTIVE (budgeted and funded).
CREATE OR REPLACE FUNCTION hcm.fn_trg_enforce_position_control()
RETURNS TRIGGER AS $$
DECLARE
    v_pos_status VARCHAR;
BEGIN
    SELECT status INTO v_pos_status 
    FROM hcm.positions 
    WHERE position_id = NEW.position_id;

    IF v_pos_status != 'ACTIVE' THEN
        RAISE EXCEPTION 'Position Control Violation: Cannot assign employee to Position %. Position status is % (Must be ACTIVE).', 
            NEW.position_id, v_pos_status;
    END IF;

    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_emp_position_control
BEFORE INSERT OR UPDATE OF position_id ON hcm.employees
FOR EACH ROW
EXECUTE FUNCTION hcm.fn_trg_enforce_position_control();

Rule 2: Certification Expiration Lockout (Dynamic View)
To fulfill the requirement "automatically lock them out of all Warehouse Tasks at 12:01 AM", we do not run a batch job. We create a dynamic view that uses CURRENT_DATE. The MES and WMS APIs must join against this view. If a certification expires, it mathematically vanishes from this view the second the clock rolls over.
CREATE OR REPLACE VIEW hcm.vw_valid_certifications AS
SELECT 
    c.certification_id,
    c.employee_id,
    e.user_id,
    c.skill_code,
    c.expiration_date
FROM hcm.certifications c
JOIN hcm.employees e ON c.employee_id = e.employee_id
WHERE e.employment_status = 'ACTIVE'
  AND c.expiration_date >= CURRENT_DATE;

Rule 3: Time Reconciliation Hard-Stop (Database Constraint Function)
At shift end, the system must ensure the operator hasn't logged 10 hours in MES if their HCM timesheet says they were only in the building for 8 hours.
CREATE OR REPLACE FUNCTION hcm.fn_validate_mes_time_reconciliation(p_employee_id UUID, p_punch_in TIMESTAMPTZ, p_punch_out TIMESTAMPTZ)
RETURNS BOOLEAN AS $$
DECLARE
    v_total_hcm_hours DECIMAL;
    v_total_mes_hours DECIMAL;
BEGIN
    -- 1. Calculate Elapsed Time for the shift
    v_total_hcm_hours := EXTRACT(EPOCH FROM (p_punch_out - p_punch_in)) / 3600;

    -- 2. Sum the MES Labor Hours logged by this user ID during this time block
    SELECT COALESCE(SUM(labor_hours), 0) INTO v_total_mes_hours
    FROM mes.production_transactions pt
    JOIN hcm.employees e ON pt.operator_id = e.user_id
    WHERE e.employee_id = p_employee_id
      AND pt.created_at >= p_punch_in 
      AND pt.created_at <= p_punch_out;

    -- 3. The check: Did they log more task time than physical presence time?
    IF v_total_mes_hours > v_total_hcm_hours THEN
        RAISE EXCEPTION 'Time Variance Exception: Operator logged % hours in MES, but shift duration was only % hours.', 
            v_total_mes_hours, v_total_hcm_hours;
    END IF;

    RETURN TRUE;
END;
$$ LANGUAGE plpgsql;

(Architectural Note: This function is called by the API layer during the punch_out execution transaction).

5. Architectural Directives for the Application Layer
Security Directive: Strict PII Isolation (Data Privacy)
An employee's pii_encrypted_data (SSN, Salary, Medical) cannot be retrieved via simple ORM queries.
Mandatory Implementation Pattern:
The database column is BYTEA and must be encrypted using GCP Cloud KMS (Key Management Service) envelope encryption before insert.
An HR Manager requesting this data must pass the Global Layer's Node Authorization check. The API must traverse from the HR Manager's assigned Node to verify the target Employee's hcm.positions.node_id is a child node.
# Conceptual Architecture Logic for PII Retrieval
def get_employee_pii(request, target_employee_id):
    target_emp = Employee.objects.select_related('position').get(pk=target_employee_id)
    
    # Evaluate Global Node Access Matrix
    is_authorized = db.execute(
        "SELECT platform.fn_check_user_node_authorization(%s, %s, %s)",
        [request.user.id, target_emp.position.node_id, 'HR_MANAGER']
    )
    
    if not is_authorized:
        raise PermissionDenied("Node Hierarchy Violation: You do not have HR authority over this location.")
        
    # Proceed to decrypt via Cloud KMS
    decrypted_pii = kms_client.decrypt(target_emp.pii_encrypted_data)
    return Response(decrypted_pii)

Asynchronous Architecture: Cost Center Rollup via Subledger
When an employee executes a punch_out, the system has finalized a chunk of labor expense.
The Django API validates the punch out and saves the hcm.time_logs record.
The API triggers a Celery task: celery_app.send_task('fin.tasks.post_payroll_liability', args=[log_id]).
The Celery worker retrieves the time log, calculates (punch_out - punch_in) * hcm.positions.standard_cost_rate.
The worker queries the Global Layer platform.fn_resolve_node_setting() to find the appropriate Labor Expense GL Account for the hcm.positions.node_id.
The worker pushes a balanced Journal Entry (Debit Labor Expense, Credit Payroll Liability) to the fin schema.

