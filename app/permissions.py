from functools import wraps

from flask import abort
from flask_login import current_user


def roles_required(*allowed_roles):
    def decorator(view):
        @wraps(view)
        def wrapped(*args, **kwargs):
            if current_user.role not in allowed_roles:
                abort(403)

            return view(*args, **kwargs)

        return wrapped

    return decorator