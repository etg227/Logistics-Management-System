# Inventory movement history

After pulling this feature, run `flask --app run db upgrade` before starting the
app. The committed migration adds a ledger; do not regenerate the migration.
Existing quantities become explicitly labelled opening balances with a system
actor. The migration does not reconstruct historical movements.

Sign in as Admin or Staff, open Warehouses, then select a warehouse.
Each inventory row has three operations:

- **Set balance**: quantity is the final stock balance (for stocktake corrections).
- **Receive**: quantity is the number of units added.
- **Dispatch**: quantity is the number of units removed.

Enter a reason and save. The history below the inventory shows before/change/after,
staff, reason and UTC time, newest first, with 20 records per page. New items
receive an opening entry. Unchanged quantities and invalid movements create no
history entry. Dispatch cannot make stock negative. Quantity and history are
saved in one transaction; concurrent updates are rejected rather than overwritten.
Low-stock notifications continue to work. Old clients omitting operation/reason
retain the Set balance behavior with reason 'Manual stock adjustment'.

Drivers and customers cannot access these operations or history. There is no
application operation to edit or delete history. A database administrator can
still change database contents; this is not a tamper-proof external audit log.

Run `python -m pytest -q` before submitting. Downgrading this migration removes
movement history, but retains inventory quantities. Back up a real database
before any downgrade.
