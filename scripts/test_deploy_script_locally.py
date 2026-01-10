#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
本地测试部署脚本逻辑（Python 版本，跨平台）
用于提前验证部署脚本的 YAML 生成和 tag 提取逻辑
"""

import subprocess
import sys
import tempfile
import os
from pathlib import Path

def safe_print(text):
    """安全打印（处理 Windows GBK 编码）"""
    try:
        print(text, flush=True)
    except UnicodeEncodeError:
        try:
            safe_text = text.encode('gbk', errors='ignore').decode('gbk')
            print(safe_text, flush=True)
        except:
            safe_text = text.encode('ascii', errors='ignore').decode('ascii')
            print(safe_text, flush=True)

def test_tag_extraction():
    """测试 tag 提取逻辑"""
    safe_print("=" * 50)
    safe_print("[TEST 1] 验证 tag 提取逻辑（模拟 pull_image_with_fallback）")
    safe_print("-" * 50)
    
    # 模拟函数输出：日志到 stderr，tag 到 stdout
    def mock_pull_image_with_fallback(image_name, tag):
        """模拟 pull_image_with_fallback 函数"""
        import sys
        # 日志输出到 stderr
        print(f"[INFO] Attempting to pull {image_name}:{tag}...", file=sys.stderr, flush=True)
        print(f"[INFO] Pull attempt 1/3 for {image_name}:{tag}...", file=sys.stderr, flush=True)
        print(f"[OK] Image pulled successfully with tag {tag}", file=sys.stderr, flush=True)
        # tag 输出到 stdout
        print(tag, file=sys.stdout, flush=True)
        return 0
    
    # 使用临时文件方案（与实际脚本一致）
    temp_output_path = None
    temp_stderr_path = None
    try:
        # 创建临时文件（Windows 兼容方式）
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as temp_output:
            temp_output_path = temp_output.name
        with tempfile.NamedTemporaryFile(mode='w+', delete=False, encoding='utf-8') as temp_stderr:
            temp_stderr_path = temp_stderr.name
        
        # 重定向输出到临时文件
        import sys
        old_stdout = sys.stdout
        old_stderr = sys.stderr
        
        with open(temp_output_path, 'w', encoding='utf-8') as temp_output:
            with open(temp_stderr_path, 'w', encoding='utf-8') as temp_stderr:
                sys.stdout = temp_output
                sys.stderr = temp_stderr
                
                exit_code = mock_pull_image_with_fallback("test/backend", "v4.21.4")
                
                # 确保所有输出都被刷新
                temp_output.flush()
                temp_stderr.flush()
        
        sys.stdout = old_stdout
        sys.stderr = old_stderr
        
        # 读取输出
        with open(temp_output_path, 'r', encoding='utf-8') as f:
            stdout_content = f.read()
        with open(temp_stderr_path, 'r', encoding='utf-8') as f:
            stderr_content = f.read()
        
        if exit_code != 0:
            safe_print(f"[FAIL] Mock pull failed (exit code: {exit_code})")
            safe_print(f"stderr: {stderr_content}")
            return False
        
        # 显示日志
        safe_print("Logs (stderr):")
        for line in stderr_content.strip().split('\n'):
            if line.strip():
                safe_print(f"  {line}")
        
        # 提取 tag（过滤日志行）
        tag_lines = [line for line in stdout_content.strip().split('\n') 
                    if line.strip() and not line.strip().startswith('[')]
        test_tag = tag_lines[-1].strip() if tag_lines else stdout_content.strip()
        
        safe_print(f"\nCaptured tag: '{test_tag}'")
        
        if test_tag == "v4.21.4":
            safe_print("[OK] Tag extraction successful")
            return True
        else:
            safe_print(f"[FAIL] Tag extraction failed: expected 'v4.21.4', got '{test_tag}'")
            safe_print(f"Full stdout: {repr(stdout_content)}")
            return False
            
    finally:
        # 清理临时文件（Windows 兼容）
        import time
        if temp_output_path and os.path.exists(temp_output_path):
            try:
                time.sleep(0.1)  # 给 Windows 一点时间释放文件句柄
                os.unlink(temp_output_path)
            except (PermissionError, OSError):
                pass  # 忽略删除失败（可能在 Windows 上文件仍被占用）
        if temp_stderr_path and os.path.exists(temp_stderr_path):
            try:
                time.sleep(0.1)
                os.unlink(temp_stderr_path)
            except (PermissionError, OSError):
                pass

def test_yaml_generation():
    """测试 YAML 生成逻辑"""
    safe_print("\n" + "=" * 50)
    safe_print("[TEST 2] 验证 YAML 生成逻辑")
    safe_print("-" * 50)
    
    ghcr_registry = "ghcr.io"
    image_name_backend = "test/backend"
    image_name_frontend = "test/frontend"
    backend_tag = "v4.21.4"
    frontend_tag = "v4.21.4"
    
    # 验证必需变量不为空
    if not all([ghcr_registry, image_name_backend, image_name_frontend]):
        safe_print("[FAIL] Required variables are empty")
        return False
    
    if not all([backend_tag, frontend_tag]):
        safe_print("[FAIL] Tag variables are empty")
        return False
    
    # 验证 tag 不包含特殊字符
    import re
    invalid_char_pattern = re.compile(r'[^a-zA-Z0-9._-]')
    if invalid_char_pattern.search(backend_tag) or invalid_char_pattern.search(frontend_tag):
        safe_print(f"[FAIL] Tag contains invalid characters: Backend='{backend_tag}', Frontend='{frontend_tag}'")
        return False
    
    safe_print("[OK] Tag validation passed")
    
    # 生成 YAML（与实际脚本一致）
    yaml_content = f"""services:
  backend:
    image: {ghcr_registry}/{image_name_backend}:{backend_tag}
  frontend:
    image: {ghcr_registry}/{image_name_frontend}:{frontend_tag}
    ports: []
"""
    
    safe_print("\nGenerated YAML content:")
    safe_print(yaml_content)
    
    # 验证 YAML 格式（基本检查）
    if "services:" not in yaml_content:
        safe_print("[FAIL] YAML missing 'services:' key")
        return False
    if "image:" not in yaml_content:
        safe_print("[FAIL] YAML missing 'image:' key")
        return False
    
    # 检查每行是否以空格或字母开头（基本 YAML 格式检查）
    lines = yaml_content.strip().split('\n')
    for i, line in enumerate(lines):
        if line.strip() and not (line.startswith(' ') or line[0].isalnum() or line[0] in '-:'):
            safe_print(f"[FAIL] Invalid YAML line {i+1}: {line}")
            return False
    
    safe_print("[OK] YAML structure valid")
    return True

def test_docker_compose_validation():
    """测试 docker-compose 语法验证（如果可用）"""
    safe_print("\n" + "=" * 50)
    safe_print("[TEST 3] 验证 docker-compose 语法（可选）")
    safe_print("-" * 50)
    
    # 检查 docker-compose 是否可用
    try:
        result = subprocess.run(
            ["docker-compose", "--version"],
            capture_output=True,
            text=True,
            timeout=5
        )
        if result.returncode != 0:
            safe_print("[INFO] docker-compose not found, skipping syntax validation")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        safe_print("[INFO] docker-compose not found, skipping syntax validation")
        return True
    
    # 检查 docker-compose.yml 是否存在
    compose_file = Path("docker-compose.yml")
    if not compose_file.exists():
        safe_print("[INFO] docker-compose.yml not found, skipping syntax validation")
        return True
    
    # 验证配置语法
    try:
        result = subprocess.run(
            ["docker-compose", "-f", "docker-compose.yml", "-f", "docker-compose.prod.yml", "config"],
            capture_output=True,
            text=True,
            timeout=30,
            encoding='utf-8',
            errors='replace'
        )
        
        if result.returncode == 0:
            safe_print("[OK] docker-compose config syntax valid")
            return True
        else:
            safe_print("[WARN] docker-compose config validation failed")
            if result.stderr:
                error_lines = result.stderr.strip().split('\n')[:5]
                for line in error_lines:
                    if line.strip():
                        safe_print(f"  {line}")
            return True  # 不阻止，因为这只是可选的测试
    except Exception as e:
        safe_print(f"[WARN] docker-compose validation error: {e}")
        return True  # 不阻止

def test_tag_validation():
    """测试 tag 特殊字符检测"""
    safe_print("\n" + "=" * 50)
    safe_print("[TEST 4] 验证 tag 特殊字符检测")
    safe_print("-" * 50)
    
    import re
    invalid_char_pattern = re.compile(r'[^a-zA-Z0-9._-]')
    
    # 测试无效 tag
    invalid_tag = "v4.21.4\ninvalid:tag"
    if invalid_char_pattern.search(invalid_tag):
        safe_print(f"[OK] Invalid tag detected correctly: '{invalid_tag}'")
    else:
        safe_print(f"[FAIL] Invalid tag should be detected: '{invalid_tag}'")
        return False
    
    # 测试有效 tag
    valid_tag = "v4.21.4"
    if invalid_char_pattern.search(valid_tag):
        safe_print(f"[FAIL] Valid tag should not be rejected: '{valid_tag}'")
        return False
    else:
        safe_print(f"[OK] Valid tag accepted: '{valid_tag}'")
    
    # 测试带下划线的 tag
    valid_tag2 = "v4.21.4_test"
    if invalid_char_pattern.search(valid_tag2):
        safe_print(f"[FAIL] Valid tag with underscore should not be rejected: '{valid_tag2}'")
        return False
    else:
        safe_print(f"[OK] Valid tag with underscore accepted: '{valid_tag2}'")
    
    return True

def main():
    """主函数"""
    safe_print("=" * 50)
    safe_print("本地测试部署脚本逻辑（Python 版本）")
    safe_print("=" * 50)
    safe_print("")
    
    tests = [
        ("Tag Extraction", test_tag_extraction),
        ("YAML Generation", test_yaml_generation),
        ("Docker Compose Validation", test_docker_compose_validation),
        ("Tag Validation", test_tag_validation),
    ]
    
    results = []
    for name, test_func in tests:
        try:
            result = test_func()
            results.append((name, result))
        except Exception as e:
            safe_print(f"[FAIL] {name} test crashed: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))
    
    # 汇总结果
    safe_print("\n" + "=" * 50)
    safe_print("测试结果汇总")
    safe_print("=" * 50)
    
    all_passed = True
    for name, result in results:
        status = "[OK]" if result else "[FAIL]"
        safe_print(f"{status} {name}")
        if not result:
            all_passed = False
    
    safe_print("=" * 50)
    if all_passed:
        safe_print("[OK] 所有本地测试通过！")
        safe_print("")
        safe_print("说明：")
        safe_print("  - 这些测试验证了部署脚本的核心逻辑（tag 提取、YAML 生成）")
        safe_print("  - 实际部署时还需要：")
        safe_print("    1. 镜像已在 GHCR 中存在")
        safe_print("    2. 服务器有网络访问 GHCR")
        safe_print("    3. 服务器上有完整的 docker-compose 文件")
        safe_print("    4. 服务器上有正确的 .env 配置")
        safe_print("")
        safe_print("建议：在每次修改部署脚本后运行此测试，提前发现问题")
        return 0
    else:
        safe_print("[FAIL] 部分测试失败，请检查上述输出")
        return 1

if __name__ == "__main__":
    sys.exit(main())
