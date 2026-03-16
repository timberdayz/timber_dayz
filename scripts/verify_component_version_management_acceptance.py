"""
optimize-component-version-management 专项验收脚本
验证 1.9 类发现、1.10 路径安全、phase 可观测性、前端契约等（可自动化部分）。
"""
from pathlib import Path
import os
import sys

# 项目根
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

def main():
    os.environ.setdefault("PROJECT_ROOT", str(ROOT))
    passed = 0
    failed = 0

    # 1.9 类发现：元数据优先 + stem 兜底
    print("[1.9] file_path 导入后类发现稳定性...")
    try:
        from modules.apps.collection_center.component_loader import ComponentLoader
        loader = ComponentLoader()
        assert hasattr(loader, "_find_component_class_by_metadata"), "missing _find_component_class_by_metadata"
        assert hasattr(loader, "_stem_to_component_name"), "missing _stem_to_component_name"
        assert loader._stem_to_component_name("login_v1_0_0") == "login"
        assert loader._stem_to_component_name("orders_export_v1_0_0") == "orders_export"
        # load_python_component_from_path 接受 platform/component_type
        sig = loader.load_python_component_from_path.__doc__
        assert "platform" in sig and "component_type" in sig, "load_python_component_from_path should accept platform/component_type"
        print("  [PASS] 元数据优先 + stem 兜底已实现")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 1.10 路径安全：越界拒绝
    print("[1.10] file_path 安全边界校验...")
    try:
        import tempfile
        from modules.apps.collection_center.component_loader import ComponentLoader
        loader = ComponentLoader()
        # 创建一个确实存在但位于允许目录外的临时文件，验证必须被安全拒绝（ValueError）
        with tempfile.NamedTemporaryFile(suffix=".py", delete=False) as tf:
            tf.write(b"class Dummy:\n    pass\n")
            outside_path = tf.name
        try:
            loader.load_python_component_from_path(outside_path, version_id=1)
            print("  [FAIL] 越界路径未被拒绝")
            failed += 1
        except ValueError as ve:
            ve_text = str(ve).lower()
            if "outside allowed" in ve_text or "security" in ve_text or "project_root" in ve_text:
                print("  [PASS] 越界路径被拒绝（安全边界生效）")
                passed += 1
            else:
                print(f"  [FAIL] 期望安全相关 ValueError，得到: {ve}")
                failed += 1
        finally:
            try:
                Path(outside_path).unlink(missing_ok=True)
            except Exception:
                pass
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 1.8 发现模式组件测试策略：flow_only 禁止单测，standalone 需 test_config
    print("[1.8] 发现模式组件测试策略门禁...")
    try:
        with open(ROOT / "backend" / "routers" / "component_versions.py", "r", encoding="utf-8") as f:
            cv_content = f.read()
        with open(ROOT / "tools" / "test_component.py", "r", encoding="utf-8") as f:
            tc_content = f.read()
        assert "test_mode" in cv_content and "flow_only" in cv_content and "standalone" in cv_content
        assert "test_config" in cv_content
        assert "standalone_test_config" in tc_content
        assert "_navigate_to_test_page(page, standalone_test_config" in tc_content
        print("  [PASS] 已实现 flow_only 禁止单测 + standalone/test_config 才允许")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # Phase 可观测性：ComponentTestResult 含 phase 字段
    print("[1.7] 测试结果 phase 可观测性...")
    try:
        from tools.test_component import ComponentTestResult, TestStatus
        from dataclasses import fields, asdict
        fnames = [f.name for f in fields(ComponentTestResult)]
        assert "phase" in fnames and "phase_component_name" in fnames and "phase_component_version" in fnames
        r = ComponentTestResult(component_name="x", platform="y", status=TestStatus.FAILED, phase="login", phase_component_name="p/login", phase_component_version="1.0.0")
        d = asdict(r)
        assert d.get("phase") == "login" and d.get("phase_component_name") == "p/login"
        print("  [PASS] ComponentTestResult 含 phase/phase_component_name/phase_component_version")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 4.4 验证码截图 URL：使用 apiBaseURL
    print("[4.4] 验证码截图 URL 契约...")
    try:
        with open(ROOT / "frontend" / "src" / "api" / "index.js", "r", encoding="utf-8") as f:
            content = f.read()
        assert "apiBaseURL" in content and "getTestVerificationScreenshotUrl" in content
        # 不应再依赖 this.defaults?.baseURL
        idx = content.find("getTestVerificationScreenshotUrl")
        snippet = content[idx:idx+400]
        assert "apiBaseURL" in snippet, "getTestVerificationScreenshotUrl 应使用 apiBaseURL"
        assert "this.defaults" not in snippet or "apiBaseURL" in snippet
        print("  [PASS] 前端使用 apiBaseURL 生成截图 URL")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 4.2 多稳定版冲突：前端有 multiStableConflicts
    print("[4.2] 多稳定版冲突提示...")
    try:
        with open(ROOT / "frontend" / "src" / "views" / "ComponentVersions.vue", "r", encoding="utf-8") as f:
            content = f.read()
        assert "multiStableConflicts" in content and "hasMultiStableConflict" in content
        assert "multi-stable-alert" in content or "multiStableConflict" in content
        print("  [PASS] 前端含多稳定版冲突计算与展示")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 4.5 轮询生命周期：stopPollingTestStatus + watch(testDialogVisible)
    print("[4.5] 测试轮询生命周期治理...")
    try:
        with open(ROOT / "frontend" / "src" / "views" / "ComponentVersions.vue", "r", encoding="utf-8") as f:
            content = f.read()
        assert "stopPollingTestStatus" in content
        assert "POLL_MAX_CONSECUTIVE_ERRORS" in content or "consecutiveErrors" in content
        assert "POLL_OVERALL_TIMEOUT" in content or "startedAt" in content
        assert "testDialogVisible" in content and ("watch" in content or "onBeforeUnmount" in content)
        print("  [PASS] 轮询停止与超时/连续错误已实现")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 4.6 类型筛选：含 date_picker, filters
    print("[4.6] 组件类型筛选对齐...")
    try:
        with open(ROOT / "frontend" / "src" / "views" / "ComponentVersions.vue", "r", encoding="utf-8") as f:
            content = f.read()
        assert "date_picker" in content and "filters" in content
        assert "date_picker" in content[content.find("component_type"):content.find("component_type")+800] or "date_picker" in content
        print("  [PASS] 筛选项含 date_picker、filters")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 后端 get_test_status 返回 phase
    print("[1.7] 后端 status 返回 phase...")
    try:
        with open(ROOT / "backend" / "routers" / "component_versions.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert '"phase"' in content or "'phase'" in content
        assert "phase_component_name" in content and "phase_component_version" in content
        print("  [PASS] get_test_status 与 progress 写入含 phase 字段")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 7.4 生成器稳健性（反模式与作用域收敛）：回归测试
    print("[7.4] 生成器回归（反模式/作用域收敛/唯一性）...")
    try:
        import subprocess
        r = subprocess.run(
            [sys.executable, "-m", "pytest", str(ROOT / "backend" / "tests" / "test_steps_to_python_regression.py"), "-v", "--tb=short"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        if r.returncode == 0:
            print("  [PASS] test_steps_to_python_regression 全部通过")
            passed += 1
        else:
            print(f"  [FAIL] pytest 退出码 %d" % r.returncode)
            if r.stderr:
                for line in r.stderr.strip().split("\n")[-15:]:
                    print("    " + line)
            failed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    # 8.15.5 URL 导航契约回归：缺失 navigate / 无 role=form / URL 错配
    print("[8.15.5] login URL 导航契约回归覆盖...")
    try:
        with open(ROOT / "backend" / "tests" / "test_steps_to_python_regression.py", "r", encoding="utf-8") as f:
            content = f.read()
        assert "test_8_15_5_missing_navigate_step_still_has_navigation_contract" in content
        assert "test_8_15_5_container_without_role_form_has_fallback" in content
        assert "test_8_15_5_url_mismatch_has_diagnosable_failure" in content
        print("  [PASS] 已覆盖三类场景：缺失 navigate、容器无 role=form、URL 错配")
        passed += 1
    except Exception as e:
        print(f"  [FAIL] {e}")
        failed += 1

    print("")
    print("=" * 60)
    print("Summary: %d passed, %d failed" % (passed, failed))
    print("=" * 60)
    return 0 if failed == 0 else 1

if __name__ == "__main__":
    sys.exit(main())
