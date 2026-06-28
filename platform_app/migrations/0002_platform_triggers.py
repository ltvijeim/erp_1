from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('platform_app', '0001_initial'),
    ]

    operations = [
        # 1. GiST Index for ultra-fast spatial search
        migrations.RunSQL(
            sql="CREATE INDEX idx_nodes_lineage_gist ON platform_nodes USING gist (lineage_path);",
            reverse_sql="DROP INDEX idx_nodes_lineage_gist;"
        ),
        
        # 2. Automated ltree path generation & propagation
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION fn_trg_preserve_and_build_lineage()
            RETURNS TRIGGER AS $$
            DECLARE
                v_parent_path ltree;
                v_cleaned_uuid VARCHAR(32);
            BEGIN
                v_cleaned_uuid := REPLACE(NEW.node_id::TEXT, '-', '');
                IF NEW.parent_node_id IS NULL THEN
                    NEW.lineage_path := v_cleaned_uuid::ltree;
                ELSE
                    SELECT lineage_path INTO v_parent_path FROM platform_nodes WHERE node_id = NEW.parent_node_id;
                    NEW.lineage_path := (v_parent_path::text || '.' || v_cleaned_uuid)::ltree;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_nodes_build_lineage
            BEFORE INSERT OR UPDATE OF parent_node_id, node_id ON platform_nodes
            FOR EACH ROW EXECUTE FUNCTION fn_trg_preserve_and_build_lineage();
            """,
            reverse_sql="DROP TRIGGER trg_nodes_build_lineage ON platform_nodes; DROP FUNCTION fn_trg_preserve_and_build_lineage;"
        ),

        # 3. Acyclic Loop Prevention
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION fn_trg_prevent_circular_dependency()
            RETURNS TRIGGER AS $$
            DECLARE
                v_cleaned_target_id VARCHAR(32);
                v_parent_path_text TEXT;
            BEGIN
                IF (TG_OP = 'UPDATE' AND OLD.parent_node_id IS NOT DISTINCT FROM NEW.parent_node_id) THEN
                    RETURN NEW;
                END IF;
                IF NEW.parent_node_id IS NOT NULL THEN
                    v_cleaned_target_id := REPLACE(NEW.node_id::TEXT, '-', '');
                    SELECT lineage_path::TEXT INTO v_parent_path_text FROM platform_nodes WHERE node_id = NEW.parent_node_id;
                    IF v_parent_path_text ~ ('(^|\.)' || v_cleaned_target_id || '($|\.)') THEN
                        RAISE EXCEPTION 'Cyclic Reference Violation';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_nodes_prevent_loops
            BEFORE UPDATE ON platform_nodes
            FOR EACH ROW EXECUTE FUNCTION fn_trg_prevent_circular_dependency();
            """,
            reverse_sql="DROP TRIGGER trg_nodes_prevent_loops ON platform_nodes; DROP FUNCTION fn_trg_prevent_circular_dependency();"
        ),
    ]