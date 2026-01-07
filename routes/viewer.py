from flask import Blueprint, render_template, jsonify, send_from_directory, send_file, current_app, session
import os
from . import login_required
from utils.storage import StorageManager

# 创建查看器蓝图
viewer_bp = Blueprint('viewer', __name__)


def get_user_model_dir(username):
    data_dir = current_app.config.get('DATA_DIR', 'data')
    sm = StorageManager(data_dir)
    return sm.ensure_user(username)




@viewer_bp.route('/models/<path:filename>')
@login_required
def serve_model(filename):
    
    username = session.get('username', 'demo_user')
    
    data_dir = current_app.config.get('DATA_DIR', 'data')
    sm = StorageManager(data_dir)
    models_dir = sm.ensure_user(username)

    try:
        # 规范化路径，防止路径穿越攻击
        user_file_path = sm.get_full_path(username, filename)

        # Ensure requested file is inside the user's models directory
        if not user_file_path.startswith(models_dir + os.sep) and os.path.basename(user_file_path) != filename:
            current_app.logger.warning(f"Attempt to access file outside user dir: {user_file_path}")
            return jsonify({'success': False, 'message': '非法的文件路径'}), 400

        if os.path.isfile(user_file_path):
            # 返回文件内容（send_file 会处理 mime-type）
            current_app.logger.info(f"Serving model file: {user_file_path}")
            return send_file(user_file_path)
        else:
            return jsonify({'success': False, 'message': '模型文件不存在'}), 404
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        current_app.logger.error('Error serving model file: %s', tb)
        if current_app.debug:
            return jsonify({'success': False, 'message': '服务器内部错误', 'error': str(e), 'trace': tb}), 500
        else:
            return jsonify({'success': False, 'message': '服务器内部错误'}), 500
            


@viewer_bp.route('/models/')
@login_required
def list_models():
    username = session.get('username', 'demo_user')
    data_dir = current_app.config.get('DATA_DIR', 'data')
    sm = StorageManager(data_dir)
    try:
        models = sm.list_models(username)
        return jsonify({'success': True, 'models': [m['relpath'] for m in models]})
    except Exception as e:
        current_app.logger.error(f"列出模型失败: {str(e)}", exc_info=True)
        return jsonify({'success': False, 'message': '获取模型列表失败'}), 500



@viewer_bp.route('/viewer')
@login_required
def viewer_page():
    """3D查看器主页面"""
    return render_template('viewer.html')