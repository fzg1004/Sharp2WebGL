from flask import Blueprint, render_template, jsonify, request, session, redirect, url_for, send_from_directory
import os

from . import login_required


# 创建登录蓝图
login_bp = Blueprint('login', __name__)

@login_bp.route('/')
def index():
    """首页（重定向到登录）"""
    return redirect(url_for('login.login_page'))

@login_bp.route('/login', methods=['GET'])
def login_page():
    """登录页面（GET请求）"""
    return render_template('login.html')

@login_bp.route('/login', methods=['POST'])
def login_api():
    """登录API（POST请求）"""
    data = request.get_json()
    username = data.get('username', '').strip()
    password = data.get('password', '').strip()
    
    # 简化登录验证（演示用）
    if username and password:
        session['username'] = username
        session['logged_in'] = True
        return jsonify({
            'success': True,
            'username': username,
            'message': '登录成功',
            'redirect': url_for('viewer.viewer_page')
        })
    else:
        return jsonify({
            'success': False,
            'message': '用户名和密码不能为空'
        }), 401

@login_bp.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('login.login_page'))

@login_bp.route('/check_login')
def check_login():
    """检查登录状态"""
    if session.get('logged_in'):
        return jsonify({
            'logged_in': True,
            'username': session.get('username')
        })
    return jsonify({'logged_in': False})