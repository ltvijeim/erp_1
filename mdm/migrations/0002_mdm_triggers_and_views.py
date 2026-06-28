from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('mdm', '0001_initial'),
    ]

    operations = [
        # 1. Effective Status Resolution View
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE VIEW mdm.vw_effective_item_status AS
            SELECT
                ext.extension_id,
                ext.item_id,
                ext.node_id,
                i.global_status,
                ext.local_status AS raw_local_status,
                CASE
                    WHEN i.global_status = 'INACTIVE' THEN 'INACTIVE'
                    WHEN i.global_status = 'IN_DEVELOPMENT' THEN 'IN_DEVELOPMENT'
                    WHEN ext.local_status = 'INACTIVE' THEN 'INACTIVE'
                    WHEN ext.local_status = 'DISCONTINUED' THEN 'DISCONTINUED'
                    ELSE 'ACTIVE'
                END AS effective_status,
                i.traceability_type
            FROM mdm.item_node_extensions ext
            JOIN mdm.items i ON i.item_id = ext.item_id;
            """,
            reverse_sql="DROP VIEW IF EXISTS mdm.vw_effective_item_status;"
        ),

        # 2. Immutability of Base UoM Protection Trigger
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION mdm.fn_trg_protect_base_uom()
            RETURNS TRIGGER AS $$
            BEGIN
                IF OLD.base_uom IS DISTINCT FROM NEW.base_uom THEN
                    IF OLD.global_status = 'ACTIVE' THEN
                        RAISE EXCEPTION 'Architectural Hard-Stop: Base UoM cannot be modified once an Item is moved to ACTIVE status to prevent historical ledger corruption.';
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_items_protect_uom
            BEFORE UPDATE OF base_uom ON mdm.items
            FOR EACH ROW EXECUTE FUNCTION mdm.fn_trg_protect_base_uom();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_items_protect_uom ON mdm.items; DROP FUNCTION IF EXISTS mdm.fn_trg_protect_base_uom();"
        ),

        # 3. Corporate Hierarchy Acyclic Protection Trigger
        migrations.RunSQL(
            sql="""
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
            BEFORE UPDATE OF parent_bp_id ON mdm.business_partners
            FOR EACH ROW EXECUTE FUNCTION mdm.fn_trg_prevent_bp_circular_dependency();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_bp_prevent_loops ON mdm.business_partners; DROP FUNCTION IF EXISTS mdm.fn_trg_prevent_bp_circular_dependency();"
        )
    ]