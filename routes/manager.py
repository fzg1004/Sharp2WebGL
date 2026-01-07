from flask import Blueprint, render_template, jsonify, request, session, current_app, send_from_directory
import os
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from . import login_required
from utils.storage import StorageManager

# 创建蓝图
manager_bp = Blueprint('manager', __name__)


@manager_bp.route('/manager')
@login_required
def manager_page():
    """显示manager页面"""
    username = session.get('username', 'demo_user')
    return render_template('manager.html', username=username)


@manager_bp.route('/manager/delete/<path:model_name>', methods=['POST'])
@login_required
def delete_model(model_name):
    """删除指定的3D模型"""
    user_name = session.get('username', 'demo_user')
    data_dir = current_app.config.get('DATA_DIR', 'data')
    model_path = os.path.abspath(os.path.join(data_dir, user_name, model_name))
    user_dir = os.path.abspath(os.path.join(data_dir, user_name))

    sm = StorageManager(data_dir)

    # 防止路径穿越
    if not model_path.startswith(user_dir + os.sep) and os.path.basename(model_path) != model_name:
        return jsonify({"status": "error", "message": "非法的文件路径"}), 400

    if os.path.isfile(model_path):
        try:
            os.remove(model_path)
            # remove from xml index
            try:
                sm.remove_model(user_name, model_name)
            except Exception:
                current_app.logger.exception('从索引移除模型失败')
            return jsonify({"status": "success", "message": "模型删除成功"})
        except Exception as e:
            current_app.logger.exception('删除文件失败')
            return jsonify({"status": "error", "message": str(e)}), 500
    elif os.path.isdir(model_path):
        try:
            shutil.rmtree(model_path)
            # remove any indexed models under this folder
            try:
                models = sm.list_models(user_name)
                prefix = model_name.rstrip('/') + '/'
                for m in models:
                    if m['relpath'].startswith(prefix):
                        sm.remove_model(user_name, m['relpath'])
            except Exception:
                current_app.logger.exception('从索引移除模型失败')
            return jsonify({"status": "success", "message": "模型删除成功"})
        except Exception as e:
            current_app.logger.exception('删除目录失败')
            return jsonify({"status": "error", "message": str(e)}), 500
    else:
        return jsonify({"status": "error", "message": "模型不存在"}), 404


@manager_bp.route('/manager/rename', methods=['POST'])
@login_required
def rename_model():
    """重命名用户模型文件。接受 JSON 或表单：{ old_name, new_name }"""
    user_name = session.get('username', 'demo_user')
    data = request.get_json(silent=True) or request.form
    old_name = data.get('old_name')
    new_name = data.get('new_name')

    if not old_name or not new_name:
        return jsonify({"status": "error", "message": "参数缺失"}), 400

    data_dir = current_app.config.get('DATA_DIR', 'data')
    sm = StorageManager(data_dir)
    try:
        # old_name is relpath; new_name is base name without extension
        new_rel = sm.rename_model(user_name, old_name, new_name)
        return jsonify({"status": "success", "message": "重命名成功", 'new_name': new_rel})
    except FileNotFoundError:
        return jsonify({"status": "error", "message": "源文件不存在"}), 404
    except FileExistsError:
        return jsonify({"status": "error", "message": "目标文件已存在"}), 409
    except ValueError:
        return jsonify({"status": "error", "message": "非法的源文件路径"}), 400
    except Exception as e:
        current_app.logger.exception('重命名失败')
        return jsonify({"status": "error", "message": str(e)}), 500