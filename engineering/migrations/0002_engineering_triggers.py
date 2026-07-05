from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('engineering', '0001_initial'),
        ('mdm', '0002_mdm_triggers_and_views'), # Ensure MDM schema exists first
    ]

    operations = [
        # 1. Component Node Validation
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION eng.fn_trg_validate_component_node_extension()
            RETURNS TRIGGER AS $$
            DECLARE
                v_parent_node_id UUID;
                v_extension_exists BOOLEAN;
            BEGIN
                SELECT node_id INTO v_parent_node_id FROM eng.bom_headers WHERE bom_id = NEW.bom_id;
                
                SELECT EXISTS (
                    SELECT 1 FROM mdm.item_node_extensions ext
                    JOIN mdm.vw_effective_item_status v_status ON ext.extension_id = v_status.extension_id
                    WHERE ext.item_id = NEW.component_item_id
                      AND ext.node_id = v_parent_node_id
                      AND v_status.effective_status = 'ACTIVE'
                ) INTO v_extension_exists;
                
                IF NOT v_extension_exists THEN
                    RAISE EXCEPTION 'Component Validation Failed: Component % does not have an ACTIVE Node Extension at Node %.', NEW.component_item_id, v_parent_node_id;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bom_lines_node_validation
            BEFORE INSERT OR UPDATE OF component_item_id ON eng.bom_lines
            FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_validate_component_node_extension();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_bom_lines_node_validation ON eng.bom_lines; DROP FUNCTION IF EXISTS eng.fn_trg_validate_component_node_extension();"
        ),

        # 2. Acyclic BOM Enforcement (No Infinite Loops)
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION eng.fn_trg_prevent_bom_circular_dependency()
            RETURNS TRIGGER AS $$
            DECLARE
                v_parent_item_id UUID;
                v_is_circular BOOLEAN;
            BEGIN
                SELECT item_id INTO v_parent_item_id FROM eng.bom_headers WHERE bom_id = NEW.bom_id;
                
                WITH RECURSIVE bom_explosion AS (
                    SELECT NEW.component_item_id
                    UNION ALL
                    SELECT bl.component_item_id
                    FROM eng.bom_lines bl
                    JOIN eng.bom_headers bh ON bh.bom_id = bl.bom_id
                    JOIN bom_explosion be ON bh.item_id = be.component_item_id
                    WHERE bh.status = 'ACTIVE'
                )
                SELECT EXISTS (
                    SELECT 1 FROM bom_explosion WHERE component_item_id = v_parent_item_id
                ) INTO v_is_circular;
                
                IF v_is_circular THEN
                    RAISE EXCEPTION 'Acyclic BOM Violation: Inserting component creates an infinite loop back to parent item.';
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bom_lines_prevent_loops
            AFTER INSERT OR UPDATE OF component_item_id ON eng.bom_lines
            FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_prevent_bom_circular_dependency();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_bom_lines_prevent_loops ON eng.bom_lines; DROP FUNCTION IF EXISTS eng.fn_trg_prevent_bom_circular_dependency();"
        ),

        # 3. Immutability of Active BOMs
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION eng.fn_trg_enforce_bom_immutability()
            RETURNS TRIGGER AS $$
            DECLARE
                v_bom_status VARCHAR;
            BEGIN
                IF TG_TABLE_NAME = 'bom_headers' THEN
                    IF OLD.status = 'ACTIVE' AND NEW.status = 'ACTIVE' THEN
                        IF OLD.item_id != NEW.item_id OR OLD.bom_type != NEW.bom_type THEN
                            RAISE EXCEPTION 'Immutability Lock: Cannot modify core fields of an ACTIVE BOM Header. Issue an ECO.';
                        END IF;
                    END IF;
                    RETURN NEW;
                END IF;
                
                IF TG_TABLE_NAME = 'bom_lines' THEN
                    SELECT status INTO v_bom_status FROM eng.bom_headers WHERE bom_id = OLD.bom_id;
                    IF v_bom_status = 'ACTIVE' THEN
                        RAISE EXCEPTION 'Immutability Lock: Cannot add, edit, or delete lines on an ACTIVE BOM. Draft a new revision via ECO.';
                    END IF;
                    RETURN NEW;
                END IF;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_bom_headers_immutability
            BEFORE UPDATE ON eng.bom_headers
            FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_enforce_bom_immutability();

            CREATE TRIGGER trg_bom_lines_immutability
            BEFORE UPDATE OR DELETE ON eng.bom_lines
            FOR EACH ROW EXECUTE FUNCTION eng.fn_trg_enforce_bom_immutability();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_bom_headers_immutability ON eng.bom_headers; DROP TRIGGER IF EXISTS trg_bom_lines_immutability ON eng.bom_lines; DROP FUNCTION IF EXISTS eng.fn_trg_enforce_bom_immutability();"
        ),
        
        # 4. GiST Index for Daterange Effectivity
        migrations.RunSQL(
            sql="CREATE INDEX idx_bom_lines_effectivity ON eng.bom_lines USING gist (effectivity_dates);",
            reverse_sql="DROP INDEX IF EXISTS idx_bom_lines_effectivity;"
        )
    ]