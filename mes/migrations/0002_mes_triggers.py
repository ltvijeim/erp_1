from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('mes', '0001_initial'),
    ]

    operations = [
        # 1. Sequential Enforcement (Cannot yield Op 20 until Op 10 yields)
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION mes.fn_trg_enforce_operation_sequence()
            RETURNS TRIGGER AS $$
            DECLARE
                v_previous_yield DECIMAL(19,4);
                v_previous_seq INTEGER;
            BEGIN
                IF NEW.yield_qty > OLD.yield_qty THEN
                    SELECT operation_seq, yield_qty INTO v_previous_seq, v_previous_yield
                    FROM mes.wo_operations
                    WHERE wo_id = NEW.wo_id AND operation_seq < NEW.operation_seq
                    ORDER BY operation_seq DESC
                    LIMIT 1;

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
            FOR EACH ROW EXECUTE FUNCTION mes.fn_trg_enforce_operation_sequence();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_wo_op_sequence ON mes.wo_operations; DROP FUNCTION IF EXISTS mes.fn_trg_enforce_operation_sequence();"
        ),

        # 2. Strict Material Allocation Hard-Stop
        migrations.RunSQL(
            sql="""
            CREATE OR REPLACE FUNCTION mes.fn_trg_enforce_material_allocation()
            RETURNS TRIGGER AS $$
            DECLARE
                v_unfulfilled_components INTEGER;
            BEGIN
                IF OLD.status != 'COMPLETED' AND NEW.status = 'COMPLETED' THEN
                    SELECT COUNT(*) INTO v_unfulfilled_components
                    FROM mes.wo_material_requirements
                    WHERE wo_id = NEW.wo_id AND consumed_qty < required_qty;

                    IF v_unfulfilled_components > 0 THEN
                        RAISE EXCEPTION 'Material Allocation Hard-Stop: Work Order cannot be COMPLETED. % component(s) have unmet material requirements.', v_unfulfilled_components;
                    END IF;
                END IF;
                RETURN NEW;
            END;
            $$ LANGUAGE plpgsql;

            CREATE TRIGGER trg_wo_completion_allocation
            BEFORE UPDATE OF status ON mes.work_orders
            FOR EACH ROW EXECUTE FUNCTION mes.fn_trg_enforce_material_allocation();
            """,
            reverse_sql="DROP TRIGGER IF EXISTS trg_wo_completion_allocation ON mes.work_orders; DROP FUNCTION IF EXISTS mes.fn_trg_enforce_material_allocation();"
        )
    ]