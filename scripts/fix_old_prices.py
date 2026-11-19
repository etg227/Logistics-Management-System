import sys
from pathlib import Path
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app import create_app
from app.extensions import db
from app.models import Shipment
from app.services.shipment_service import calculate_shipping_cost

app = create_app()
with app.app_context():
    shipments = db.session.scalars(db.select(Shipment)).all()
    for s in shipments:
        if s.shipping_cost == 0.0: # 如果價錢是 0，就幫他重算
            s.shipping_cost = calculate_shipping_cost(s.weight_kg)
    db.session.commit()
    print("✅ 所有舊訂單的價錢已更新完畢！")