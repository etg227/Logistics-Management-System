from flask import Blueprint, redirect, render_template, url_for
from flask_login import current_user, login_required

from app.extensions import db
from app.models import Notification

notifications_bp = Blueprint("notifications", __name__, url_prefix="/notifications")


@notifications_bp.get("/")
@login_required
def index():
    notifications = db.session.scalars(
        db.select(Notification).where(Notification.user_id == current_user.id)
        .order_by(Notification.created_at.desc(), Notification.id.desc())
    ).all()
    return render_template("notifications/index.html", notifications=notifications)


@notifications_bp.post("/<int:notification_id>/read")
@login_required
def mark_read(notification_id):
    notification = db.get_or_404(Notification, notification_id)
    if notification.user_id != current_user.id:
        from flask import abort
        abort(403)
    notification.is_read = True
    db.session.commit()
    return redirect(url_for("notifications.index"))


@notifications_bp.post("/read-all")
@login_required
def mark_all_read():
    db.session.query(Notification).filter_by(user_id=current_user.id, is_read=False).update(
        {Notification.is_read: True}, synchronize_session=False)
    db.session.commit()
    return redirect(url_for("notifications.index"))
