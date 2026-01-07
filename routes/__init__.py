from functools import wraps
from flask import session, redirect, url_for

def login_required(f):
    """登录装饰器"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login.login'))
        return f(*args, **kwargs)
    return decorated_function