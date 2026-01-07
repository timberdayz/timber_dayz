"""
简化的测试服务器 - 用于诊断问题
"""

from fastapi import FastAPI, Depends
from sqlalchemy.orm import Session
from models.database import get_db, DataFile
from pathlib import Path
import uvicorn
import sys

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent.parent))
from modules.core.path_manager import get_output_dir

app = FastAPI(title="测试服务器")

@app.get("/test-db")
async def test_database(db: Session = Depends(get_db)):
    """测试数据库连接"""
    try:
        # 查询文件数量
        file_count = db.query(DataFile).count()
        
        # 查询前5个文件
        files = db.query(DataFile).limit(5).all()
        file_list = []
        for f in files:
            file_list.append({
                "id": f.id,
                "file_name": f.file_name,
                "file_path": f.file_path,
                "platform": f.platform,
                "status": f.status
            })
        
        return {
            "success": True,
            "message": "数据库连接正常",
            "data": {
                "total_files": file_count,
                "sample_files": file_list
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "数据库连接失败"
        }

@app.get("/test-files")
async def test_file_system():
    """测试文件系统"""
    try:
        # 检查temp/outputs目录（使用统一路径管理，支持云端迁移）
        temp_outputs = get_output_dir()
        if not temp_outputs.exists():
            return {
                "success": False,
                "message": "temp/outputs目录不存在"
            }
        
        # 统计文件
        excel_files = list(temp_outputs.rglob("*.xlsx")) + list(temp_outputs.rglob("*.xls"))
        json_files = list(temp_outputs.rglob("*.json"))
        
        return {
            "success": True,
            "message": "文件系统正常",
            "data": {
                "temp_outputs_exists": temp_outputs.exists(),
                "excel_files_count": len(excel_files),
                "json_files_count": len(json_files),
                "sample_excel_files": [str(f) for f in excel_files[:5]],
                "sample_json_files": [str(f) for f in json_files[:5]]
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "文件系统检查失败"
        }

@app.post("/test-cleanup")
async def test_cleanup(db: Session = Depends(get_db)):
    """测试清理功能"""
    try:
        # 获取所有文件记录
        db_files = db.query(DataFile).all()
        
        orphaned_count = 0
        valid_count = 0
        
        for db_record in db_files:
            try:
                if db_record.file_path and db_record.file_path.strip():
                    file_path = Path(db_record.file_path)
                    if file_path.exists():
                        valid_count += 1
                    else:
                        orphaned_count += 1
                else:
                    orphaned_count += 1
            except Exception as e:
                print(f"检查文件时出错: {e}")
                orphaned_count += 1
        
        return {
            "success": True,
            "message": "清理测试完成",
            "data": {
                "total_files": len(db_files),
                "valid_files": valid_count,
                "orphaned_files": orphaned_count
            }
        }
    except Exception as e:
        return {
            "success": False,
            "error": str(e),
            "message": "清理测试失败"
        }

if __name__ == "__main__":
    uvicorn.run("simple_test:app", host="0.0.0.0", port=8000, reload=True)
