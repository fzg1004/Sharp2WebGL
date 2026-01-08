from flask import Blueprint, render_template, jsonify, request, session, current_app, send_from_directory
import os
import uuid
import threading
import time
import shutil
from datetime import datetime
from werkzeug.utils import secure_filename
from . import login_required
from config import Config
from trainer_image import ImageModelTrainer
from convert import convert as ply_convert
from pathlib import Path
from utils.storage import StorageManager

# 创建蓝图
sharp_bp = Blueprint('sharp', __name__)

# 存储任务状态的全局字典
sharp_tasks = {}

class TaskStatus:
    """任务状态跟踪"""
    UPLOADING = "uploading"
    UPLOADED = "uploaded"
    PROCESSING = "processing"
    TRAINING = "training"
    COMPLETED = "completed"
    FAILED = "failed"

def update_task_status(task_id, status, message="", progress=0, result=None):
    """更新任务状态"""
    if task_id not in sharp_tasks:
        sharp_tasks[task_id] = {
            "status": status,
            "message": message,
            "progress": progress,
            "result": result,
            "created_at": time.time(),
            "updated_at": time.time()
        }
    else:
        sharp_tasks[task_id].update({
            "status": status,
            "message": message,
            "progress": progress,
            "result": result,
            "updated_at": time.time()
        })

# 允许的扩展名


def allowed_file(filename):
    """检查文件扩展名是否允许"""
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in Config.ALLOWED_IMAGE_EXTENSIONS

def generate_unique_filename(original_filename, username):
    """生成唯一的文件名"""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    ext = original_filename.rsplit('.', 1)[1].lower()
    unique_id = str(uuid.uuid4())[:8]
    return f"{username}_{timestamp}_{unique_id}.{ext}"

def get_user_image_dir(username):
    """获取用户图片目录"""
    data_dir = current_app.config.get('DATA_DIR', 'data')
    user_dir = os.path.join(data_dir, username, 'sharp_images')
    os.makedirs(user_dir, exist_ok=True)
    return user_dir


@sharp_bp.route('/sharp')
@login_required
def sharp_page():
    """显示sharp页面"""
    username = session.get('username', 'Guest')
    return render_template('sharp.html', username=username)


@sharp_bp.route('/sharp/images', methods=['POST'])
@login_required
def upload_image():
    """接收前端上传的单张图片，启动后台处理任务，并返回 task_id"""
    username = session.get('username', 'demo_user')

    if 'image' not in request.files:
        return jsonify({'success': False, 'message': '未找到上传的文件'}), 400

    file = request.files['image']
    if file.filename == '':
        return jsonify({'success': False, 'message': '未选择文件'}), 400

    if not allowed_file(file.filename):
        return jsonify({'success': False, 'message': '不支持的文件类型'}), 400

    try:
        
        # create task
        task_id = str(uuid.uuid4())
        update_task_status(task_id, TaskStatus.UPLOADING, "正在上传文件......", 0)
        
        
        # save uploaded image into its own folder (username/<image_folder>/image.jpg)
        data_dir = current_app.config.get('DATA_DIR', 'data')
        sm = StorageManager(data_dir)
        rel_folder, filename_saved, save_path = sm.save_image(username, file)
        update_task_status(task_id, TaskStatus.UPLOADED, "文件已上传", 10)
       


        # start background processing thread
        t = threading.Thread(target=_run_sharp_task, args=(task_id, data_dir, save_path, username, rel_folder), daemon=True)
        t.start()

        return jsonify({'success': True, 'task_id': task_id})
    except Exception as e:
        current_app.logger.exception('上传图像失败')
        return jsonify({'success': False, 'message': '服务器错误: ' + str(e)}), 500


def _run_sharp_task(task_id, data_dir,image_path, username, rel_folder):
    
    """后台处理任务"""
    update_task_status(task_id, TaskStatus.PROCESSING, "正在处理文件...", 10)
    trainer = ImageModelTrainer()
    sm = StorageManager(data_dir)
    # image_path is the saved image file; sharp predict expects an input directory
    image_dir = os.path.dirname(image_path)
    # output directory should be the same image folder so generated ply sits alongside the image
    user_dir = os.path.join(data_dir, username)
    out_dir = os.path.join(user_dir, rel_folder)
    os.makedirs(out_dir, exist_ok=True)

    # call trainer with input directory and output directory
    training_result = trainer.train(image_dir, out_dir)
    if not training_result.get('success'):
        update_task_status(task_id, TaskStatus.FAILED, f"重建失败: {training_result.get('message')}", training_result.get('log', []))
        return

    update_task_status(task_id, TaskStatus.TRAINING, "重建完成，查找输出...", 80)
    out_dir = training_result.get('output_dir')

    # 查找输出目录中的 ply / ply.gz / splat 文件
    result_file = None
    try:
        for fname in os.listdir(out_dir):
            if fname.lower().endswith(('.ply', '.splat')):
                result_file = fname
                break
    except Exception:
        result_file = None

    if result_file:
        # 1) attempt conversion using convert.py (if available)
        try:
            teaser_full = os.path.join(out_dir, result_file)
            # determine output filename: base + _convert + ext
            base, ext = os.path.splitext(result_file)
            converted_name = f"{base}_convert{ext}"
            converted_full = os.path.join(out_dir, converted_name)
            target_full = os.path.join(out_dir, Config.Target_File)

            print(f"input file : {teaser_full}")
            print(f"target file: {target_full}")
            print(f"output file: {converted_full}")
            # call converter
            ply_convert(Path(teaser_full), Path(Config.Target_File), Path(converted_full))
            # register converted file
            rel_converted = os.path.join(rel_folder, converted_name).replace('\\', '/')
            try:
                sm.add_model(username, rel_converted)
            except Exception:
                current_app.logger.exception('注册转换后模型失败')
            # prefer returning converted file as task result
            update_task_status(task_id, TaskStatus.COMPLETED, "完成（已转换）", 100, result=rel_converted)
            os.remove(teaser_full)
        except Exception as e:
            # conversion failed; still register original result and finish
            current_app.logger.exception('PLY 转换失败')
            rel = os.path.join(rel_folder, result_file).replace('\\', '/')
            update_task_status(task_id, TaskStatus.COMPLETED, f"完成（转换失败: {e}", 100, result=rel)
    else:
        # 若没有找到直接的模型文件，仍返回输出目录供人工查看
        update_task_status(task_id, TaskStatus.COMPLETED, "完成（未找到明确的模型文件，输出在目录）", 100, result=os.path.basename(out_dir))


@sharp_bp.route('/sharp/status/<task_id>')
@login_required
def sharp_status(task_id):
    task = sharp_tasks.get(task_id)
    if not task:
        return jsonify({'success': False, 'message': '任务不存在'}), 404

    return jsonify({'success': True, 'task': {
        'status': task.get('status'),
        'progress': task.get('progress', 0),
        'message': task.get('message', ''),
        'result': task.get('result')
    }})
